"""Onboarding service — analyze company from URL/description, confirm profile."""

import json
import logging
import re
from datetime import datetime, timezone

from bson import ObjectId

from app.db.mongo import get_db
from app.services.llm import chat_completion
from app.services.scraper import scrape_website
from app.schemas.onboarding import CompanyProfile

logger = logging.getLogger(__name__)

ANALYZE_WEBSITE_PROMPT = """You are a company analyst. Given the text content scraped from a company's website, extract structured information about the company.

Extract the following fields:
- name: The company's official name
- industry: The industry or sector they operate in
- description: A 2-3 sentence summary of what the company does
- services: A list of services they offer (up to 8)
- products: A list of their products (up to 8)
- target_market: Who their customers are (B2B, B2C, enterprise, SMB, etc.)
- location: Their headquarters or primary location if mentioned

Return ONLY valid JSON matching this schema, no markdown:
{"name": "...", "industry": "...", "description": "...", "services": ["..."], "products": ["..."], "target_market": "...", "location": "..."}

Use null for any field you cannot determine from the text."""

ANALYZE_DESCRIPTION_PROMPT = """You are a company analyst. Given a user's description of their company, structure and enrich it into a detailed company profile.

Extract and infer the following fields:
- name: The company's name
- industry: The industry or sector
- description: A polished 2-3 sentence summary
- services: A list of services they offer (up to 8)
- products: A list of their products (up to 8)
- target_market: Who their customers are
- location: Their location if mentioned

Return ONLY valid JSON matching this schema, no markdown:
{"name": "...", "industry": "...", "description": "...", "services": ["..."], "products": ["..."], "target_market": "...", "location": "..."}

Use null for any field you cannot determine. Infer reasonable values where the description provides enough context."""


def _parse_llm_json(raw: str) -> dict | None:
    """Strip markdown fences and think blocks, parse JSON."""
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _llm_analyze(system_prompt: str, user_content: str) -> dict:
    """Call LLM with retry for JSON parsing."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content[:6000]},
    ]
    for attempt in range(3):
        result = await chat_completion(messages, temperature=0.0, max_tokens=2048)
        parsed = _parse_llm_json(result["content"] or "")
        if parsed:
            return parsed
        logger.warning("LLM JSON parse failed (attempt %d/3)", attempt + 1)
    raise ValueError("Failed to extract company profile after 3 attempts")


async def analyze_from_website(url: str) -> tuple[CompanyProfile, str]:
    """Scrape URL, run LLM analysis. Returns (profile, raw_summary)."""
    text = await scrape_website(url)
    data = await _llm_analyze(ANALYZE_WEBSITE_PROMPT, text)
    data["website"] = url
    filtered = {k: v for k, v in data.items() if k in CompanyProfile.model_fields and v is not None}
    if "name" not in filtered:
        filtered["name"] = url
    profile = CompanyProfile(**filtered)
    raw_summary = text[:500] + ("..." if len(text) > 500 else "")
    return profile, raw_summary


async def analyze_from_description(description: str) -> CompanyProfile:
    """Run LLM to structure a free-text description into CompanyProfile."""
    data = await _llm_analyze(ANALYZE_DESCRIPTION_PROMPT, description)
    filtered = {k: v for k, v in data.items() if k in CompanyProfile.model_fields and v is not None}
    if "name" not in filtered:
        filtered["name"] = description[:80].strip()
    return CompanyProfile(**filtered)


async def confirm_onboarding(user: dict, profile: CompanyProfile) -> dict:
    """Create/update company + onboarding profile, mark onboarding completed."""
    db = get_db()
    now = datetime.now(timezone.utc)
    user_id = user["_id"]

    # Upsert company
    existing = await db.companies.find_one({"owner_id": user_id})
    company_data = {
        "name": profile.name,
        "description": profile.description,
        "industry": profile.industry,
        "website": profile.website,
        "updated_at": now,
    }
    if existing:
        await db.companies.update_one({"_id": existing["_id"]}, {"$set": company_data})
        company_id = existing["_id"]
    else:
        company_data.update({
            "owner_id": user_id,
            "logo_url": "",
            "ranking_score": 0.0,
            "created_at": now,
        })
        result = await db.companies.insert_one(company_data)
        company_id = result.inserted_id

    # Upsert onboarding profile (used for system prompt injection)
    onboarding_doc = {
        "user_id": user_id,
        "company_id": company_id,
        "name": profile.name,
        "industry": profile.industry,
        "description": profile.description,
        "services": profile.services,
        "products": profile.products,
        "target_market": profile.target_market,
        "location": profile.location,
        "website": profile.website,
        "updated_at": now,
    }
    await db.onboarding_profiles.update_one(
        {"user_id": user_id},
        {"$set": onboarding_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    # Mark onboarding completed in user_settings
    await db.user_settings.update_one(
        {"user_id": user_id},
        {"$set": {"onboarding_completed": True, "updated_at": now}, "$setOnInsert": {"user_id": user_id}},
        upsert=True,
    )

    return {"company_id": str(company_id), "onboarding_completed": True}


async def get_onboarding_status(user: dict) -> dict:
    """Check if user has completed onboarding."""
    db = get_db()
    settings = await db.user_settings.find_one({"user_id": user["_id"]})
    completed = bool(settings and settings.get("onboarding_completed"))

    company_id = None
    if completed:
        profile = await db.onboarding_profiles.find_one({"user_id": user["_id"]})
        if profile:
            company_id = str(profile["company_id"])

    return {"onboarding_completed": completed, "company_id": company_id}
