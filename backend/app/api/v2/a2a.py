"""
A2A 协议端点

对外暴露日志分析 Agent 的 Agent Card 与 Task API，供外部系统发现和调用诊断能力。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config.database import async_session_factory
from app.config.settings import settings
from app.models.project import Project
from app.services.test_diagnosis_service import TestDiagnosisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/a2a", tags=["A2A 日志分析 Agent"])

A2A_API_KEY_HEADER = "X-A2A-API-Key"

# 内存 Task 存储（生产环境可替换为 Redis/DB）
_tasks: dict[str, dict[str, Any]] = {}


class A2ATaskInput(BaseModel):
    run_id: str = Field(..., description="测试运行 ID")
    project_identifier: str = Field(..., description="项目标识符")
    test_output: str = Field(default="", description="可选测试输出文本")
    source_type: str = Field(default="api_test", description="来源类型")


class A2ATaskSendRequest(BaseModel):
    skill_id: str = Field(default="log_diagnosis", description="技能 ID")
    input: A2ATaskInput


def _agent_card() -> dict[str, Any]:
    base_url = settings.public_api_url.rstrip("/")
    return {
        "name": "TestLogAnalyzer",
        "description": "分析 API 测试日志，定位代码问题并输出根因诊断报告",
        "url": f"{base_url}/api/v2/a2a",
        "version": "1.0.0",
        "capabilities": {
            "streaming": True,
            "push_notifications": True,
            "state_transition_webhooks": False,
        },
        "auth": {
            "type": "api_key",
            "in": "header",
            "key_name": A2A_API_KEY_HEADER,
        },
        "skills": [
            {
                "id": "log_diagnosis",
                "name": "测试日志诊断",
                "description": "分析测试执行日志，输出根因和代码位置",
                "input": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string"},
                        "project_identifier": {"type": "string"},
                        "test_output": {"type": "string"},
                    },
                    "required": ["run_id", "project_identifier"],
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "report_id": {"type": "string"},
                        "status": {"type": "string"},
                        "summary": {"type": "object"},
                    },
                },
            }
        ],
    }


async def verify_a2a_api_key(x_a2a_api_key: Optional[str] = Header(None, alias=A2A_API_KEY_HEADER)):
    """A2A API Key 鉴权；未配置 keys 且 debug 模式时跳过"""
    keys = settings.a2a_api_keys
    if not keys:
        if settings.debug:
            return
        raise HTTPException(status_code=503, detail="A2A API Key 未配置")
    if not x_a2a_api_key or x_a2a_api_key not in keys:
        raise HTTPException(status_code=401, detail="无效的 A2A API Key")
    return x_a2a_api_key


async def _resolve_project_id(project_identifier: str):
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project.id).where(Project.identifier == project_identifier)
        )
        project_id = result.scalar_one_or_none()
        if not project_id:
            raise HTTPException(status_code=404, detail=f"项目不存在: {project_identifier}")
        return project_id


def _task_snapshot(task_id: str) -> dict[str, Any]:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task 不存在: {task_id}")
    return task


async def _run_diagnosis_task(task_id: str, inp: A2ATaskInput):
    task = _tasks[task_id]
    try:
        task["status"] = "working"
        task["metadata"]["stage"] = "collecting"
        task["metadata"]["progress"] = 10

        project_id = await _resolve_project_id(inp.project_identifier)
        service = TestDiagnosisService()

        task["metadata"]["stage"] = "classifying"
        task["metadata"]["progress"] = 30

        report = await service.diagnose_run(
            run_id=inp.run_id,
            project_id=str(project_id),
            project_identifier=inp.project_identifier,
            options={"test_output": inp.test_output, "source_type": inp.source_type},
        )

        task["status"] = "completed" if report.status == "completed" else "failed"
        task["output"] = {
            "report_id": report.report_id,
            "status": report.status,
            "summary": report.summary,
            "degradation": report.degradation,
        }
        task["metadata"]["stage"] = "reporting"
        task["metadata"]["progress"] = 100
        task["metadata"]["completed_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        logger.error(f"A2A Task {task_id} 失败: {e}")
        task["status"] = "failed"
        task["output"] = {"error": str(e)}
        task["metadata"]["completed_at"] = datetime.now(timezone.utc).isoformat()


@router.get("/agent-card", summary="A2A Agent Card")
async def get_agent_card(_: str = Depends(verify_a2a_api_key)):
    return _agent_card()


@router.post("/tasks/send", summary="创建诊断 Task")
async def send_task(request: A2ATaskSendRequest, _: str = Depends(verify_a2a_api_key)):
    if request.skill_id != "log_diagnosis":
        raise HTTPException(status_code=400, detail=f"不支持的 skill_id: {request.skill_id}")

    task_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    _tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "input": request.input.model_dump(),
        "output": {},
        "metadata": {
            "created_at": now,
            "completed_at": None,
            "progress": 0,
            "stage": "pending",
        },
    }

    asyncio.create_task(_run_diagnosis_task(task_id, request.input))

    return {"id": task_id, "status": "pending"}


@router.get("/tasks/{task_id}", summary="查询 Task 状态")
async def get_task(task_id: str, _: str = Depends(verify_a2a_api_key)):
    return _task_snapshot(task_id)


@router.get("/tasks/{task_id}/stream", summary="SSE 流式推送 Task 状态")
async def stream_task(task_id: str, _: str = Depends(verify_a2a_api_key)):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task 不存在: {task_id}")

    async def event_generator():
        last_payload = ""
        while True:
            task = _tasks.get(task_id)
            if not task:
                break
            payload = json.dumps(task, ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"data: {payload}\n\n"
            if task["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
