"""Chat service for client discovery sessions."""

import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.config import get_settings
from app.db.mongo import get_db
from app.services.llm import chat_completion_stream, generate_session_title
from app.services.vendor_discovery_agent import run_client_discovery

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are Lumio AI's Client Discovery Agent. You help SaaS providers find and evaluate
potential new clients by searching the web and comparing results against their existing
client portfolio. When the user asks to add a prospect, use the add_company_to_lumio tool.
Respond in the same language as the user's message.

## Formatting rules
When presenting prospect lists, comparisons, or evaluation results:
- ALWAYS use well-formed Markdown tables with a header row, a separator row (|---|---|), and data rows.
- Keep table columns concise — abbreviate headers if needed.
- Use bold (**value**) only for notable or outlier values.
- After a table, add a short 1-3 sentence insight or recommendation — never repeat the raw data in prose.
- Do NOT mix bullet-list and table formats for the same data set; prefer tables for ≥3 items.
- For yes/no or flag-type data, use checkmarks (✓) and dashes (–) instead of full words."""


async def _get_history(db, session_id) -> list[dict]:
    cursor = db.chat_messages.find({"session_id": session_id}).sort("created_at", -1).limit(20)
    return list(reversed([m async for m in cursor]))


async def send_web_search_stream(session: dict, user: dict, content: str):
    """Streaming client discovery. Yields JSON-serialisable event dicts."""
    db = get_db()
    session_id = session["_id"]
    user_id = str(user["_id"])

    # Save user message
    now = datetime.now(timezone.utc)
    user_msg = {
        "session_id": session_id,
        "role": "user",
        "content": content,
        "tokens_used": 0,
        "sources": None,
        "created_at": now,
    }
    await db.chat_messages.insert_one(user_msg)

    # Status: searching
    yield {"type": "status", "data": "Searching for prospects..."}

    # Run client discovery pipeline
    discovery = await run_client_discovery(
        user_query=content,
        user_id=user_id,
        session_id=str(session_id),
    )

    # Emit found prospects
    found_prospects = discovery.get("found_prospects", [])
    if found_prospects:
        yield {"type": "prospects_found", "data": found_prospects}

    # Emit tool executions
    for added in discovery.get("added_companies", []):
        yield {
            "type": "tool_executed",
            "data": {
                "action": "add_company",
                "company_id": added["company_id"],
                "document_id": added["document_id"],
                "name": added["company_name"],
                "enriched": added.get("enriched", False),
            },
        }

    # Stream the comparison/recommendation response
    response_text = discovery.get("response_text", "")
    if response_text:
        history = await _get_history(db, session_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in history:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({
            "role": "system",
            "content": f"Client discovery results and analysis:\n{response_text}",
        })
        messages.append({
            "role": "user",
            "content": content,
        })

        full_content = ""
        usage = None
        async for delta, chunk_usage in chat_completion_stream(messages):
            if delta:
                full_content += delta
                yield {"type": "chunk", "data": delta}
            if chunk_usage:
                usage = chunk_usage
    else:
        full_content = "I couldn't find relevant prospects for your query."
        usage = None
        yield {"type": "chunk", "data": full_content}

    # Sources
    sources = {
        "found_prospects": found_prospects,
        "added_companies": discovery.get("added_companies", []),
        "web_results_count": len(found_prospects),
    }
    yield {"type": "sources", "data": sources}

    # Save assistant message
    total_tokens = (usage["total_tokens"] if usage else 0) + discovery.get("total_tokens", 0)
    assistant_msg = {
        "session_id": session_id,
        "role": "assistant",
        "content": full_content,
        "tokens_used": total_tokens,
        "sources": sources,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.chat_messages.insert_one(assistant_msg)

    # Track tokens
    if total_tokens > 0:
        await db.token_usage.insert_one({
            "user_id": user["_id"],
            "model": settings.regolo_model,
            "prompt_tokens": usage["prompt_tokens"] if usage else 0,
            "completion_tokens": usage["completion_tokens"] if usage else 0,
            "total_tokens": total_tokens,
            "endpoint": "client_discovery",
            "created_at": datetime.now(timezone.utc),
        })

    # Auto-rename session on first message
    update_fields = {"updated_at": datetime.now(timezone.utc)}
    new_title = None
    msg_count = await db.chat_messages.count_documents({"session_id": session_id})
    if msg_count <= 2:
        try:
            new_title = await generate_session_title(content)
            update_fields["title"] = new_title
        except Exception:
            logger.warning("Failed to generate session title", exc_info=True)

    await db.chat_sessions.update_one({"_id": session_id}, {"$set": update_fields})

    done_data = {
        "message_id": str(result.inserted_id),
        "content": full_content,
        "sources": sources,
        "tokens_used": total_tokens,
    }
    if new_title:
        done_data["new_title"] = new_title

    yield {"type": "done", "data": done_data}
