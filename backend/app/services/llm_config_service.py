"""
LLM 配置服务

处理 LLM 配置相关的业务逻辑
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from uuid import UUID
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LLMConfig
from app.models.project import Project
from app.repositories.llm_config_repo import LLMConfigRepository
from app.schemas.llm_config import LLMConfigCreate, LLMConfigUpdate, LLMConfigInfo, LLMConfigDetailInfo


class LLMConfigService:
    """LLM 配置服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LLMConfigRepository(session)

    def _to_info(self, config: LLMConfig) -> LLMConfigInfo:
        """转换为配置信息（不包含 API Key）"""
        return LLMConfigInfo(
            id=config.id,
            project_id=config.project_id,
            provider=config.provider,
            model_name=config.model_name,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    def _to_detail_info(self, config: LLMConfig) -> LLMConfigDetailInfo:
        """转换为配置详细信息（包含 API Key）"""
        return LLMConfigDetailInfo(
            id=config.id,
            project_id=config.project_id,
            provider=config.provider,
            model_name=config.model_name,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    async def _get_project_id_by_identifier(self, identifier: str) -> Optional[UUID]:
        """根据项目标识符获取项目 UUID"""
        result = await self.session.execute(
            select(Project.id).where(Project.identifier == identifier)
        )
        row = result.scalar_one_or_none()
        return row

    async def get_by_project_id(self, project_id: UUID) -> Optional[LLMConfigDetailInfo]:
        """
        根据项目 ID 获取配置

        Args:
            project_id: 项目 ID

        Returns:
            LLMConfigDetailInfo | None: 配置详情或 None
        """
        config = await self.repo.get_by_project_id(project_id)
        if not config:
            return None
        return self._to_detail_info(config)

    async def get_by_project_identifier(self, identifier: str) -> Optional[LLMConfigDetailInfo]:
        """
        根据项目标识符获取配置

        Args:
            identifier: 项目标识符，如 PR-1

        Returns:
            LLMConfigDetailInfo | None: 配置详情或 None
        """
        project_id = await self._get_project_id_by_identifier(identifier)
        if not project_id:
            return None
        return await self.get_by_project_id(project_id)

    async def get_model_instance_config(self, project_id: UUID) -> Optional[LLMConfig]:
        """
        获取原始模型实例（用于 Agent 动态切换）

        Args:
            project_id: 项目 ID

        Returns:
            LLMConfig | None: 原始配置对象
        """
        return await self.repo.get_by_project_id(project_id)

    async def create_or_update(
        self,
        project_id: UUID,
        data: LLMConfigCreate,
    ) -> LLMConfigInfo:
        """
        创建或更新配置

        如果项目已有配置则更新，否则创建

        Args:
            project_id: 项目 ID
            data: 配置数据

        Returns:
            LLMConfigInfo: 配置信息
        """
        existing = await self.repo.get_by_project_id(project_id)

        if existing:
            # 更新
            existing.provider = data.provider
            existing.model_name = data.model_name
            existing.api_key = data.api_key
            existing.base_url = data.base_url
            existing.temperature = data.temperature
            existing.max_tokens = data.max_tokens
            config = await self.repo.update(existing)
        else:
            # 创建
            config = LLMConfig(
                project_id=project_id,
                provider=data.provider,
                model_name=data.model_name,
                api_key=data.api_key,
                base_url=data.base_url,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
            )
            config = await self.repo.create(config)

        return self._to_info(config)

    async def create_or_update_by_identifier(
        self,
        identifier: str,
        data: LLMConfigCreate,
    ) -> LLMConfigInfo:
        """
        根据项目标识符创建或更新配置

        Args:
            identifier: 项目标识符，如 PR-1
            data: 配置数据

        Returns:
            LLMConfigInfo: 配置信息

        Raises:
            ValueError: 项目不存在
        """
        project_id = await self._get_project_id_by_identifier(identifier)
        if not project_id:
            raise ValueError(f"项目不存在: {identifier}")
        return await self.create_or_update(project_id, data)

    async def delete_by_project_id(self, project_id: UUID) -> bool:
        """
        根据项目 ID 删除配置

        Args:
            project_id: 项目 ID

        Returns:
            bool: 是否成功删除
        """
        config = await self.repo.get_by_project_id(project_id)
        if not config:
            return False
        await self.repo.delete(config)
        return True
