"""
代码分析 Agent 上下文注入

将项目代码库统计、commit 版本信息等动态注入到 Agent 系统提示中。
借鉴 GitNexus 的动态上下文注入设计。
"""

from dataclasses import dataclass
from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from app.config.database import async_session_factory
from app.services.code_repo_service import CodeRepoService
from app.kg.persistence import GraphPersistence


# ── 上下文定义 ──────────────────────────────────────────────────────────


@dataclass
class CodeAgentContext:
    """代码分析智能体运行时上下文"""
    project_identifier: str = ""
    current_user_id: str = "00000000-0000-0000-0000-000000000001"


# ── 中间件 ──────────────────────────────────────────────────────────────


class CodeContextInjectionMiddleware(AgentMiddleware):
    """代码库上下文注入中间件

    在每次模型调用前，将项目代码库统计信息注入到系统提示中。
    包括：节点数、关系数、commit 版本、文件数等。
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        project_identifier = request.runtime.context.project_identifier

        # 动态查询项目代码库统计
        context_info = await self._build_context_info(project_identifier)

        if isinstance(request.system_message.content, list):
            request.system_message.content = request.system_message.content + [
                {"type": "text", "text": context_info}
            ]
        else:
            request.system_message.content = request.system_message.content + context_info

        return await handler(request)

    async def _build_context_info(self, project_identifier: str) -> str:
        """构建动态上下文信息"""
        if not project_identifier:
            return ""

        try:
            async with async_session_factory() as session:
                # 获取项目信息
                repo_service = CodeRepoService(session)
                try:
                    project = await repo_service.get_project(project_identifier)
                except ValueError:
                    return ""

                if not project.code_repo_path:
                    return ""

                repo_path = project.code_repo_path
                persister = GraphPersistence(session)

                # 获取统计
                try:
                    node_count = await persister.get_node_count(repo_path)
                    rel_count = await persister.get_relationship_count(repo_path)
                    type_counts = await persister.get_type_counts(repo_path)
                    commits = await persister.list_commits(repo_path, limit=3)
                except Exception:
                    return ""

                lines = [
                    "",
                    "---",
                    "## 📊 代码库上下文",
                    "",
                    f"**项目**: {project_identifier}",
                    f"**仓库**: {repo_path}",
                    f"**节点总数**: {node_count}",
                    f"**关系总数**: {rel_count}",
                    "",
                ]

                # 类型分布
                if type_counts:
                    lines.append("**节点类型分布**:")
                    for typ, count in sorted(type_counts.items(), key=lambda x: -x[1])[:8]:
                        lines.append(f"  - {typ}: {count}")
                    lines.append("")

                # 最近版本
                if commits:
                    lines.append("**最近分析的版本**:")
                    for i, c in enumerate(commits[:3], 1):
                        short = c.commit_hash[:8] if len(c.commit_hash) >= 8 else c.commit_hash
                        msg = (c.commit_message or "无提交信息")[:30]
                        lines.append(f"  {i}. `{short}` {msg}")
                    lines.append("")

                lines.append(
                    "**注意**: 以上信息由系统自动注入，调用工具时请使用 "
                    f"`project_identifier='{project_identifier}'`。"
                )
                lines.append("---")
                lines.append("")

                return "\n".join(lines)

        except Exception:
            return ""
