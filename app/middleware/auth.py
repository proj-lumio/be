"""JWT Authentication middleware.

DEV_AUTH_BYPASS=true → fake dev user for testing.
Production → verifies JWT tokens, loads user from MongoDB.
Token refresh: every authenticated request returns a fresh token
in the X-Refreshed-Token response header (sliding 7-day expiry).
"""

from datetime import datetime, timezone, timedelta

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import get_settings
from app.db.mongo import get_db

settings = get_settings()
security = HTTPBearer(auto_error=not settings.dev_auth_bypass)

DEV_USER = {
    "email": "dev@lumio.local",
    "display_name": "Dev User",
}


def _create_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


async def get_current_user(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Get current user from MongoDB via JWT. Returns user dict.

    Sets X-Refreshed-Token header with a fresh token on every call.
    """
    db = get_db()

    if settings.dev_auth_bypass:
        user = await db.users.find_one({"email": DEV_USER["email"]})
        if not user:
            now = datetime.now(timezone.utc)
            user = {
                "email": DEV_USER["email"],
                "display_name": DEV_USER["display_name"],
                "photo_url": "",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            result = await db.users.insert_one(user)
            user["_id"] = result.inserted_id
        return user

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token")

    payload = _verify_token(credentials.credentials)
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # Sliding expiry: issue a fresh token on every authenticated request
    refreshed = _create_token(str(user["_id"]), user["email"])
    response.headers["X-Refreshed-Token"] = refreshed

    return user
