"""
测试运行仓储

提供测试运行数据访问层
参考: https://www.browserstack.com/docs/test-management/api-reference/test-runs
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_run import TestRun, TestRunTestCase
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.enums import TestRunState, TestRunActiveState, TestResultStatus


class TestRunRepository:
    """测试运行数据仓储"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, test_run_id: UUID) -> Optional[TestRun]:
        """根据 ID 获取测试运行"""
        stmt = select(TestRun).where(TestRun.id == test_run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_identifier(self, identifier: str) -> Optional[TestRun]:
        """根据标识符获取测试运行"""
        stmt = select(TestRun).where(TestRun.identifier == identifier)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_list(
        self,
        project_id: UUID,
        active_state: Optional[TestRunActiveState] = None,
        run_state: Optional[TestRunState] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[TestRun], int]:
        """获取测试运行列表"""
        stmt = select(TestRun).where(TestRun.project_id == project_id)
        count_stmt = select(func.count()).select_from(TestRun).where(TestRun.project_id == project_id)
        
        # 过滤条件
        if active_state:
            stmt = stmt.where(TestRun.active_state == active_state)
            count_stmt = count_stmt.where(TestRun.active_state == active_state)
        
        if run_state:
            stmt = stmt.where(TestRun.run_state == run_state)
            count_stmt = count_stmt.where(TestRun.run_state == run_state)
        
        if search:
            search_filter = or_(
                TestRun.name.ilike(f"%{search}%"),
                TestRun.identifier.ilike(f"%{search}%"),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)
        
        # 排序和分页
        stmt = stmt.order_by(TestRun.created_at.desc()).offset(offset).limit(limit)
        
        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        
        return list(result.scalars().all()), count_result.scalar() or 0
    
    async def create(self, test_run: TestRun) -> TestRun:
        """创建测试运行"""
        self.session.add(test_run)
        await self.session.flush()
        return test_run
    
    async def update(self, test_run: TestRun) -> TestRun:
        """更新测试运行"""
        await self.session.flush()
        await self.session.refresh(test_run)
        return test_run
    
    async def delete(self, test_run: TestRun) -> None:
        """删除测试运行"""
        await self.session.delete(test_run)
        await self.session.flush()
    
    async def generate_identifier(self, project_id: UUID) -> str:
        """生成测试运行标识符"""
        # 获取当前项目最大编号
        stmt = select(func.count()).select_from(TestRun).where(TestRun.project_id == project_id)
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return f"TR-{count + 1}"
    
    async def update_counts(self, test_run_id: UUID) -> None:
        """更新测试运行的统计数据"""
        # 统计各状态数量
        status_counts = {}
        for status in TestResultStatus:
            stmt = select(func.count()).select_from(TestRunTestCase).where(
                and_(
                    TestRunTestCase.test_run_id == test_run_id,
                    TestRunTestCase.latest_status == status
                )
            )
            result = await self.session.execute(stmt)
            status_counts[status] = result.scalar() or 0

        # 更新测试运行
        total = sum(status_counts.values())
        update_stmt = (
            update(TestRun)
            .where(TestRun.id == test_run_id)
            .values(
                test_cases_count=total,
                passed_count=status_counts.get(TestResultStatus.PASSED, 0),
                failed_count=status_counts.get(TestResultStatus.FAILED, 0),
                skipped_count=status_counts.get(TestResultStatus.SKIPPED, 0),
                blocked_count=status_counts.get(TestResultStatus.BLOCKED, 0),
                not_executed_count=status_counts.get(TestResultStatus.NOT_EXECUTED, 0),
            )
        )
        await self.session.execute(update_stmt)
        await self.session.flush()

    async def get_by_test_plan_id(
        self,
        test_plan_id: UUID,
        offset: int = 0,
        limit: int = 30,
    ) -> list[TestRun]:
        """
        根据测试计划 ID 获取测试运行列表

        Args:
            test_plan_id: 测试计划 ID
            offset: 偏移量
            limit: 限制数量

        Returns:
            list[TestRun]: 测试运行列表
        """
        stmt = (
            select(TestRun)
            .where(TestRun.test_plan_id == test_plan_id)
            .order_by(TestRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_test_plan_id(self, test_plan_id: UUID) -> int:
        """
        获取测试计划下测试运行总数

        Args:
            test_plan_id: 测试计划 ID

        Returns:
            int: 测试运行总数
        """
        stmt = (
            select(func.count())
            .select_from(TestRun)
            .where(TestRun.test_plan_id == test_plan_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0


class TestRunTestCaseRepository:
    """测试运行测试用例仓储"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[TestRunTestCase]:
        """根据 ID 获取关联"""
        stmt = select(TestRunTestCase).where(TestRunTestCase.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_test_run_and_case(
        self,
        test_run_id: UUID,
        test_case_id: UUID,
        configuration_id: Optional[int] = None,
    ) -> Optional[TestRunTestCase]:
        """获取特定测试运行中的测试用例"""
        conditions = [
            TestRunTestCase.test_run_id == test_run_id,
            TestRunTestCase.test_case_id == test_case_id,
        ]
        if configuration_id is not None:
            conditions.append(TestRunTestCase.configuration_id == configuration_id)

        stmt = select(TestRunTestCase).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_list(
        self,
        test_run_id: UUID,
        status: Optional[TestResultStatus] = None,
        assignee: Optional[str] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[TestRunTestCase], int]:
        """获取测试运行中的测试用例列表"""
        stmt = (
            select(TestRunTestCase)
            .options(joinedload(TestRunTestCase.test_case))
            .where(TestRunTestCase.test_run_id == test_run_id)
        )
        count_stmt = (
            select(func.count())
            .select_from(TestRunTestCase)
            .where(TestRunTestCase.test_run_id == test_run_id)
        )

        if status:
            stmt = stmt.where(TestRunTestCase.latest_status == status)
            count_stmt = count_stmt.where(TestRunTestCase.latest_status == status)

        if assignee:
            stmt = stmt.where(TestRunTestCase.assignee == assignee)
            count_stmt = count_stmt.where(TestRunTestCase.assignee == assignee)

        if search:
            stmt = stmt.join(TestCase).where(
                or_(
                    TestCase.name.ilike(f"%{search}%"),
                    TestCase.identifier.ilike(f"%{search}%"),
                )
            )
            count_stmt = count_stmt.join(TestCase).where(
                or_(
                    TestCase.name.ilike(f"%{search}%"),
                    TestCase.identifier.ilike(f"%{search}%"),
                )
            )

        stmt = stmt.order_by(TestRunTestCase.created_at.asc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)

        return list(result.scalars().unique().all()), count_result.scalar() or 0

    async def add_test_cases(
        self,
        test_run_id: UUID,
        test_cases: list[TestRunTestCase],
    ) -> list[TestRunTestCase]:
        """批量添加测试用例到测试运行"""
        for tc in test_cases:
            self.session.add(tc)
        await self.session.flush()
        return test_cases

    async def remove_test_cases(
        self,
        test_run_id: UUID,
        test_case_ids: list[UUID],
        configuration_ids: Optional[list[int]] = None,
    ) -> int:
        """批量移除测试用例"""
        conditions = [
            TestRunTestCase.test_run_id == test_run_id,
            TestRunTestCase.test_case_id.in_(test_case_ids),
        ]
        if configuration_ids:
            conditions.append(TestRunTestCase.configuration_id.in_(configuration_ids))

        stmt = delete(TestRunTestCase).where(and_(*conditions))
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def update_assignees(
        self,
        test_run_id: UUID,
        assignments: list[dict],
    ) -> int:
        """批量更新负责人"""
        count = 0
        for assignment in assignments:
            conditions = [
                TestRunTestCase.test_run_id == test_run_id,
                TestRunTestCase.test_case_id == assignment["test_case_id"],
            ]
            if assignment.get("configuration_id"):
                conditions.append(
                    TestRunTestCase.configuration_id == assignment["configuration_id"]
                )

            stmt = (
                update(TestRunTestCase)
                .where(and_(*conditions))
                .values(assignee=assignment["assignee"])
            )
            result = await self.session.execute(stmt)
            count += result.rowcount

        await self.session.flush()
        return count

    async def update_status(
        self,
        id: UUID,
        status: TestResultStatus,
        result_id: Optional[UUID] = None,
    ) -> TestRunTestCase:
        """更新测试用例状态"""
        stmt = (
            update(TestRunTestCase)
            .where(TestRunTestCase.id == id)
            .values(latest_status=status, latest_result_id=result_id)
            .returning(TestRunTestCase)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()

