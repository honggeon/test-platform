"""
LangGraph 自定义认证

校验 Authorization: Bearer <JWT>，与 FastAPI /auth/login 签发的 token 共用 SECRET_KEY。
"""

from langgraph_sdk import Auth

from app.auth_security import verify_bearer_token
from app.config.auth_database import auth_session_factory

auth = Auth()


@auth.authenticate
async def get_current_user(authorization: str | None) -> Auth.types.MinimalUserDict:
    """Check if the user's token is valid."""
    if not authorization:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Missing authorization header"
        )

    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid authorization scheme"
        )

    token = parts[1]
    async with auth_session_factory() as db:
        user_id = await verify_bearer_token(token, db)

    if not user_id:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="Invalid or expired token"
        )

    return {"identity": user_id}
