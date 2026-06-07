"""测试环境 URL 解析与脱敏工具测试"""
import json
from pathlib import Path

import pytest

from app.utils.test_environment_url import (
    PLACEHOLDER_API_BASE_URL,
    PLACEHOLDER_AUTH_TOKEN,
    _is_explicit_public_api_configured,
    apply_hat_runtime_urls,
    inject_auth_token_placeholders,
    inject_url_placeholders,
    is_resolvable_url,
    mask_agent_payload,
    mask_sensitive_url,
    mask_sensitive_urls,
    prepare_hat_cases_with_url,
    resolve_base_url_fallback,
    resolve_bearer_token,
    resolve_project_base_url,
    sanitize_allure_results_dir,
)


def test_is_resolvable_url_rejects_placeholders():
    assert is_resolvable_url("{{API_BASE_URL}}") is False
    assert is_resolvable_url("{{URL}}") is False
    assert is_resolvable_url("http://localhost:8001") is True


def test_inject_and_mask_roundtrip():
    real = "http://localhost:8001"
    raw = f'URL: "{PLACEHOLDER_API_BASE_URL}"/api'
    injected = inject_url_placeholders(raw, real)
    assert "8001" in injected
    masked = mask_sensitive_url(injected, real)
    assert "8001" not in masked
    assert PLACEHOLDER_API_BASE_URL in masked


def test_mask_sensitive_urls_multiple():
    text = "a http://localhost:8000/x b http://staging.example.com/y"
    masked = mask_sensitive_urls(
        text,
        ["http://staging.example.com", "http://localhost:8000"],
    )
    assert "8000" not in masked
    assert "staging.example.com" not in masked
    assert masked.count(PLACEHOLDER_API_BASE_URL) == 2


def test_mask_agent_payload_recursive():
    payload = {
        "tests": [
            {"error": "connect http://localhost:8001 failed"},
            {"stack": "at http://localhost:8001/api"},
        ]
    }
    masked = mask_agent_payload(payload, ["http://localhost:8001"])
    assert "8001" not in json.dumps(masked, ensure_ascii=False)


def test_resolve_bearer_token_from_env(monkeypatch):
    for key in ("HAT_BEARER_TOKEN", "API_BEARER_TOKEN", "AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HAT_BEARER_TOKEN", "eyJ.test.token")
    assert resolve_bearer_token() == "eyJ.test.token"
    monkeypatch.setenv("HAT_BEARER_TOKEN", "YOUR_BEARER_TOKEN_HERE")
    assert resolve_bearer_token() is None


def test_inject_auth_token_placeholders():
    raw = f"token: {PLACEHOLDER_AUTH_TOKEN}\nauth: YOUR_BEARER_TOKEN_HERE"
    injected = inject_auth_token_placeholders(raw, "secret-jwt")
    assert "secret-jwt" in injected
    assert PLACEHOLDER_AUTH_TOKEN not in injected
    assert "YOUR_BEARER_TOKEN_HERE" not in injected


def test_prepare_hat_cases_injects_bearer_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HAT_BEARER_TOKEN", "eyJ.runtime.token")
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "context.yaml").write_text(
        'URL: "{{API_BASE_URL}}"\ntoken: "{{AUTH_TOKEN}}"\n',
        encoding="utf-8",
    )

    exec_dir, temp_root = prepare_hat_cases_with_url(cases_dir, "http://192.168.0.64:9010")
    assert temp_root is not None
    content = (exec_dir / "context.yaml").read_text(encoding="utf-8")
    assert "eyJ.runtime.token" in content
    assert PLACEHOLDER_AUTH_TOKEN not in content
    assert "9010" in content

    import shutil
    shutil.rmtree(temp_root, ignore_errors=True)


def test_apply_hat_runtime_urls_injects_bearer_token(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8001")
    monkeypatch.setenv("HAT_BEARER_TOKEN", "eyJ.hat.token")
    from HAT.core.globalContext import g_context

    g_context().set_by_dict({"token": "{{AUTH_TOKEN}}"})
    apply_hat_runtime_urls()
    assert g_context().get_dict("token") == "eyJ.hat.token"
    assert g_context().get_dict("auth_token") == "eyJ.hat.token"


def test_prepare_hat_cases_with_url(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "context.yaml").write_text(
        'URL: "{{API_BASE_URL}}"\n', encoding="utf-8"
    )
    (cases_dir / "test.yaml").write_text("steps: []\n", encoding="utf-8")

    exec_dir, temp_root = prepare_hat_cases_with_url(cases_dir, "http://localhost:8001")
    assert temp_root is not None
    content = (exec_dir / "context.yaml").read_text(encoding="utf-8")
    assert "8001" in content
    assert "{{API_BASE_URL}}" in (cases_dir / "context.yaml").read_text(encoding="utf-8")

    import shutil
    shutil.rmtree(temp_root, ignore_errors=True)


def test_prepare_hat_cases_injects_folder_id(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "context.yaml").write_text(
        'URL: "{{API_BASE_URL}}"\n', encoding="utf-8"
    )

    exec_dir, temp_root = prepare_hat_cases_with_url(
        cases_dir,
        "http://localhost:8001",
        folder_id="36e8cbc2-15a2-47ce-b2a4-44d4123164b4",
        project_identifier="PR-1",
    )
    assert temp_root is not None
    content = (exec_dir / "context.yaml").read_text(encoding="utf-8")
    assert "36e8cbc2-15a2-47ce-b2a4-44d4123164b4" in content
    assert "PR-1" in content

    import shutil
    shutil.rmtree(temp_root, ignore_errors=True)


def test_apply_hat_runtime_urls_injects_folder_id(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8001")
    monkeypatch.setenv("FOLDER_ID", "36e8cbc2-15a2-47ce-b2a4-44d4123164b4")
    from HAT.core.globalContext import g_context

    g_context().set_by_dict({"URL": "{{API_BASE_URL}}"})
    applied = apply_hat_runtime_urls()
    assert applied == "http://localhost:8001"
    assert g_context().get_dict("folder_id") == "36e8cbc2-15a2-47ce-b2a4-44d4123164b4"


def test_apply_hat_runtime_urls_overrides_context(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8001")
    from HAT.core.globalContext import g_context

    g_context().set_by_dict({"URL": "{{API_BASE_URL}}", "project_identifier": "PR-1"})
    applied = apply_hat_runtime_urls()
    assert applied == "http://localhost:8001"
    assert g_context().get_dict("URL") == "http://localhost:8001"
    assert g_context().get_dict("API_BASE_URL") == "http://localhost:8001"


def test_sanitize_allure_results_dir(tmp_path):
    results_dir = tmp_path / "allure-results"
    results_dir.mkdir()
    attachment = results_dir / "demo-attachment.txt"
    attachment.write_text(
        "请求地址: http://localhost:8001/api/v2/test\n",
        encoding="utf-8",
    )
    result_json = results_dir / "demo-result.json"
    result_json.write_text(
        json.dumps(
            {
                "statusDetails": {
                    "trace": "ConnectionError http://localhost:8001/api",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    changed = sanitize_allure_results_dir(results_dir, ["http://localhost:8001"])
    assert changed == 2
    assert "8001" not in attachment.read_text(encoding="utf-8")
    assert "8001" not in result_json.read_text(encoding="utf-8")


def test_resolve_base_url_fallback(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_API_URL", raising=False)
    url = resolve_base_url_fallback()
    assert url.startswith("http")


def test_explicit_public_api_overrides_default(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_API_URL", raising=False)
    monkeypatch.setattr(
        "app.utils.test_environment_url.settings.public_api_url",
        "http://localhost:8001",
    )
    assert _is_explicit_public_api_configured() is True


def test_resolve_project_base_url_prefers_db_over_default_env(monkeypatch):
    import asyncio

    async def fake_db(_pid: str) -> str:
        return "http://192.168.0.64:9010"

    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.setenv("PUBLIC_API_URL", "http://localhost:8000")
    monkeypatch.setattr(
        "app.utils.test_environment_url.settings.public_api_url",
        "http://localhost:8000",
    )
    monkeypatch.setattr(
        "app.utils.test_environment_url._resolve_db_base_url",
        fake_db,
    )
    url = asyncio.run(resolve_project_base_url("PR-1"))
    assert url == "http://192.168.0.64:9010"


def test_resolve_project_base_url_prefers_explicit_env_over_db(monkeypatch):
    import asyncio

    async def fake_db(_pid: str) -> str:
        return "http://192.168.0.64:9010"

    monkeypatch.setenv("API_BASE_URL", "http://staging.example.com:9000")
    monkeypatch.setattr(
        "app.utils.test_environment_url._resolve_db_base_url",
        fake_db,
    )
    url = asyncio.run(resolve_project_base_url("PR-1"))
    assert url == "http://staging.example.com:9000"


def test_inject_url_placeholders_replaces_base_url():
    injected = inject_url_placeholders(
        '请求地址: "{{base_url}}/auth/v1/login"',
        "http://192.168.0.64:9010",
    )
    assert injected == '请求地址: "http://192.168.0.64:9010/auth/v1/login"'


def test_build_hat_context_auth_env_entries_aliases(monkeypatch):
    monkeypatch.setenv("HAT_TEST_EMAIL", "user@test.com")
    monkeypatch.setenv("HAT_TEST_PASSWORD", "secret123")
    from app.utils.test_environment_url import build_hat_context_auth_env_entries

    entries = build_hat_context_auth_env_entries()
    assert entries["HAT_TEST_EMAIL"] == "user@test.com"
    assert entries["USER_ACCOUNT"] == "user@test.com"
    assert entries["USER_PASSWORD"] == "secret123"
    assert entries["admin_account"] == "user@test.com"


def test_apply_hat_runtime_urls_sets_base_url(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://192.168.0.64:9010")
    from HAT.core.globalContext import g_context

    g_context().set_by_dict({"base_url": "{{API_BASE_URL}}"})
    apply_hat_runtime_urls()
    assert g_context().get_dict("base_url") == "http://192.168.0.64:9010"
