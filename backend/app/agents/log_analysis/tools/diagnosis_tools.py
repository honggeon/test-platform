"""
诊断分析工具

为 AI Agent 提供测试失败根因分析和诊断报告管理能力。
包含规则引擎分类、LLM 兜底、报告保存和前端推送功能。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import tool

from app.models.mongodb.diagnosis_report import DiagnosisReport
from app.services.diagnosis_llm import classify_failure_with_llm
from app.services.diagnosis_notification_service import manager as ws_manager

logger = logging.getLogger(__name__)

# 简单的内存缓存（后续可替换为 Redis / diagnosis_cache.py）
_llm_diagnosis_cache: dict[str, dict] = {}

# failure_rules.yaml 默认路径
_FAILURE_RULES_PATH = Path("backend/config/failure_rules.yaml")


def _load_failure_rules() -> list[dict]:
    """加载失败分类规则库

    从 backend/config/failure_rules.yaml 读取规则，按 priority 降序排列。
    文件不存在时返回空列表。
    """
    try:
        if not _FAILURE_RULES_PATH.exists():
            alt_path = Path(__file__).resolve().parents[5] / "config" / "failure_rules.yaml"
            if alt_path.exists():
                path = alt_path
            else:
                logger.warning(f"failure_rules.yaml 不存在: {_FAILURE_RULES_PATH}")
                return []
        else:
            path = _FAILURE_RULES_PATH

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = data.get("rules", []) if data else []
        rules.sort(key=lambda r: r.get("priority", 0), reverse=True)
        return rules
    except Exception as e:
        logger.warning(f"加载 failure_rules.yaml 失败: {e}")
        return []


def _match_rule(status_code: int, error_message: str, rule: dict) -> bool:
    """匹配单条规则

    规则匹配逻辑：
    1. status_code 条件：列表为空/为 ["*"] 时跳过；否则检查匹配
    2. error_patterns 条件：正则匹配 error_message（re.IGNORECASE）
    3. 两个条件同时满足才算匹配
    """
    conditions = rule.get("conditions", {})

    # status_code 条件
    sc_list = conditions.get("status_code", [])
    if sc_list and sc_list != ["*"]:
        if str(status_code) not in [str(s) for s in sc_list]:
            return False

    # error_patterns / error_message_patterns 条件
    patterns = conditions.get("error_patterns", []) or conditions.get("error_message_patterns", [])
    if not patterns:
        return True

    for pat in patterns:
        if re.search(pat, error_message, re.IGNORECASE):
            return True

    return False


def _cache_key(status_code: int, method: str, endpoint: str, error_message: str) -> str:
    """生成诊断缓存 key

    使用 sha256(f"{status_code}|{method}|{endpoint}|{error_message}") 保证唯一性。
    """
    raw = f"{status_code}|{method}|{endpoint}|{error_message}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _llm_classify(
    endpoint: str,
    method: str,
    status_code: int,
    error_message: str,
    response_body: str,
) -> dict:
    """LLM 兜底分类（使用共享 diagnosis_llm 模块，带内存缓存）"""
    cache = _llm_diagnosis_cache
    key = _cache_key(status_code, method, endpoint, error_message)
    if key in cache:
        cached = cache[key].copy()
        cached["cache_hit"] = True
        return cached

    result, _usage = await classify_failure_with_llm(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        error_message=error_message,
        response_body=response_body,
    )
    result["cache_hit"] = False

    cache[key] = {
        "type": result["type"],
        "confidence": result["confidence"],
        "reason": result.get("reason", ""),
    }
    return result


@tool
async def diagnose_failure(
    endpoint: str,
    method: str,
    status_code: int,
    error_message: str,
    response_body: str = "",
    project_identifier: str = "",
) -> str:
    """分析单个失败的根因（规则引擎 + LLM 兜底）

    首先使用规则引擎快速匹配已知失败模式，未命中时调用 LLM 进行分类。
    支持缓存：相同的失败特征在 24h 内复用 LLM 结果。

    Args:
        endpoint: API 端点路径
        method: HTTP 方法
        status_code: HTTP 状态码
        error_message: 错误消息文本
        response_body: 响应体文本（可选）
        project_identifier: 项目标识符（可选）

    Returns:
        JSON 字符串，包含 type / confidence / reason / classifier / cache_hit
    """
    rules = _load_failure_rules()

    # 1. 规则匹配
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if _match_rule(status_code, error_message, rule):
            result = {
                "type": rule.get("category", "unknown"),
                "confidence": rule.get("confidence", 0.9),
                "reason": rule.get("description", ""),
                "classifier": "rule",
                "matching_rule": rule.get("id", ""),
                "cache_hit": False,
            }
            return json.dumps(result, ensure_ascii=False)

    # 2. LLM 兜底
    llm_result = await _llm_classify(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        error_message=error_message,
        response_body=response_body,
    )
    llm_result["classifier"] = "llm"
    return json.dumps(llm_result, ensure_ascii=False)


@tool
async def save_diagnosis_report(
    report_data: str,
) -> str:
    """保存诊断报告到数据库（PG + MongoDB）

    Args:
        report_data: 诊断报告 JSON 字符串

    Returns:
        操作结果描述
    """
    try:
        from app.services.test_diagnosis_service import TestDiagnosisService

        data = json.loads(report_data)
        report = DiagnosisReport(**data)
        svc = TestDiagnosisService()
        await svc._save_report(report)
        logger.info(f"保存诊断报告 report_id={report.report_id}")
        return json.dumps(
            {"success": True, "report_id": report.report_id, "message": "报告已保存"},
            ensure_ascii=False,
        )
    except json.JSONDecodeError as e:
        return json.dumps(
            {"success": False, "error": f"无效的 JSON: {e}"},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"success": False, "error": str(e)},
            ensure_ascii=False,
        )


@tool
async def notify_frontend(
    project_id: str,
    report_id: str,
    status: str,
) -> str:
    """通过 WebSocket / Redis Pub/Sub 推送诊断状态更新

    Args:
        project_id: 项目 ID
        report_id: 报告 ID
        status: 状态（如 "analyzing" / "completed" / "failed"）

    Returns:
        操作结果描述
    """
    if status == "completed":
        await ws_manager.send_completed(project_id, {
            "type": "diagnosis_completed",
            "report_id": report_id,
            "status": status,
        })
    else:
        await ws_manager.send_progress(project_id, {
            "type": "diagnosis_progress",
            "report_id": report_id,
            "status": status,
            "phase": status,
            "message": f"诊断状态: {status}",
            "progress": 50 if status == "analyzing" else 0,
        })
    logger.info(f"推送诊断进展 project_id={project_id} report_id={report_id} status={status}")
    return json.dumps(
        {
            "success": True,
            "message": f"已推送状态 {status} 到前端",
            "project_id": project_id,
            "report_id": report_id,
        },
        ensure_ascii=False,
    )
