"""
代码仓库配置相关的 Pydantic 模型

用于全栈分析功能，管理项目关联的 Git 代码仓库
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import BaseResponse


class CodeRepoConfig(BaseModel):
    """
    代码仓库配置
    项目关联的 Git 仓库地址和分支信息
    """
    repo_url: str = Field(
        ..., max_length=500,
        description="Git 仓库地址，如 https://github.com/xxx/yyy.git"
    )
    repo_branch: str = Field(
        default="main", max_length=100,
        description="要分析的分支，默认 main"
    )


class CodeRepoInfo(BaseModel):
    """
    代码仓库信息（返回）
    """
    repo_url: Optional[str] = Field(default=None, description="Git 仓库地址")
    repo_path: Optional[str] = Field(default=None, description="本地克隆路径")
    repo_branch: Optional[str] = Field(default=None, description="分支")
    analyzed: bool = Field(default=False, description="是否已完成代码分析")
    analyzed_at: Optional[datetime] = Field(default=None, description="上次分析时间")
    last_commit: Optional[str] = Field(default=None, description="最后分析的提交 SHA")
    is_local: bool = Field(default=False, description="是否为本地路径")


class CodeRepoStatus(BaseModel):
    """代码仓库分析状态"""
    repo_url: Optional[str] = None
    repo_path: Optional[str] = None
    repo_branch: Optional[str] = None
    configured: bool = False
    cloned: bool = False
    analyzed: bool = False
    analyzing: bool = False
    message: str = ""
    progress: int = 0        # 0-100 进度百分比
    current_step: str = ""   # 当前步骤名称


class CodeRepoStatusResponse(BaseResponse):
    """代码仓库状态响应"""
    success: bool = True
    data: CodeRepoStatus


class CodeRepoConfigResponse(BaseResponse):
    """代码仓库配置响应"""
    success: bool = True
    data: CodeRepoInfo
