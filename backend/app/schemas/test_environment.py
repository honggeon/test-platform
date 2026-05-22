"""
测试环境相关的 Pydantic 模型

项目的测试环境配置，用于 AI 生成测试脚本时确定目标地址
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TestEnvironmentCreate(BaseModel):
    """创建测试环境请求模型"""
    name: str = Field(
        ..., min_length=1, max_length=100,
        description="环境名称，如 '开发环境'"
    )
    base_url: str = Field(
        ..., min_length=1, max_length=500,
        description="环境基础 URL，如 'http://dev-api.example.com'"
    )
    description: Optional[str] = Field(
        default=None, description="环境描述"
    )
    sort_order: int = Field(
        default=0, description="排序顺序（升序）"
    )
    is_default: bool = Field(
        default=False, description="是否设为默认环境"
    )


class TestEnvironmentUpdate(BaseModel):
    """更新测试环境请求模型"""
    name: Optional[str] = Field(
        default=None, min_length=1, max_length=100,
        description="环境名称"
    )
    base_url: Optional[str] = Field(
        default=None, min_length=1, max_length=500,
        description="环境基础 URL"
    )
    description: Optional[str] = Field(
        default=None, description="环境描述"
    )
    sort_order: Optional[int] = Field(
        default=None, description="排序顺序（升序）"
    )
    is_default: Optional[bool] = Field(
        default=None, description="是否设为默认环境"
    )


class TestEnvironmentInfo(BaseModel):
    """测试环境信息响应模型"""
    id: str = Field(..., description="环境 ID")
    project_id: str = Field(..., description="项目 ID")
    name: str = Field(..., description="环境名称")
    base_url: str = Field(..., description="环境基础 URL")
    description: Optional[str] = Field(default=None, description="环境描述")
    sort_order: int = Field(default=0, description="排序顺序")
    is_default: bool = Field(default=False, description="是否默认环境")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    updated_at: Optional[str] = Field(default=None, description="更新时间")

    model_config = {"from_attributes": True}
