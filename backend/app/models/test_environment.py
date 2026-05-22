"""
测试环境模型

定义项目的测试环境配置，支持多环境管理（开发、测试、预发布等）
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TestEnvironment(Base, UUIDMixin, TimestampMixin):
    """
    测试环境表

    存储项目下的测试环境配置，用于 AI 生成测试脚本时确定目标地址
    """
    __tablename__ = "test_environments"
    __table_args__ = {"comment": "测试环境表"}

    # 所属项目
    project_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属项目 ID"
    )

    # 环境信息
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="环境名称，如 '开发环境'、'测试环境'、'预发布'"
    )
    base_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="环境基础 URL，如 'http://dev-api.example.com'"
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="环境描述"
    )

    # 排序与默认
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="排序顺序（升序）"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否默认环境（每个项目只有一个默认环境）"
    )

    # 关系
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="test_environments"
    )

    def __repr__(self) -> str:
        return (
            f"<TestEnvironment(id={self.id}, "
            f"name={self.name}, "
            f"base_url={self.base_url}, "
            f"is_default={self.is_default})>"
        )
