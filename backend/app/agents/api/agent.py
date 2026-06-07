'''
Author: Developer dev@example.com
Date: 2026-05-26 14:06:46
LastEditors: Developer dev@example.com
LastEditTime: 2026-06-04 08:48:55
FilePath: /ai-test-agent-system-platform/backend/app/agents/api/agent.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
"""
API 自动化测试智能体

该智能体负责 API 测试的全生命周期管理：
- OpenAPI 文档解析与端点管理
- 测试计划生成、测试代码生成
- 测试执行与结果收集
- 测试修复与报告生成

架构设计：
- Coordinator: 工作流编排与用户交互，通过 task() 委派 subagent
- Subagents: 专用 HAT 子智能体（计划/生成/场景/执行/修复），隔离上下文
- Skills: 由各 subagent 按需加载
- Tools: 原子操作（数据库、存储、MCP）
"""



from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from deepagents import create_deep_agent as create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.chat_models import init_chat_model
from langgraph.pregel import Pregel

from app.agents.api.subagents import COORDINATOR_PROMPT, COORDINATOR_TOOLS, build_subagents
from app.utils.filesystem import FixedFilesystemBackend
from app.utils.hat_paths import get_api_workspace_root


def _create_workspace_backend() -> FixedFilesystemBackend:
    """与 deploy_hat_case / execute_api_script 使用同一 workspace 根目录。"""
    return FixedFilesystemBackend(root_dir=get_api_workspace_root(), virtual_mode=True)


# =============================================================================
# 上下文定义
# =============================================================================

@dataclass
class APIAgentContext:
    """API 智能体运行时上下文"""
    project_identifier: str = ""
    folder_id: str = ""
    current_user_id: str = "00000000-0000-0000-0000-000000000001"


# =============================================================================
# 中间件
# =============================================================================

class APIContextInjectionMiddleware(AgentMiddleware):
    """上下文注入中间件 - 将运行时参数注入到系统提示词"""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        project_identifier = request.runtime.context.project_identifier
        folder_id = request.runtime.context.folder_id

        context_info = f"""

---
## 🎯 运行时上下文

**当前会话参数（调用工具时必须使用）：**
- `project_identifier`: `{project_identifier}`
- `folder_id`: `{folder_id}`

**重要提示：** 这些参数由系统自动注入，不要询问用户提供。
---
"""
        # 如果 content 是列表，需要将字符串包装成正确的内容块格式
        if isinstance(request.system_message.content, list):
            request.system_message.content = request.system_message.content + [{"type": "text", "text": context_info}]
        else:
            request.system_message.content = request.system_message.content + context_info
        return await handler(request)


# =============================================================================
# 智能体工厂
# =============================================================================

async def _load_model_from_config(config: dict | None) -> object:
    """
    根据配置动态加载 LLM 模型。
    如果配置不存在或加载失败，回退到默认 DeepSeek。
    """
    project_identifier = ""
    if config and "configurable" in config:
        project_identifier = config["configurable"].get("project_identifier", "")

    if project_identifier:
        try:
            from sqlalchemy import select
            from app.config.database import async_session_factory
            from app.models.project import Project
            from app.services.llm_config_service import LLMConfigService
            async with async_session_factory() as session:
                # 先通过 identifier 查找项目 UUID
                result = await session.execute(
                    select(Project.id).where(Project.identifier == project_identifier)
                )
                project_id = result.scalar_one_or_none()
                if not project_id:
                    print(f"[api_agent] Project not found: {project_identifier}, fallback to default")
                    return init_chat_model("deepseek:deepseek-chat")

                service = LLMConfigService(session)
                cfg = await service.get_model_instance_config(project_id)
                if cfg:
                    kwargs = {}
                    if cfg.api_key:
                        kwargs["api_key"] = cfg.api_key
                    if cfg.base_url:
                        kwargs["base_url"] = cfg.base_url
                    if cfg.temperature is not None:
                        kwargs["temperature"] = cfg.temperature
                    model = init_chat_model(f"{cfg.provider}:{cfg.model_name}", **kwargs)
                    print(f"[api_agent] Using model: {cfg.provider}:{cfg.model_name}")
                    return model
        except Exception as e:
            print(f"[api_agent] Failed to load LLM config: {e}, fallback to default")

    # 默认回退
    return init_chat_model("deepseek:deepseek-chat")


@asynccontextmanager
async def make_agent(config=None) -> AsyncIterator[Pregel]:
    """
    创建 API 测试智能体的工厂函数。

    使用 asynccontextmanager 模式确保：
    - MCP session 在智能体生命周期内保持活跃
    - 退出时自动清理资源
    """
    model = await _load_model_from_config(config)

    context_middleware = APIContextInjectionMiddleware()
    subagents = build_subagents(context_middleware)

    api_agent = create_agent(
        model=model,
        tools=COORDINATOR_TOOLS,
        system_prompt=COORDINATOR_PROMPT,
        middleware=[context_middleware],
        subagents=subagents,
        backend=_create_workspace_backend(),
        context_schema=APIAgentContext,
        name="api-test-coordinator",
    )

    yield api_agent


# 导出 make_agent 供 LangGraph API 使用
agent = make_agent
