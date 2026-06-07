"""
认证安全工具：密码哈希与 JWT
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_models import UserSession
from app.config.settings import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, username: str, jti: str) -> tuple[str, int]:
    expires_minutes = settings.access_token_expire_minutes
    expires_delta = timedelta(minutes=expires_minutes)
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    payload = {
        "sub": user_id,
        "username": username,
        "jti": jti,
        "exp": expire,
        "iat": now,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, int(expires_delta.total_seconds())


async def verify_bearer_token(token: str, db: AsyncSession | None = None) -> str | None:
    """校验 Bearer token，返回 user_id；无效时返回 None。"""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except jwt.PyJWTError:
        return None

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        return None

    if db is None:
        return str(user_id)

    result = await db.execute(select(UserSession).where(UserSession.token_jti == jti))
    session = result.scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        return None

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None

    return str(user_id)


def new_session_jti() -> str:
    return str(uuid4())
