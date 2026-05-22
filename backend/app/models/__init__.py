"""
SQLAlchemy 数据库模型模块

定义所有 PostgreSQL 数据库表的 ORM 模型
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from .base import Base, TimestampMixin, UUIDMixin
from .user import User
from .team import Team, ProjectTeam
from .project import Project
from .folder import Folder
from .folder_type import FolderType
from .test_case import TestCase, TestStep, Tag, TestCaseTag
from .test_run import TestRun, TestRunTestCase
from .test_result import TestResult, TestStepResult
from .attachment import Attachment, AttachmentEntityType
from .configuration import Configuration
from .llm_config import LLMConfig
from .test_plan import TestPlan
from .api_test import APITest, APITestRun, APITestResult
from .test_environment import TestEnvironment
from .test_execution_log import TestExecutionLog
from .api_endpoint import APIEndpoint
from .web_test import WebTest, WebTestRun, WebTestResult
from .web_function import WebFunction, WebSubFunction
from .test_scenario import (
    TestScenario,
    ScenarioStep,
    StepDataMapping,
    ScenarioVariable,
    ScenarioRun,
    ScenarioStepResult,
)

# 枚举类型从 schemas.enums 导入，避免重复定义
from ..schemas.enums import TestPlanStatus, TestPlanActiveState

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "User",
    "Team",
    "ProjectTeam",
    "Project",
    "Folder",
    "FolderType",
    "TestCase",
    "TestStep",
    "Tag",
    "TestCaseTag",
    "TestRun",
    "TestRunTestCase",
    "TestResult",
    "TestStepResult",
    "Attachment",
    "AttachmentEntityType",
    "Configuration",
    "LLMConfig",
    "TestPlan",
    "TestPlanStatus",
    "TestPlanActiveState",
    "APITest",
    "APITestRun",
    "APITestResult",
    "APIEndpoint",
    "WebTest",
    "WebTestRun",
    "WebTestResult",
    "WebFunction",
    "WebSubFunction",
    "TestScenario",
    "ScenarioStep",
    "StepDataMapping",
    "ScenarioVariable",
    "ScenarioRun",
    "ScenarioStepResult",
]

