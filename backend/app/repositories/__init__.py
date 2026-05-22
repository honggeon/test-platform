"""
数据访问层模块

包含所有数据库操作的仓储类
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from .base import BaseRepository
from .project_repo import ProjectRepository
from .folder_repo import FolderRepository
from .test_case_repo import TestCaseRepository
from .test_run_repo import TestRunRepository, TestRunTestCaseRepository
from .test_result_repo import TestResultRepository
from .attachment_repo import AttachmentRepository
from .configuration_repo import ConfigurationRepository

__all__ = [
    "BaseRepository",
    "ProjectRepository",
    "FolderRepository",
    "TestCaseRepository",
    "TestRunRepository",
    "TestRunTestCaseRepository",
    "TestResultRepository",
    "AttachmentRepository",
    "ConfigurationRepository",
]

