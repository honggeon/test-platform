"""
HAT YAML 用例静态校验（生成/部署/执行前）

拦截常见 Agent 生成错误：非法 jsonpath、非 HAT 结构、错误文件命名等。
"""

from __future__ import annotations

import re
from pathlib import Path

_FORBIDDEN_JSONPATH = re.compile(
    r"(\$\.length\s*\(|\$\.count\s*\(|\.length\s*\(|\.size\s*\(|fn\s*\()",
    re.IGNORECASE,
)
_JSONPATH_EXPR_LINE = re.compile(
    r"^\s*表达式\s*:\s*[\"']?(.+?)[\"']?\s*$",
    re.MULTILINE,
)
_CASE_FILE_PATTERN = re.compile(r"^\d+_.+\.yaml$", re.IGNORECASE)
_NON_HAT_MARKERS = re.compile(
    r"(?m)^(?:tests|config|setup)\s*:",
)
_HAT_REQUIRED_MARKERS = re.compile(
    r"(?m)^(?:基础配置|用例步骤)\s*:",
)


def lint_hat_yaml_content(
    content: str,
    filename: str = "",
    *,
    check_hat_structure: bool = False,
) -> list[str]:
    """校验单个 YAML 文件内容，返回错误列表（空=通过）。"""
    errors: list[str] = []
    prefix = f"{filename}: " if filename else ""

    for match in _JSONPATH_EXPR_LINE.finditer(content):
        expr = match.group(1).strip()
        if _FORBIDDEN_JSONPATH.search(expr):
            errors.append(
                f"{prefix}jsonpath 不支持函数式语法 {expr!r}，"
                "请改用 $[0].field 或 $..field"
            )

    if "$.length()" in content or "$.length(" in content:
        if not any("jsonpath" in e for e in errors):
            errors.append(
                f"{prefix}检测到 $.length()，HAT 底层 jsonpath 库不支持，"
                "请改用 $[0].id 验证非空"
            )

    if not check_hat_structure or filename == "context.yaml":
        return errors

    has_non_hat = bool(_NON_HAT_MARKERS.search(content))
    has_hat = bool(_HAT_REQUIRED_MARKERS.search(content))
    if has_non_hat and not has_hat:
        errors.append(
            f"{prefix}检测到非 HAT 结构（config/tests/setup），"
            "须使用「基础配置」+「用例步骤」+「操作类型」关键字驱动格式"
        )
    elif not has_hat and content.strip():
        errors.append(
            f"{prefix}缺少 HAT 必需节「基础配置」或「用例步骤」，"
            "HAT 解析器无法加载该文件"
        )

    return errors


def lint_hat_case_dir(case_dir: Path, *, strict: bool = True) -> list[str]:
    """
    校验用例目录下所有 YAML 文件。

    strict=True（deploy/execute）：结构 + 至少一个 {序号}_*.yaml
    strict=False（save_test_script）：仅 jsonpath 等轻量规则
    """
    errors: list[str] = []
    if not case_dir.is_dir():
        return [f"用例目录不存在: {case_dir}"]

    yaml_files = sorted(case_dir.glob("*.yaml"))
    if not yaml_files:
        return [f"用例目录缺少 YAML 文件: {case_dir}"]

    case_files = [p for p in yaml_files if p.name != "context.yaml"]
    numbered_cases = [p for p in case_files if _CASE_FILE_PATTERN.match(p.name)]

    if strict:
        if not numbered_cases:
            names = ", ".join(p.name for p in case_files) or "(无)"
            errors.append(
                f"用例目录须至少包含一个「数字前缀」YAML（如 0_login.yaml），"
                f"HAT 仅加载此类文件；当前: {names}"
            )
        orphan_cases = [p for p in case_files if not _CASE_FILE_PATTERN.match(p.name)]
        for path in orphan_cases:
            errors.append(
                f"{path.name}: 文件名须为 {{序号}}_{{名称}}.yaml（如 1_list.yaml），"
                "否则 HAT 解析器会忽略"
            )

    for path in yaml_files:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path.name}: 无法读取 ({exc})")
            continue
        errors.extend(
            lint_hat_yaml_content(
                content,
                path.name,
                check_hat_structure=strict,
            )
        )

    return errors


def run_hat_preflight(case_dir: Path, *, strict: bool = True) -> list[str]:
    """HAT 执行/部署前统一校验入口。"""
    return lint_hat_case_dir(case_dir, strict=strict)
