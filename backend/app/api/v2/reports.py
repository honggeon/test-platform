"""
报告 API 路由

提供测试报告相关的 API 接口
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import DbSessionDep
from app.schemas.common import SuccessResponse
from app.services.report_service import ReportService

router = APIRouter(
    prefix="/projects/{project_identifier}/reports",
    tags=["测试报告"],
)


@router.get(
    "/dashboard",
    response_model=SuccessResponse,
    summary="获取仪表盘数据",
    description="获取项目的测试仪表盘统计数据，支持按时间范围和执行人筛选",
)
async def get_dashboard(
    project_identifier: str,
    db: DbSessionDep,
    date_range: str = Query(default="all", description="时间范围: 7d, 30d, 90d, all"),
    user_id: Optional[str] = Query(default=None, description="执行人 ID 筛选"),
):
    """获取仪表盘数据"""
    service = ReportService(db)
    data = await service.get_dashboard(
        project_identifier=project_identifier,
        date_range=date_range,
        user_id=user_id,
    )
    return SuccessResponse(data=data)
