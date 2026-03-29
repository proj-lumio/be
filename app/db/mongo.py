"""MongoDB connection via Motor (async)."""

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

settings = get_settings()

client: AsyncIOMotorClient = AsyncIOMotorClient(
    settings.mongodb_url, tlsCAFile=certifi.where()
) if settings.mongodb_url else None
db: AsyncIOMotorDatabase = client[settings.mongodb_db_name] if client else None


def get_db() -> AsyncIOMotorDatabase:
    return db


async def init_indexes():
    """Create indexes on startup. Idempotent — safe to call multiple times."""
    if db is None:
        return
    await db.users.create_index("email", unique=True)
    await db.companies.create_index("owner_id")
    await db.companies.create_index("name")
    await db.documents.create_index("company_id")
    await db.document_chunks.create_index("document_id")
    await db.chat_sessions.create_index([("user_id", 1), ("company_id", 1)])
    await db.chat_messages.create_index("session_id")
    await db.token_usage.create_index([("user_id", 1), ("created_at", -1)])
    await db.user_settings.create_index("user_id", unique=True)
    await db.contract_analyses.create_index("company_id")
    await db.contract_analyses.create_index("document_id", unique=True)
    await db.onboarding_profiles.create_index("user_id", unique=True)
    await db.chat_sessions.create_index("scope")
    await db.companies.create_index("source")
    await db.web_search_results.create_index([("user_id", 1), ("created_at", -1)])
    await db.companies.create_index("piva", sparse=True)
    await db.company_lookup_cache.create_index(
        [("user_id", 1), ("vat_number", 1)], unique=True
    )


async def drop_all():
    """Nuclear option — drop all collections. Use for dev reset."""
    if db is None:
        return
    for name in await db.list_collection_names():
        await db[name].drop()
