"""
测试报告数据模型

提供测试报告相关的 Pydantic 模型
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TestReportSummary(BaseModel):
    """测试报告摘要"""
    total: int = Field(..., description="总测试用例数")
    passed: int = Field(..., description="通过数")
    failed: int = Field(..., description="失败数")
    skipped: int = Field(..., description="跳过数")
    total_duration_ms: int = Field(..., description="总耗时(毫秒)")


class TestReportTestInfo(BaseModel):
    """测试用例信息"""
    name: str = Field(..., description="测试用例名称")
    project: str = Field(default="default", description="项目名称")
    status: str = Field(..., description="状态: passed/failed/timedOut/skipped/interrupted")
    expected_status: str = Field(default="passed", description="预期状态")
    ok: bool = Field(default=True, description="是否通过")
    duration_ms: int = Field(default=0, description="耗时(毫秒)")
    error: Optional[str] = Field(default=None, description="错误信息")
    stack: Optional[str] = Field(default=None, description="错误堆栈")


class TestReportInfo(BaseModel):
    """测试报告详情"""
    id: str = Field(..., description="报告 ID (时间戳)")
    project_identifier: str = Field(..., description="项目标识符")
    framework: str = Field(..., description="测试框架")
    test_path: str = Field(..., description="测试路径")
    exit_code: int = Field(..., description="退出码")
    summary: TestReportSummary = Field(..., description="测试摘要")
    tests: list[TestReportTestInfo] = Field(..., description="测试用例列表")
    generated_at: str = Field(..., description="生成时间")
    minio_path: str = Field(..., description="MinIO 存储路径")
    presigned_url: Optional[str] = Field(default=None, description="预签名下载 URL")


class TestReportListInfo(BaseModel):
    """测试报告列表项"""
    id: str = Field(..., description="报告 ID")
    project_identifier: str = Field(..., description="项目标识符")
    generated_at: str = Field(..., description="生成时间")
    minio_path: str = Field(..., description="MinIO 存储路径")
    summary: TestReportSummary = Field(..., description="测试摘要")
    presigned_url: Optional[str] = Field(default=None, description="预签名下载 URL")
    report_type: str = Field(default="structured", description="报告类型: structured/allure")
