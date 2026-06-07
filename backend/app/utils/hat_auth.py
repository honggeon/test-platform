"""
HAT 执行前 Bearer Token 获取（arag-auth 等外部认证服务）

凭证仅来自环境变量，不写入仓库或 Agent 上下文。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def resolve_arag_auth_url() -> str | None:
    """解析 arag-auth 基址（环境变量优先，其次 settings）。"""
    for key in ("ARAG_AUTH_URL",):
        raw = os.environ.get(key)
        if raw and str(raw).strip().startswith(("http://", "https://")):
            return str(raw).rstrip("/")
    try:
        from app.config.settings import settings

        configured = getattr(settings, "arag_auth_url", None)
        if configured and str(configured).strip().startswith(("http://", "https://")):
            return str(configured).rstrip("/")
    except Exception:
        pass
    return None


def _parse_login_token(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and data.get("token"):
        return str(data["token"]).strip()
    token = payload.get("token")
    if token:
        return str(token).strip()
    return None


def fetch_arag_bearer_token(
    *,
    auth_base_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
    timeout: float = 15.0,
) -> str | None:
    """
    POST {auth_base}/auth/v1/login，返回 JWT；失败返回 None。
    """
    base = (auth_base_url or resolve_arag_auth_url() or "").rstrip("/")
    mail = (email or os.environ.get("HAT_TEST_EMAIL") or "").strip()
    pwd = password or os.environ.get("HAT_TEST_PASSWORD") or ""
    if not base or not mail or not pwd:
        return None

    body = json.dumps({"email": mail, "password": pwd}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/auth/v1/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _parse_login_token(parsed)


def ensure_hat_bearer_token_env() -> bool:
    """
    若未设置 HAT_BEARER_TOKEN 且具备登录凭据，则登录并写入进程环境变量。

    Returns:
        是否成功设置 HAT_BEARER_TOKEN
    """
    existing = os.environ.get("HAT_BEARER_TOKEN", "").strip()
    if existing and existing not in ("", "YOUR_BEARER_TOKEN_HERE", "{{AUTH_TOKEN}}"):
        return True

    token = fetch_arag_bearer_token()
    if not token:
        return False

    os.environ["HAT_BEARER_TOKEN"] = token
    for alias in ("API_BEARER_TOKEN", "AUTH_TOKEN"):
        os.environ.setdefault(alias, token)
    return True
