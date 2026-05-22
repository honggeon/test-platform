"""
报告服务

提供项目级别的测试报告聚合数据
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_endpoint import APIEndpoint
from app.models.project import Project
from app.models.test_execution_log import TestExecutionLog


def _parse_date_range(range_str: str) -> tuple[datetime, datetime]:
    """解析时间范围字符串为起止时间"""
    now = datetime.now(timezone.utc)
    if range_str == "7d":
        start = now - timedelta(days=7)
    elif range_str == "30d":
        start = now - timedelta(days=30)
    elif range_str == "90d":
        start = now - timedelta(days=90)
    else:
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return start, now


class ReportService:
    """报告服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(
        self,
        project_identifier: str,
        date_range: str = "all",
        user_id: Optional[str] = None,
    ) -> dict:
        """获取项目仪表盘统计"""
        # 查项目
        project_result = await self.db.execute(
            select(Project).where(Project.identifier == project_identifier)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            return {"error": f"项目 {project_identifier} 不存在"}

        project_id = project.id
        start_time, end_time = _parse_date_range(date_range)

        # 构建执行日志查询的基础条件
        log_conditions = [
            TestExecutionLog.project_id == project_id,
            TestExecutionLog.created_at >= start_time,
            TestExecutionLog.created_at <= end_time,
        ]
        if user_id:
            log_conditions.append(TestExecutionLog.user_id == user_id)

        # 1. 端点统计（来自 APIEndpoint 表）
        endpoint_result = await self.db.execute(
            select(
                func.count().label("total"),
                func.sum(case((APIEndpoint.last_run_status == "success", 1), else_=0)).label("passed"),
                func.sum(case((APIEndpoint.last_run_status == "failed", 1), else_=0)).label("failed"),
            ).where(APIEndpoint.project_id == project_id)
        )
        endpoint_row = endpoint_result.one()
        total_endpoints = endpoint_row.total or 0
        endpoints_passed = endpoint_row.passed or 0
        endpoints_failed = endpoint_row.failed or 0

        # 2. 执行日志聚合统计
        log_stats = await self.db.execute(
            select(
                func.count().label("total"),
                func.sum(case((TestExecutionLog.status == "success", 1), else_=0)).label("passed"),
                func.sum(case((TestExecutionLog.status == "failed", 1), else_=0)).label("failed"),
                func.coalesce(func.avg(TestExecutionLog.duration_ms), 0).label("avg_duration"),
            ).where(and_(*log_conditions))
        )
        log_row = log_stats.one()
        total_executions = log_row.total or 0
        executions_passed = log_row.passed or 0
        executions_failed = log_row.failed or 0
        avg_duration_ms = round(log_row.avg_duration or 0, 1)

        # 3. 执行人列表（用于前端筛选）
        users_result = await self.db.execute(
            select(TestExecutionLog.user_id)
            .where(TestExecutionLog.project_id == project_id)
            .distinct()
            .order_by(TestExecutionLog.user_id)
        )
        user_list = [row[0] for row in users_result.all()]

        # 4. 最近执行记录
        recent_result = await self.db.execute(
            select(
                TestExecutionLog.status,
                TestExecutionLog.script_name,
                TestExecutionLog.user_id,
                TestExecutionLog.duration_ms,
                TestExecutionLog.endpoint_id,
                TestExecutionLog.created_at,
            )
            .where(TestExecutionLog.project_id == project_id)
            .order_by(TestExecutionLog.created_at.desc())
            .limit(20)
        )
        recent_executions = [
            {
                "status": row.status,
                "script_name": row.script_name,
                "user_id": row.user_id,
                "duration_ms": row.duration_ms,
                "endpoint_id": str(row.endpoint_id) if row.endpoint_id else None,
                "executed_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent_result.all()
        ]

        # 5. 通过率
        if total_executions > 0:
            pass_rate = round(executions_passed / total_executions * 100, 1)
        elif endpoints_passed + endpoints_failed > 0:
            tested = endpoints_passed + endpoints_failed
            pass_rate = round(endpoints_passed / tested * 100, 1)
        else:
            pass_rate = 0

        return {
            "summary": {
                "total_endpoints": total_endpoints,
                "endpoints_passed": endpoints_passed,
                "endpoints_failed": endpoints_failed,
                "total_executions": total_executions,
                "executions_passed": executions_passed,
                "executions_failed": executions_failed,
                "avg_duration_ms": avg_duration_ms,
                "pass_rate": pass_rate,
            },
            "users": user_list,
            "recent_executions": recent_executions,
        }
