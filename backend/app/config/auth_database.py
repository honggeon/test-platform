"""
认证 SQLite 数据库连接

独立于 PostgreSQL 的用户认证存储，便于后续迁移到其他数据库。
"""

from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_auth_db_path() -> Path:
    path = Path(settings.auth_db_path)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


AUTH_DB_PATH = _resolve_auth_db_path()

auth_engine = create_async_engine(
    f"sqlite+aiosqlite:///{AUTH_DB_PATH}",
    echo=settings.debug,
)

auth_session_factory = async_sessionmaker(
    auth_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class AuthBase(DeclarativeBase):
    """认证库 SQLAlchemy 基类"""

    pass


async def get_auth_db() -> AsyncGenerator[AsyncSession, None]:
    """获取认证库会话（FastAPI 依赖注入）"""
    async with auth_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_auth_db() -> None:
    """创建认证库表结构"""
    from app.auth_models import AuthUser, UserSession  # noqa: F401

    async with auth_engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)
