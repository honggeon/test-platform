"""HAT arag-auth 登录工具测试"""

import json
import os
from unittest.mock import patch

from app.utils.hat_auth import (
    _parse_login_token,
    ensure_hat_bearer_token_env,
    fetch_arag_bearer_token,
)


def test_parse_login_token_flat():
    assert _parse_login_token({"token": "abc", "user": {}}) == "abc"


def test_parse_login_token_wrapped():
    payload = {"code": 0, "data": {"token": "wrapped"}}
    assert _parse_login_token(payload) == "wrapped"


@patch("app.utils.hat_auth.urllib.request.urlopen")
def test_fetch_arag_bearer_token_success(mock_urlopen, monkeypatch):
    monkeypatch.setenv("HAT_TEST_EMAIL", "u@test.com")
    monkeypatch.setenv("HAT_TEST_PASSWORD", "secret")
    body = json.dumps({"token": "jwt-123"}).encode()
    mock_urlopen.return_value.__enter__.return_value.read.return_value = body

    token = fetch_arag_bearer_token(auth_base_url="http://auth.example:9011")
    assert token == "jwt-123"


@patch("app.utils.hat_auth.fetch_arag_bearer_token", return_value="auto-jwt")
def test_ensure_hat_bearer_token_env_sets_env(mock_fetch, monkeypatch):
    monkeypatch.delenv("HAT_BEARER_TOKEN", raising=False)
    assert ensure_hat_bearer_token_env() is True
    assert mock_fetch.called
    assert os.environ.get("HAT_BEARER_TOKEN") == "auto-jwt"
