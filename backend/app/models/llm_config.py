"""
LLM 配置模型

存储每个项目的 LLM Provider 配置
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from uuid import UUID

from sqlalchemy import ForeignKey, String, Float, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class LLMConfig(Base, UUIDMixin, TimestampMixin):
    """
    LLM 配置表

    每个项目可以配置自己的 LLM Provider、模型和 API Key
    """
    __tablename__ = "llm_configs"
    __table_args__ = {"comment": "LLM 配置表"}

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="关联的项目 ID",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="deepseek",
        comment="LLM 提供商: deepseek, openai, anthropic, ollama",
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="deepseek-chat",
        comment="模型名称",
    )
    api_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="API Key",
    )
    base_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="自定义 Base URL",
    )
    temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=0.7,
        comment="温度参数",
    )
    max_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最大 Token 数",
    )

    # 关系
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="llm_config",
    )

    def __repr__(self) -> str:
        return f"<LLMConfig(id={self.id}, project_id={self.project_id}, provider={self.provider}, model={self.model_name})>"
