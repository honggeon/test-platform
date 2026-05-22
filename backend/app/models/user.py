"""
用户模型

定义系统用户表结构
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """
    用户表
    
    存储系统用户信息
    """
    __tablename__ = "users"
    __table_args__ = {"comment": "用户表"}
    
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="用户邮箱"
    )
    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="用户名"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="密码哈希"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        comment="是否激活"
    )
    
    # 关系
    created_projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="creator",
        foreign_keys="Project.created_by"
    )
    owned_test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        back_populates="owner",
        foreign_keys="TestCase.owner_id"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

