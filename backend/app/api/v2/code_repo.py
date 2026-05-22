"""
代码仓库分析 API

管理项目关联的 Git 代码仓库，支持设置仓库地址、触发分析、查询状态。
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSessionDep, CurrentUserIdDep
from app.schemas.code_repo import (
    CodeRepoConfig,
    CodeRepoStatusResponse,
    CodeRepoConfigResponse,
)
from app.services.code_repo_service import CodeRepoService


router = APIRouter(prefix="/projects/{project_identifier}/code-repo")


@router.get(
    "/status",
    response_model=CodeRepoStatusResponse,
    summary="获取代码仓库分析状态",
)
async def get_repo_status(
    project_identifier: str,
    db: DbSessionDep,
    _user_id: CurrentUserIdDep,
) -> CodeRepoStatusResponse:
    """查询项目关联的代码仓库配置和分析状态"""
    service = CodeRepoService(db)
    try:
        status_data = await service.get_status(project_identifier)
        return CodeRepoStatusResponse(data=status_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "",
    response_model=CodeRepoConfigResponse,
    summary="配置代码仓库地址或本地路径",
)
async def configure_repo(
    project_identifier: str,
    config: CodeRepoConfig,
    db: DbSessionDep,
    _user_id: CurrentUserIdDep,
) -> CodeRepoConfigResponse:
    """设置项目关联的 Git 仓库地址或本地代码目录路径"""
    service = CodeRepoService(db)
    try:
        info = await service.configure_repo(
            project_identifier,
            repo_url=config.repo_url,
            repo_branch=config.repo_branch,
        )
        return CodeRepoConfigResponse(data=info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/analyze",
    response_model=CodeRepoStatusResponse,
    summary="触发代码分析",
)
async def trigger_analysis(
    project_identifier: str,
    db: DbSessionDep,
    _user_id: CurrentUserIdDep,
) -> CodeRepoStatusResponse:
    """
    分析代码

    - 本地路径：直接执行代码分析
    - Git URL：自动 clone（或 pull 更新）后再分析
    """
    service = CodeRepoService(db)
    try:
        status_data = await service.clone_and_analyze(project_identifier)
        return CodeRepoStatusResponse(data=status_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
