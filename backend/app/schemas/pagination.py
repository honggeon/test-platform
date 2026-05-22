"""
分页模型

基于 BrowserStack Test Management API 的分页设计
参考: https://www.browserstack.com/docs/test-management/api-reference/pagination
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

from app.config.settings import settings


T = TypeVar("T")


class PaginationParams(BaseModel):
    """
    分页查询参数

    用于接收分页请求的查询参数
    """
    p: int = Field(
        default=1,
        ge=1,
        description="页码，从 1 开始"
    )
    page_size: int = Field(
        default=settings.default_page_size,
        ge=1,
        le=settings.max_page_size,
        description=f"每页数量，默认 {settings.default_page_size}，最大 {settings.max_page_size}"
    )

    @property
    def page(self) -> int:
        """获取当前页码（别名，兼容 p 属性）"""
        return self.p

    @property
    def offset(self) -> int:
        """计算偏移量"""
        return (self.p - 1) * self.page_size

    @property
    def limit(self) -> int:
        """获取限制数量"""
        return self.page_size


class TestCaseFilterParams(PaginationParams):
    """
    测试用例过滤参数
    
    扩展分页参数，添加测试用例特定的过滤条件
    """
    test_case_id: Optional[str] = Field(
        default=None,
        description="测试用例 ID 过滤"
    )
    updated_after: Optional[datetime] = Field(
        default=None,
        description="更新时间晚于指定时间"
    )
    updated_before: Optional[datetime] = Field(
        default=None,
        description="更新时间早于指定时间"
    )
    issue_ids: Optional[str] = Field(
        default=None,
        description="关联问题 ID 列表，逗号分隔"
    )
    issue_type: Optional[str] = Field(
        default=None,
        description="关联问题类型"
    )


class PaginationInfo(BaseModel):
    """
    分页信息

    包含在分页响应中的分页元数据
    """
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    count: Optional[int] = Field(default=None, description="当前页返回的记录数")
    total: int = Field(..., description="总记录数")
    prev: Optional[str] = Field(default=None, description="上一页链接")
    next: Optional[str] = Field(default=None, description="下一页链接")
    
    @classmethod
    def create(
        cls,
        page: int,
        page_size: int,
        total: int,
        base_url: str,
    ) -> "PaginationInfo":
        """
        创建分页信息
        
        Args:
            page: 当前页码
            page_size: 每页数量
            total: 总记录数
            base_url: 基础 URL
            
        Returns:
            PaginationInfo: 分页信息实例
        """
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        count = min(page_size, max(0, total - (page - 1) * page_size))
        
        prev_url = None
        next_url = None
        
        if page > 1:
            prev_url = f"{base_url}?p={page - 1}&page_size={page_size}"
        
        if page < total_pages:
            next_url = f"{base_url}?p={page + 1}&page_size={page_size}"
        
        return cls(
            page=page,
            page_size=page_size,
            count=count,
            total=total,
            prev=prev_url,
            next=next_url,
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    分页响应模型

    用于返回分页数据的通用响应结构
    支持 info 或 pagination 作为分页信息字段名（兼容不同使用场景）
    """
    success: bool = Field(default=True, description="API 调用成功")
    info: PaginationInfo = Field(default=None, alias="pagination", description="分页信息")
    data: list[T] = Field(default_factory=list, description="数据列表")

    model_config = {"populate_by_name": True}

