"""
测试环境 API 路由

提供测试环境管理的 RESTful API 接口
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

from typing import Optional

from fastapi import APIRouter

from app.api.deps import DbSessionDep
from app.schemas.common import SuccessResponse
from app.schemas.test_environment import (
    TestEnvironmentCreate,
    TestEnvironmentUpdate,
    TestEnvironmentInfo,
)
from app.services.test_environment_service import TestEnvironmentService

router = APIRouter(
    prefix="/projects/{project_identifier}/environments",
    tags=["测试环境"],
)


@router.get(
    "",
    response_model=SuccessResponse,
    summary="获取测试环境列表",
    description="获取项目下的所有测试环境",
)
async def list_environments(
    project_identifier: str,
    db: DbSessionDep,
):
    """获取项目下的所有测试环境"""
    service = TestEnvironmentService(db)
    environments = await service.list_environments(project_identifier)
    return SuccessResponse(data=environments)


@router.get(
    "/default",
    response_model=SuccessResponse,
    summary="获取默认测试环境",
    description="获取项目的默认测试环境",
)
async def get_default_environment(
    project_identifier: str,
    db: DbSessionDep,
):
    """获取项目的默认测试环境"""
    service = TestEnvironmentService(db)
    env = await service.get_default_environment(project_identifier)
    return SuccessResponse(data=env)


@router.get(
    "/{environment_id}",
    response_model=SuccessResponse,
    summary="获取测试环境详情",
    description="获取指定测试环境的详细信息",
)
async def get_environment(
    project_identifier: str,
    environment_id: str,
    db: DbSessionDep,
):
    """获取测试环境详情"""
    service = TestEnvironmentService(db)
    env = await service.get_environment(project_identifier, environment_id)
    return SuccessResponse(data=env)


@router.post(
    "",
    response_model=SuccessResponse,
    summary="创建测试环境",
    description="创建新的测试环境",
    status_code=201,
)
async def create_environment(
    project_identifier: str,
    data: TestEnvironmentCreate,
    db: DbSessionDep,
):
    """创建测试环境"""
    service = TestEnvironmentService(db)
    env = await service.create_environment(project_identifier, data)
    return SuccessResponse(data=env, message="测试环境创建成功")


@router.patch(
    "/{environment_id}",
    response_model=SuccessResponse,
    summary="更新测试环境",
    description="更新指定的测试环境",
)
async def update_environment(
    project_identifier: str,
    environment_id: str,
    data: TestEnvironmentUpdate,
    db: DbSessionDep,
):
    """更新测试环境"""
    service = TestEnvironmentService(db)
    env = await service.update_environment(project_identifier, environment_id, data)
    return SuccessResponse(data=env, message="测试环境更新成功")


@router.delete(
    "/{environment_id}",
    response_model=SuccessResponse,
    summary="删除测试环境",
    description="删除指定的测试环境",
)
async def delete_environment(
    project_identifier: str,
    environment_id: str,
    db: DbSessionDep,
):
    """删除测试环境"""
    service = TestEnvironmentService(db)
    await service.delete_environment(project_identifier, environment_id)
    return SuccessResponse(message="测试环境删除成功")
