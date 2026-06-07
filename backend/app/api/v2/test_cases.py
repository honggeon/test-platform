"""
测试用例管理 API

提供测试用例的 CRUD 操作接口
参考: https://www.browserstack.com/docs/test-management/api-reference/test-cases
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Optional, Union, Any
from uuid import UUID

from fastapi import APIRouter, Query, status, Request, Response, Body, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TestCaseServiceDep,
    PaginationDep,
    CurrentUserIdDep,
    DbSessionDep,
    ExportServiceDep,
)
from app.schemas.test_case import (
    TestCaseCreate, TestCaseUpdate, TestCaseInfo, TestCaseMinifiedInfo,
    BulkTestCaseRequest, BulkEditWithOperationsRequest, BulkDeleteRequest,
    BulkOperationResponse, ExportBDDRequest, ExportBDDResponse,
    ExportStatusResponse,     TestCaseHistoryResponse, TestCaseImportResponse,
    ImportTestCasesFromApiRequest, LatestTestResultUpdate,
)
from app.utils.test_case_import import build_csv_template
from app.schemas.common import SuccessResponse, MessageResponse
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.schemas.enums import Priority, TestCaseState, TestCaseType
from app.config.settings import settings


router = APIRouter(prefix="/projects/{project_identifier}")


# ============ 测试用例列表和查询接口 ============

@router.get(
    "/test-cases",
    response_model=PaginatedResponse[Union[TestCaseInfo, TestCaseMinifiedInfo]],
    summary="获取测试用例列表",
    description="获取项目下的所有测试用例列表，支持过滤和分页",
)
async def get_test_cases(
    project_identifier: str,
    request: Request,
    service: TestCaseServiceDep,
    pagination: PaginationDep,
    # 精简模式
    minify: bool = Query(False, description="是否返回精简数据"),
    # 根据 ID 过滤
    id: Optional[str] = Query(None, description="测试用例标识符列表，逗号分隔，如 TC-1234,TC-1235"),
    # 属性过滤
    folder_id: Optional[str] = Query(None, description="文件夹 ID 列表，逗号分隔"),
    status: Optional[str] = Query(None, description="状态列表，逗号分隔，如 active,draft"),
    priority: Optional[str] = Query(None, description="优先级列表，逗号分隔，如 high,medium"),
    case_type: Optional[str] = Query(None, description="测试类型列表，逗号分隔，如 functional,regression"),
    owner: Optional[str] = Query(None, description="负责人邮箱列表，逗号分隔"),
    tags: Optional[str] = Query(None, description="标签列表，逗号分隔"),
    # 时间过滤
    updated_after: Optional[datetime] = Query(None, description="更新时间晚于"),
    updated_before: Optional[datetime] = Query(None, description="更新时间早于"),
    # Jira 集成
    issue_ids: Optional[str] = Query(None, description="关联的 Jira issue ID 列表，逗号分隔"),
    issue_type: Optional[str] = Query(None, description="issue 类型，如 jira"),
):
    """
    获取测试用例列表

    支持多种过滤条件：
    - **minify**: 是否返回精简数据（仅包含基本字段）
    - **id**: 根据测试用例标识符过滤
    - **folder_id**: 根据文件夹过滤
    - **status**: 根据状态过滤
    - **priority**: 根据优先级过滤
    - **case_type**: 根据测试类型过滤
    - **owner**: 根据负责人过滤
    - **tags**: 根据标签过滤
    - **issue_ids**: 根据关联的 Jira issue 过滤

    多个值用逗号分隔，同一参数内的多个值为 OR 关系，不同参数之间为 AND 关系

    自定义字段过滤：使用 custom_fields[字段名]=值1,值2 格式
    """
    # 解析自定义字段过滤
    custom_fields = {}
    for key, value in request.query_params.items():
        if key.startswith("custom_fields[") and key.endswith("]"):
            field_name = key[14:-1]  # 提取字段名
            custom_fields[field_name] = value.split(",") if value else []

    # 构建过滤参数
    filters = {
        "test_case_ids": id.split(",") if id else None,
        "folder_ids": folder_id.split(",") if folder_id else None,
        "statuses": status.split(",") if status else None,
        "priorities": priority.split(",") if priority else None,
        "case_types": case_type.split(",") if case_type else None,
        "owners": owner.split(",") if owner else None,
        "tags": tags.split(",") if tags else None,
        "issue_ids": issue_ids.split(",") if issue_ids else None,
        "issue_type": issue_type,
        "custom_fields": custom_fields if custom_fields else None,
        "updated_after": updated_after,
        "updated_before": updated_before,
    }

    offset = (pagination.page - 1) * pagination.page_size
    test_cases, total = await service.get_test_cases(
        project_identifier,
        offset,
        pagination.page_size,
        minify=minify,
        **filters
    )

    total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1
    base_url = f"{settings.api_prefix}/projects/{project_identifier}/test-cases"

    prev_url = None
    if pagination.page > 1:
        prev_url = f"{base_url}?p={pagination.page - 1}&page_size={pagination.page_size}"

    next_url = None
    if pagination.page < total_pages:
        next_url = f"{base_url}?p={pagination.page + 1}&page_size={pagination.page_size}"

    return PaginatedResponse(
        success=True,
        data=test_cases,
        info=PaginationInfo(
            page=pagination.page,
            page_size=pagination.page_size,
            count=len(test_cases),
            total=total,
            prev=prev_url,
            next=next_url,
        ),
    )


# ============ 测试用例详情接口 ============

@router.get(
    "/folders/{folder_id}/test-cases",
    response_model=PaginatedResponse[Union[TestCaseInfo, TestCaseMinifiedInfo]],
    summary="获取文件夹下的测试用例列表",
    description="获取指定文件夹下的所有测试用例列表，支持过滤和分页",
)
async def get_folder_test_cases(
    project_identifier: str,
    folder_id: str,
    service: TestCaseServiceDep,
    pagination: PaginationDep,
    # 精简模式
    minify: bool = Query(False, description="是否返回精简数据"),
    # 属性过滤
    status: Optional[str] = Query(None, description="状态列表，逗号分隔，如 active,draft"),
    priority: Optional[str] = Query(None, description="优先级列表，逗号分隔，如 high,medium"),
    case_type: Optional[str] = Query(None, description="测试类型列表，逗号分隔，如 functional,regression"),
    owner: Optional[str] = Query(None, description="负责人邮箱列表，逗号分隔"),
    tags: Optional[str] = Query(None, description="标签列表，逗号分隔"),
):
    """获取文件夹下的测试用例列表"""
    filters = {
        "folder_ids": [folder_id],
        "statuses": status.split(",") if status else None,
        "priorities": priority.split(",") if priority else None,
        "case_types": case_type.split(",") if case_type else None,
        "owners": owner.split(",") if owner else None,
        "tags": tags.split(",") if tags else None,
    }

    offset = (pagination.page - 1) * pagination.page_size
    test_cases, total = await service.get_test_cases(
        project_identifier,
        offset,
        pagination.page_size,
        minify=minify,
        **filters
    )

    total_pages = (total + pagination.page_size - 1) // pagination.page_size if total > 0 else 1
    base_url = f"{settings.api_prefix}/projects/{project_identifier}/folders/{folder_id}/test-cases"

    prev_url = None
    if pagination.page > 1:
        prev_url = f"{base_url}?p={pagination.page - 1}&page_size={pagination.page_size}"

    next_url = None
    if pagination.page < total_pages:
        next_url = f"{base_url}?p={pagination.page + 1}&page_size={pagination.page_size}"

    return PaginatedResponse(
        success=True,
        data=test_cases,
        info=PaginationInfo(
            page=pagination.page,
            page_size=pagination.page_size,
            count=len(test_cases),
            total=total,
            prev=prev_url,
            next=next_url,
        ),
    )


@router.get(
    "/test-cases/import-template",
    summary="下载测试用例导入模板",
    description="下载 CSV 格式的测试用例导入模板",
)
async def download_test_case_import_template() -> Response:
    """下载 CSV 导入模板"""
    content = build_csv_template()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="test-cases-import-template.csv"'
        },
    )


# ============ 创建 / 导入测试用例接口（静态路径，必须在 {test_case_identifier} 之前） ============

@router.post(
    "/test-cases",
    response_model=SuccessResponse[TestCaseInfo],
    status_code=status.HTTP_201_CREATED,
    summary="创建测试用例",
    description="在项目根目录下创建新的测试用例（不指定文件夹）",
)
async def create_test_case(
    project_identifier: str,
    data: TestCaseCreate,
    service: TestCaseServiceDep,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> SuccessResponse[TestCaseInfo]:
    """在项目根目录创建测试用例（不关联文件夹）"""
    test_case = await service.create_test_case(
        project_identifier, data, current_user_id, folder_id=None
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


@router.post(
    "/test-cases/import",
    response_model=TestCaseImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="导入测试用例",
    description="从 CSV、Excel (.xlsx) 或 JSON 文件批量导入测试用例",
)
async def import_test_cases(
    project_identifier: str,
    service: TestCaseServiceDep,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    file: UploadFile = File(..., description="CSV / Excel / JSON 文件"),
    folder_id: Optional[UUID] = Form(default=None, description="目标文件夹 ID"),
) -> TestCaseImportResponse:
    """批量导入测试用例"""
    content = await file.read()
    if not content:
        from app.utils.exceptions import BadRequestException
        raise BadRequestException("上传文件为空")

    result = await service.import_test_cases(
        project_identifier,
        file.filename or "import.csv",
        content,
        current_user_id,
        folder_id=folder_id,
    )
    await db.commit()
    return TestCaseImportResponse(
        success=result["imported_count"] > 0,
        message=result["message"],
        imported_count=result["imported_count"],
        failed_count=result["failed_count"],
        errors=result["errors"],
        test_cases=result["test_cases"],
    )


@router.post(
    "/test-cases/import-from-api",
    response_model=TestCaseImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="从 API 测试导入测试用例",
    description="将 API 测试中 AI 生成的测试用例成果物导入到测试用例库",
)
async def import_test_cases_from_api(
    project_identifier: str,
    data: ImportTestCasesFromApiRequest,
    service: TestCaseServiceDep,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> TestCaseImportResponse:
    """从 API 测试成果物导入测试用例"""
    result = await service.import_test_cases_from_api_endpoints(
        project_identifier,
        data.endpoint_ids,
        current_user_id,
        folder_id=data.folder_id,
    )
    await db.commit()
    return TestCaseImportResponse(
        success=result["imported_count"] > 0,
        message=result["message"],
        imported_count=result["imported_count"],
        failed_count=result["failed_count"],
        errors=result["errors"],
        test_cases=result["test_cases"],
    )


@router.post(
    "/test-cases/export-bdd",
    response_model=ExportBDDResponse,
    summary="导出 BDD 测试用例",
    description="启动 BDD 测试用例导出任务，生成 .feature 文件",
)
async def export_bdd_test_cases(
    project_identifier: str,
    data: ExportBDDRequest,
    service: TestCaseServiceDep,
    export_service: ExportServiceDep,
) -> ExportBDDResponse:
    """导出 BDD 测试用例"""
    export_result = await export_service.start_bdd_export(
        project_identifier, data
    )
    return export_result


@router.patch(
    "/test-cases/with-operations",
    response_model=BulkOperationResponse,
    summary="带操作符的批量更新",
    description="使用操作符（ignore, replace, add, remove）批量更新测试用例",
)
async def bulk_update_with_operations(
    project_identifier: str,
    data: BulkEditWithOperationsRequest,
    service: TestCaseServiceDep,
    db: DbSessionDep,
) -> BulkOperationResponse:
    """带操作符的批量更新测试用例"""
    affected_count = await service.bulk_update_with_operations(
        project_identifier, data
    )
    await db.commit()
    return BulkOperationResponse(
        success=True,
        message=f"成功更新 {affected_count} 个测试用例",
        affected_count=affected_count
    )


@router.get(
    "/test-cases/{test_case_identifier}",
    response_model=SuccessResponse[TestCaseInfo],
    summary="获取测试用例详情",
    description="获取指定测试用例的详细信息",
)
async def get_test_case(
    project_identifier: str,
    test_case_identifier: str,
    service: TestCaseServiceDep,
) -> SuccessResponse[TestCaseInfo]:
    """获取测试用例详情"""
    test_case = await service.get_test_case(project_identifier, test_case_identifier)
    return SuccessResponse(success=True, data=test_case)


@router.post(
    "/folders/{folder_id}/test-cases",
    response_model=SuccessResponse[TestCaseInfo],
    status_code=status.HTTP_201_CREATED,
    summary="在文件夹中创建测试用例",
    description="在指定文件夹下创建新的测试用例（支持普通测试用例和 BDD 测试用例）",
)
async def create_test_case_in_folder(
    project_identifier: str,
    folder_id: UUID,
    data: TestCaseCreate,
    service: TestCaseServiceDep,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> SuccessResponse[TestCaseInfo]:
    """
    在文件夹中创建测试用例

    支持两种模板类型：
    - **test_case**: 普通测试用例，需要提供 test_case_steps
    - **test_case_bdd**: BDD 测试用例，需要提供 feature 和 scenario

    请求体字段：
    - **name**: 测试用例名称（必填）
    - **template**: 模板类型（可选，默认 test_case）
    - **description**: 描述（可选，支持 HTML）
    - **preconditions**: 前置条件（可选，支持 HTML）
    - **priority**: 优先级（可选）
    - **status**: 状态（可选）
    - **case_type**: 测试类型（可选）
    - **owner**: 负责人邮箱（可选）
    - **tags**: 标签列表（可选）
    - **issues**: 关联的 Jira issues（可选）
    - **custom_fields**: 自定义字段（可选）
    - **test_case_steps**: 测试步骤列表（普通测试用例）
    - **feature**: BDD Feature 描述（BDD 测试用例必填）
    - **scenario**: BDD Scenario 描述（BDD 测试用例必填）
    - **background**: BDD Background 描述（BDD 测试用例可选）
    """
    test_case = await service.create_test_case(
        project_identifier, data, current_user_id, folder_id
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


# ============ 更新测试用例接口 ============

@router.patch(
    "/test-cases/{test_case_identifier}/latest-test-result",
    response_model=SuccessResponse[TestCaseInfo],
    summary="更新最近测试结果",
    description="设置或清除测试用例最近一次测试结果",
)
async def update_latest_test_result(
    project_identifier: str,
    test_case_identifier: str,
    data: LatestTestResultUpdate,
    service: TestCaseServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestCaseInfo]:
    """更新测试用例最近一次测试结果"""
    test_case = await service.set_latest_test_result_status(
        project_identifier,
        test_case_identifier,
        data.status,
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


@router.patch(
    "/test-cases/{test_case_identifier}",
    response_model=SuccessResponse[TestCaseInfo],
    summary="更新测试用例",
    description="更新指定测试用例的信息",
)
async def update_test_case(
    project_identifier: str,
    test_case_identifier: str,
    data: TestCaseUpdate,
    service: TestCaseServiceDep,
    db: DbSessionDep,
) -> SuccessResponse[TestCaseInfo]:
    """更新测试用例"""
    test_case = await service.update_test_case(
        project_identifier, test_case_identifier, data
    )
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


# ============ 删除测试用例接口 ============

@router.delete(
    "/test-cases/{test_case_identifier}",
    response_model=MessageResponse,
    summary="删除测试用例",
    description="删除指定的测试用例",
)
async def delete_test_case(
    project_identifier: str,
    test_case_identifier: str,
    service: TestCaseServiceDep,
    db: DbSessionDep,
) -> MessageResponse:
    """删除测试用例"""
    message = await service.delete_test_case(project_identifier, test_case_identifier)
    await db.commit()
    return MessageResponse(success=True, message=message)


# ============ 批量操作接口 ============

@router.patch(
    "/test-cases",
    response_model=BulkOperationResponse,
    summary="批量更新测试用例",
    description="批量更新多个测试用例的信息",
)
async def bulk_update_test_cases(
    project_identifier: str,
    data: BulkTestCaseRequest,
    service: TestCaseServiceDep,
    db: DbSessionDep,
) -> BulkOperationResponse:
    """
    批量更新测试用例

    - **test_case_ids**: 要更新的测试用例标识符列表
    - **update_data**: 要更新的字段
    """
    affected_count = await service.bulk_update_test_cases(
        project_identifier,
        data.test_case_ids,
        data.update_data,
    )
    await db.commit()
    return BulkOperationResponse(
        success=True,
        message=f"成功更新 {affected_count} 个测试用例",
        affected_count=affected_count
    )


@router.delete(
    "/test-cases",
    response_model=BulkOperationResponse,
    summary="批量删除测试用例",
    description="批量删除多个测试用例",
)
async def bulk_delete_test_cases(
    project_identifier: str,
    service: TestCaseServiceDep,
    db: DbSessionDep,
    data: BulkDeleteRequest = Body(...),
) -> BulkOperationResponse:
    """
    批量删除测试用例

    - **test_case_ids**: 要删除的测试用例标识符列表
    """
    affected_count = await service.bulk_delete_test_cases(
        project_identifier,
        data.test_case_ids,
    )
    await db.commit()
    return BulkOperationResponse(
        success=True,
        message=f"成功删除 {affected_count} 个测试用例",
        affected_count=affected_count
    )


# ============ 测试用例历史接口 ============

@router.get(
    "/test-cases/{test_case_identifier}/history",
    response_model=TestCaseHistoryResponse,
    summary="获取测试用例历史",
    description="获取测试用例的变更历史记录",
)
async def get_test_case_history(
    project_identifier: str,
    test_case_identifier: str,
    service: TestCaseServiceDep,
    pagination: PaginationDep,
) -> TestCaseHistoryResponse:
    """
    获取测试用例历史

    返回测试用例的所有变更记录，包括：
    - 修改的字段
    - 修改前后的值
    - 修改时间
    - 修改人
    """
    history_data = await service.get_test_case_history(
        project_identifier,
        test_case_identifier,
        pagination.page,
        pagination.page_size
    )
    return history_data


# ============ 导出状态和下载接口（独立路由器） ============

exports_router = APIRouter(prefix="/exports")


@exports_router.get(
    "/{export_id}/status",
    response_model=ExportStatusResponse,
    summary="获取导出状态",
    description="获取 BDD 测试用例导出任务的状态",
)
async def get_export_status(
    export_id: str,
    export_service: ExportServiceDep,
) -> ExportStatusResponse:
    """
    获取导出状态

    返回导出任务的当前状态和下载 URL（如果已完成）
    """
    return await export_service.get_export_status(export_id)


@exports_router.get(
    "/{export_id}/download",
    summary="下载导出文件",
    description="下载已完成的 BDD 测试用例导出文件",
)
async def download_export(
    export_id: str,
    export_service: ExportServiceDep,
) -> StreamingResponse:
    """
    下载导出文件

    返回 .feature 文件或 .zip 压缩包
    """
    file_content, filename, content_type = await export_service.download_export(export_id)
    return StreamingResponse(
        iter([file_content]),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
