"""
测试环境 URL 解析与脱敏工具

Agent 侧始终使用 {{API_BASE_URL}} 占位符；真实 URL 仅在测试执行时注入，不暴露给 LLM。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config.settings import _DEFAULT_PUBLIC_API_URL
from app.config import settings

PLACEHOLDER_API_BASE_URL = "{{API_BASE_URL}}"
PLACEHOLDER_URL = "{{URL}}"
PLACEHOLDER_AUTH_TOKEN = "{{AUTH_TOKEN}}"
PLACEHOLDER_ARAG_AUTH_URL = "{{ARAG_AUTH_URL}}"
_AUTH_TOKEN_ENV_KEYS = ("HAT_BEARER_TOKEN", "API_BEARER_TOKEN", "AUTH_TOKEN")
_INVALID_STATIC_TOKENS = frozenset(
    {"", "YOUR_BEARER_TOKEN_HERE", PLACEHOLDER_AUTH_TOKEN}
)
_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]+\}\}")
_ALLURE_SANITIZE_SUFFIXES = {".json", ".txt", ".xml", ".html", ".md"}


def is_resolvable_url(url: str | None) -> bool:
    """判断是否为可实际访问的 URL（非 Jinja 占位符）。"""
    if not url or not str(url).strip():
        return False
    value = str(url).strip()
    if value in (PLACEHOLDER_API_BASE_URL, PLACEHOLDER_URL):
        return False
    if _PLACEHOLDER_PATTERN.search(value):
        return False
    return value.startswith(("http://", "https://"))


def resolve_base_url_fallback() -> str:
    """从环境变量或 settings 获取兜底 base_url。"""
    for key in ("API_BASE_URL", "PUBLIC_API_URL"):
        env_url = os.environ.get(key)
        if is_resolvable_url(env_url):
            return str(env_url).rstrip("/")
    configured = settings.public_api_url.rstrip("/")
    if is_resolvable_url(configured):
        return configured
    return _DEFAULT_PUBLIC_API_URL


async def _resolve_db_base_url(project_identifier: str) -> str | None:
    if not project_identifier:
        return None
    try:
        from sqlalchemy import select

        from app.config.database import async_session_factory
        from app.models.project import Project
        from app.repositories.test_environment_repo import TestEnvironmentRepository

        async with async_session_factory() as session:
            project_result = await session.execute(
                select(Project).where(Project.identifier == project_identifier)
            )
            project = project_result.scalar_one_or_none()
            if not project:
                return None
            repo = TestEnvironmentRepository(session)
            env_obj = await repo.get_default(project.id)
            if not env_obj:
                envs = await repo.list_by_project(project.id)
                if envs:
                    env_obj = envs[0]
            if env_obj and is_resolvable_url(env_obj.base_url):
                return str(env_obj.base_url).rstrip("/")
    except Exception:
        return None
    return None


def _is_explicit_public_api_configured() -> bool:
    """是否在 .env / 环境变量中显式配置了 PUBLIC_API_URL（非内置默认 8000）。"""
    for key in ("API_BASE_URL", "PUBLIC_API_URL"):
        if is_resolvable_url(os.environ.get(key)):
            return True
    configured = settings.public_api_url.rstrip("/")
    return is_resolvable_url(configured) and configured != _DEFAULT_PUBLIC_API_URL


def _dedupe_urls(urls: list[str]) -> list[str]:
    """去重并按长度降序排列，避免短 URL 先替换导致残留。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        if not raw:
            continue
        base = str(raw).rstrip("/")
        for candidate in (base, f"{base}/"):
            if candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
    return sorted(normalized, key=len, reverse=True)


async def resolve_sensitive_urls_by_project_id(project_id: UUID) -> list[str]:
    """按项目 UUID 收集需脱敏的全部 base_url。"""
    urls = [resolve_base_url_fallback()]
    try:
        from app.config.database import async_session_factory
        from app.repositories.test_environment_repo import TestEnvironmentRepository

        async with async_session_factory() as session:
            repo = TestEnvironmentRepository(session)
            for env in await repo.list_by_project(project_id):
                if is_resolvable_url(env.base_url):
                    urls.append(str(env.base_url).rstrip("/"))
    except Exception:
        pass
    return _dedupe_urls(urls)


async def resolve_project_sensitive_urls(project_identifier: str) -> list[str]:
    """按项目 identifier 收集需脱敏的全部 base_url。"""
    urls = [
        resolve_base_url_fallback(),
        _DEFAULT_PUBLIC_API_URL,
        f"{_DEFAULT_PUBLIC_API_URL}/",
    ]
    if not project_identifier:
        return _dedupe_urls(urls)

    try:
        from sqlalchemy import select

        from app.config.database import async_session_factory
        from app.models.project import Project

        async with async_session_factory() as session:
            project_result = await session.execute(
                select(Project).where(Project.identifier == project_identifier)
            )
            project = project_result.scalar_one_or_none()
            if project:
                urls.extend(await resolve_sensitive_urls_by_project_id(project.id))
    except Exception:
        pass
    return _dedupe_urls(urls)


async def resolve_project_base_url(project_identifier: str) -> str:
    """
    解析项目可用的测试 base_url（执行时注入用）。

    优先级：
    1. 环境变量 API_BASE_URL / PUBLIC_API_URL（非内置默认 localhost:8000 时）
    2. DB 项目默认测试环境（UI「测试环境」配置）
    3. .env / settings 中的 PUBLIC_API_URL（含默认 localhost:8000）
    4. 内置默认值
    """
    default_url = _DEFAULT_PUBLIC_API_URL.rstrip("/")

    for key in ("API_BASE_URL", "PUBLIC_API_URL"):
        env_url = os.environ.get(key)
        if is_resolvable_url(env_url) and str(env_url).rstrip("/") != default_url:
            return str(env_url).rstrip("/")

    db_url = await _resolve_db_base_url(project_identifier)
    if db_url:
        return db_url

    if _is_explicit_public_api_configured():
        return resolve_base_url_fallback()

    for key in ("API_BASE_URL", "PUBLIC_API_URL"):
        env_url = os.environ.get(key)
        if is_resolvable_url(env_url):
            return str(env_url).rstrip("/")

    return resolve_base_url_fallback()


def inject_url_placeholders(content: str, real_url: str) -> str:
    """将文本中的 URL 占位符替换为真实地址（仅用于执行阶段）。"""
    normalized = str(real_url).rstrip("/")
    content = content.replace(PLACEHOLDER_API_BASE_URL, normalized)
    content = content.replace(PLACEHOLDER_URL, normalized)
    content = content.replace("{{base_url}}", normalized)
    return content


def build_hat_context_url_entries(real_url: str) -> dict[str, str]:
    """Build HAT g_context URL keys from a resolved base URL."""
    normalized = str(real_url).rstrip("/")
    return {
        "URL": normalized,
        "API_BASE_URL": normalized,
        "base_url": normalized,
    }


def resolve_arag_auth_url_for_runtime() -> str | None:
    """Resolve arag-auth base URL for HAT runtime context injection."""
    from app.utils.hat_auth import resolve_arag_auth_url

    return resolve_arag_auth_url()


def build_hat_context_auth_env_entries() -> dict[str, str]:
    """Inject login credentials from env into temp context (exec dir only)."""
    entries: dict[str, str] = {}
    auth_url = resolve_arag_auth_url_for_runtime()
    if auth_url:
        entries["ARAG_AUTH_URL"] = auth_url

    email = os.environ.get("HAT_TEST_EMAIL", "").strip()
    password = os.environ.get("HAT_TEST_PASSWORD", "")
    admin_email = os.environ.get("HAT_ADMIN_EMAIL", "").strip() or email
    admin_password = os.environ.get("HAT_ADMIN_PASSWORD", "") or password
    user_account = os.environ.get("HAT_TEST_ACCOUNT", "").strip() or email

    if email:
        entries["HAT_TEST_EMAIL"] = email
        entries["login_email"] = email
        entries.setdefault("USER_ACCOUNT", user_account or email)
    if password:
        entries["HAT_TEST_PASSWORD"] = password
        entries["login_password"] = password
        entries.setdefault("USER_PASSWORD", password)
    if admin_email:
        entries.setdefault("admin_account", admin_email)
    if admin_password:
        entries.setdefault("admin_password", admin_password)
    return entries


def resolve_bearer_token() -> str | None:
    """Resolve Bearer token from process env (never commit real values to repo)."""
    for key in _AUTH_TOKEN_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        value = str(raw).strip()
        if value and value not in _INVALID_STATIC_TOKENS:
            return value
    return None


def build_hat_context_auth_entries(token: str) -> dict[str, str]:
    """Build HAT g_context auth keys from a resolved Bearer token."""
    value = str(token).strip()
    return {
        "token": value,
        "auth_token": value,
    }


def build_hat_context_runtime_entries(
    real_url: str,
    folder_id: str | None = None,
    project_identifier: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, str]:
    """Build runtime context entries injected at HAT execution time."""
    entries = build_hat_context_url_entries(real_url)
    if folder_id and str(folder_id).strip():
        fid = str(folder_id).strip()
        entries["folder_id"] = fid
        entries["FOLDER_ID"] = fid
    if project_identifier and str(project_identifier).strip():
        entries["project_identifier"] = str(project_identifier).strip()
    token = bearer_token if bearer_token else resolve_bearer_token()
    if token:
        entries.update(build_hat_context_auth_entries(token))
    entries.update(build_hat_context_auth_env_entries())
    return entries


def inject_auth_token_placeholders(content: str, real_token: str) -> str:
    """Replace auth placeholders in YAML with the runtime Bearer token."""
    if not real_token:
        return content
    token = str(real_token).strip()
    updated = content.replace(PLACEHOLDER_AUTH_TOKEN, token)
    updated = updated.replace("YOUR_BEARER_TOKEN_HERE", token)
    return updated


def apply_hat_runtime_urls() -> str | None:
    """
    Override HAT g_context URL keys from process env.

    execute_api_script injects API_BASE_URL into the subprocess env; HAT reads
    context.yaml into g_context but does not consume env vars by default.
    """
    import os

    from HAT.core.globalContext import g_context

    applied_url: str | None = None
    for key in ("API_BASE_URL", "PUBLIC_API_URL"):
        raw = os.environ.get(key)
        if is_resolvable_url(raw):
            entries = build_hat_context_url_entries(str(raw))
            g_context().set_by_dict(entries)
            applied_url = entries["URL"]
            break

    folder_id = os.environ.get("FOLDER_ID") or os.environ.get("folder_id")
    if folder_id and str(folder_id).strip():
        fid = str(folder_id).strip()
        g_context().set_by_dict({"folder_id": fid, "FOLDER_ID": fid})

    project_id = os.environ.get("PROJECT_IDENTIFIER") or os.environ.get("project_identifier")
    if project_id and str(project_id).strip():
        g_context().set_by_dict({"project_identifier": str(project_id).strip()})

    bearer_token = resolve_bearer_token()
    if bearer_token:
        g_context().set_by_dict(build_hat_context_auth_entries(bearer_token))

    auth_env = build_hat_context_auth_env_entries()
    if auth_env:
        g_context().set_by_dict(auth_env)

    return applied_url


def mask_sensitive_url(text: str, real_url: str) -> str:
    """将文本中的单个真实 URL 脱敏为占位符。"""
    if not text or not real_url:
        return text
    masked = text.replace(real_url, PLACEHOLDER_API_BASE_URL)
    alt = real_url.rstrip("/")
    if alt != real_url:
        masked = masked.replace(alt, PLACEHOLDER_API_BASE_URL)
    trailing = f"{alt}/"
    masked = masked.replace(trailing, f"{PLACEHOLDER_API_BASE_URL}/")
    return masked


def mask_sensitive_urls(text: str, sensitive_urls: list[str]) -> str:
    """将文本中多个真实 URL 脱敏为占位符。"""
    if not text or not sensitive_urls:
        return text
    masked = text
    for url in sensitive_urls:
        masked = mask_sensitive_url(masked, url)
    return masked


def mask_agent_payload(payload: Any, sensitive_urls: list[str]) -> Any:
    """递归脱敏 Agent 可见的结构化数据。"""
    if not sensitive_urls:
        return payload
    if isinstance(payload, str):
        return mask_sensitive_urls(payload, sensitive_urls)
    if isinstance(payload, dict):
        return {key: mask_agent_payload(value, sensitive_urls) for key, value in payload.items()}
    if isinstance(payload, list):
        return [mask_agent_payload(item, sensitive_urls) for item in payload]
    if isinstance(payload, tuple):
        return tuple(mask_agent_payload(item, sensitive_urls) for item in payload)
    return payload


def sanitize_allure_results_dir(results_dir: Path, sensitive_urls: list[str]) -> int:
    """
    脱敏 Allure 结果目录中的文本文件（原地修改）。

    Returns:
        修改的文件数量
    """
    if not results_dir.exists() or not sensitive_urls:
        return 0

    changed = 0
    for path in results_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _ALLURE_SANITIZE_SUFFIXES:
            continue
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
            masked = mask_sensitive_urls(original, sensitive_urls)
            if masked != original:
                path.write_text(masked, encoding="utf-8")
                changed += 1
        except OSError:
            continue
    return changed


def sanitize_allure_results_dir_copy(
    results_dir: Path,
    sensitive_urls: list[str],
) -> tuple[Path, Path | None]:
    """
    复制 Allure 结果到临时目录并脱敏，不修改原始目录。

    Returns:
        (脱敏后的目录, 临时根目录或 None)
    """
    if not results_dir.exists():
        return results_dir, None

    temp_root = Path(tempfile.mkdtemp(prefix="allure_sanitized_"))
    sanitized_dir = temp_root / "allure-results"
    shutil.copytree(results_dir, sanitized_dir, dirs_exist_ok=True)
    sanitize_allure_results_dir(sanitized_dir, sensitive_urls)
    return sanitized_dir, temp_root


def prepare_hat_cases_with_url(
    cases_dir: Path,
    real_url: str,
    folder_id: str | None = None,
    project_identifier: str | None = None,
) -> tuple[Path, Path | None]:
    """
    若 context.yaml 含占位符，复制到临时目录并注入真实 URL 后执行。
    同时替换目录内所有 YAML 中的占位符，并在 context 中写入 URL/API_BASE_URL。

    Returns:
        (执行目录, 临时根目录或 None)
    """
    context_yaml = cases_dir / "context.yaml"
    normalized_url = str(real_url).rstrip("/")
    bearer_token = resolve_bearer_token()
    runtime_entries = build_hat_context_runtime_entries(
        normalized_url,
        folder_id=folder_id,
        project_identifier=project_identifier,
        bearer_token=bearer_token,
    )

    yaml_files = list(cases_dir.glob("*.yaml"))
    has_placeholders = False
    for path in yaml_files:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if (
            PLACEHOLDER_API_BASE_URL in content
            or PLACEHOLDER_URL in content
            or "{{base_url}}" in content
        ):
            has_placeholders = True
            break

    needs_runtime_inject = bool(runtime_entries) and (
        folder_id or project_identifier or has_placeholders or context_yaml.exists()
    )

    if not context_yaml.exists() and not has_placeholders and not folder_id and not project_identifier:
        return cases_dir, None

    if not needs_runtime_inject:
        return cases_dir, None

    temp_root = Path(tempfile.mkdtemp(prefix="hat_exec_"))
    exec_dir = temp_root / "cases"
    shutil.copytree(cases_dir, exec_dir, dirs_exist_ok=True)

    for path in exec_dir.glob("*.yaml"):
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue
        updated = inject_url_placeholders(original, normalized_url)
        auth_url = resolve_arag_auth_url_for_runtime()
        if auth_url:
            updated = updated.replace(PLACEHOLDER_ARAG_AUTH_URL, auth_url)
        if bearer_token:
            updated = inject_auth_token_placeholders(updated, bearer_token)
        if path.name == "context.yaml":
            lines = updated.splitlines()
            extra_lines = []
            for key, value in runtime_entries.items():
                if f"{key}:" not in updated:
                    extra_lines.append(f'{key}: "{value}"')
            if extra_lines:
                updated = updated.rstrip() + "\n" + "\n".join(extra_lines) + "\n"
        if updated != original:
            path.write_text(updated, encoding="utf-8")

    return exec_dir, temp_root


def dumps_agent_json(payload: Any, sensitive_urls: list[str], **kwargs: Any) -> str:
    """序列化并脱敏 Agent 可见 JSON。"""
    masked = mask_agent_payload(payload, sensitive_urls)
    return json.dumps(masked, **kwargs)
