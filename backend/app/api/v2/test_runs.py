"""
测试运行 API 路由

提供测试运行相关的 RESTful API 接口
参考: https://www.browserstack.com/docs/test-management/api-reference/test-runs
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from typing import Optional

from fastapi import APIRouter, Query, status

from app.api.deps import (
    TestRunServiceDep,
    PaginationDep,
    DbSessionDep,
)
from app.schemas.common import SuccessResponse, MessageResponse
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.schemas.test_run import (
    TestRunCreate,
    TestRunUpdate,
    TestRunInfo,
    TestRunListInfo,
    TestRunTestCaseInfo,
    AddTestCasesRequest,
    RemoveTestCasesRequest,
    TestRunAssigneeUpdate,
    CloseTestRunRequest,
)
from app.schemas.enums import TestRunActiveState, TestResultStatus

router = APIRouter(
    prefix="/projects/{project_identifier}/test-runs",
    tags=["测试运行"],
)


@router.get(
    "",
    response_model=PaginatedResponse[TestRunListInfo],
    summary="获取测试运行列表",
    description="获取项目下的所有测试运行",
)
async def list_test_runs(
    project_identifier: str,
    service: TestRunServiceDep,
    pagination: PaginationDep,
    active_state: Optional[TestRunActiveState] = Query(
        default=None,
        description="活跃状态过滤: active, closed"
    ),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
) -> PaginatedResponse[TestRunListInfo]:
    """
    获取测试运行列表
    
    - **active_state**: 活跃状态过滤
    - **search**: 按名称或标识符搜索
    """
    items, total = await service.get_list(
        project_identifier,
        active_state=active_state,
        search=search,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=items,
        pagination=PaginationInfo(
            total=total,
            page=pagination.page,
            page_size=pagination.limit,
        ),
    )


@router.get(
    "/{test_run_identifier}",
    response_model=SuccessResponse[TestRunInfo],
    summary="获取测试运行详情",
    description="根据标识符获取测试运行详情",
)
async def get_test_run(
    project_identifier: str,
    test_run_identifier: str,
    service: TestRunServiceDep,
) -> SuccessResponse[TestRunInfo]:
    """
    获取测试运行详情
    
    - **test_run_identifier**: 测试运行标识符，如 TR-1
    """
    test_run = await service.get_by_identifier(project_identifier, test_run_identifier)
    return SuccessResponse(success=True, data=test_run)


@router.post(
    "",
    response_model=SuccessResponse[TestRunInfo],
    status_code=status.HTTP_201_CREATED,
    summary="创建测试运行",
    description="创建新的测试运行",
)
async def create_test_run(
    project_identifier: str,
    data: TestRunCreate,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestRunInfo]:
    """
    创建测试运行
    
    - **name**: 测试运行名称
    - **test_cases**: 要包含的测试用例标识符列表
    - **configurations**: 配置 ID 列表
    """
    test_run = await service.create(project_identifier, data)
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


@router.patch(
    "/{test_run_identifier}",
    response_model=SuccessResponse[TestRunInfo],
    summary="更新测试运行",
    description="部分更新测试运行信息",
)
async def update_test_run(
    project_identifier: str,
    test_run_identifier: str,
    data: TestRunUpdate,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestRunInfo]:
    """
    更新测试运行 (PATCH)

    只更新提供的字段
    """
    test_run = await service.update(project_identifier, test_run_identifier, data)
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


@router.post(
    "/{test_run_identifier}/delete",
    response_model=MessageResponse,
    summary="删除测试运行",
    description="删除指定的测试运行（符合 BrowserStack API: POST /test-runs/{test_run_id}/delete）",
)
async def delete_test_run(
    project_identifier: str,
    test_run_identifier: str,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> MessageResponse:
    """
    删除测试运行

    - **test_run_identifier**: 测试运行标识符

    注意: 根据 BrowserStack API 规范，删除操作使用 POST 方法而非 DELETE
    """
    await service.delete(project_identifier, test_run_identifier)
    await db.commit()
    return MessageResponse(success=True, message=f"Test Run {test_run_identifier} has been deleted successfully")


@router.post(
    "/{test_run_identifier}/close",
    response_model=SuccessResponse[TestRunInfo],
    summary="关闭测试运行",
    description="关闭测试运行，将 active_state 设置为 closed",
)
async def close_test_run(
    project_identifier: str,
    test_run_identifier: str,
    data: CloseTestRunRequest,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestRunInfo]:
    """
    关闭测试运行

    - **active_state**: closed
    """
    test_run = await service.close_test_run(
        project_identifier, test_run_identifier, data
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


# =============== 测试用例管理接口 ===============

@router.get(
    "/{test_run_identifier}/test-cases",
    response_model=PaginatedResponse[TestRunTestCaseInfo],
    summary="获取测试运行中的测试用例",
    description="获取测试运行中包含的测试用例列表及其状态",
)
async def list_test_run_test_cases(
    project_identifier: str,
    test_run_identifier: str,
    service: TestRunServiceDep,
    pagination: PaginationDep,
    status: Optional[TestResultStatus] = Query(default=None, description="状态过滤"),
    assignee: Optional[str] = Query(default=None, description="负责人过滤"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
) -> PaginatedResponse[TestRunTestCaseInfo]:
    """
    获取测试运行中的测试用例列表

    - **status**: 状态过滤 (untested, passed, failed, etc.)
    - **assignee**: 负责人邮箱过滤
    """
    items, total = await service.get_test_cases(
        project_identifier,
        test_run_identifier,
        status=status,
        assignee=assignee,
        search=search,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=items,
        pagination=PaginationInfo(
            total=total,
            page=pagination.page,
            page_size=pagination.limit,
        ),
    )


@router.post(
    "/{test_run_identifier}/test-cases",
    response_model=SuccessResponse[TestRunInfo],
    summary="添加测试用例到测试运行",
    description="向测试运行中添加测试用例",
)
async def add_test_cases_to_run(
    project_identifier: str,
    test_run_identifier: str,
    data: AddTestCasesRequest,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestRunInfo]:
    """
    添加测试用例到测试运行

    - **test_cases**: 测试用例标识符列表
    - **configuration_ids**: 配置 ID 列表
    - **assignee**: 负责人邮箱
    """
    test_run = await service.add_test_cases(
        project_identifier, test_run_identifier, data
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


@router.delete(
    "/{test_run_identifier}/test-cases",
    response_model=SuccessResponse[TestRunInfo],
    summary="从测试运行移除测试用例",
    description="从测试运行中移除测试用例",
)
async def remove_test_cases_from_run(
    project_identifier: str,
    test_run_identifier: str,
    data: RemoveTestCasesRequest,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestRunInfo]:
    """
    从测试运行移除测试用例

    - **test_cases**: 测试用例标识符列表
    - **configuration_ids**: 配置 ID 列表 (可选)
    """
    test_run = await service.remove_test_cases(
        project_identifier, test_run_identifier, data
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_run)


@router.patch(
    "/{test_run_identifier}/assignees",
    response_model=SuccessResponse[TestRunInfo],
    summary="更新测试用例分配",
    description="批量更新测试运行中测试用例的负责人",
)
async def update_test_case_assignees(
    project_identifier: str,
    test_run_identifier: str,
    data: TestRunAssigneeUpdate,
    service: TestRunServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestRunInfo]:
    """
    更新测试用例分配

    - **assign_to**: 分配列表，包含 test_case_id, configuration_id, assignee
    """
    test_run = await service.update_assignees(
        project_identifier, test_run_identifier, data
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_run)

