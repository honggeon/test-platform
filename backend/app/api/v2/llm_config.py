"""
LLM 配置管理 API

提供 LLM Provider 配置的获取和保存操作
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.llm_config import LLMConfigCreate, LLMConfigInfo, LLMConfigDetailInfo
from app.schemas.common import SuccessResponse
from app.services.llm_config_service import LLMConfigService


router = APIRouter(prefix="/llm-configs", tags=["LLM 配置管理"])


def get_llm_config_service(session: AsyncSession = Depends(get_db)) -> LLMConfigService:
    """获取 LLM 配置服务"""
    return LLMConfigService(session)


LLMConfigServiceDep = Annotated[LLMConfigService, Depends(get_llm_config_service)]


@router.get(
    "/{project_identifier}",
    response_model=SuccessResponse[LLMConfigDetailInfo],
    summary="获取项目 LLM 配置",
    description="""
根据项目标识符获取 LLM 配置详情。

返回配置的所有属性，包括 API Key。
""",
)
async def get_llm_config(
    project_identifier: str,
    service: LLMConfigServiceDep,
) -> SuccessResponse[LLMConfigDetailInfo]:
    """获取项目 LLM 配置"""
    config = await service.get_by_project_identifier(project_identifier)
    return SuccessResponse(success=True, data=config)


@router.post(
    "/{project_identifier}",
    response_model=SuccessResponse[LLMConfigInfo],
    summary="保存项目 LLM 配置",
    description="""
创建或更新项目的 LLM 配置。

如果项目已有配置则更新，否则创建新配置。
""",
)
async def save_llm_config(
    project_identifier: str,
    data: LLMConfigCreate,
    service: LLMConfigServiceDep,
) -> SuccessResponse[LLMConfigInfo]:
    """保存项目 LLM 配置"""
    config = await service.create_or_update_by_identifier(project_identifier, data)
    return SuccessResponse(success=True, data=config)
