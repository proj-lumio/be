"""Chat service for general (cross-company) chat sessions."""

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.db.mongo import get_db
from app.services.llm import chat_completion_stream, generate_session_title
from app.services.general_chat_agent import run_general_rag_pipeline

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are Lumio AI, a strategic intelligence assistant with full awareness of the user's
entire client portfolio. The user is a seller/provider — the companies in the system are their CLIENTS.
You can analyze cross-client trends, compare clients, identify risks and opportunities,
and provide strategic recommendations based on all available data including contracts, revenue,
client scores, and document content across ALL clients.

Cite specific numbers (revenue, scores, client names) when available.
Respond in the same language as the user's message.

## Formatting rules
When presenting structured data (lists of clients, comparisons, rankings, risk summaries):
- ALWAYS use well-formed Markdown tables with a header row, a separator row (|---|---|), and data rows.
- Align numeric columns to the right where possible.
- Keep table columns concise — abbreviate headers if needed (e.g. "Score" not "Punteggio Cliente / 100").
- Use bold (**value**) only for notable or outlier values, not every cell.
- After a table, add a short 1-3 sentence insight or recommendation — never repeat the raw data in prose.
- Do NOT mix bullet-list and table formats for the same data set; prefer tables for ≥3 items.
- For yes/no or flag-type data, use checkmarks (✓) and dashes (–) instead of full words."""


async def _get_history(db, session_id) -> list[dict]:
    cursor = db.chat_messages.find({"session_id": session_id}).sort("created_at", -1).limit(20)
    return list(reversed([m async for m in cursor]))


async def send_general_message_stream(session: dict, user: dict, content: str):
    """Streaming cross-company chat. Yields JSON-serialisable event dicts."""
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

    # Conversation history
    history = await _get_history(db, session_id)

    # Cross-company RAG pipeline
    rag = await run_general_rag_pipeline(
        query=content,
        user_id=user_id,
        history_messages=[{"role": m["role"], "content": m["content"]} for m in history],
    )

    sources = {
        "vector_results": [
            {"document_id": r["document_id"], "company_id": r.get("company_id", ""), "score": r["score"]}
            for r in rag["vector_results"]
        ],
        "graph_entities": rag["graph_entities"],
    }

    # Send sources early
    yield {"type": "sources", "data": sources}

    # Build LLM messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Context:\n{rag['context_text']}"},
    ]
    for m in history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})

    # Stream LLM response
    full_content = ""
    usage = None
    async for delta, chunk_usage in chat_completion_stream(messages):
        if delta:
            full_content += delta
            yield {"type": "chunk", "data": delta}
        if chunk_usage:
            usage = chunk_usage

    # Save assistant message
    assistant_msg = {
        "session_id": session_id,
        "role": "assistant",
        "content": full_content,
        "tokens_used": usage["total_tokens"] if usage else 0,
        "sources": sources,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.chat_messages.insert_one(assistant_msg)

    # Track tokens
    if usage:
        await db.token_usage.insert_one({
            "user_id": user["_id"],
            "model": settings.regolo_model,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "endpoint": "general_chat_stream",
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
        "tokens_used": usage["total_tokens"] if usage else 0,
    }
    if new_title:
        done_data["new_title"] = new_title

    yield {"type": "done", "data": done_data}
