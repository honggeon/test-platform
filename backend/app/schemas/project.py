"""
项目相关的 Pydantic 模型

基于 BrowserStack Test Management API 的项目接口设计
参考: https://www.browserstack.com/docs/test-management/api-reference/projects
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import BaseResponse, LinkInfo


class ProjectBase(BaseModel):
    """项目基础模型"""
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=255,
        description="项目名称"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="项目描述，简要说明项目的目的"
    )


class ProjectCreate(ProjectBase):
    """
    创建项目请求模型
    
    用于创建新项目的请求体
    """
    team_id: Optional[list[int]] = Field(
        default=None,
        description="关联的团队 ID 列表"
    )


class ProjectUpdate(BaseModel):
    """
    更新项目请求模型
    
    用于更新项目信息的请求体
    """
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="项目名称"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="项目描述"
    )
    team_id: Optional[list[int]] = Field(
        default=None,
        description="关联的团队 ID 列表"
    )


class ProjectInfo(ProjectBase):
    """
    项目信息模型
    
    用于返回项目详细信息
    """
    identifier: str = Field(
        ...,
        description="项目唯一标识符，如 PR-1234"
    )
    created_at: datetime = Field(
        ...,
        description="项目创建时间"
    )
    created_by: str = Field(
        ...,
        description="项目创建者邮箱"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="项目最后更新时间"
    )
    team_id: Optional[list[int]] = Field(
        default=None,
        description="关联的团队 ID 列表"
    )
    test_cases_count: int = Field(
        default=0,
        description="项目中的测试用例数量"
    )
    folders_count: int = Field(
        default=0,
        description="项目中的文件夹数量"
    )
    links: Optional[LinkInfo] = Field(
        default=None,
        description="相关资源链接"
    )

    # 全栈分析关联的代码仓库
    code_repo_url: Optional[str] = Field(
        default=None, description="关联的 Git 仓库地址"
    )
    code_repo_path: Optional[str] = Field(
        default=None, description="代码仓库本地路径"
    )
    code_repo_branch: Optional[str] = Field(
        default=None, description="分析分支"
    )

    class Config:
        from_attributes = True


class ProjectResponse(BaseResponse):
    """
    单个项目响应模型
    
    用于返回单个项目的 API 响应
    """
    success: bool = Field(default=True, description="API 调用成功")
    project: ProjectInfo = Field(..., description="项目信息")


class ProjectListResponse(BaseResponse):
    """
    项目列表响应模型
    
    用于返回项目列表的 API 响应
    """
    success: bool = Field(default=True, description="API 调用成功")
    projects: list[ProjectInfo] = Field(
        default_factory=list,
        description="项目列表"
    )


class ProjectDeleteResponse(BaseResponse):
    """
    删除项目响应模型
    
    用于返回删除项目操作的结果
    """
    success: bool = Field(default=True, description="API 调用成功")
    message: str = Field(..., description="删除结果消息")

