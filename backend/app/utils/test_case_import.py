"""
测试用例文件导入解析工具

支持 CSV、Excel (.xlsx)、JSON 格式。
"""
import csv
import io
import json
from typing import Any, Optional

from app.schemas.test_case import TestCaseCreate, TestStepCreate
from app.schemas.enums import Priority, TestCaseState, TestCaseType, AutomationStatus

COLUMN_ALIASES: dict[str, str] = {
    "name": "name",
    "title": "name",
    "用例名称": "name",
    "名称": "name",
    "测试用例名称": "name",
    "description": "description",
    "描述": "description",
    "preconditions": "preconditions",
    "前置条件": "preconditions",
    "priority": "priority",
    "优先级": "priority",
    "status": "status",
    "state": "status",
    "状态": "status",
    "case_type": "case_type",
    "type": "case_type",
    "类型": "case_type",
    "用例类型": "case_type",
    "tags": "tags",
    "标签": "tags",
    "steps": "steps",
    "测试步骤": "steps",
    "步骤": "steps",
}

PRIORITY_MAP = {
    "critical": Priority.CRITICAL,
    "紧急": Priority.CRITICAL,
    "high": Priority.HIGH,
    "高": Priority.HIGH,
    "medium": Priority.MEDIUM,
    "中": Priority.MEDIUM,
    "low": Priority.LOW,
    "低": Priority.LOW,
}

STATUS_MAP = {
    "new": TestCaseState.NEW,
    "新建": TestCaseState.NEW,
    "review_pending": TestCaseState.REVIEW_PENDING,
    "待评审": TestCaseState.REVIEW_PENDING,
    "reviewed": TestCaseState.REVIEWED,
    "已评审": TestCaseState.REVIEWED,
    "not_run": TestCaseState.NOT_RUN,
    "未执行": TestCaseState.NOT_RUN,
    "passed": TestCaseState.PASSED,
    "通过": TestCaseState.PASSED,
    "failed": TestCaseState.FAILED,
    "失败": TestCaseState.FAILED,
    "blocked": TestCaseState.BLOCKED,
    "阻塞": TestCaseState.BLOCKED,
    "skipped": TestCaseState.SKIPPED,
    "跳过": TestCaseState.SKIPPED,
}

CASE_TYPE_MAP = {
    "functional": TestCaseType.FUNCTIONAL,
    "功能测试": TestCaseType.FUNCTIONAL,
    "smoke_sanity": TestCaseType.SMOKE_SANITY,
    "冒烟测试": TestCaseType.SMOKE_SANITY,
    "regression": TestCaseType.REGRESSION,
    "回归测试": TestCaseType.REGRESSION,
    "security": TestCaseType.SECURITY,
    "安全测试": TestCaseType.SECURITY,
    "performance": TestCaseType.PERFORMANCE,
    "性能测试": TestCaseType.PERFORMANCE,
    "usability": TestCaseType.USABILITY,
    "可用性测试": TestCaseType.USABILITY,
    "acceptance": TestCaseType.ACCEPTANCE,
    "验收测试": TestCaseType.ACCEPTANCE,
    "integration": TestCaseType.FUNCTIONAL,
    "集成测试": TestCaseType.FUNCTIONAL,
    "exploratory": TestCaseType.OTHER,
    "探索性测试": TestCaseType.OTHER,
    "other": TestCaseType.OTHER,
    "其他": TestCaseType.OTHER,
}


def _normalize_header(header: str) -> str:
    key = header.strip().lower()
    return COLUMN_ALIASES.get(key, COLUMN_ALIASES.get(header.strip(), key))


def _parse_steps(raw: Any) -> list[TestStepCreate]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                steps: list[TestStepCreate] = []
                for item in data:
                    if isinstance(item, dict):
                        step = str(item.get("step") or item.get("action") or "").strip()
                        result = str(item.get("result") or item.get("expected_result") or "").strip()
                        if step:
                            steps.append(TestStepCreate(step=step, result=result or None))
                return steps
        except json.JSONDecodeError:
            pass

    steps = []
    for chunk in text.split(";;"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "|" in chunk:
            step_text, result_text = chunk.split("|", 1)
        else:
            step_text, result_text = chunk, ""
        step_text = step_text.strip()
        if step_text:
            steps.append(
                TestStepCreate(step=step_text, result=result_text.strip() or None)
            )
    return steps


def _parse_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [tag.strip() for tag in text.replace("，", ",").split(",") if tag.strip()]


def _row_to_test_case(row: dict[str, Any], row_number: int) -> TestCaseCreate:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = _normalize_header(str(key))
        if normalized_key in normalized and normalized[normalized_key] not in (None, ""):
            continue
        normalized[normalized_key] = value

    name = str(normalized.get("name") or "").strip()
    if not name:
        raise ValueError(f"第 {row_number} 行缺少用例名称")

    priority_raw = str(normalized.get("priority") or "medium").strip().lower()
    status_raw = str(normalized.get("status") or "new").strip().lower()
    case_type_raw = str(normalized.get("case_type") or "functional").strip().lower()

    return TestCaseCreate(
        name=name,
        description=str(normalized.get("description") or "").strip() or None,
        preconditions=str(normalized.get("preconditions") or "").strip() or None,
        priority=PRIORITY_MAP.get(priority_raw, Priority.MEDIUM),
        status=STATUS_MAP.get(status_raw, TestCaseState.NEW),
        case_type=CASE_TYPE_MAP.get(case_type_raw, TestCaseType.FUNCTIONAL),
        tags=_parse_tags(normalized.get("tags")) or None,
        test_case_steps=_parse_steps(normalized.get("steps")) or None,
    )


def parse_csv_content(content: bytes) -> list[TestCaseCreate]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 文件缺少表头")

    items: list[TestCaseCreate] = []
    for index, row in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        items.append(_row_to_test_case(row, index))
    return items


def parse_excel_content(content: bytes) -> list[TestCaseCreate]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ValueError("服务器未安装 pandas，无法解析 Excel 文件") from exc

    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    if df.empty:
        return []

    items: list[TestCaseCreate] = []
    records = df.fillna("").to_dict(orient="records")
    for index, row in enumerate(records, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        items.append(_row_to_test_case(row, index))
    return items


def parse_json_content(content: bytes) -> list[TestCaseCreate]:
    data = json.loads(content.decode("utf-8-sig"))
    if isinstance(data, dict):
        if "test_cases" in data:
            data = data["test_cases"]
        elif "data" in data:
            data = data["data"]
        else:
            data = [data]

    if not isinstance(data, list):
        raise ValueError("JSON 格式应为数组，或包含 test_cases/data 字段的对象")

    items: list[TestCaseCreate] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条记录不是对象")
        if "name" not in item and "title" in item:
            item = {**item, "name": item["title"]}
        if "status" not in item and "state" in item:
            item = {**item, "status": item["state"]}
        if "case_type" not in item and "test_case_type" in item:
            item = {**item, "case_type": item["test_case_type"]}
        if "steps" not in item and "test_case_steps" in item:
            steps = item["test_case_steps"]
            if isinstance(steps, list):
                item = {
                    **item,
                    "steps": json.dumps(steps, ensure_ascii=False),
                }
        items.append(_row_to_test_case(item, index))
    return items


def parse_import_file(filename: str, content: bytes) -> list[TestCaseCreate]:
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        return parse_csv_content(content)
    if lower_name.endswith((".xlsx", ".xls")):
        return parse_excel_content(content)
    if lower_name.endswith(".json"):
        return parse_json_content(content)
    raise ValueError("不支持的文件格式，请上传 CSV、Excel (.xlsx) 或 JSON 文件")


def build_csv_template() -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "name",
            "description",
            "preconditions",
            "priority",
            "status",
            "case_type",
            "tags",
            "steps",
        ]
    )
    writer.writerow(
        [
            "用户登录-正确密码",
            "验证用户使用正确密码可以登录",
            "用户已注册",
            "high",
            "new",
            "functional",
            "登录,冒烟",
            "打开登录页|页面正常显示;;输入正确账号密码|输入成功;;点击登录|跳转首页",
        ]
    )
    return output.getvalue().encode("utf-8-sig")


def extract_api_test_cases_list(data: Any) -> list[dict[str, Any]]:
    """从 API 测试成果物 JSON 中提取用例列表"""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        raise ValueError("API 测试用例 JSON 格式无效")

    for key in ("test_cases", "cases", "items", "scenarios"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return [data]


def _api_steps_to_create(raw_steps: Any, fallback_result: Optional[str] = None) -> list[TestStepCreate]:
    if raw_steps is None:
        if fallback_result:
            return [TestStepCreate(step="执行测试", result=fallback_result)]
        return []

    if isinstance(raw_steps, str):
        text = raw_steps.strip()
        if not text:
            return [TestStepCreate(step="执行测试", result=fallback_result)] if fallback_result else []
        if text.startswith("["):
            try:
                return _api_steps_to_create(json.loads(text), fallback_result)
            except json.JSONDecodeError:
                pass
        return [TestStepCreate(step=text, result=fallback_result)]

    if isinstance(raw_steps, list):
        steps: list[TestStepCreate] = []
        for item in raw_steps:
            if isinstance(item, str):
                step_text = item.strip()
                if step_text:
                    steps.append(TestStepCreate(step=step_text, result=None))
            elif isinstance(item, dict):
                step_text = str(
                    item.get("step")
                    or item.get("action")
                    or item.get("description")
                    or item.get("name")
                    or ""
                ).strip()
                result_text = str(
                    item.get("result")
                    or item.get("expected_result")
                    or item.get("expected")
                    or item.get("断言")
                    or ""
                ).strip()
                if step_text:
                    steps.append(TestStepCreate(step=step_text, result=result_text or None))
        if steps:
            return steps
        if fallback_result:
            return [TestStepCreate(step="执行测试", result=fallback_result)]
        return []

    if fallback_result:
        return [TestStepCreate(step="执行测试", result=fallback_result)]
    return []


def convert_api_test_case_item(
    item: dict[str, Any],
    *,
    endpoint_name: Optional[str] = None,
    endpoint_method: Optional[str] = None,
    endpoint_path: Optional[str] = None,
) -> TestCaseCreate:
    """将 API 测试成果物中的单条用例转换为 TestCaseCreate"""
    name = str(
        item.get("name")
        or item.get("title")
        or item.get("case_name")
        or item.get("用例名称")
        or item.get("用例标题")
        or ""
    ).strip()
    if not name:
        raise ValueError("缺少用例名称")

    description = str(
        item.get("description")
        or item.get("summary")
        or item.get("desc")
        or item.get("描述")
        or ""
    ).strip() or None

    preconditions = str(
        item.get("preconditions")
        or item.get("precondition")
        or item.get("前置条件")
        or ""
    ).strip() or None

    priority_raw = str(item.get("priority") or item.get("优先级") or "medium").strip().lower()
    status_raw = str(item.get("status") or item.get("state") or "new").strip().lower()
    case_type_raw = str(
        item.get("case_type")
        or item.get("test_case_type")
        or item.get("type")
        or "functional"
    ).strip().lower()

    raw_steps = (
        item.get("test_case_steps")
        or item.get("steps")
        or item.get("测试步骤")
    )
    fallback_result = str(
        item.get("expected_result")
        or item.get("expected")
        or item.get("result")
        or item.get("预期结果")
        or ""
    ).strip() or None

    tags = _parse_tags(item.get("tags") or item.get("标签"))
    if endpoint_name:
        tags.append("API导入")
        tags.append(endpoint_name)
    if endpoint_method and endpoint_path:
        tags.append(f"{endpoint_method} {endpoint_path}")

    return TestCaseCreate(
        name=name,
        description=description,
        preconditions=preconditions,
        priority=PRIORITY_MAP.get(priority_raw, Priority.MEDIUM),
        status=STATUS_MAP.get(status_raw, TestCaseState.NEW),
        case_type=CASE_TYPE_MAP.get(case_type_raw, TestCaseType.FUNCTIONAL),
        tags=list(dict.fromkeys(tags)) or None,
        test_case_steps=_api_steps_to_create(raw_steps, fallback_result) or None,
        automation_status=AutomationStatus.AUTOMATED,
    )


def parse_api_test_cases_json(
    content: bytes,
    *,
    endpoint_name: Optional[str] = None,
    endpoint_method: Optional[str] = None,
    endpoint_path: Optional[str] = None,
) -> list[TestCaseCreate]:
    """解析 API 测试成果物 JSON 并转换为 TestCaseCreate 列表"""
    data = json.loads(content.decode("utf-8-sig"))
    raw_items = extract_api_test_cases_list(data)
    if not raw_items:
        raise ValueError("未找到可导入的测试用例")

    items: list[TestCaseCreate] = []
    for index, item in enumerate(raw_items, start=1):
        try:
            items.append(
                convert_api_test_case_item(
                    item,
                    endpoint_name=endpoint_name,
                    endpoint_method=endpoint_method,
                    endpoint_path=endpoint_path,
                )
            )
        except ValueError as exc:
            raise ValueError(f"第 {index} 条用例解析失败: {exc}") from exc
    return items


RESOURCE_NAME_ZH_MAP: dict[str, str] = {
    "test-cases": "测试用例",
    "test_cases": "测试用例",
    "testcases": "测试用例",
    "projects": "项目",
    "folders": "文件夹",
    "test-runs": "测试运行",
    "test_runs": "测试运行",
    "results": "测试结果",
    "test-results": "测试结果",
    "users": "用户",
    "attachments": "附件",
    "configurations": "配置",
    "endpoints": "端点",
    "api-endpoints": "API端点",
    "test-plans": "测试计划",
    "documents": "文档",
    "environments": "测试环境",
    "reports": "测试报告",
}


def extract_resource_name_from_path(path: str) -> str:
    """从 API 路径提取资源名（忽略路径参数段）"""
    parts = [
        part
        for part in path.strip("/").split("/")
        if part and not (part.startswith("{") and part.endswith("}"))
    ]
    if not parts:
        return "未分类"
    return parts[-1].replace("{", "").replace("}", "") or "未分类"


def humanize_api_import_subfolder_name(
    *,
    path: str,
    summary: Optional[str] = None,
    custom_config: Optional[dict[str, Any]] = None,
) -> str:
    """推导 API 导入时第二层功能文件夹名称"""
    if summary and summary.strip():
        cleaned = summary.strip()
        if len(cleaned) <= 50:
            return cleaned

    resource = None
    if custom_config:
        resource = custom_config.get("resource_name")
    if not resource:
        resource = extract_resource_name_from_path(path)

    key = str(resource).lower().replace("_", "-")
    if key in RESOURCE_NAME_ZH_MAP:
        return RESOURCE_NAME_ZH_MAP[key]

    if "-" in key and all(ord(char) < 128 for char in key):
        return key.replace("-", " ")

    return str(resource) or "未分类"


def resolve_api_import_tag_group_name(
    tag_group: Optional[str],
    tags: Optional[list[str]] = None,
) -> str:
    """推导 API 导入时第一层功能文件夹名称（与 Swagger tag 一致）"""
    if tag_group and tag_group.strip():
        return tag_group.strip()
    if tags:
        for tag in tags:
            if tag and str(tag).strip():
                return str(tag).strip()
    return "API导入"


def map_test_result_status_string(value: str) -> Optional["TestResultStatus"]:
    """将字符串映射为测试结果状态"""
    from app.schemas.enums import TestResultStatus

    key = str(value).strip().lower()
    mapping = {
        "passed": TestResultStatus.PASSED,
        "pass": TestResultStatus.PASSED,
        "success": TestResultStatus.PASSED,
        "failed": TestResultStatus.FAILED,
        "fail": TestResultStatus.FAILED,
        "error": TestResultStatus.FAILED,
        "skipped": TestResultStatus.SKIPPED,
        "skip": TestResultStatus.SKIPPED,
        "blocked": TestResultStatus.BLOCKED,
        "not_executed": TestResultStatus.NOT_EXECUTED,
        "not executed": TestResultStatus.NOT_EXECUTED,
    }
    return mapping.get(key)


def parse_execution_status_from_raw_item(item: dict[str, Any]) -> Optional["TestResultStatus"]:
    """从 API 成果物单条用例中提取执行状态"""
    candidates: list[str] = []
    for key in (
        "test_result_status",
        "execution_status",
        "last_run_status",
        "result_status",
        "run_status",
    ):
        value = item.get(key)
        if isinstance(value, dict):
            nested = value.get("status") or value.get("result")
            if nested is not None and str(nested).strip():
                candidates.append(str(nested).strip())
        elif value is not None and str(value).strip():
            candidates.append(str(value).strip())

    test_result = item.get("test_result")
    if isinstance(test_result, dict):
        nested = test_result.get("status") or test_result.get("result")
        if nested is not None and str(nested).strip():
            candidates.append(str(nested).strip())

    for candidate in candidates:
        mapped = map_test_result_status_string(candidate)
        if mapped:
            return mapped
    return None
