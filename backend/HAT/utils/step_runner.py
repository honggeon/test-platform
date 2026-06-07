"""Normalize and execute HAT YAML steps (canonical + agent-generated variants)."""
from __future__ import annotations

import copy
from typing import Any

from HAT.core.globalContext import g_context
from HAT.utils.VarRender import refresh

FIELD_ALIASES = {
    "请求体": "请求数据",
    "请求参数": "URL参数",
}

POST_REQUEST_KEYS = frozenset(
    {
        "断言",
        "断言文本",
        "断言文本相等",
        "断言文本包含",
        "断言文本被包含",
        "提取变量",
        "提取数据JSON",
    }
)

ASSERTION_OPERATION_KEYS = frozenset(
    {
        "断言文本",
        "断言文本相等",
        "断言文本包含",
        "断言文本被包含",
        "提取数据JSON",
    }
)


def parse_step(step: dict) -> tuple[str, dict]:
    """支持 {步骤名: {...}} 与扁平 {用例名称, 操作类型, ...} 两种写法。"""
    if not isinstance(step, dict):
        raise ValueError(f"步骤必须是 dict: {step!r}")

    if len(step) == 1:
        name, value = next(iter(step.items()))
        if isinstance(value, dict) and "操作类型" in value:
            return str(name), copy.deepcopy(value)

    if "操作类型" in step:
        data = copy.deepcopy(step)
        name = (
            data.pop("用例名称", None)
            or data.pop("步骤名称", None)
            or data.get("操作类型", "步骤")
        )
        return str(name), data

    raise ValueError(f"无法解析步骤结构: {step!r}")


def normalize_step_fields(step_value: dict) -> dict:
    normalized = copy.deepcopy(step_value)
    for src, dst in FIELD_ALIASES.items():
        if src in normalized and dst not in normalized:
            normalized[dst] = normalized.pop(src)
    if "请求数据" in normalized and isinstance(normalized["请求数据"], dict):
        normalized.setdefault("请求类型", "json")
    return normalized


def split_request_and_post(step_value: dict) -> tuple[dict, dict]:
    request_part: dict[str, Any] = {}
    post_part: dict[str, Any] = {}
    operation = step_value.get("操作类型", "")

    if operation in ASSERTION_OPERATION_KEYS:
        return {}, step_value

    for key, value in step_value.items():
        if key in POST_REQUEST_KEYS:
            post_part[key] = value
        else:
            request_part[key] = value
    return request_part, post_part


def build_render_context(local_context: dict | None = None) -> dict:
    context = copy.deepcopy(g_context().show_dict())
    if local_context:
        context.update(local_context)

    response = context.get("响应结果")
    if response is not None and hasattr(response, "status_code"):
        status = str(response.status_code)
        context.setdefault("status_code", status)
        context["响应结果"] = {"status_code": status}
    return context


def render_step_dict(step_value: dict, local_context: dict | None = None) -> dict:
    context = build_render_context(local_context)
    return eval(refresh(step_value, context))


def _run_jsonpath_assertion(keywords, assertion: dict) -> None:
    import jsonpath

    response = g_context().get_dict("响应结果")
    if response is None:
        raise AssertionError("jsonpath 断言失败：响应结果为空")

    payload = response.json()
    expression = assertion.get("表达式", "")
    matches = jsonpath.jsonpath(payload, expression)
    if matches is False:
        matches = []

    if assertion.get("期望类型") == "not_empty":
        if not matches:
            raise AssertionError(f"jsonpath 无匹配: {expression}")
        return

    if assertion.get("期望类型") == "array":
        if not isinstance(matches, list) or not matches:
            raise AssertionError(f"jsonpath 未返回数组: {expression}")
        return

    if assertion.get("期望类型") == "string":
        if not matches:
            raise AssertionError(f"jsonpath 无匹配: {expression}")
        return

    expected = assertion.get("期望值")
    if expected is not None:
        actual = matches[0] if matches else None
        keywords.断言文本相等(期望结果=str(expected), 实际结果=str(actual))


def run_post_operations(keywords, post_part: dict, local_context: dict | None = None) -> None:
    if not post_part:
        return

    extract_specs: list[dict] = []
    if "提取数据JSON" in post_part:
        spec = post_part["提取数据JSON"]
        if isinstance(spec, dict):
            extract_specs.append(spec)
        elif isinstance(spec, list):
            extract_specs.extend(item for item in spec if isinstance(item, dict))
    for item in post_part.get("提取变量") or []:
        if not isinstance(item, dict):
            continue
        extract_specs.append(
            {
                "表达式": item.get("表达式"),
                "变量名": item.get("变量名"),
                "下标": item.get("下标", 0),
            }
        )

    for spec in extract_specs:
        keywords.提取数据JSON(
            表达式=spec.get("表达式"),
            变量名=spec.get("变量名"),
            下标=spec.get("下标", 0),
        )

    for assertion in post_part.get("断言") or []:
        if not isinstance(assertion, dict):
            continue
        if assertion.get("类型") == "状态码":
            expected = str(assertion.get("预期值", assertion.get("期望值", "")))
            actual = str(g_context().get_dict("status_code") or "")
            keywords.断言文本相等(期望结果=expected, 实际结果=actual)
        elif assertion.get("类型") == "jsonpath":
            _run_jsonpath_assertion(keywords, assertion)

    for key in ("断言文本相等", "断言文本包含", "断言文本被包含", "断言文本"):
        if key not in post_part:
            continue
        payload = post_part[key]
        if not isinstance(payload, dict):
            continue
        rendered = eval(refresh(payload, build_render_context(local_context)))
        keywords.__getattribute__(key)(**rendered)


def execute_step(keywords, step: dict, local_context: dict | None = None) -> None:
    step_name, raw_value = parse_step(step)
    normalized = normalize_step_fields(raw_value)
    request_part, post_part = split_request_and_post(normalized)

    if request_part:
        rendered_request = render_step_dict(request_part, local_context)
        operation = rendered_request.pop("操作类型", None)
        if not operation:
            raise ValueError(f"步骤 {step_name} 缺少操作类型")
        try:
            key_func = keywords.__getattribute__(operation)
            key_func(**rendered_request)
        except AttributeError:
            if get_key_dirs():
                keywords.ex_invoke(key=operation, step_value=rendered_request)
            else:
                raise
        run_post_operations(keywords, post_part, local_context)
        return

    rendered_post = render_step_dict(post_part, local_context)
    operation = rendered_post.get("操作类型")
    if operation in ASSERTION_OPERATION_KEYS:
        payload = {k: v for k, v in rendered_post.items() if k != "操作类型"}
        keywords.__getattribute__(operation)(**payload)


def get_key_dirs():
    from HAT.utils.key_dir import get_key_dirs as _get

    return _get()
