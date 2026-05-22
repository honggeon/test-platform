"""
诊断报告 PG 表模型

存储诊断报告的元数据及摘要，完整数据引用 MongoDB
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class DiagnosisReportPG(Base, UUIDMixin, TimestampMixin):
    """
    诊断报告表

    冗余存储 summary 方便 SQL 查询，完整数据见 MongoDB
    """
    __tablename__ = "diagnosis_reports"
    __table_args__ = {"comment": "诊断报告表"}

    project_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属项目 ID"
    )
    run_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="测试运行 ID"
    )
    dedup_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="幂等性唯一键"
    )
    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="报告类型: auto / manual"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="分析状态: completed / failed / analyzing"
    )
    summary_json: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        comment="概要 JSON，冗余存储方便 SQL 查询"
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="来源类型: api_test / scenario"
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="错误数量"
    )
    degradation_level: Mapped[str] = mapped_column(
        String(50),
        default="none",
        comment="降级级别: none / partial / severe"
    )
    llm_tokens_used: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="LLM Token 使用量"
    )
    analysis_duration_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="分析耗时(毫秒)"
    )
    mongo_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="MongoDB 完整数据引用 ID"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="完成时间"
    )

    def __repr__(self) -> str:
        return f"<DiagnosisReportPG(id={self.id}, run_id={self.run_id}, status={self.status})>"
