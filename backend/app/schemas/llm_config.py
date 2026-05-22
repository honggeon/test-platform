"""
LLM 配置相关的 Pydantic 模型
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


class LLMConfigBase(BaseModel):
    """LLM 配置基础模型"""
    provider: str = Field(..., max_length=50, description="LLM 提供商")
    model_name: str = Field(..., max_length=100, description="模型名称")
    api_key: Optional[str] = Field(default=None, max_length=500, description="API Key")
    base_url: Optional[str] = Field(default=None, max_length=500, description="自定义 Base URL")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="最大 Token 数")


class LLMConfigCreate(LLMConfigBase):
    """创建 LLM 配置请求模型"""
    project_id: Optional[UUID] = Field(default=None, description="关联的项目 ID")


class LLMConfigUpdate(BaseModel):
    """更新 LLM 配置请求模型"""
    provider: Optional[str] = Field(default=None, max_length=50, description="LLM 提供商")
    model_name: Optional[str] = Field(default=None, max_length=100, description="模型名称")
    api_key: Optional[str] = Field(default=None, max_length=500, description="API Key")
    base_url: Optional[str] = Field(default=None, max_length=500, description="自定义 Base URL")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="最大 Token 数")


class LLMConfigInfo(BaseModel):
    """LLM 配置信息响应模型"""
    id: UUID = Field(..., description="配置 ID")
    project_id: UUID = Field(..., description="关联的项目 ID")
    provider: str = Field(..., description="LLM 提供商")
    model_name: str = Field(..., description="模型名称")
    base_url: Optional[str] = Field(default=None, description="自定义 Base URL")
    temperature: Optional[float] = Field(default=None, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, description="最大 Token 数")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class LLMConfigDetailInfo(LLMConfigInfo):
    """LLM 配置详细信息（包含 API Key）"""
    api_key: Optional[str] = Field(default=None, description="API Key")
