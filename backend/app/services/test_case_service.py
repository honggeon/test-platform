"""
测试用例服务

处理测试用例相关的业务逻辑
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Optional, Any, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.models.folder_type import FolderType
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.folder_repo import FolderRepository
from app.repositories.user_repo import UserRepository
from app.repositories.test_result_repo import TestResultRepository
from app.repositories.test_run_repo import TestRunRepository
from app.models.test_result import TestResult
from app.schemas.test_case import (
    TestCaseCreate, TestCaseUpdate, TestCaseInfo, TestCaseMinifiedInfo,
    TestStepInfo, BulkEditWithOperationsRequest, TestCaseHistoryResponse,
    TestCaseHistoryItem, ModifiedFieldInfo, LatestTestResultInfo,
)
from app.schemas.common import LinkInfo
from app.schemas.enums import TestCaseTemplate, BulkEditOperation, TestResultStatus
from app.utils.exceptions import NotFoundException, BadRequestException
from app.utils.identifier import generate_test_case_identifier
from app.utils.test_case_import import (
    parse_import_file,
    parse_api_test_cases_json,
    humanize_api_import_subfolder_name,
    resolve_api_import_tag_group_name,
    extract_api_test_cases_list,
    convert_api_test_case_item,
    parse_execution_status_from_raw_item,
    map_test_result_status_string,
)
from app.config.settings import settings
from app.services.mongodb_service import MongoDBService


MANUAL_TEST_RUN_NAME = "手动标记结果"
API_SYNC_TEST_RUN_NAME = "API测试同步结果"


class TestCaseService:
    """
    测试用例服务类

    处理测试用例相关的业务逻辑
    """

    def __init__(self, session: AsyncSession, mongodb=None):
        self.session = session
        self.mongodb = mongodb
        self.repo = TestCaseRepository(session)
        self.project_repo = ProjectRepository(session)
        self.folder_repo = FolderRepository(session)
        self.test_result_repo = TestResultRepository(session)
        self.run_repo = TestRunRepository(session)

    @staticmethod
    def _latest_result_to_info(result: TestResult) -> LatestTestResultInfo:
        return LatestTestResultInfo(
            status=result.status,
            tested_at=result.created_at,
            test_run_id=result.test_run_id,
        )

    async def _get_project_by_identifier(self, identifier: str):
        """获取项目，不存在则抛出异常"""
        project = await self.project_repo.get_by_identifier(identifier)
        if not project:
            raise NotFoundException(resource_type="项目", resource_id=identifier)
        return project
    
    async def _test_case_to_info(
        self,
        tc: TestCase,
        project_identifier: str,
        latest_result: Optional[TestResult] = None,
    ) -> TestCaseInfo:
        """将测试用例模型转换为完整响应模型"""
        steps = [
            TestStepInfo(
                id=step.id,
                order=step.step_number,
                step=step.action,
                result=step.expected_result,
            )
            for step in tc.steps
        ] if tc.steps else []

        tags = [tag.name for tag in tc.tags] if tc.tags else []
        issues = tc.issues if tc.issues else []

        return TestCaseInfo(
            id=tc.id,
            identifier=tc.identifier,
            name=tc.name,
            description=tc.description,
            preconditions=tc.preconditions,
            priority=tc.priority,
            status=tc.state,
            case_type=tc.test_case_type,
            template=tc.template,
            automation_status=tc.automation_status,
            project_id=tc.project_id,
            folder_id=tc.folder_id,
            owner=tc.owner.email if tc.owner else None,
            created_by=tc.creator.email if tc.creator else "",
            created_at=tc.created_at,
            updated_at=tc.updated_at,
            version=tc.version,
            tags=tags,
            issues=issues,
            custom_fields=tc.custom_fields,
            test_case_steps=steps,
            feature=tc.feature,
            scenario=tc.scenario,
            background=tc.background,
            links=LinkInfo(
                self=f"{settings.api_prefix}/projects/{project_identifier}/test-cases/{tc.identifier}",
                project=f"{settings.api_prefix}/projects/{project_identifier}",
                folder=f"{settings.api_prefix}/projects/{project_identifier}/folders/{tc.folder_id}" if tc.folder_id else None,
            ),
            latest_test_result=(
                self._latest_result_to_info(latest_result) if latest_result else None
            ),
        )

    async def _test_case_to_minified(
        self,
        tc: TestCase
    ) -> TestCaseMinifiedInfo:
        """将测试用例模型转换为精简响应模型"""
        tags = [tag.name for tag in tc.tags] if tc.tags else []

        return TestCaseMinifiedInfo(
            id=tc.id,
            identifier=tc.identifier,
            name=tc.name,
            priority=tc.priority,
            status=tc.state,
            case_type=tc.test_case_type,
            folder_id=tc.folder_id,
            owner=tc.owner.email if tc.owner else None,
            tags=tags,
        )
    
    async def get_test_cases(
        self,
        project_identifier: str,
        offset: int = 0,
        limit: int = 30,
        minify: bool = False,
        test_case_ids: Optional[list[str]] = None,
        folder_ids: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        priorities: Optional[list[str]] = None,
        case_types: Optional[list[str]] = None,
        owners: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        issue_ids: Optional[list[str]] = None,
        issue_type: Optional[str] = None,
        custom_fields: Optional[dict[str, list[str]]] = None,
        updated_after: Optional[datetime] = None,
        updated_before: Optional[datetime] = None,
    ) -> tuple[list[Union[TestCaseInfo, TestCaseMinifiedInfo]], int]:
        """
        获取测试用例列表

        支持多种过滤条件，同一参数内的多个值为 OR 关系，不同参数之间为 AND 关系
        """
        project = await self._get_project_by_identifier(project_identifier)

        # 构建过滤条件
        filters = {
            "test_case_ids": test_case_ids,
            "folder_ids": folder_ids,
            "statuses": statuses,
            "priorities": priorities,
            "case_types": case_types,
            "owners": owners,
            "tags": tags,
            "issue_ids": issue_ids,
            "issue_type": issue_type,
            "custom_fields": custom_fields,
            "updated_after": updated_after,
            "updated_before": updated_before,
        }

        test_cases = await self.repo.get_by_project_with_filters(
            project.id, offset, limit, **filters
        )
        total = await self.repo.count_by_project_with_filters(project.id, **filters)

        latest_results: dict[UUID, TestResult] = {}
        if not minify and test_cases:
            latest_results = await self.test_result_repo.get_latest_by_test_case_ids(
                [tc.id for tc in test_cases]
            )

        result = []
        for tc in test_cases:
            if minify:
                info = await self._test_case_to_minified(tc)
            else:
                info = await self._test_case_to_info(
                    tc,
                    project_identifier,
                    latest_result=latest_results.get(tc.id),
                )
            result.append(info)

        return result, total
    
    async def get_test_case(
        self,
        project_identifier: str,
        test_case_identifier: str,
    ) -> TestCaseInfo:
        """获取测试用例详情"""
        project = await self._get_project_by_identifier(project_identifier)
        
        tc = await self.repo.get_by_identifier(test_case_identifier)
        if not tc or tc.project_id != project.id:
            raise NotFoundException(
                resource_type="测试用例", 
                resource_id=test_case_identifier
            )

        latest_results = await self.test_result_repo.get_latest_by_test_case_ids([tc.id])
        return await self._test_case_to_info(
            tc,
            project_identifier,
            latest_result=latest_results.get(tc.id),
        )

    async def _get_or_create_manual_test_run(self, project_id: UUID) -> TestRun:
        """获取或创建用于手动标记结果的测试运行"""
        test_run = await self.run_repo.get_by_project_and_name(
            project_id,
            MANUAL_TEST_RUN_NAME,
        )
        if test_run:
            return test_run

        identifier = await self.run_repo.generate_identifier(project_id)
        test_run = TestRun(
            project_id=project_id,
            identifier=identifier,
            name=MANUAL_TEST_RUN_NAME,
            description="用于测试用例库中手动标记测试结果",
        )
        return await self.run_repo.create(test_run)

    async def _get_or_create_api_sync_test_run(self, project_id: UUID) -> TestRun:
        """获取或创建用于同步 API 测试执行结果的测试运行"""
        test_run = await self.run_repo.get_by_project_and_name(
            project_id,
            API_SYNC_TEST_RUN_NAME,
        )
        if test_run:
            return test_run

        identifier = await self.run_repo.generate_identifier(project_id)
        test_run = TestRun(
            project_id=project_id,
            identifier=identifier,
            name=API_SYNC_TEST_RUN_NAME,
            description="用于从 API 测试同步执行结果到测试用例库",
        )
        return await self.run_repo.create(test_run)

    @staticmethod
    def _normalize_case_match_key(name: str) -> str:
        return " ".join(str(name).strip().lower().split())

    @staticmethod
    def _map_endpoint_last_run_status(status: Optional[str]) -> Optional[TestResultStatus]:
        if not status:
            return None
        return map_test_result_status_string(status)

    async def _get_endpoint_execution_status_map(
        self,
        endpoint,
    ) -> tuple[dict[str, TestResultStatus], Optional[TestResultStatus]]:
        """获取端点最新 API 执行结果（用例名 -> 状态）及端点级兜底状态"""
        from sqlalchemy import select
        from app.models.api_test import APITestRun, APITestResult

        status_by_name: dict[str, TestResultStatus] = {}
        fallback = self._map_endpoint_last_run_status(endpoint.last_run_status)

        api_test_ids = endpoint.api_test_ids or []
        if not api_test_ids:
            return status_by_name, fallback

        test_uuids: list[UUID] = []
        for test_id in api_test_ids:
            try:
                test_uuids.append(UUID(str(test_id)))
            except ValueError:
                continue
        if not test_uuids:
            return status_by_name, fallback

        run_result = await self.session.execute(
            select(APITestRun)
            .where(APITestRun.api_test_id.in_(test_uuids))
            .order_by(APITestRun.created_at.desc())
            .limit(1)
        )
        latest_run = run_result.scalar_one_or_none()
        if not latest_run:
            return status_by_name, fallback

        results_result = await self.session.execute(
            select(APITestResult).where(APITestResult.test_run_id == latest_run.id)
        )
        for item in results_result.scalars().all():
            status_by_name[self._normalize_case_match_key(item.scenario_name)] = item.status

        return status_by_name, fallback

    def _resolve_case_execution_status(
        self,
        case_name: str,
        raw_item: Optional[dict[str, Any]],
        status_by_name: dict[str, TestResultStatus],
        fallback: Optional[TestResultStatus],
    ) -> Optional[TestResultStatus]:
        """解析单条用例的执行状态"""
        if raw_item:
            raw_status = parse_execution_status_from_raw_item(raw_item)
            if raw_status:
                return raw_status

        key = self._normalize_case_match_key(case_name)
        if key in status_by_name:
            return status_by_name[key]

        for scenario_key, status in status_by_name.items():
            if key in scenario_key or scenario_key in key:
                return status

        return fallback

    async def _record_test_case_execution_result(
        self,
        project_id: UUID,
        test_case_id: UUID,
        status: TestResultStatus,
    ) -> TestResult:
        test_run = await self._get_or_create_api_sync_test_run(project_id)
        result = TestResult(
            test_run_id=test_run.id,
            test_case_id=test_case_id,
            status=status,
            description="从 API 测试执行结果同步",
        )
        return await self.test_result_repo.create(result)

    async def _refresh_test_case_info(
        self,
        test_case_id: UUID,
        project_identifier: str,
    ) -> TestCaseInfo:
        tc = await self.repo.get_by_id_with_relations(test_case_id)
        latest_results = await self.test_result_repo.get_latest_by_test_case_ids([test_case_id])
        return await self._test_case_to_info(
            tc,
            project_identifier,
            latest_result=latest_results.get(test_case_id),
        )

    async def set_latest_test_result_status(
        self,
        project_identifier: str,
        test_case_identifier: str,
        status: Optional[TestResultStatus],
    ) -> TestCaseInfo:
        """设置或清除测试用例最近一次测试结果"""
        project = await self._get_project_by_identifier(project_identifier)

        tc = await self.repo.get_by_identifier(test_case_identifier)
        if not tc or tc.project_id != project.id:
            raise NotFoundException(
                resource_type="测试用例",
                resource_id=test_case_identifier,
            )

        latest_results = await self.test_result_repo.get_latest_by_test_case_ids([tc.id])
        latest = latest_results.get(tc.id)

        if status is None:
            if latest:
                await self.test_result_repo.delete(latest)
        elif latest:
            await self.test_result_repo.update_status(latest, status)
        else:
            test_run = await self._get_or_create_manual_test_run(project.id)
            result = TestResult(
                test_run_id=test_run.id,
                test_case_id=tc.id,
                status=status,
            )
            await self.test_result_repo.create(result)

        tc = await self.repo.get_by_id_with_relations(tc.id)
        latest_results = await self.test_result_repo.get_latest_by_test_case_ids([tc.id])
        return await self._test_case_to_info(
            tc,
            project_identifier,
            latest_result=latest_results.get(tc.id),
        )

    async def _resolve_api_import_target_folder(
        self,
        project_id: UUID,
        endpoint,
        root_parent_id: Optional[UUID] = None,
    ) -> UUID:
        """按 Swagger 功能模块自动创建测试用例库文件夹：{tag}/{子目录}"""
        tag_name = resolve_api_import_tag_group_name(endpoint.tag_group, endpoint.tags)
        subfolder_name = humanize_api_import_subfolder_name(
            path=endpoint.path,
            summary=endpoint.summary,
            custom_config=endpoint.custom_config,
        )

        tag_folder = await self.folder_repo.get_or_create(
            project_id=project_id,
            name=tag_name,
            parent_id=root_parent_id,
            folder_type=FolderType.TEST_CASE,
            description=f"从 API 测试导入：{tag_name}",
        )
        target_folder = await self.folder_repo.get_or_create(
            project_id=project_id,
            name=subfolder_name,
            parent_id=tag_folder.id,
            folder_type=FolderType.TEST_CASE,
            description=f"从 API 测试导入：{endpoint.display_name}",
        )
        return target_folder.id
    
    async def create_test_case(
        self,
        project_identifier: str,
        data: TestCaseCreate,
        created_by: UUID,
        folder_id: Optional[UUID] = None,
    ) -> TestCaseInfo:
        """
        创建测试用例

        支持普通测试用例和 BDD 测试用例
        """
        project = await self._get_project_by_identifier(project_identifier)

        # 验证文件夹
        if folder_id:
            folder = await self.folder_repo.get_by_id(folder_id)
            if not folder or folder.project_id != project.id:
                raise BadRequestException("文件夹不存在或不属于该项目")

        # 查找负责人
        owner_id = None
        if data.owner:
            user_repo = UserRepository(self.session)
            owner = await user_repo.get_by_email(data.owner)
            if owner:
                owner_id = owner.id

        # 生成唯一标识符（使用随机数，最多重试 10 次）
        max_retries = 10
        identifier = None
        for _ in range(max_retries):
            identifier = generate_test_case_identifier()
            if not await self.repo.identifier_exists(identifier):
                break
        else:
            # 如果 10 次都冲突，抛出异常
            raise BadRequestException("无法生成唯一的测试用例标识符，请重试")

        # 创建测试用例
        tc = await self.repo.create(
            project_id=project.id,
            folder_id=folder_id,
            identifier=identifier,
            name=data.name,
            description=data.description,
            preconditions=data.preconditions,
            priority=data.priority,
            state=data.state,
            test_case_type=data.test_case_type,
            template=data.template,
            feature=data.feature,
            scenario=data.scenario,
            background=data.background,
            automation_status=data.automation_status,
            custom_fields=data.custom_fields,
            issues=data.issues,
            owner_id=owner_id,
            created_by=created_by,
        )

        # 添加测试步骤（仅普通测试用例）
        if data.test_case_steps and data.template != TestCaseTemplate.TEST_CASE_BDD:
            for idx, step in enumerate(data.test_case_steps, 1):
                await self.repo.add_step(
                    tc.id, idx, step.step, step.result
                )

        # 添加标签
        if data.tags:
            for tag_name in data.tags:
                tag = await self.repo.get_or_create_tag(project.id, tag_name)
                await self.repo.add_tag_to_test_case(tc.id, tag)

        # 重新获取完整数据
        tc = await self.repo.get_by_id_with_relations(tc.id)
        return await self._test_case_to_info(tc, project_identifier)

    async def update_test_case(
        self,
        project_identifier: str,
        test_case_identifier: str,
        data: TestCaseUpdate,
    ) -> TestCaseInfo:
        """更新测试用例"""
        project = await self._get_project_by_identifier(project_identifier)

        tc = await self.repo.get_by_identifier(test_case_identifier)
        if not tc or tc.project_id != project.id:
            raise NotFoundException(
                resource_type="测试用例",
                resource_id=test_case_identifier
            )

        # 验证文件夹
        if data.folder_id:
            folder = await self.folder_repo.get_by_id(data.folder_id)
            if not folder or folder.project_id != project.id:
                raise BadRequestException("文件夹不存在或不属于该项目")

        # 更新基本信息
        update_data = data.model_dump(exclude_unset=True, exclude={"steps", "tags"})
        tc = await self.repo.update(tc, **update_data)

        # 更新版本号
        tc.version = (tc.version or 1) + 1

        # 重新获取完整数据
        tc = await self.repo.get_by_id_with_relations(tc.id)
        return await self._test_case_to_info(tc, project_identifier)

    async def delete_test_case(
        self,
        project_identifier: str,
        test_case_identifier: str,
    ) -> str:
        """删除测试用例"""
        project = await self._get_project_by_identifier(project_identifier)

        tc = await self.repo.get_by_identifier(test_case_identifier)
        if not tc or tc.project_id != project.id:
            raise NotFoundException(
                resource_type="测试用例",
                resource_id=test_case_identifier
            )

        await self.repo.delete(tc)
        return f"测试用例 {test_case_identifier} 已成功删除"

    async def bulk_update_test_cases(
        self,
        project_identifier: str,
        test_case_ids: list[str],
        update_data: Optional[dict],
    ) -> int:
        """批量更新测试用例（简单批量更新）"""
        project = await self._get_project_by_identifier(project_identifier)

        if not update_data:
            return 0

        updated_count = 0
        for tc_identifier in test_case_ids:
            tc = await self.repo.get_by_identifier(tc_identifier)
            if tc and tc.project_id == project.id:
                await self.repo.update(tc, **update_data)
                updated_count += 1

        return updated_count

    async def bulk_update_with_operations(
        self,
        project_identifier: str,
        data: BulkEditWithOperationsRequest,
    ) -> int:
        """
        带操作符的批量更新测试用例

        支持 ignore, replace, add, remove 操作
        """
        project = await self._get_project_by_identifier(project_identifier)

        updated_count = 0
        for tc_identifier in data.test_case_ids:
            tc = await self.repo.get_by_identifier(tc_identifier)
            if not tc or tc.project_id != project.id:
                continue

            update_fields = {}

            # 处理单值字段（只支持 ignore, replace）
            single_value_fields = [
                ("automation_status", data.automation_status),
                ("case_type", data.case_type),
                ("priority", data.priority),
                ("state", data.state),
                ("owner", data.owner),
                ("preconditions", data.preconditions),
            ]

            for field_name, field_op in single_value_fields:
                if field_op and field_op.operation == BulkEditOperation.REPLACE:
                    update_fields[field_name] = field_op.value

            # 处理多值字段（支持 ignore, replace, add, remove）
            # 标签
            if data.tags and data.tags.operation != BulkEditOperation.IGNORE:
                await self._apply_list_operation(
                    tc, "tags", data.tags.operation, data.tags.value, project.id
                )

            # Issues
            if data.issues and data.issues.operation != BulkEditOperation.IGNORE:
                current_issues = tc.issues or []
                new_issues = self._apply_list_op(
                    current_issues, data.issues.operation, data.issues.value
                )
                update_fields["issues"] = new_issues

            # 自定义字段
            if data.custom_fields and data.custom_fields.operation != BulkEditOperation.IGNORE:
                current_cf = tc.custom_fields or {}
                if data.custom_fields.operation == BulkEditOperation.REPLACE:
                    update_fields["custom_fields"] = data.custom_fields.value
                elif data.custom_fields.operation == BulkEditOperation.ADD:
                    current_cf.update(data.custom_fields.value or {})
                    update_fields["custom_fields"] = current_cf
                elif data.custom_fields.operation == BulkEditOperation.REMOVE:
                    for key in (data.custom_fields.value or {}).keys():
                        current_cf.pop(key, None)
                    update_fields["custom_fields"] = current_cf

            if update_fields:
                await self.repo.update(tc, **update_fields)

            updated_count += 1

        return updated_count

    def _apply_list_op(
        self,
        current: list,
        operation: BulkEditOperation,
        value: Any
    ) -> list:
        """应用列表操作"""
        if operation == BulkEditOperation.REPLACE:
            return value or []
        elif operation == BulkEditOperation.ADD:
            return list(set(current + (value or [])))
        elif operation == BulkEditOperation.REMOVE:
            return [item for item in current if item not in (value or [])]
        return current

    async def _apply_list_operation(
        self,
        tc: TestCase,
        field: str,
        operation: BulkEditOperation,
        value: Any,
        project_id: UUID,
    ) -> None:
        """应用标签列表操作"""
        if field == "tags":
            if operation == BulkEditOperation.REPLACE:
                # 清除所有标签
                await self.repo.clear_test_case_tags(tc.id)
                # 添加新标签
                for tag_name in (value or []):
                    tag = await self.repo.get_or_create_tag(project_id, tag_name)
                    await self.repo.add_tag_to_test_case(tc.id, tag)
            elif operation == BulkEditOperation.ADD:
                # 获取现有标签
                existing_tags = await self.repo.get_test_case_tags(tc.id)
                existing_tag_names = {t.name for t in existing_tags}
                # 添加新标签
                for tag_name in (value or []):
                    if tag_name not in existing_tag_names:
                        tag = await self.repo.get_or_create_tag(project_id, tag_name)
                        await self.repo.add_tag_to_test_case(tc.id, tag)
            elif operation == BulkEditOperation.REMOVE:
                # 获取要移除的标签
                tags_to_remove = await self.repo.get_test_case_tags(tc.id)
                for tag in tags_to_remove:
                    if tag.name in (value or []):
                        await self.repo.remove_tag_from_test_case(tc.id, tag.id)

    async def bulk_delete_test_cases(
        self,
        project_identifier: str,
        test_case_ids: list[str],
    ) -> int:
        """批量删除测试用例"""
        project = await self._get_project_by_identifier(project_identifier)

        deleted_count = 0
        for tc_identifier in test_case_ids:
            tc = await self.repo.get_by_identifier(tc_identifier)
            if tc and tc.project_id == project.id:
                await self.repo.delete(tc)
                deleted_count += 1

        return deleted_count

    async def get_test_case_history(
        self,
        project_identifier: str,
        test_case_identifier: str,
        page: int = 1,
        page_size: int = 20,
    ) -> TestCaseHistoryResponse:
        """获取测试用例历史记录"""
        project = await self._get_project_by_identifier(project_identifier)

        tc = await self.repo.get_by_identifier(test_case_identifier)
        if not tc or tc.project_id != project.id:
            raise NotFoundException(
                resource_type="测试用例",
                resource_id=test_case_identifier
            )

        # 从 MongoDB 获取历史记录
        if not self.mongodb:
            return TestCaseHistoryResponse(
                success=True,
                info={
                    "page": page,
                    "page_size": page_size,
                    "count": 0,
                    "prev": None,
                    "next": None,
                },
                history=[]
            )

        mongodb_service = MongoDBService(self.mongodb)
        history_data = await mongodb_service.get_version_history(
            str(tc.id), page, page_size
        )

        # 转换为响应模型
        history_items = []
        for item in history_data.get("history", []):
            modified = {}
            for field, changes in item.get("modified", {}).items():
                modified[field] = ModifiedFieldInfo(
                    old=changes.get("old"),
                    new=changes.get("new")
                )

            history_items.append(TestCaseHistoryItem(
                version_id=item.get("version_id", ""),
                version_name=item.get("version_name", ""),
                source=item.get("source", "update"),
                modified_fields=item.get("modified_fields", []),
                modified=modified,
                user_id=item.get("user_id"),
                updated_by=item.get("updated_by"),
                testcase_id=test_case_identifier,
                created_at=item.get("created_at", datetime.utcnow()),
            ))

        return TestCaseHistoryResponse(
            success=True,
            info={
                "page": page,
                "page_size": page_size,
                "count": len(history_items),
                "prev": None if page <= 1 else f"?p={page-1}&page_size={page_size}",
                "next": None,  # 需要根据总数判断
            },
            history=history_items
        )

    async def import_test_cases(
        self,
        project_identifier: str,
        filename: str,
        content: bytes,
        created_by: UUID,
        folder_id: Optional[UUID] = None,
    ) -> dict:
        """从文件批量导入测试用例"""
        from app.schemas.test_case import TestCaseImportError

        project = await self._get_project_by_identifier(project_identifier)

        if folder_id:
            folder = await self.folder_repo.get_by_id(folder_id)
            if not folder or folder.project_id != project.id:
                raise BadRequestException("文件夹不存在或不属于该项目")

        try:
            parsed_cases = parse_import_file(filename, content)
        except ValueError as exc:
            raise BadRequestException(str(exc)) from exc

        if not parsed_cases:
            raise BadRequestException("文件中没有可导入的测试用例")

        imported: list[TestCaseInfo] = []
        errors: list[TestCaseImportError] = []

        for index, data in enumerate(parsed_cases, start=1):
            try:
                test_case = await self.create_test_case(
                    project_identifier,
                    data,
                    created_by,
                    folder_id=folder_id,
                )
                imported.append(test_case)
            except Exception as exc:
                errors.append(
                    TestCaseImportError(
                        row=index,
                        name=data.name,
                        message=str(exc),
                    )
                )

        imported_count = len(imported)
        failed_count = len(errors)

        if imported_count == 0:
            message = f"导入失败，{failed_count} 条记录未能创建"
        elif failed_count == 0:
            message = f"成功导入 {imported_count} 个测试用例"
        else:
            message = f"成功导入 {imported_count} 个测试用例，{failed_count} 条失败"

        return {
            "message": message,
            "imported_count": imported_count,
            "failed_count": failed_count,
            "errors": errors,
            "test_cases": imported,
        }

    async def import_test_cases_from_api_endpoints(
        self,
        project_identifier: str,
        endpoint_ids: list[str],
        created_by: UUID,
        folder_id: Optional[UUID] = None,
    ) -> dict:
        """从 API 测试成果物导入测试用例"""
        import json
        from uuid import UUID as UUIDType
        from sqlalchemy import select
        from app.models.attachment import Attachment, AttachmentEntityType
        from app.models.api_endpoint import APIEndpoint
        from app.config.minio_client import MinIOClient
        from app.schemas.test_case import TestCaseImportError

        project = await self._get_project_by_identifier(project_identifier)

        root_parent_id: Optional[UUID] = None
        if folder_id:
            folder = await self.folder_repo.get_by_id(folder_id)
            if not folder or folder.project_id != project.id:
                raise BadRequestException("文件夹不存在或不属于该项目")
            if folder.folder_type != FolderType.TEST_CASE:
                raise BadRequestException("请选择一个测试用例文件夹作为导入根目录")
            root_parent_id = folder_id

        if not endpoint_ids:
            raise BadRequestException("请至少选择一个 API 端点")

        endpoint_uuids: list[UUIDType] = []
        for endpoint_id in endpoint_ids:
            try:
                endpoint_uuids.append(UUIDType(endpoint_id))
            except ValueError as exc:
                raise BadRequestException(f"无效的端点 ID: {endpoint_id}") from exc

        endpoint_stmt = select(APIEndpoint).where(
            APIEndpoint.id.in_(endpoint_uuids),
            APIEndpoint.project_id == project.id,
        )
        endpoint_result = await self.session.execute(endpoint_stmt)
        endpoints = {str(ep.id): ep for ep in endpoint_result.scalars().all()}

        missing = [eid for eid in endpoint_ids if eid not in endpoints]
        if missing:
            raise BadRequestException(f"以下 API 端点不存在或不属于该项目: {', '.join(missing)}")

        attachment_stmt = select(Attachment).where(
            Attachment.entity_id.in_(endpoint_uuids),
            Attachment.entity_type == AttachmentEntityType.API_TEST_CASE,
        )
        attachment_result = await self.session.execute(attachment_stmt)
        attachments = list(attachment_result.scalars().all())
        attachment_map = {str(item.entity_id): item for item in attachments}

        imported: list[TestCaseInfo] = []
        errors: list[TestCaseImportError] = []
        row_counter = 0

        for endpoint_id in endpoint_ids:
            endpoint = endpoints[endpoint_id]
            attachment = attachment_map.get(endpoint_id)
            if not attachment:
                errors.append(
                    TestCaseImportError(
                        row=0,
                        name=endpoint.display_name,
                        message="该端点尚未生成测试用例成果物",
                    )
                )
                continue

            try:
                content_bytes = MinIOClient.download_file(attachment.object_name)
                raw_data = json.loads(content_bytes.decode("utf-8-sig"))
                raw_items = extract_api_test_cases_list(raw_data)
                if not raw_items:
                    raise ValueError("未找到可导入的测试用例")

                parsed_cases: list[TestCaseCreate] = []
                for index, item in enumerate(raw_items, start=1):
                    try:
                        parsed_cases.append(
                            convert_api_test_case_item(
                                item,
                                endpoint_name=endpoint.display_name,
                                endpoint_method=endpoint.method,
                                endpoint_path=endpoint.path,
                            )
                        )
                    except ValueError as exc:
                        raise ValueError(f"第 {index} 条用例解析失败: {exc}") from exc
            except Exception as exc:
                errors.append(
                    TestCaseImportError(
                        row=0,
                        name=endpoint.display_name,
                        message=f"解析成果物失败: {exc}",
                    )
                )
                continue

            target_folder_id = await self._resolve_api_import_target_folder(
                project.id,
                endpoint,
                root_parent_id,
            )
            status_by_name, endpoint_fallback = await self._get_endpoint_execution_status_map(
                endpoint
            )

            for raw_item, case_data in zip(raw_items, parsed_cases):
                row_counter += 1
                try:
                    test_case = await self.create_test_case(
                        project_identifier,
                        case_data,
                        created_by,
                        folder_id=target_folder_id,
                    )
                    exec_status = self._resolve_case_execution_status(
                        case_data.name,
                        raw_item,
                        status_by_name,
                        endpoint_fallback,
                    )
                    if exec_status:
                        await self._record_test_case_execution_result(
                            project.id,
                            UUID(test_case.id),
                            exec_status,
                        )
                        test_case = await self._refresh_test_case_info(
                            UUID(test_case.id),
                            project_identifier,
                        )
                    imported.append(test_case)
                except Exception as exc:
                    errors.append(
                        TestCaseImportError(
                            row=row_counter,
                            name=case_data.name,
                            message=str(exc),
                        )
                    )

        imported_count = len(imported)
        failed_count = len(errors)

        if imported_count == 0:
            message = f"导入失败，{failed_count} 条记录未能创建"
        elif failed_count == 0:
            message = f"已从 API 测试导入 {imported_count} 个测试用例"
        else:
            message = f"已从 API 测试导入 {imported_count} 个测试用例，{failed_count} 条失败"

        return {
            "message": message,
            "imported_count": imported_count,
            "failed_count": failed_count,
            "errors": errors,
            "test_cases": imported,
        }
