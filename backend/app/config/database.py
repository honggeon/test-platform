"""
数据库连接配置

管理 PostgreSQL 和 MongoDB 的连接
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings


# ==================== PostgreSQL 配置 ====================

# 创建异步引擎
engine = create_async_engine(
    settings.postgres_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话的依赖注入函数
    
    Yields:
        AsyncSession: 异步数据库会话
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ==================== MongoDB 配置 ====================

class MongoDB:
    """MongoDB 连接管理器"""
    
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None
    
    @classmethod
    async def connect(cls) -> None:
        """建立 MongoDB 连接"""
        cls.client = AsyncIOMotorClient(settings.mongodb_url)
        cls.database = cls.client[settings.mongodb_db]
    
    @classmethod
    async def disconnect(cls) -> None:
        """关闭 MongoDB 连接"""
        if cls.client:
            cls.client.close()
    
    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """获取数据库实例"""
        return cls.database


async def get_mongodb() -> AsyncIOMotorDatabase:
    """
    获取 MongoDB 数据库的依赖注入函数
    
    Returns:
        AsyncIOMotorDatabase: MongoDB 数据库实例
    """
    return MongoDB.get_database()

