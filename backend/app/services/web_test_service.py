"""
Web 测试服务

处理 Web 测试相关的业务逻辑
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import json
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.web_test import WebTest, WebTestRun, WebTestResult
from app.models.web_function import WebFunction, WebSubFunction
from app.repositories.web_test_repo import (
    WebTestRepository,
    WebTestRunRepository,
    WebTestResultRepository,
)
from app.repositories.project_repo import ProjectRepository
from app.schemas.enums import TestResultStatus
from app.utils.exceptions import NotFoundException
from app.config.minio_client import MinIOClient
from app.config.settings import settings


class WebTestService:
    """Web 测试服务类"""

    def __init__(self, session: AsyncSession, mongodb=None):
        self.session = session
        self.mongodb = mongodb
        self.web_test_repo = WebTestRepository(session)
        self.web_test_run_repo = WebTestRunRepository(session)
        self.web_test_result_repo = WebTestResultRepository(session)
        self.project_repo = ProjectRepository(session)

    async def _get_project_by_identifier(self, identifier: str):
        """获取项目，不存在则抛出异常"""
        project = await self.project_repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException(resource_type="项目", resource_id=identifier)
        return project

    # ==================== Web 测试管理 ====================

    async def create_web_test(
        self,
        project_identifier: str,
        name: str,
        base_url: str,
        script_path: str,
        script_format: str = "playwright",
        script_language: str = "typescript",
        description: Optional[str] = None,
        test_config: Optional[dict] = None,
        folder_id: Optional[str] = None,
        target_pages: Optional[list] = None,
        test_flows: Optional[list] = None,
    ) -> dict:
        """创建 Web 测试"""
        project = await self._get_project_by_identifier(project_identifier)

        # 生成标识符 (简化版本，实际应该用序列)
        identifier = f"WT-{uuid4().hex[:8].upper()}"

        web_test = await self.web_test_repo.create(
            project_id=project.id,
            identifier=identifier,
            name=name,
            base_url=base_url,
            script_path=script_path,
            script_format=script_format,
            script_language=script_language,
            description=description,
            test_config=test_config or {},
            target_pages=target_pages,
            test_flows=test_flows,
            generated_by_agent="web_agent",
            total_pages=len(target_pages) if target_pages else 0,
            total_flows=len(test_flows) if test_flows else 0,
        )

        return {
            "id": str(web_test.id),
            "identifier": web_test.identifier,
            "name": web_test.name,
            "base_url": web_test.base_url,
            "description": web_test.description,
            "script_format": web_test.script_format,
            "script_language": web_test.script_language,
            "total_pages": web_test.total_pages,
            "total_flows": web_test.total_flows,
            "created_at": web_test.created_at.isoformat(),
        }

    async def get_web_test(
        self,
        project_identifier: str,
        web_test_id: str,
    ) -> dict:
        """获取 Web 测试详情"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id_with_relations(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        return {
            "id": str(web_test.id),
            "identifier": web_test.identifier,
            "name": web_test.name,
            "base_url": web_test.base_url,
            "description": web_test.description,
            "script_path": web_test.script_path,
            "script_format": web_test.script_format,
            "script_language": web_test.script_language,
            "test_config": web_test.test_config,
            "target_pages": web_test.target_pages,
            "test_flows": web_test.test_flows,
            "total_pages": web_test.total_pages,
            "total_flows": web_test.total_flows,
            "created_at": web_test.created_at.isoformat(),
            "updated_at": web_test.updated_at.isoformat() if web_test.updated_at else None,
        }

    async def list_web_tests(
        self,
        project_identifier: str,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        script_format: Optional[str] = None,
    ) -> dict:
        """获取 Web 测试列表"""
        project = await self._get_project_by_identifier(project_identifier)

        offset = (page - 1) * page_size
        items, total = await self.web_test_repo.get_by_project(
            project.id,
            offset=offset,
            limit=page_size,
            search=search,
            script_format=script_format,
        )

        return {
            "items": [
                {
                    "id": str(item.id),
                    "identifier": item.identifier,
                    "name": item.name,
                    "base_url": item.base_url,
                    "description": item.description,
                    "script_format": item.script_format,
                    "script_language": item.script_language,
                    "total_pages": item.total_pages,
                    "total_flows": item.total_flows,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def update_web_test(
        self,
        project_identifier: str,
        web_test_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        test_config: Optional[dict] = None,
    ) -> dict:
        """更新 Web 测试"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if test_config is not None:
            update_data["test_config"] = test_config

        updated = await self.web_test_repo.update(web_test, **update_data)

        return {
            "id": str(updated.id),
            "identifier": updated.identifier,
            "name": updated.name,
            "description": updated.description,
            "test_config": updated.test_config,
            "updated_at": updated.updated_at.isoformat() if updated.updated_at else None,
        }

    async def delete_web_test(
        self,
        project_identifier: str,
        web_test_id: str,
    ) -> None:
        """删除 Web 测试"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        await self.web_test_repo.delete(web_test)

    async def get_test_script(
        self,
        project_identifier: str,
        web_test_id: str,
    ) -> str:
        """获取测试脚本内容"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        # 从 MinIO 下载脚本
        content_bytes = MinIOClient.download_file(web_test.script_path)
        return content_bytes.decode('utf-8')

    async def update_test_script(
        self,
        project_identifier: str,
        web_test_id: str,
        script_content: str,
    ) -> None:
        """更新测试脚本内容"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        # 上传到 MinIO
        script_bytes = script_content.encode('utf-8')
        MinIOClient.upload_bytes(
            object_name=web_test.script_path,
            data=script_bytes,
            content_type="text/plain"
        )

    async def run_web_test(
        self,
        project_identifier: str,
        web_test_id: str,
        execution_config: Optional[dict] = None,
    ) -> dict:
        """执行 Web 测试"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        # 创建测试运行记录
        identifier = f"WTR-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6]}"
        test_run = await self.web_test_run_repo.create(
            project_id=project.id,
            web_test_id=web_test.id,
            identifier=identifier,
            status="pending",
            execution_config=execution_config or {},
        )

        # TODO: 实际执行测试的逻辑需要在独立的工作进程中完成
        # 这里只创建运行记录，实际执行由异步任务完成

        return {
            "run_id": str(test_run.id),
            "identifier": test_run.identifier,
            "status": test_run.status,
        }

    async def get_test_runs(
        self,
        project_identifier: str,
        web_test_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """获取测试运行历史"""
        project = await self._get_project_by_identifier(project_identifier)
        web_test = await self.web_test_repo.get_by_id(UUID(web_test_id))

        if not web_test or web_test.project_id != project.id:
            raise NotFoundException(resource_type="Web 测试", resource_id=web_test_id)

        offset = (page - 1) * page_size
        items, total = await self.web_test_run_repo.get_by_web_test(
            web_test.id,
            offset=offset,
            limit=page_size,
        )

        return {
            "items": [
                {
                    "id": str(item.id),
                    "identifier": item.identifier,
                    "status": item.status,
                    "total_tests": item.total_tests,
                    "passed_tests": item.passed_tests,
                    "failed_tests": item.failed_tests,
                    "skipped_tests": item.skipped_tests,
                    "duration_ms": item.duration_ms,
                    "error_message": item.error_message,
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_folder_web_tests(
        self,
        project_identifier: str,
        folder_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """获取文件夹下的 Web 测试列表"""
        from sqlalchemy import select, func

        project = await self._get_project_by_identifier(project_identifier)

        query = select(WebTest).where(
            WebTest.project_id == project.id,
            WebTest.folder_id == UUID(folder_id)
        )

        count_result = await self.session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        query = query.order_by(WebTest.created_at.desc())
        query = query.offset(offset).limit(page_size)

        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return {
            "items": [
                {
                    "id": str(item.id),
                    "identifier": item.identifier,
                    "name": item.name,
                    "base_url": item.base_url,
                    "description": item.description,
                    "script_format": item.script_format,
                    "total_pages": item.total_pages,
                    "total_flows": item.total_flows,
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
