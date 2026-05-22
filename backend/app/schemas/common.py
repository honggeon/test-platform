"""
通用响应模型

定义 API 响应的通用结构
参考: https://www.browserstack.com/docs/test-management/api-reference/status-code
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class BaseResponse(BaseModel):
    """基础响应模型"""
    success: bool = Field(..., description="API 调用是否成功")


class SuccessResponse(BaseResponse, Generic[T]):
    """成功响应模型"""
    success: bool = Field(default=True, description="API 调用成功")
    data: Optional[T] = Field(default=None, description="响应数据")


class MessageResponse(BaseResponse):
    """消息响应模型"""
    success: bool = Field(default=True, description="API 调用成功")
    message: str = Field(..., description="响应消息")


class ErrorDetail(BaseModel):
    """错误详情"""
    field: Optional[str] = Field(default=None, description="错误字段")
    message: str = Field(..., description="错误消息")
    code: Optional[str] = Field(default=None, description="错误代码")


class ErrorResponse(BaseResponse):
    """
    错误响应模型
    
    用于返回 API 错误信息
    """
    success: bool = Field(default=False, description="API 调用失败")
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    details: Optional[list[ErrorDetail]] = Field(
        default=None, 
        description="错误详情列表"
    )


class LinkInfo(BaseModel):
    """
    链接信息
    
    用于 HATEOAS 风格的 API 响应
    """
    self: Optional[str] = Field(default=None, description="当前资源链接")
    project: Optional[str] = Field(default=None, description="所属项目链接")
    folder: Optional[str] = Field(default=None, description="所属文件夹链接")
    parent: Optional[str] = Field(default=None, description="父级资源链接")
    sub_folders: Optional[str] = Field(default=None, description="子文件夹链接")
    test_cases: Optional[str] = Field(default=None, description="测试用例链接")


class TimestampMixin(BaseModel):
    """时间戳混入类"""
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class AuditMixin(TimestampMixin):
    """审计信息混入类"""
    created_by: str = Field(..., description="创建者邮箱")
    updated_by: Optional[str] = Field(default=None, description="更新者邮箱")

