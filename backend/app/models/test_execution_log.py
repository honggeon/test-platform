"""
测试执行日志模型

记录每次测试执行的详细信息，支持按项目、执行人、时间范围聚合统计
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TestExecutionLog(Base, UUIDMixin, TimestampMixin):
    """
    测试执行日志表

    记录每次 execute_api_script / run_tests 的执行记录
    """
    __tablename__ = "test_execution_logs"
    __table_args__ = {"comment": "测试执行日志表"}

    # 所属项目
    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属项目 ID"
    )

    # 关联端点（可选）
    endpoint_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_endpoints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联端点 ID"
    )

    # 执行人
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="system",
        comment="执行人 ID"
    )

    # 执行结果
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="执行状态: success / failed / timeout"
    )
    duration_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="执行耗时（毫秒）"
    )
    return_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="进程返回码"
    )

    # 脚本信息
    script_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="脚本文件名"
    )
    framework: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="测试框架"
    )

    # 关联报告（可选）
    report_attachment_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的测试报告附件 ID"
    )

    # 关系
    project: Mapped["Project"] = relationship(
        "Project", back_populates="test_execution_logs"
    )
    endpoint: Mapped["APIEndpoint | None"] = relationship(
        "APIEndpoint", back_populates="execution_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<TestExecutionLog(id={self.id}, "
            f"status={self.status}, "
            f"endpoint_id={self.endpoint_id})>"
        )
