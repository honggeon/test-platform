"""
测试计划模型

定义测试计划的表结构
参考: https://www.browserstack.com/docs/test-management/api-reference/test-plans
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.schemas.enums import TestPlanStatus, TestPlanActiveState


class TestPlan(Base, UUIDMixin, TimestampMixin):
    """
    测试计划表

    存储测试计划的基本信息，用于组织和跟踪多个测试运行
    """
    __tablename__ = "test_plans"
    __table_args__ = {"comment": "测试计划表"}

    # 所属项目
    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属项目 ID"
    )
    
    # 标识符
    identifier: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="测试计划标识符，如 TP-123"
    )
    
    # 基本信息
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="测试计划名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="测试计划描述"
    )
    
    # 状态
    plan_status: Mapped[TestPlanStatus] = mapped_column(
        SQLEnum(TestPlanStatus),
        default=TestPlanStatus.DRAFT,
        nullable=False,
        comment="计划状态"
    )
    active_state: Mapped[TestPlanActiveState] = mapped_column(
        SQLEnum(TestPlanActiveState),
        default=TestPlanActiveState.ACTIVE,
        nullable=False,
        comment="活跃状态"
    )
    
    # 时间范围
    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="开始日期"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="结束日期"
    )
    
    # 负责人
    owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="负责人邮箱"
    )
    
    # 统计信息
    test_runs_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="关联的测试运行数量"
    )
    
    # 标签和自定义字段
    tags: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="标签列表"
    )
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="自定义字段"
    )

    # 关系
    project: Mapped["Project"] = relationship("Project", back_populates="test_plans")
    test_runs: Mapped[list["TestRun"]] = relationship(
        "TestRun",
        back_populates="test_plan",
        foreign_keys="TestRun.test_plan_id"
    )

    def __repr__(self) -> str:
        return f"<TestPlan(id={self.id}, identifier={self.identifier}, name={self.name})>"

