"""
诊断触发工具

为 API Agent 提供测试失败后的自动诊断触发能力。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import asyncio
import json
import logging
from uuid import uuid4, UUID

from langchain_core.tools import tool
from sqlalchemy import select

from app.config.database import async_session_factory
from app.models.project import Project
from app.models.diagnosis_report import DiagnosisReportPG
from app.services.test_diagnosis_service import TestDiagnosisService

logger = logging.getLogger(__name__)


@tool
async def diagnose_test_run(
    run_id: str,
    project_identifier: str,
    test_output: str = "",
) -> str:
    """
    对测试运行结果进行分析诊断。

    当测试执行失败时调用此工具，它将：
    1. 自动收集失败日志
    2. 调用日志分析引擎定位根因
    3. 通过 KG 定位源码位置
    4. 保存诊断报告并推送前端

    注意：此工具是异步非阻塞的。调用后立即返回 report_id，
    诊断在后台执行。API Agent 无需阻塞等待诊断完成即可继续后续操作。
    如果修复流程需要诊断结果，可通过 report_id 轮询或 WebSocket 获取。

    Args:
        run_id: 测试运行 ID（从 execute_api_script 返回）
        project_identifier: 项目标识符
        test_output: 测试执行的标准输出（可选，用于补充信息）

    Returns:
        JSON 字符串 {"report_id": "...", "status": "analyzing"}
    """
    # 1. 解析 project_id（从 identifier 查 PG 的 projects 表）
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Project.id).where(Project.identifier == project_identifier)
            )
            project_id = result.scalar_one_or_none()
            if not project_id:
                return json.dumps(
                    {"error": f"项目标识符不存在: {project_identifier}"},
                    ensure_ascii=False,
                )
    except Exception as e:
        logger.exception(f"查询项目失败: {e}")
        return json.dumps(
            {"error": f"查询项目失败: {str(e)}"},
            ensure_ascii=False,
        )

    # 2. 生成 report_id 作为前端跟踪标识
    report_id = str(uuid4())
    dedup_key = f"{run_id}_{str(project_id)}"

    # 3. 先插入一条 analyzing 记录，方便前端轮询
    try:
        async with async_session_factory() as session:
            # run_id 可能不是 UUID，尝试转换，失败则用零值
            try:
                run_uuid = UUID(run_id)
            except ValueError:
                run_uuid = UUID("00000000-0000-0000-0000-000000000000")

            pg_report = DiagnosisReportPG(
                id=UUID(report_id),
                project_id=project_id,
                run_id=run_uuid,
                dedup_key=dedup_key,
                report_type="auto",
                status="analyzing",
                summary_json={"message": "诊断分析中...", "tracking": True},
                source_type="api_test",
                mongo_id=report_id,
            )
            session.add(pg_report)
            await session.commit()
    except Exception as e:
        logger.warning(f"创建 analyzing 记录失败（非阻塞）: {e}")
        # 非阻塞错误，继续启动后台任务

    # 4. 启动后台异步诊断任务
    async def _background_diagnose():
        try:
            service = TestDiagnosisService()
            await service.diagnose_run(
                run_id=run_id,
                project_id=str(project_id),
                project_identifier=project_identifier,
                options={
                    "test_output": test_output,
                    "skip_dedup": True,
                    "preset_report_id": report_id,
                },
            )
        except Exception as e:
            logger.exception(f"后台诊断任务失败: run_id={run_id}, error={e}")

    asyncio.create_task(_background_diagnose())

    # 5. 立即返回 report_id
    return json.dumps(
        {"report_id": report_id, "status": "analyzing"},
        ensure_ascii=False,
    )
