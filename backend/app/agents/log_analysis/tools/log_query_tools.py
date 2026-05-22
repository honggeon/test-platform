"""
日志查询工具

为 AI Agent 提供查询失败日志的能力。
从 MongoDB api_test_logs 和 PostgreSQL scenario_step_results 读取失败日志。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import json
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import select

from app.config.database import MongoDB, async_session_factory
from app.models.test_scenario import ScenarioStepResult


@tool
async def query_test_logs(
    run_id: str,
    status_filter: str = "failed",
    limit: int = 100,
) -> str:
    """查询测试运行的失败日志列表

    从 MongoDB api_test_logs 和 PostgreSQL scenario_step_results 查询失败的日志记录，
    返回格式化的日志列表文本。Agent 在诊断测试失败时首先调用此工具获取失败列表。

    Args:
        run_id: 测试运行 ID（UUID 字符串）
        status_filter: 状态过滤，默认 "failed"，可选 "failed" / "error" / "all"
        limit: 最大返回数量（默认 100）

    Returns:
        格式化的失败日志列表文本
    """
    logs = []

    # 1. 查询 MongoDB api_test_logs
    try:
        db = MongoDB.get_database()
        collection = db.get_collection("api_test_logs")

        mongo_filter: dict = {"test_run_id": run_id}
        if status_filter != "all":
            mongo_filter["status"] = {"$in": ["failed", "error"]}

        cursor = collection.find(mongo_filter).sort("created_at", -1).limit(limit)
        mongo_logs = await cursor.to_list(length=limit)

        for doc in mongo_logs:
            logs.append({
                "source": "mongodb",
                "log_id": str(doc.get("log_id", doc.get("_id", ""))),
                "endpoint": doc.get("endpoint", "未知端点"),
                "method": doc.get("method", "UNKNOWN"),
                "status": doc.get("status", "unknown"),
                "error": doc.get("error", {}),
                "created_at": str(doc.get("created_at", "")),
            })
    except Exception as e:
        logs.append({
            "source": "mongodb",
            "error": f"MongoDB 查询失败: {e}",
        })

    # 2. 查询 PostgreSQL scenario_step_results
    try:
        async with async_session_factory() as session:
            pg_filter = [ScenarioStepResult.run_id == UUID(run_id)]
            if status_filter != "all":
                from sqlalchemy import or_
                pg_filter.append(
                    or_(
                        ScenarioStepResult.status == "failed",
                        ScenarioStepResult.status == "error",
                    )
                )

            result = await session.execute(
                select(ScenarioStepResult).where(*pg_filter)
            )
            pg_logs = result.scalars().all()

            for row in pg_logs:
                logs.append({
                    "source": "postgresql",
                    "log_id": str(row.id),
                    "step_id": str(row.step_id),
                    "step_order": row.step_order,
                    "status": row.status,
                    "error_message": row.error_message or "",
                    "duration_ms": row.duration_ms,
                    "created_at": str(row.created_at) if row.created_at else "",
                })
    except Exception as e:
        logs.append({
            "source": "postgresql",
            "error": f"PostgreSQL 查询失败: {e}",
        })

    if not logs:
        return f"运行 ID {run_id} 未找到失败日志"

    show_limit = min(limit, 50)
    # 格式化输出
    lines = [f"运行 ID {run_id} 的失败日志（共 {len(logs)} 条）:\n"]
    for idx, log in enumerate(logs[:show_limit], start=1):
        if "error" in log and "source" in log and len(log) <= 3:
            lines.append(f"  [{idx}] [{log['source']}] 查询错误: {log['error']}")
            continue
        source_tag = log.get("source", "unknown")
        if source_tag == "mongodb":
            endpoint = log.get("endpoint", "未知")
            method = log.get("method", "UNKNOWN")
            status = log.get("status", "unknown")
            error = log.get("error", {})
            error_msg = error.get("message", "") if isinstance(error, dict) else str(error)
            lines.append(
                f"  [{idx}] [{source_tag}] {method} {endpoint} | 状态: {status} | "
                f"错误: {error_msg[:80]}"
            )
        else:
            step_order = log.get("step_order", "?")
            status = log.get("status", "unknown")
            error_msg = log.get("error_message", "")
            lines.append(
                f"  [{idx}] [{source_tag}] 步骤 #{step_order} | 状态: {status} | "
                f"错误: {error_msg[:80]}"
            )

    if len(logs) > show_limit:
        lines.append(f"\n... 还有 {len(logs) - show_limit} 条日志未展示")

    return "\n".join(lines)


@tool
async def get_log_detail(
    log_id: str,
    source: str = "mongodb",
) -> str:
    """获取单条日志的详细信息

    根据 source 从对应数据库查询完整日志详情，包括请求/响应数据、断言结果、错误堆栈等。

    Args:
        log_id: 日志 ID
        source: 数据来源，"mongodb" 或 "postgresql"

    Returns:
        格式化的日志详情文本
    """
    if source == "mongodb":
        try:
            db = MongoDB.get_database()
            collection = db.get_collection("api_test_logs")
            doc = await collection.find_one({"log_id": log_id})
            if not doc:
                doc = await collection.find_one({"_id": log_id})

            if not doc:
                return f"MongoDB 中未找到 log_id={log_id} 的日志"

            lines = [
                f"日志来源: MongoDB",
                f"日志 ID: {doc.get('log_id', doc.get('_id', ''))}",
                f"测试运行 ID: {doc.get('test_run_id', '')}",
                f"场景: {doc.get('scenario_name', '')}",
                f"端点: {doc.get('method', 'UNKNOWN')} {doc.get('endpoint', '未知')}",
                f"",
                f"--- 请求 ---",
                json.dumps(doc.get("request", {}), ensure_ascii=False, indent=2),
                f"",
                f"--- 响应 ---",
                json.dumps(doc.get("response", {}), ensure_ascii=False, indent=2),
                f"",
                f"--- 断言结果 ---",
                json.dumps(doc.get("assertions", []), ensure_ascii=False, indent=2),
                f"",
                f"--- 错误详情 ---",
                json.dumps(doc.get("error", {}), ensure_ascii=False, indent=2),
                f"",
                f"--- 时间线 ---",
                f"开始: {doc.get('started_at', '')}",
                f"结束: {doc.get('completed_at', '')}",
                f"耗时: {doc.get('duration_ms', 'N/A')} ms",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"查询 MongoDB 日志失败: {e}"

    elif source == "postgresql":
        try:
            async with async_session_factory() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(ScenarioStepResult).where(ScenarioStepResult.id == UUID(log_id))
                )
                row = result.scalar_one_or_none()
                if not row:
                    return f"PostgreSQL 中未找到 id={log_id} 的日志"

                lines = [
                    f"日志来源: PostgreSQL",
                    f"日志 ID: {row.id}",
                    f"运行 ID: {row.run_id}",
                    f"步骤 ID: {row.step_id}",
                    f"步骤序号: {row.step_order}",
                    f"状态: {row.status}",
                    f"",
                    f"--- 请求数据 ---",
                    json.dumps(row.request_data or {}, ensure_ascii=False, indent=2),
                    f"",
                    f"--- 响应数据 ---",
                    json.dumps(row.response_data or {}, ensure_ascii=False, indent=2),
                    f"",
                    f"--- 提取数据 ---",
                    json.dumps(row.extracted_data or {}, ensure_ascii=False, indent=2),
                    f"",
                    f"--- 断言结果 ---",
                    json.dumps(row.assertion_results or [], ensure_ascii=False, indent=2),
                    f"",
                    f"--- 错误信息 ---",
                    row.error_message or "无",
                    f"",
                    f"--- 错误堆栈 ---",
                    row.error_stack or "无",
                    f"",
                    f"耗时: {row.duration_ms} ms",
                ]
                return "\n".join(lines)
        except Exception as e:
            return f"查询 PostgreSQL 日志失败: {e}"

    else:
        return f"不支持的 source: {source}，请使用 'mongodb' 或 'postgresql'"
