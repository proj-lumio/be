"""Chat service — agentic GraphRAG via LangGraph + MongoDB persistence."""

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.db.mongo import get_db
from app.services.llm import chat_completion_stream, generate_session_title
from app.services.langgraph_agent import run_rag_pipeline

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are Lumio AI, an intelligent assistant that helps users understand company data and documents.
You have access to company documents and a knowledge graph connecting entities across documents.
Always cite your sources when possible. Be concise and precise.
Respond in the same language as the user's message.

## Formatting rules
When presenting structured data (contract details, document summaries, comparisons):
- ALWAYS use well-formed Markdown tables with a header row, a separator row (|---|---|), and data rows.
- Keep table columns concise — abbreviate headers if needed.
- Use bold (**value**) only for notable or outlier values.
- After a table, add a short 1-3 sentence insight or recommendation — never repeat the raw data in prose.
- Do NOT mix bullet-list and table formats for the same data set; prefer tables for ≥3 items.
- For yes/no or flag-type data, use checkmarks (✓) and dashes (–) instead of full words."""


async def _build_system_prompt(user: dict) -> str:
    """Build system prompt with optional company context from onboarding."""
    profile = await get_db().onboarding_profiles.find_one({"user_id": user["_id"]})
    if not profile:
        return SYSTEM_PROMPT

    parts = [SYSTEM_PROMPT, "\n\n## Company Context"]
    if profile.get("name"):
        parts.append(f"The user's company is {profile['name']}.")
    if profile.get("industry"):
        parts.append(f"Industry: {profile['industry']}.")
    if profile.get("description"):
        parts.append(f"About: {profile['description']}")
    if profile.get("services"):
        parts.append(f"Services: {', '.join(profile['services'])}.")
    if profile.get("products"):
        parts.append(f"Products: {', '.join(profile['products'])}.")
    if profile.get("target_market"):
        parts.append(f"Target market: {profile['target_market']}.")
    parts.append(
        "\nUse this company context to provide more relevant, "
        "tailored answers. Reference the user's industry and business when appropriate."
    )
    return "\n".join(parts)


async def _run_rag_and_build_sources(company_id: str, content: str, history: list[dict]) -> tuple[str, dict]:
    """Run the agentic RAG pipeline, return (context_text, sources_dict)."""
    rag = await run_rag_pipeline(
        query=content,
        company_id=company_id,
        history_messages=history,
    )

    sources = {
        "vector_results": [
            {"document_id": r["document_id"], "score": r["score"]}
            for r in rag["vector_results"]
        ],
        "graph_entities": rag["graph_entities"],
    }

    if rag.get("iteration", 0) > 0:
        logger.info("RAG agent iterated %d time(s) for richer context", rag["iteration"])

    return rag["context_text"], sources


async def _get_history(db, session_id) -> list[dict]:
    cursor = db.chat_messages.find({"session_id": session_id}).sort("created_at", -1).limit(20)
    return list(reversed([m async for m in cursor]))


async def send_message_stream(session: dict, user: dict, content: str):
    """Streaming version. Yields JSON-serialisable event dicts."""
    db = get_db()
    company_id = str(session["company_id"])
    session_id = session["_id"]

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

    # Agentic RAG pipeline
    context_text, sources = await _run_rag_and_build_sources(company_id, content, history)

    # Send sources early so the FE can render them while streaming
    yield {"type": "sources", "data": sources}

    # Build LLM messages (system prompt includes per-user company context if onboarded)
    system_prompt = await _build_system_prompt(user)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Context:\n{context_text}"},
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
            "endpoint": "chat_stream",
            "created_at": datetime.now(timezone.utc),
        })

    # Auto-rename session on first message
    update_fields = {"updated_at": datetime.now(timezone.utc)}
    new_title = None
    msg_count = await db.chat_messages.count_documents({"session_id": session_id})
    if msg_count <= 2:  # user + assistant = first exchange
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
