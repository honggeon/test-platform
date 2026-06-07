"""
Pydantic 模式定义模块

包含所有 API 请求和响应的数据模型
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from .common import (
    BaseResponse,
    ErrorResponse,
    SuccessResponse,
    MessageResponse,
)
from .pagination import (
    PaginationInfo,
    PaginatedResponse,
    PaginationParams,
)
from .enums import (
    Priority,
    TestCaseState,
    TestCaseType,
    TestRunState,
    TestRunActiveState,
    TestResultStatus,
)
from .auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
)

__all__ = [
    # 通用响应
    "BaseResponse",
    "ErrorResponse",
    "SuccessResponse",
    "MessageResponse",
    # 分页
    "PaginationInfo",
    "PaginatedResponse",
    "PaginationParams",
    # 枚举
    "Priority",
    "TestCaseState",
    "TestCaseType",
    "TestRunState",
    "TestRunActiveState",
    "TestResultStatus",
    # 认证
    "UserRegister",
    "UserLogin",
    "UserResponse",
    "TokenResponse",
    # 测试环境
    "TestEnvironmentCreate",
    "TestEnvironmentUpdate",
    "TestEnvironmentInfo",
]

