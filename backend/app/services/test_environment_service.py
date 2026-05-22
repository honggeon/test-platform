"""
测试环境服务

处理测试环境相关的业务逻辑
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

"""


from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.test_environment import TestEnvironment
from app.repositories.test_environment_repo import TestEnvironmentRepository
from app.schemas.test_environment import (
    TestEnvironmentCreate,
    TestEnvironmentUpdate,
    TestEnvironmentInfo,
)
from app.utils.exceptions import NotFoundException


class TestEnvironmentService:
    """测试环境服务"""

    def __init__(self, db: AsyncSession):
        self.repo = TestEnvironmentRepository(db)

    @staticmethod
    def _to_info(env: TestEnvironment) -> TestEnvironmentInfo:
        """模型转响应模型"""
        return TestEnvironmentInfo(
            id=str(env.id),
            project_id=str(env.project_id),
            name=env.name,
            base_url=env.base_url,
            description=env.description,
            sort_order=env.sort_order,
            is_default=env.is_default,
            created_at=env.created_at.isoformat() if env.created_at else None,
            updated_at=env.updated_at.isoformat() if env.updated_at else None,
        )

    async def _resolve_project_id(self, project_identifier: str) -> UUID:
        """将项目标识符（如 PR-1）解析为项目 UUID"""
        result = await self.repo.session.execute(
            select(Project.id).where(Project.identifier == project_identifier)
        )
        project_id = result.scalar_one_or_none()
        if not project_id:
            raise NotFoundException(f"项目 {project_identifier} 不存在")
        return project_id

    async def list_environments(self, project_identifier: str) -> list[TestEnvironmentInfo]:
        """获取项目下的所有测试环境"""
        project_uuid = await self._resolve_project_id(project_identifier)
        envs = await self.repo.list_by_project(project_uuid)
        return [self._to_info(env) for env in envs]

    async def get_environment(
        self, project_identifier: str, env_id: str
    ) -> TestEnvironmentInfo:
        """获取单个测试环境"""
        project_uuid = await self._resolve_project_id(project_identifier)
        env_uuid = UUID(env_id)
        env = await self.repo.get_by_id(env_uuid)
        if not env or env.project_id != project_uuid:
            raise NotFoundException("测试环境不存在")
        return self._to_info(env)

    async def create_environment(
        self, project_identifier: str, data: TestEnvironmentCreate
    ) -> TestEnvironmentInfo:
        """创建测试环境"""
        project_uuid = await self._resolve_project_id(project_identifier)

        # 如果设为默认，先清除其他环境的默认标记
        if data.is_default:
            await self.repo.clear_default(project_uuid)

        env = TestEnvironment(
            project_id=project_uuid,
            name=data.name,
            base_url=data.base_url,
            description=data.description,
            sort_order=data.sort_order,
            is_default=data.is_default,
        )
        self.repo.session.add(env)
        await self.repo.session.flush()
        await self.repo.session.refresh(env)
        return self._to_info(env)

    async def update_environment(
        self, project_identifier: str, env_id: str, data: TestEnvironmentUpdate
    ) -> TestEnvironmentInfo:
        """更新测试环境"""
        project_uuid = await self._resolve_project_id(project_identifier)
        env_uuid = UUID(env_id)

        env = await self.repo.get_by_id(env_uuid)
        if not env or env.project_id != project_uuid:
            raise NotFoundException("测试环境不存在")

        # 如果设为默认，先清除其他环境的默认标记
        if data.is_default is True:
            await self.repo.clear_default(project_uuid, exclude_id=env_uuid)

        # 更新字段
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(env, field, value)

        updated = await self.repo.update(env)
        return self._to_info(updated)

    async def delete_environment(
        self, project_identifier: str, env_id: str
    ) -> None:
        """删除测试环境"""
        project_uuid = await self._resolve_project_id(project_identifier)
        env_uuid = UUID(env_id)

        env = await self.repo.get_by_id(env_uuid)
        if not env or env.project_id != project_uuid:
            raise NotFoundException("测试环境不存在")

        await self.repo.delete(env_uuid)

    async def get_default_environment(
        self, project_identifier: str
    ) -> TestEnvironmentInfo | None:
        """获取项目的默认测试环境"""
        project_uuid = await self._resolve_project_id(project_identifier)
        env = await self.repo.get_default(project_uuid)
        if not env:
            return None
        return self._to_info(env)
