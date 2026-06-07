"""
A2A 端点单元测试
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.api.v2.a2a import (
    verify_a2a_api_key,
    _agent_card,
    A2ATaskSendRequest,
    A2ATaskInput,
    send_task,
    _task_snapshot,
    _tasks,
)
from app.config import settings as app_settings


class TestA2AAuth:
    @pytest.mark.asyncio
    async def test_rejects_missing_key_when_keys_configured(self):
        with patch.object(app_settings, "a2a_api_keys", ["secret-key"]):
            with patch.object(app_settings, "debug", False):
                with pytest.raises(HTTPException) as exc:
                    await verify_a2a_api_key(None)
                assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_allows_debug_without_keys(self):
        with patch.object(app_settings, "a2a_api_keys", []):
            with patch.object(app_settings, "debug", True):
                assert await verify_a2a_api_key(None) is None

    @pytest.mark.asyncio
    async def test_accepts_valid_key(self):
        with patch.object(app_settings, "a2a_api_keys", ["secret-key"]):
            with patch.object(app_settings, "debug", False):
                assert await verify_a2a_api_key("secret-key") == "secret-key"


class TestA2AAgentCard:
    def test_agent_card_schema(self):
        with patch.object(app_settings, "public_api_url", "http://localhost:8000"):
            card = _agent_card()
            assert card["name"] == "TestLogAnalyzer"
            assert "log_diagnosis" in [s["id"] for s in card["skills"]]
            assert card["auth"]["key_name"] == "X-A2A-API-Key"


class TestA2ATasks:
    @pytest.mark.asyncio
    async def test_send_task_creates_pending_task(self):
        _tasks.clear()
        request = A2ATaskSendRequest(
            input=A2ATaskInput(run_id="run-1", project_identifier="PR-1")
        )
        with patch("app.api.v2.a2a._run_diagnosis_task", new=AsyncMock()):
            result = await send_task(request, "key")
        assert result["status"] == "pending"
        assert result["id"] in _tasks
        _tasks.clear()

    @pytest.mark.asyncio
    async def test_get_task_not_found(self):
        with pytest.raises(HTTPException) as exc:
            _task_snapshot("nonexistent")
        assert exc.value.status_code == 404
