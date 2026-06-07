"""认证服务单元测试"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth_models import AuthUser, UserSession  # noqa: F401
from app.auth_security import verify_bearer_token
from app.config.auth_database import AuthBase
from app.schemas.auth import UserRegister
from app.services.auth_service import AuthService


async def _with_auth_db(coro):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await coro(session)
    await engine.dispose()
    return result


def test_register_and_login():
    async def run(session):
        user = await AuthService.register(
            session,
            UserRegister(
                username="testuser",
                email="test@example.com",
                password="password123",
                display_name="Test User",
            ),
        )
        assert user.username == "testuser"
        assert user.email == "test@example.com"

        token_response = await AuthService.login(session, "testuser", "password123")
        assert token_response.token_type == "bearer"
        assert token_response.access_token
        assert token_response.user.id == user.id

        verified = await verify_bearer_token(token_response.access_token, session)
        assert verified == user.id

    asyncio.run(_with_auth_db(run))


def test_login_invalid_password():
    async def run(session):
        await AuthService.register(
            session,
            UserRegister(
                username="user2",
                email="user2@example.com",
                password="password123",
            ),
        )
        with pytest.raises(ValueError, match="用户名或密码错误"):
            await AuthService.login(session, "user2", "wrong-password")

    asyncio.run(_with_auth_db(run))


def test_register_duplicate_username():
    async def run(session):
        data = UserRegister(
            username="dupuser",
            email="a@example.com",
            password="password123",
        )
        await AuthService.register(session, data)
        with pytest.raises(ValueError, match="已被注册"):
            await AuthService.register(
                session,
                UserRegister(
                    username="dupuser",
                    email="b@example.com",
                    password="password123",
                ),
            )

    asyncio.run(_with_auth_db(run))
