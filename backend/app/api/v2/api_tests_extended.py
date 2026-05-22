"""
API 测试扩展 API

提供基于文件夹的 API 测试查询接口
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import (
    APITestServiceDep,
    PaginationDep,
)
from app.schemas.common import SuccessResponse


router = APIRouter(prefix="/projects/{project_identifier}/folders")


@router.get(
    "/{folder_id}/api-tests",
    response_model=SuccessResponse,
    summary="获取文件夹下的 API 测试列表",
    description="获取指定文件夹下的所有 API 测试列表，支持搜索和分页",
)
async def list_api_tests_by_folder(
    project_identifier: str,
    folder_id: UUID,
    service: APITestServiceDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None, description="搜索关键词（名称、标识符、描述）"),
):
    """
    获取文件夹下的 API 测试列表

    - **project_identifier**: 项目标识符
    - **folder_id**: 文件夹 ID
    - **p**: 页码
    - **page_size**: 每页数量
    - **search**: 搜索关键词（可选）
    """
    result = await service.list_api_tests_by_folder(
        project_identifier=project_identifier,
        folder_id=str(folder_id),
        page=pagination.p,
        page_size=pagination.page_size,
        search=search,
    )

    return SuccessResponse(data=result)
