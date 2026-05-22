"""
测试环境仓储

处理测试环境相关的数据库操作
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models.test_environment import TestEnvironment


class TestEnvironmentRepository(BaseRepository[TestEnvironment]):
    """测试环境仓储"""

    def __init__(self, session: AsyncSession):
        super().__init__(TestEnvironment, session)

    async def list_by_project(self, project_id: UUID) -> list[TestEnvironment]:
        """获取项目下的所有测试环境，按 sort_order 排序"""
        result = await self.session.execute(
            select(TestEnvironment)
            .where(TestEnvironment.project_id == project_id)
            .order_by(TestEnvironment.sort_order.asc(), TestEnvironment.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_default(self, project_id: UUID) -> TestEnvironment | None:
        """获取项目的默认测试环境"""
        result = await self.session.execute(
            select(TestEnvironment)
            .where(TestEnvironment.project_id == project_id)
            .where(TestEnvironment.is_default == True)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def clear_default(self, project_id: UUID, exclude_id: UUID | None = None) -> None:
        """清除项目下所有环境的默认标记"""
        stmt = (
            update(TestEnvironment)
            .where(TestEnvironment.project_id == project_id)
            .where(TestEnvironment.is_default == True)
        )
        if exclude_id:
            stmt = stmt.where(TestEnvironment.id != exclude_id)
        await self.session.execute(stmt.values(is_default=False))
