"""
诊断报告 MongoDB 文档模型

存储日志分析 Agent 生成的完整诊断报告
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DiagnosisReport(BaseModel):
    """
    诊断报告文档模型

    存储日志分析 Agent 生成的完整诊断结果，包括根因分析、修复建议等
    """
    report_id: str = Field(..., description="报告 ID (UUID)")
    run_id: str = Field(..., description="关联的测试运行 ID")
    project_id: str = Field(..., description="项目 ID")
    status: str = Field(..., description="分析状态: pending / analyzing / completed / failed")
    dedup_key: str = Field(..., description="幂等键: f'{run_id}_{project_id}'，唯一索引")
    retry_of_report_id: Optional[str] = Field(None, description="重新诊断时记录前次报告 ID")
    source_type: str = Field(default="api_test", description="来源类型: api_test / scenario / manual")
    test_type: str = Field(default="single", description="测试类型: single / scenario / batch")

    # 降级信息
    degradation: dict[str, Any] = Field(
        ...,
        description="降级信息: has_db_logs, has_kg_locations, has_llm_analysis, fallback_reason"
    )

    # 概要统计
    summary: dict[str, Any] = Field(
        default_factory=lambda: {
            "total_failures": 0,
            "root_cause_counts": {
                "token_expired": 0,
                "permission_denied": 0,
                "api_changed": 0,
                "data_error": 0,
                "network_timeout": 0,
                "script_error": 0,
                "unknown": 0,
            },
        },
        description="诊断概要统计"
    )

    # 诊断详情列表
    findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="诊断详情列表"
    )

    analysis_duration_ms: int = Field(default=0, description="分析耗时(毫秒)")

    # LLM Token 成本
    llm_token_cost: dict[str, Any] = Field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
        description="LLM Token 消耗: prompt_tokens, completion_tokens, total_tokens, total_cost_usd"
    )

    llm_provider: str = Field(default="local", description="LLM 提供商")

    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat(),
        }

    @classmethod
    def collection_name(cls) -> str:
        """获取 MongoDB 集合名称"""
        return "diagnosis_reports"

    def to_document(self) -> dict:
        """转换为 MongoDB 文档"""
        return self.model_dump(mode="json")
