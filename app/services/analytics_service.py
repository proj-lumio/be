"""Token analytics and Lumio Credit system — MongoDB aggregation."""

from datetime import datetime, timedelta, timezone

from app.db.mongo import get_db

# ── Lumio Credit System ──────────────────────────────────────────────────
# 1 Lumio Credit = 1,000 real LLM tokens
# Conversion is applied on read — raw token counts are always stored.

CREDIT_FACTOR = 1000  # real tokens per 1 Lumio Credit

PLANS = {
    "starter": {
        "name": "Starter",
        "price_eur": 29,
        "credits": 5_000,
        "max_companies": 10,
        "max_users": 1,
    },
    "professional": {
        "name": "Professional",
        "price_eur": 89,
        "credits": 20_000,
        "max_companies": 50,
        "max_users": 5,
    },
    "enterprise": {
        "name": "Enterprise",
        "price_eur": None,      # custom pricing, contact sales
        "credits": None,        # custom allocation
        "max_companies": None,  # unlimited
        "max_users": None,      # unlimited
        "custom": True,
    },
}

# Estimated credit cost per operation (for UI hints)
COST_ESTIMATES = {
    "chat_message": 1.5,
    "document_processing": 12,
    "audio_transcription_per_min": 3,
    "web_search": 3.0,
    "general_chat_message": 2.5,
}


def tokens_to_credits(tokens: int) -> float:
    """Convert raw token count to Lumio Credits."""
    return round(tokens / CREDIT_FACTOR, 2)


async def get_user_plan(user_id) -> dict:
    """Get the user's current plan and credit balance."""
    db = get_db()
    user = await db.users.find_one({"_id": user_id}, {"plan": 1})
    plan_id = (user or {}).get("plan", "starter")
    plan = PLANS.get(plan_id, PLANS["starter"])

    # Total tokens used this billing period (current calendar month)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {"$match": {"user_id": user_id, "created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total_tokens": {"$sum": "$total_tokens"}}},
    ]
    result = await db.token_usage.aggregate(pipeline).to_list(1)
    total_tokens = result[0]["total_tokens"] if result else 0
    credits_used = tokens_to_credits(total_tokens)

    return {
        "plan_id": plan_id,
        "plan": plan,
        "billing_period_start": month_start.isoformat(),
        "credits_total": plan["credits"],
        "credits_used": credits_used,
        "credits_remaining": round(plan["credits"] - credits_used, 2),
        "tokens_used": total_tokens,
    }


async def get_analytics_dashboard(user_id, days: int = 30) -> dict:
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    match = {"user_id": user_id, "created_at": {"$gte": since}}

    # Summary
    pipeline_summary = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_prompt_tokens": {"$sum": "$prompt_tokens"},
            "total_completion_tokens": {"$sum": "$completion_tokens"},
            "total_tokens": {"$sum": "$total_tokens"},
            "request_count": {"$sum": 1},
        }},
    ]
    summary_result = await db.token_usage.aggregate(pipeline_summary).to_list(1)
    summary = summary_result[0] if summary_result else {
        "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "request_count": 0
    }
    summary.pop("_id", None)
    summary["period_start"] = since.isoformat()
    summary["period_end"] = datetime.now(timezone.utc).isoformat()

    # Add credit conversion to summary
    summary["credits_used"] = tokens_to_credits(summary["total_tokens"])
    summary["credits_prompt"] = tokens_to_credits(summary["total_prompt_tokens"])
    summary["credits_completion"] = tokens_to_credits(summary["total_completion_tokens"])

    # By endpoint
    pipeline_ep = [
        {"$match": match},
        {"$group": {
            "_id": "$endpoint",
            "total_tokens": {"$sum": "$total_tokens"},
            "prompt_tokens": {"$sum": "$prompt_tokens"},
            "completion_tokens": {"$sum": "$completion_tokens"},
            "request_count": {"$sum": 1},
        }},
        {"$sort": {"total_tokens": -1}},
    ]
    by_endpoint = [
        {
            "endpoint": r["_id"],
            "total_tokens": r["total_tokens"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "credits": tokens_to_credits(r["total_tokens"]),
            "request_count": r["request_count"],
        }
        async for r in db.token_usage.aggregate(pipeline_ep)
    ]

    # By day
    pipeline_day = [
        {"$match": match},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "total_tokens": {"$sum": "$total_tokens"},
            "prompt_tokens": {"$sum": "$prompt_tokens"},
            "completion_tokens": {"$sum": "$completion_tokens"},
            "request_count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    by_day = [
        {
            "date": r["_id"],
            "total_tokens": r["total_tokens"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "credits": tokens_to_credits(r["total_tokens"]),
            "request_count": r["request_count"],
        }
        async for r in db.token_usage.aggregate(pipeline_day)
    ]

    # Plan & credits
    plan_info = await get_user_plan(user_id)

    return {
        "summary": summary,
        "by_endpoint": by_endpoint,
        "by_day": by_day,
        "plan": plan_info,
        "credit_factor": CREDIT_FACTOR,
        "cost_estimates": COST_ESTIMATES,
    }
