"""
用户认证服务
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_models import AuthUser, UserSession
from app.auth_security import (
    create_access_token,
    hash_password,
    new_session_jti,
    verify_password,
)
from app.config.settings import settings
from app.schemas.auth import TokenResponse, UserRegister, UserResponse


class AuthService:
    @staticmethod
    async def register(db: AsyncSession, data: UserRegister) -> UserResponse:
        existing = await db.execute(
            select(AuthUser).where(
                or_(AuthUser.username == data.username, AuthUser.email == data.email)
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("用户名或邮箱已被注册")

        user = AuthUser(
            id=str(uuid4()),
            username=data.username,
            email=str(data.email),
            password_hash=hash_password(data.password),
            display_name=data.display_name or data.username,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return UserResponse.model_validate(user)

    @staticmethod
    async def login(
        db: AsyncSession,
        username: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        result = await db.execute(select(AuthUser).where(AuthUser.username == username))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("用户名或密码错误")
        if not user.is_active:
            raise ValueError("账号已被禁用")

        jti = new_session_jti()
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
        expires_at = datetime.now(timezone.utc) + expires_delta

        session = UserSession(
            id=str(uuid4()),
            user_id=user.id,
            token_jti=jti,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        user.last_login_at = datetime.now(timezone.utc)
        db.add(session)

        access_token, expires_in = create_access_token(user.id, user.username, jti)
        await db.flush()
        await db.refresh(user)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserResponse.model_validate(user),
        )
