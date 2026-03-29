"""Authentication endpoints — register and login with email/password."""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from passlib.context import CryptContext

from app.config import get_settings
from app.db.mongo import get_db
from app.middleware.auth import _create_token
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _safe_user(user: dict) -> dict:
    """Strip sensitive fields and serialise for response."""
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "display_name": user.get("display_name", ""),
        "is_active": user.get("is_active", True),
        "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    db = get_db()

    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    now = datetime.now(timezone.utc)
    user = {
        "email": body.email,
        "password_hash": _hash_password(body.password),
        "display_name": body.display_name,
        "photo_url": "",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.users.insert_one(user)
    user["_id"] = result.inserted_id

    token = _create_token(str(user["_id"]), user["email"])
    return AuthResponse(access_token=token, user=_safe_user(user))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    db = get_db()

    user = await db.users.find_one({"email": body.email})
    if not user or not _verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = _create_token(str(user["_id"]), user["email"])
    return AuthResponse(access_token=token, user=_safe_user(user))
