"""Client Discovery Agent — LangGraph pipeline with web search + OpenAPI IT enrichment.

The agent:
1. Plans and executes web searches for potential clients
2. Extracts structured prospect info from search results
3. Loads the user's existing clients for deduplication
4. Generates comparison and recommendations (with tool calling to add prospects)
5. Auto-enriches added companies via OpenAPI IT (by P.IVA)
"""

import json
import logging
from datetime import datetime, timezone
from typing import TypedDict

from bson import ObjectId
from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.db.mongo import get_db
from app.services.llm import chat_completion, chat_completion_with_tools
from app.services.web_search import search_prospects

logger = logging.getLogger(__name__)
settings = get_settings()


# ── State ────────────────────────────────────────────────────────────────

class ClientDiscoveryState(TypedDict, total=False):
    user_query: str
    user_id: str
    session_id: str
    search_queries: list[str]
    web_results: list[dict]
    found_prospects: list[dict]
    existing_clients: list[dict]
    comparison: str
    tool_calls_pending: list[dict]
    tool_results: list[dict]
    added_companies: list[dict]
    response_text: str
    total_tokens: int


# ── Tool definitions ─────────────────────────────────────────────────────

CLIENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_company_to_lumio",
            "description": "Add a discovered potential client to Lumio for tracking as a prospect. If a P.IVA is available, include it for automatic enrichment with Italian business registry data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "Name of the company"},
                    "description": {"type": "string", "description": "Brief description of the company and why it's a good prospect"},
                    "website": {"type": "string", "description": "Company website URL"},
                    "industry": {"type": "string", "description": "Industry/sector"},
                    "vat_code": {"type": "string", "description": "Italian P.IVA (Partita IVA) if found, 11 digits"},
                },
                "required": ["company_name", "description"],
            },
        },
    }
]


# ── Tool execution ───────────────────────────────────────────────────────

async def add_company_to_lumio(
    user_id: str,
    company_name: str,
    description: str,
    website: str | None = None,
    industry: str | None = None,
    vat_code: str | None = None,
) -> dict:
    """Create a prospect company and optionally enrich via OpenAPI IT."""
    db = get_db()
    now = datetime.now(timezone.utc)

    # 1. Create company
    company_doc = {
        "name": company_name,
        "description": description,
        "website": website,
        "industry": industry,
        "piva": vat_code,
        "logo_url": None,
        "owner_id": ObjectId(user_id),
        "source": "client_discovery",
        "ranking_score": 0.0,
        "client_score": 0.0,
        "total_annual_revenue_eur": 0.0,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.companies.insert_one(company_doc)
    company_id = str(result.inserted_id)

    # 2. Generate summary document
    summary_text = (
        f"Company: {company_name}\n"
        f"Website: {website or 'N/A'}\n"
        f"Industry: {industry or 'N/A'}\n"
        f"P.IVA: {vat_code or 'N/A'}\n"
        f"Source: Discovered via Lumio Client Discovery\n\n"
        f"Description:\n{description}\n"
    )

    doc_record = {
        "company_id": ObjectId(company_id),
        "filename": f"{company_name.replace(' ', '_')}_prospect_summary.txt",
        "doc_type": "txt",
        "file_url": "generated",
        "file_size": len(summary_text.encode()),
        "source": "client_discovery",
        "processing_status": "pending",
        "raw_text": None,
        "created_at": now,
        "updated_at": now,
    }
    doc_result = await db.documents.insert_one(doc_record)
    doc_id = str(doc_result.inserted_id)

    # 3. Run through ingestion pipeline
    try:
        from app.services.ingestion import process_document
        await process_document(doc_id, summary_text.encode("utf-8"))
    except Exception as e:
        logger.warning("Ingestion failed for prospect %s: %s", company_name, e)

    # 4. Auto-enrich via OpenAPI IT if we have a P.IVA
    enriched = False
    if vat_code:
        try:
            from app.services.openapi_it import enrich_company
            enrich_result = await enrich_company(company_id, vat_code, user_id=user_id)
            enriched = enrich_result.get("success", False)
        except Exception as e:
            logger.warning("OpenAPI enrichment failed for %s: %s", company_name, e)

    # 5. Full web enrichment (website, contacts, social, news, trademarks, description)
    try:
        from app.services.enrichment.agent import enrich_and_update_company
        await enrich_and_update_company(company_id, user_id=user_id)
    except Exception as e:
        logger.warning("Web enrichment failed for %s: %s", company_name, e)

    return {
        "company_id": company_id,
        "document_id": doc_id,
        "company_name": company_name,
        "enriched": enriched,
    }


# ── Nodes ────────────────────────────────────────────────────────────────

async def plan_search_node(state: ClientDiscoveryState) -> dict:
    """LLM generates targeted search queries to find potential clients."""
    prompt = (
        "You are a client discovery assistant. The user is a SaaS provider looking for "
        "potential Italian clients to sell their services to.\n"
        "Given their request, generate 2-3 concise web search queries to find Italian companies "
        "that might need these services. Include at least one query in Italian.\n\n"
        "Return ONLY valid JSON, no markdown:\n"
        '{"queries": ["query 1", "query 2"]}\n\n'
        f"User request: {state['user_query']}"
    )
    try:
        result = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=256,
        )
        import re
        raw = (result["content"] or "").strip()
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        parsed = json.loads(raw)
        queries = parsed.get("queries", [])[:3]
    except Exception:
        queries = [state["user_query"]]

    return {
        "search_queries": queries,
        "total_tokens": state.get("total_tokens", 0),
    }


async def execute_search_node(state: ClientDiscoveryState) -> dict:
    """Execute web searches using DuckDuckGo."""
    all_results = []
    seen_urls: set[str] = set()

    for query in state.get("search_queries", [state["user_query"]]):
        for r in search_prospects(query, max_results=6):
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    return {"web_results": all_results[:20]}


async def extract_prospects_node(state: ClientDiscoveryState) -> dict:
    """LLM extracts structured prospect info from raw search results."""
    web_results = state.get("web_results", [])
    if not web_results:
        return {"found_prospects": []}

    results_text = "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('href', '')}\nSnippet: {r.get('body', '')}"
        for r in web_results[:15]
    )

    prompt = (
        "You are a client discovery assistant. From the web search results below, "
        "extract distinct Italian companies that could be potential clients for a SaaS provider.\n\n"
        "Return ONLY valid JSON:\n"
        '{"prospects": [{"name": "Company Name", "description": "what they do and why they might need SaaS services", '
        '"website": "url", "vat_code": "P.IVA if visible, else null", "fit_score": 0.8}]}\n\n'
        "fit_score: 0.0-1.0 based on how likely they are to be a good client.\n"
        "Filter out irrelevant results (blogs, directories, news articles). Keep actual companies.\n"
        "Look for P.IVA (Partita IVA, 11 digits) if visible on the page or URL.\n\n"
        f"User was looking for: {state['user_query']}\n\n"
        f"Search results:\n{results_text}"
    )
    try:
        result = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2048,
        )
        import re
        raw = (result["content"] or "").strip()
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        parsed = json.loads(raw)
        prospects = parsed.get("prospects", [])
        tokens = state.get("total_tokens", 0) + result.get("total_tokens", 0)
    except Exception:
        prospects = []
        tokens = state.get("total_tokens", 0)

    return {"found_prospects": prospects, "total_tokens": tokens}


async def load_existing_clients_node(state: ClientDiscoveryState) -> dict:
    """Load the user's existing companies for deduplication."""
    db = get_db()
    user_oid = ObjectId(state["user_id"])

    existing = []
    async for c in db.companies.find(
        {"owner_id": user_oid},
        {"name": 1, "piva": 1, "industry": 1, "source": 1, "website": 1},
    ).limit(100):
        existing.append({
            "name": c.get("name", ""),
            "piva": c.get("piva"),
            "industry": c.get("industry"),
            "source": c.get("source"),
            "website": c.get("website"),
        })

    return {"existing_clients": existing}


async def compare_and_recommend_node(state: ClientDiscoveryState) -> dict:
    """LLM compares found prospects with existing clients and recommends."""
    found = state.get("found_prospects", [])
    existing = state.get("existing_clients", [])

    existing_summary = "No existing clients." if not existing else "\n".join(
        f"- {c.get('name', 'Unknown')}: {c.get('industry', 'N/A')}, "
        f"P.IVA: {c.get('piva', 'N/A')}, source: {c.get('source', 'N/A')}"
        for c in existing
    )

    found_summary = "\n".join(
        f"- {p.get('name', 'Unknown')}: {p.get('description', 'N/A')} "
        f"(website: {p.get('website', 'N/A')}, P.IVA: {p.get('vat_code', 'N/A')}, fit: {p.get('fit_score', 'N/A')})"
        for p in found
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are Lumio AI's Client Discovery Agent. You help SaaS providers find and evaluate "
                "potential new clients by searching the web and comparing results against their existing "
                "client portfolio.\n\n"
                "When the user's request implies they want to add a prospect to track it, "
                "use the add_company_to_lumio tool. Include the P.IVA (vat_code) if available.\n\n"
                "Provide a structured evaluation: why each prospect is a good fit, their industry, "
                "estimated size, and a clear recommendation on which to pursue first. "
                "Respond in the same language as the user's message."
            ),
        },
        {
            "role": "user",
            "content": (
                f"My request: {state['user_query']}\n\n"
                f"## My existing clients:\n{existing_summary}\n\n"
                f"## Found prospects:\n{found_summary}\n\n"
                "Evaluate these prospects and recommend which ones I should pursue as clients."
            ),
        },
    ]

    result = await chat_completion_with_tools(
        messages=messages,
        tools=CLIENT_TOOLS,
        temperature=0.5,
        max_tokens=4096,
    )

    tokens = state.get("total_tokens", 0) + result.get("total_tokens", 0)

    return {
        "comparison": result["content"],
        "tool_calls_pending": result.get("tool_calls", []),
        "total_tokens": tokens,
    }


async def execute_tools_node(state: ClientDiscoveryState) -> dict:
    """Execute tool calls — add prospect companies to Lumio."""
    tool_calls = state.get("tool_calls_pending", [])
    if not tool_calls:
        return {"added_companies": [], "tool_results": []}

    added = []
    tool_results = []

    for tc in tool_calls:
        func = tc.get("function", {})
        if func.get("name") == "add_company_to_lumio":
            try:
                args = json.loads(func.get("arguments", "{}"))
                result = await add_company_to_lumio(
                    user_id=state["user_id"],
                    company_name=args.get("company_name", "Unknown"),
                    description=args.get("description", ""),
                    website=args.get("website"),
                    industry=args.get("industry"),
                    vat_code=args.get("vat_code"),
                )
                added.append(result)
                enriched_msg = " (enriched with registry data)" if result.get("enriched") else ""
                tool_results.append({
                    "tool_call_id": tc.get("id"),
                    "result": f"Added {result['company_name']} to Lumio (ID: {result['company_id']}){enriched_msg}",
                })
            except Exception as e:
                logger.warning("Tool execution failed: %s", e)
                tool_results.append({
                    "tool_call_id": tc.get("id"),
                    "result": f"Failed to add company: {e}",
                })

    return {"added_companies": added, "tool_results": tool_results}


async def build_response_node(state: ClientDiscoveryState) -> dict:
    """Assemble the final response text."""
    parts = []

    if state.get("comparison"):
        parts.append(state["comparison"])

    added = state.get("added_companies", [])
    if added:
        parts.append("\n---\n")
        for a in added:
            enriched = " | Enriched with registry data" if a.get("enriched") else ""
            parts.append(
                f"**Added to Lumio:** {a['company_name']} "
                f"(company ID: {a['company_id']}){enriched}"
            )

    return {"response_text": "\n".join(parts) if parts else "No results found."}


# ── Routing ──────────────────────────────────────────────────────────────

def route_after_compare(state: ClientDiscoveryState) -> str:
    if state.get("tool_calls_pending"):
        return "execute_tools"
    return "build_response"


# ── Build the graph ──────────────────────────────────────────────────────

def build_client_discovery_graph():
    g = StateGraph(ClientDiscoveryState)

    g.add_node("plan_search", plan_search_node)
    g.add_node("execute_search", execute_search_node)
    g.add_node("extract_prospects", extract_prospects_node)
    g.add_node("load_existing_clients", load_existing_clients_node)
    g.add_node("compare_and_recommend", compare_and_recommend_node)
    g.add_node("execute_tools", execute_tools_node)
    g.add_node("build_response", build_response_node)

    g.set_entry_point("plan_search")
    g.add_edge("plan_search", "execute_search")
    g.add_edge("execute_search", "extract_prospects")
    g.add_edge("extract_prospects", "load_existing_clients")
    g.add_edge("load_existing_clients", "compare_and_recommend")
    g.add_conditional_edges("compare_and_recommend", route_after_compare)
    g.add_edge("execute_tools", "build_response")
    g.add_edge("build_response", END)

    return g.compile()


_client_graph = None


def get_client_discovery_graph():
    global _client_graph
    if _client_graph is None:
        _client_graph = build_client_discovery_graph()
    return _client_graph


# ── Public API ───────────────────────────────────────────────────────────

async def run_client_discovery(
    user_query: str,
    user_id: str,
    session_id: str,
) -> dict:
    """Run the client discovery pipeline.

    Returns {response_text, found_prospects, added_companies, total_tokens}.
    """
    graph = get_client_discovery_graph()

    initial_state: ClientDiscoveryState = {
        "user_query": user_query,
        "user_id": user_id,
        "session_id": session_id,
        "search_queries": [],
        "web_results": [],
        "found_prospects": [],
        "existing_clients": [],
        "comparison": "",
        "tool_calls_pending": [],
        "tool_results": [],
        "added_companies": [],
        "response_text": "",
        "total_tokens": 0,
    }

    final = await graph.ainvoke(initial_state)

    return {
        "response_text": final.get("response_text", ""),
        "found_prospects": final.get("found_prospects", []),
        "added_companies": final.get("added_companies", []),
        "total_tokens": final.get("total_tokens", 0),
    }
