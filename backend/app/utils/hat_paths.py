"""
HAT 框架路径解析工具（跨平台 Windows / Linux）

统一解析 run_hat.py、key_dir、conftest.py 所在目录，避免各工具中
parent×N 硬编码导致的路径错误。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.config.settings import settings

# backend/app/utils/hat_paths.py -> parents[2] == backend/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


def get_api_workspace_root() -> Path:
    """解析 API workspace 根目录（跨平台、不依赖 CWD）。"""
    configured = settings.api_workspace_root.strip()
    path = Path(configured)
    if path.is_absolute():
        return path.resolve()

    candidates = [
        _REPO_ROOT / path,
        Path.cwd() / path,
        _BACKEND_DIR / "workspace" / "api",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (_REPO_ROOT / path).resolve()


def get_api_workspace_tests_dir() -> Path:
    return get_api_workspace_root() / "tests"


def get_hat_home() -> Path:
    """返回 HAT 框架根目录（含 run_hat.py、conftest.py、HAT/）。"""
    configured = (settings.hat_home or "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_absolute() and (candidate / "run_hat.py").exists():
            return candidate.resolve()
        if not candidate.is_absolute():
            for base in (_REPO_ROOT, Path.cwd(), _BACKEND_DIR):
                resolved = (base / configured).resolve()
                if (resolved / "run_hat.py").exists():
                    return resolved

    if (_BACKEND_DIR / "run_hat.py").exists():
        return _BACKEND_DIR

    # 兜底：从 api tools 模块向上查找（parents[4] == backend/）
    tools_fallback = Path(__file__).resolve().parents[2]
    for ancestor in (_BACKEND_DIR, tools_fallback):
        if (ancestor / "run_hat.py").exists():
            return ancestor.resolve()

    return _BACKEND_DIR


def get_run_hat_path() -> Path:
    return get_hat_home() / "run_hat.py"


def get_hat_key_dir() -> Path:
    return get_hat_home() / "HAT" / "key_dir"


def resolve_hat_key_dirs(
    cases_dir: str | Path,
    global_key_dir: str | Path | None = None,
) -> list[Path]:
    """
    合并全局 key_dir 与用例目录下的 key_dir/。

    全局目录优先；用例级扩展追加在后（同名模块时全局优先）。
    """
    dirs: list[Path] = []
    global_dir = Path(global_key_dir or get_hat_key_dir()).resolve()
    if global_dir.is_dir():
        dirs.append(global_dir)

    case_key_dir = Path(cases_dir).resolve() / "key_dir"
    if case_key_dir.is_dir() and case_key_dir not in dirs:
        dirs.append(case_key_dir)

    return dirs


def format_key_dirs_cli(key_dirs: list[Path]) -> str:
    """将多个 key_dir 格式化为 pytest --keyDir 参数值。"""
    return os.pathsep.join(str(path.resolve()) for path in key_dirs)


def sanitize_workspace_relative_path(raw_path: str, workspace_root: Path | None = None) -> str:
    """
    将用户/Agent 传入的路径规范化为 workspace 内的安全相对路径。

    拒绝 Linux 绝对路径片段（home/xxx/...）、..  traversal、越界路径。
    """
    cleaned = raw_path.strip().strip("/\\")
    if not cleaned:
        return cleaned

    if Path(cleaned).is_absolute() or cleaned.startswith(".."):
        return Path(cleaned).name

    parts = Path(cleaned).parts
    if parts and parts[0].lower() in ("home", "root", "var", "usr", "opt"):
        if "tests" in parts:
            idx = parts.index("tests")
            cleaned = str(Path(*parts[idx:]))
        else:
            cleaned = parts[-1]

    workspace_resolved = (workspace_root or get_api_workspace_root()).resolve()
    candidate = (workspace_resolved / cleaned).resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError:
        cleaned = Path(cleaned).name

    return cleaned.replace("\\", "/")


def resolve_hat_cases_dir(
    test_target: str,
    tests_dir: str | Path,
    project_root: str | Path,
) -> Path:
    """将测试目标解析为 HAT 用例目录的绝对路径。"""
    tests_base = Path(tests_dir or project_root).resolve()
    project_base = Path(project_root).resolve()
    target = Path(str(test_target).replace("\\", "/"))

    if target.is_absolute() and target.exists():
        cases = target if target.is_dir() else target.parent
        return cases.resolve()

    # 去掉重复的 tests/ 前缀（tests_dir 本身已是 .../tests）
    target_parts = target.parts
    if tests_base.name == "tests" and target_parts and target_parts[0] == "tests":
        target = Path(*target_parts[1:])

    search_bases = [tests_base, project_base, project_base / "tests"]
    for base in search_bases:
        candidate = (base / target).resolve()
        if candidate.exists():
            return candidate if candidate.is_dir() else candidate.parent

    fallback = (tests_base / target).resolve()
    return fallback if target.suffix == "" else fallback.parent


_SLUG_SAFE = re.compile(r"[^a-zA-Z0-9_\-]+")


def slugify_case_name(raw: str) -> str:
    """将端点名称/路径转为 HAT 用例目录 slug（snake_case）。"""
    value = raw.strip().lower()
    value = value.replace("{", "").replace("}", "")
    value = value.replace("/", "_").replace("-", "_").replace(" ", "_")
    value = _SLUG_SAFE.sub("_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "api_case"


def derive_case_slug(method: str, path: str, display_name: str = "") -> str:
    """从端点信息推导 canonical 用例目录名。"""
    if display_name:
        slug = slugify_case_name(display_name)
        if slug and slug != "api_case":
            return slug
    combined = f"{method}_{path}" if method else path
    return slugify_case_name(combined)


def build_canonical_case_rel_dir(project_identifier: str, case_slug: str) -> str:
    """返回 workspace 内 canonical 相对路径（POSIX）。"""
    project = project_identifier.strip().strip("/") or "default"
    slug = slugify_case_name(case_slug)
    return f"tests/{project}/api-tests/{slug}"


def resolve_canonical_case_dir(
    project_identifier: str,
    case_slug: str,
    workspace_root: Path | None = None,
) -> Path:
    """解析 canonical HAT 用例目录绝对路径。"""
    rel = build_canonical_case_rel_dir(project_identifier, case_slug)
    root = (workspace_root or get_api_workspace_root()).resolve()
    return (root / rel).resolve()


def build_execute_path_hint(project_identifier: str, case_slug: str = "<case_slug>") -> str:
    """生成 execute_api_script 推荐路径提示。"""
    return build_canonical_case_rel_dir(project_identifier, case_slug)


def is_valid_hat_case_dir(cases_dir: Path, tests_root: Path | None = None) -> bool:
    """
    判断路径是否为合法的 HAT 单用例目录（禁止 tests 根目录等过宽路径）。
    """
    cases = Path(cases_dir).resolve()
    if not cases.is_dir():
        return False

    root = Path(tests_root or get_api_workspace_tests_dir()).resolve()
    if cases == root:
        return False

    try:
        rel = cases.relative_to(root).as_posix()
    except ValueError:
        rel = cases.as_posix()

    if rel in (".", ""):
        return False
    if "/api-tests/" not in f"/{rel}/" and not rel.endswith("/api-tests"):
        return False

    has_context = (cases / "context.yaml").exists()
    has_steps = any(cases.glob("[0-9]*_*.yaml"))
    return has_context or has_steps


def detect_misplaced_linux_path(raw_path: str) -> bool:
    """检测 Agent 误用的 Linux 绝对路径片段。"""
    cleaned = raw_path.strip().replace("\\", "/")
    return cleaned.startswith("/home/") or cleaned.startswith("/root/") or "/home/" in cleaned
