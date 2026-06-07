"""
诊断 LLM 共享模块
"""
import json
import logging
import re
from typing import Any
from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)

ROOT_CAUSE_CATEGORIES = [
    "token_expired", "permission_denied", "api_changed", "data_error",
    "network_timeout", "script_error", "unknown",
]

FIX_SUGGESTION_TEMPLATES = {
    "token_expired": [
        "检查测试脚本中的 Token 获取逻辑，确保在请求前刷新 Token",
        "确认 Token 有效期配置，考虑在 beforeEach 中重新登录",
    ],
    "permission_denied": [
        "确认测试账号拥有访问该 API 所需的角色/权限",
        "检查 RBAC 配置是否与测试预期一致",
    ],
    "api_changed": [
        "对比 API 文档与当前端点路径/参数是否一致",
        "更新测试脚本中的 URL、Query 参数或请求体字段",
    ],
    "data_error": [
        "检查请求体字段类型和必填项是否满足 API 校验规则",
        "确认测试数据前置步骤是否成功创建了依赖资源",
    ],
    "network_timeout": [
        "检查被测服务是否正常运行且网络可达",
        "适当增加测试超时时间或添加重试机制",
    ],
    "script_error": [
        "检查测试脚本中的变量引用和断言逻辑",
        "确认前置步骤的输出变量已正确传递到当前步骤",
    ],
    "unknown": [
        "查看完整错误日志和响应体以获取更多上下文",
        "考虑使用 AI 对话进一步分析该失败",
    ],
}


def keyword_classify(error_message: str) -> dict[str, Any]:
    msg = str(error_message).lower()
    if any(k in msg for k in ("token", "unauthorized", "jwt")):
        return {"type": "token_expired", "confidence": 0.7, "reason": "关键词匹配: 认证相关"}
    if any(k in msg for k in ("forbidden", "permission")):
        return {"type": "permission_denied", "confidence": 0.7, "reason": "关键词匹配: 权限相关"}
    if any(k in msg for k in ("not found", "no route")):
        return {"type": "api_changed", "confidence": 0.7, "reason": "关键词匹配: 路由不存在"}
    if any(k in msg for k in ("timeout", "refused", "unavailable")):
        return {"type": "network_timeout", "confidence": 0.7, "reason": "关键词匹配: 网络/超时"}
    if any(k in msg for k in ("typeerror", "referenceerror", "syntaxerror")):
        return {"type": "script_error", "confidence": 0.7, "reason": "关键词匹配: 脚本错误"}
    if any(k in msg for k in ("validation", "invalid", "required")):
        return {"type": "data_error", "confidence": 0.6, "reason": "关键词匹配: 数据校验"}
    return {"type": "unknown", "confidence": 0.5, "reason": "无法通过关键词确定根因"}


def _build_classify_prompt(endpoint, method, status_code, error_message, response_body):
    categories = "\n".join(f"- {c}" for c in ROOT_CAUSE_CATEGORIES)
    return f"""你是一个测试失败根因分析专家。
端点: {method} {endpoint}
状态码: {status_code}
响应体: {response_body[:500]}
错误消息: {error_message}
请从以下类别中选择：
{categories}
输出格式：JSON {{"type": "...", "confidence": 0-1, "reason": "..."}}
"""


def _parse_llm_json(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {"type": "unknown", "confidence": 0.5, "reason": "LLM 返回格式异常"}
    result = json.loads(match.group())
    result.setdefault("type", "unknown")
    result.setdefault("confidence", 0.5)
    result.setdefault("reason", "")
    if result["type"] not in ROOT_CAUSE_CATEGORIES:
        result["type"] = "unknown"
    return result


async def classify_failure_with_llm(endpoint, method, status_code, error_message, response_body="", *, use_llm=True):
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if not use_llm:
        return keyword_classify(error_message), token_usage
    prompt = _build_classify_prompt(endpoint, method, status_code, error_message, response_body)
    try:
        model = init_chat_model("deepseek:deepseek-chat")
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        result = _parse_llm_json(content)
        usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {}).get("token_usage", {})
        if usage:
            token_usage["prompt_tokens"] = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            token_usage["completion_tokens"] = usage.get("output_tokens", usage.get("completion_tokens", 0))
            token_usage["total_tokens"] = token_usage["prompt_tokens"] + token_usage["completion_tokens"]
        return result, token_usage
    except Exception as e:
        logger.warning(f"LLM 兜底分类失败: {e}")
        result = keyword_classify(error_message)
        result["reason"] = f"LLM 失败回退: {result.get('reason', '')}"
        return result, token_usage


def generate_fix_suggestions(root_cause_type, code_locations, endpoint="", error_message=""):
    suggestions = list(FIX_SUGGESTION_TEMPLATES.get(root_cause_type, FIX_SUGGESTION_TEMPLATES["unknown"]))
    if endpoint:
        suggestions.insert(0, f"重点检查端点 {endpoint} 对应的实现与测试脚本")
    for loc in code_locations:
        strategy = loc.get("strategy", "")
        result = loc.get("result", {})
        if strategy == "route_layer" and result.get("matches"):
            suggestions.append("KG 定位到路由层代码，检查路由注册和 URL 映射是否变更")
        elif strategy == "middleware_layer":
            suggestions.append("KG 定位到中间件/认证层，检查 auth 中间件和 Token 校验逻辑")
    if error_message and len(error_message) > 10:
        suggestions.append(f"错误线索: {error_message[:120]}")
    seen, unique = set(), []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:6]


def extract_affects_apis(code_locations, endpoint=""):
    apis = [endpoint] if endpoint else []
    for loc in code_locations:
        result = loc.get("result", {})
        if loc.get("strategy") != "impact_analysis":
            continue
        report = result.get("report", "")
        if isinstance(report, str):
            for match in re.findall(r"(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", report):
                api = f"{match[0]} {match[1]}"
                if api not in apis:
                    apis.append(api)
    return apis
