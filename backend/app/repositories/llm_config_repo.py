"""
LLM 配置仓储

提供 LLM 配置数据访问层
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


class LLMConfigRepository:
    """LLM 配置数据仓储"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, config_id: UUID) -> Optional[LLMConfig]:
        """根据 ID 获取配置"""
        stmt = select(LLMConfig).where(LLMConfig.id == config_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_project_id(self, project_id: UUID) -> Optional[LLMConfig]:
        """根据项目 ID 获取配置"""
        stmt = select(LLMConfig).where(LLMConfig.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, config: LLMConfig) -> LLMConfig:
        """创建配置"""
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def update(self, config: LLMConfig) -> LLMConfig:
        """更新配置"""
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def delete(self, config: LLMConfig) -> None:
        """删除配置"""
        await self.session.delete(config)
        await self.session.flush()
