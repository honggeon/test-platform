"""
测试运行相关的 Pydantic 模型

基于 BrowserStack Test Management API 的测试运行接口设计
参考: https://www.browserstack.com/docs/test-management/api-reference/test-runs
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import (
    TestRunState,
    TestRunActiveState,
    TestResultStatus,
    Priority,
    TestCaseState,
    TestCaseType,
)


class IssueTracker(BaseModel):
    """问题跟踪器配置"""
    name: str = Field(..., description="问题跟踪器名称，如 jira")
    host: str = Field(..., description="问题跟踪器地址")


class TestCaseFilter(BaseModel):
    """测试用例过滤条件"""
    status: Optional[list[str]] = Field(default=None, description="状态过滤")
    priority: Optional[list[str]] = Field(default=None, description="优先级过滤")
    case_type: Optional[list[str]] = Field(default=None, description="测试类型过滤")
    owner: Optional[list[str]] = Field(default=None, description="负责人过滤")
    tags: Optional[list[str]] = Field(default=None, description="标签过滤")
    custom_fields: Optional[dict[str, list[Any]]] = Field(default=None, description="自定义字段过滤")


class TestRunCreate(BaseModel):
    """
    创建测试运行请求模型
    
    用于创建新的测试运行
    """
    name: str = Field(..., min_length=1, max_length=500, description="测试运行名称")
    description: Optional[str] = Field(default=None, description="测试运行描述")
    run_state: TestRunState = Field(default=TestRunState.NEW_RUN, description="运行状态")
    assignee: Optional[str] = Field(default=None, description="负责人邮箱")
    test_case_assignee: Optional[str] = Field(default=None, description="测试用例默认负责人邮箱")
    tags: Optional[list[str]] = Field(default=None, description="标签列表")
    issues: Optional[list[str]] = Field(default=None, description="关联的问题列表")
    issue_tracker: Optional[IssueTracker] = Field(default=None, description="问题跟踪器配置")
    configurations: Optional[list[int]] = Field(default=None, description="配置 ID 列表")
    test_plan_id: Optional[str] = Field(default=None, description="关联的测试计划 ID")
    test_cases: Optional[list[str]] = Field(default=None, description="测试用例标识符列表")
    folder_ids: Optional[list[int]] = Field(default=None, description="文件夹 ID 列表")
    include_all: Optional[bool] = Field(default=False, description="是否包含所有测试用例")
    filter_test_cases: Optional[TestCaseFilter] = Field(default=None, description="测试用例过滤条件")


class TestRunUpdate(BaseModel):
    """
    更新测试运行请求模型 (PATCH)
    
    用于部分更新测试运行
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=500, description="测试运行名称")
    description: Optional[str] = Field(default=None, description="测试运行描述")
    run_state: Optional[TestRunState] = Field(default=None, description="运行状态")
    assignee: Optional[str] = Field(default=None, description="负责人邮箱")
    tags: Optional[list[str]] = Field(default=None, description="标签列表")
    issues: Optional[list[str]] = Field(default=None, description="关联的问题列表")
    configurations: Optional[list[int]] = Field(default=None, description="配置 ID 列表")
    filter_test_cases: Optional[TestCaseFilter] = Field(default=None, description="测试用例过滤条件")


class TestRunFullUpdate(TestRunCreate):
    """
    完全更新测试运行请求模型 (POST)
    
    用于完全替换测试运行数据
    """
    pass


class TestCaseAssignee(BaseModel):
    """测试用例分配"""
    test_case_id: str = Field(..., description="测试用例标识符")
    configuration_id: Optional[int] = Field(default=None, description="配置 ID")
    assignee: str = Field(..., description="负责人邮箱")


class TestRunAssigneeUpdate(BaseModel):
    """更新测试运行中测试用例分配"""
    assign_to: list[TestCaseAssignee] = Field(..., description="分配列表")


class TestRunLinks(BaseModel):
    """测试运行相关链接"""
    self_link: Optional[str] = Field(default=None, alias="self", description="自身链接")
    test_cases: Optional[str] = Field(default=None, description="测试用例链接")
    
    class Config:
        populate_by_name = True


class OverallProgress(BaseModel):
    """
    整体进度统计

    与 BrowserStack API TestResultStatus 枚举值保持一致:
    - passed: 通过
    - failed: 失败
    - skipped: 跳过
    - blocked: 阻塞
    - not_executed: 未执行
    """
    passed: int = Field(default=0, description="通过数量")
    failed: int = Field(default=0, description="失败数量")
    skipped: int = Field(default=0, description="跳过数量")
    blocked: int = Field(default=0, description="阻塞数量")
    not_executed: int = Field(default=0, description="未执行数量")


class TestRunInfo(BaseModel):
    """
    测试运行信息模型

    用于返回测试运行详细信息
    """
    id: UUID = Field(..., description="测试运行 ID")
    identifier: str = Field(..., description="测试运行标识符，如 TR-123")
    name: str = Field(..., description="测试运行名称")
    description: Optional[str] = Field(default=None, description="测试运行描述")
    run_state: TestRunState = Field(..., description="运行状态")
    active_state: TestRunActiveState = Field(..., description="活跃状态")
    assignee: Optional[str] = Field(default=None, description="负责人邮箱")
    test_cases_count: int = Field(default=0, description="测试用例总数")
    tags: Optional[list[str]] = Field(default=None, description="标签列表")
    issues: Optional[list[str]] = Field(default=None, description="关联的问题列表")
    configurations: Optional[list[int]] = Field(default=None, description="配置列表")
    overall_progress: OverallProgress = Field(default_factory=OverallProgress, description="整体进度")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")
    links: Optional[TestRunLinks] = Field(default=None, description="相关资源链接")


class TestRunListInfo(BaseModel):
    """
    测试运行列表项模型

    用于列表返回简化的信息
    """
    id: UUID = Field(..., description="测试运行 ID")
    identifier: str = Field(..., description="测试运行标识符")
    name: str = Field(..., description="测试运行名称")
    run_state: TestRunState = Field(..., description="运行状态")
    active_state: TestRunActiveState = Field(..., description="活跃状态")
    assignee: Optional[str] = Field(default=None, description="负责人邮箱")
    test_cases_count: int = Field(default=0, description="测试用例总数")
    overall_progress: OverallProgress = Field(default_factory=OverallProgress, description="整体进度")
    created_at: datetime = Field(..., description="创建时间")


class TestRunTestCaseInfo(BaseModel):
    """
    测试运行中的测试用例信息

    用于返回测试运行中测试用例的详细状态
    """
    id: UUID = Field(..., description="关联 ID")
    test_run_id: UUID = Field(..., description="测试运行 ID")
    test_case_id: UUID = Field(..., description="测试用例 ID")
    test_case_identifier: str = Field(..., description="测试用例标识符")
    test_case_name: str = Field(..., description="测试用例名称")
    configuration_id: Optional[int] = Field(default=None, description="配置 ID")
    assignee: Optional[str] = Field(default=None, description="负责人邮箱")
    latest_status: TestResultStatus = Field(default=TestResultStatus.NOT_EXECUTED, description="最新状态")
    priority: Optional[Priority] = Field(default=None, description="优先级")
    test_case_type: Optional[TestCaseType] = Field(default=None, description="测试类型")
    folder_id: Optional[UUID] = Field(default=None, description="文件夹 ID")


class AddTestCasesRequest(BaseModel):
    """添加测试用例到测试运行"""
    test_cases: list[str] = Field(..., description="测试用例标识符列表")
    configuration_ids: Optional[list[int]] = Field(default=None, description="配置 ID 列表")
    assignee: Optional[str] = Field(default=None, description="负责人邮箱")


class RemoveTestCasesRequest(BaseModel):
    """从测试运行移除测试用例"""
    test_cases: list[str] = Field(..., description="测试用例标识符列表")
    configuration_ids: Optional[list[int]] = Field(default=None, description="配置 ID 列表")


class CloseTestRunRequest(BaseModel):
    """关闭测试运行请求"""
    active_state: TestRunActiveState = Field(
        default=TestRunActiveState.CLOSED,
        description="活跃状态"
    )

