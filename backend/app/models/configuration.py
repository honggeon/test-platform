"""
配置模型

定义测试配置（操作系统、浏览器、设备组合）的表结构
参考: https://www.browserstack.com/docs/test-management/api-reference/configurations
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Configuration(Base, TimestampMixin):
    """
    配置表

    存储测试配置信息，包括操作系统、浏览器、设备组合
    配置分为系统定义（is_system=True）和用户自定义（is_system=False）
    """
    __tablename__ = "configurations"
    __table_args__ = {"comment": "测试配置表"}

    # 主键使用整数 ID（符合 BrowserStack API）
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="配置 ID"
    )
    
    # 配置名称
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="配置名称"
    )
    
    # 操作系统信息
    os: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="操作系统"
    )
    os_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="操作系统版本"
    )
    
    # 设备信息
    device: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="设备"
    )
    
    # 浏览器信息
    browser: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="浏览器"
    )
    browser_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="浏览器版本"
    )
    
    # 是否为系统定义
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否为系统定义配置"
    )
    
    # 描述
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="配置描述"
    )

    def __repr__(self) -> str:
        return f"<Configuration(id={self.id}, name={self.name})>"

