from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.db.mongo import get_db
from app.middleware.auth import get_current_user

router = APIRouter()

DEFAULTS = {"theme": "light", "language": "it", "notifications_enabled": True, "preferences": None, "onboarding_completed": False}


@router.get("")
async def get_settings(user: dict = Depends(get_current_user)):
    db = get_db()
    settings = await db.user_settings.find_one({"user_id": user["_id"]})
    if not settings:
        settings = {**DEFAULTS, "user_id": user["_id"], "updated_at": datetime.now(timezone.utc)}
        await db.user_settings.insert_one(settings)
    return {k: settings.get(k, v) for k, v in DEFAULTS.items()}


@router.patch("")
async def update_settings(data: dict, user: dict = Depends(get_current_user)):
    db = get_db()
    allowed = {"theme", "language", "notifications_enabled", "preferences"}
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc)

    await db.user_settings.update_one(
        {"user_id": user["_id"]},
        {"$set": updates, "$setOnInsert": {"user_id": user["_id"]}},
        upsert=True,
    )
    return await get_settings(user)
