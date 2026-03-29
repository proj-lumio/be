"""General Chat Agent — cross-company LangGraph RAG pipeline.

Perspective: YOU are the seller. Companies are YOUR CLIENTS.

Like the company-scoped RAG agent, but:
1. Searches across ALL user-owned companies/clients (no company_id filter)
2. Pre-loads a client portfolio summary (rankings, revenue, client scores)
3. Graph search spans multiple clients
"""

import logging
from typing import TypedDict

from bson import ObjectId
from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.db.mongo import get_db
from app.services.llm import chat_completion, get_embeddings

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_ITERATIONS = 2


# ── State ────────────────────────────────────────────────────────────────

class GeneralChatState(TypedDict, total=False):
    query: str
    user_id: str
    company_ids: list[str]
    filtered_company_ids: list[str]
    matched_categories: list[str]
    history_messages: list
    portfolio_summary: str
    vector_results: list
    graph_entities: list
    graph_relationships: list
    context_text: str
    iteration: int
    additional_queries: list
    needs_graph: bool
    needs_more_context: bool


# ── Nodes ────────────────────────────────────────────────────────────────

async def load_portfolio_summary_node(state: GeneralChatState) -> dict:
    """Aggregate structured data across all user companies."""
    db = get_db()
    user_oid = ObjectId(state["user_id"])

    # Get all company IDs
    all_companies = await db.companies.find(
        {"owner_id": user_oid},
        {"_id": 1, "name": 1, "ranking_score": 1, "client_score": 1,
         "total_annual_revenue_eur": 1, "source": 1},
    ).sort("client_score", -1).to_list(50)

    company_ids = [str(c["_id"]) for c in all_companies]

    if not all_companies:
        return {
            "portfolio_summary": "No companies in portfolio yet.",
            "company_ids": [],
        }

    # Aggregate contract + document counts
    company_oids = [c["_id"] for c in all_companies]

    doc_counts = {}
    async for row in db.documents.aggregate([
        {"$match": {"company_id": {"$in": company_oids}}},
        {"$group": {"_id": "$company_id", "count": {"$sum": 1}}},
    ]):
        doc_counts[str(row["_id"])] = row["count"]

    contract_counts = {}
    async for row in db.contract_analyses.aggregate([
        {"$match": {"company_id": {"$in": company_oids}}},
        {"$group": {"_id": "$company_id", "count": {"$sum": 1}}},
    ]):
        contract_counts[str(row["_id"])] = row["count"]

    # Top risk flags
    risk_flags_cursor = db.contract_analyses.aggregate([
        {"$match": {"company_id": {"$in": company_oids}}},
        {"$unwind": "$risk_flags"},
        {"$group": {"_id": "$risk_flags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ])
    top_risks = [f"{r['_id']} ({r['count']}x)" async for r in risk_flags_cursor]

    # Build summary text (capped for context window)
    total_revenue = sum(c.get("total_annual_revenue_eur", 0) or 0 for c in all_companies)
    avg_client_score = (
        sum(c.get("client_score", 0) or 0 for c in all_companies) / len(all_companies)
    )

    lines = [
        "## Client Portfolio Overview",
        f"Total clients: {len(all_companies)}",
        f"Total annual revenue: EUR {total_revenue:,.0f}",
        f"Average client score: {avg_client_score:.1f}/100",
        f"Top risk flags: {', '.join(top_risks) if top_risks else 'none'}",
        "",
        "## Clients (sorted by client score):",
    ]

    for c in all_companies[:20]:
        cid = str(c["_id"])
        source_tag = " [prospect]" if c.get("source") in ("web_search", "client_discovery") else ""
        lines.append(
            f"- {c.get('name', 'Unknown')}{source_tag}: "
            f"client_score={c.get('client_score', 0):.0f}, "
            f"richness={c.get('ranking_score', 0):.0f}, "
            f"revenue=EUR {c.get('total_annual_revenue_eur', 0) or 0:,.0f}, "
            f"docs={doc_counts.get(cid, 0)}, contracts={contract_counts.get(cid, 0)}"
        )

    if len(all_companies) > 20:
        lines.append(f"... and {len(all_companies) - 20} more companies")

    return {
        "portfolio_summary": "\n".join(lines),
        "company_ids": company_ids,
    }


async def filter_by_category_node(state: GeneralChatState) -> dict:
    """Pre-filter companies by macro-category to reduce search space."""
    from app.constants.categories import MACRO_CATEGORIE

    company_ids = state.get("company_ids", [])
    if not company_ids:
        return {"filtered_company_ids": [], "matched_categories": []}

    query_lower = state["query"].lower()

    # Fast path: keyword matching
    matched = [c for c in MACRO_CATEGORIE if c.lower() in query_lower]

    # LLM fallback if no keyword match
    if not matched:
        import json
        import re

        prompt = (
            "Sei un assistente di classificazione. "
            "Data la domanda dell'utente, identifica quali macro-categorie di fornitori sono rilevanti.\n\n"
            f"Categorie disponibili: {', '.join(MACRO_CATEGORIE)}\n\n"
            f"Domanda: {state['query']}\n\n"
            'Rispondi SOLO con JSON valido, senza markdown:\n'
            '{"categorie": ["Cat1", "Cat2"]} oppure {"categorie": []} se nessuna è rilevante.'
        )
        for _attempt in range(2):
            try:
                result = await chat_completion(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=256,
                )
                raw = (result["content"] or "").strip()
                raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
                m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                if m:
                    raw = m.group(1).strip()
                if raw:
                    parsed = json.loads(raw)
                    matched = [c for c in parsed.get("categorie", []) if c in MACRO_CATEGORIE]
                    if matched:
                        break
            except Exception:
                continue

    if not matched:
        return {"filtered_company_ids": company_ids, "matched_categories": []}

    # Filter from MongoDB: companies with matching categories + uncategorized ones
    db = get_db()
    user_oid = ObjectId(state["user_id"])
    cursor = db.companies.find(
        {
            "owner_id": user_oid,
            "$or": [
                {"categories": {"$in": matched}},
                {"categories": {"$exists": False}},
                {"categories": {"$size": 0}},
            ],
        },
        {"_id": 1},
    )
    filtered = [str(c["_id"]) async for c in cursor]

    # Never return empty — fall back to all
    if not filtered:
        filtered = company_ids

    logger.info(
        "Category filter: %d/%d companies (categories: %s)",
        len(filtered), len(company_ids), matched,
    )
    return {"filtered_company_ids": filtered, "matched_categories": matched}


async def retrieve_node(state: GeneralChatState) -> dict:
    """Vector search across filtered user companies."""
    company_ids = state.get("filtered_company_ids") or state.get("company_ids", [])
    if not settings.qdrant_url or not company_ids:
        return {"vector_results": state.get("vector_results", [])}

    from app.services.vector_store import search_similar_multi_company

    queries_to_run = [state["query"]] + state.get("additional_queries", [])
    all_results = list(state.get("vector_results", []))
    seen_ids: set[str] = {r["point_id"] for r in all_results}

    for q in queries_to_run:
        try:
            hits = await search_similar_multi_company(q, company_ids, limit=8)
            for h in hits:
                if h["point_id"] not in seen_ids:
                    all_results.append(h)
                    seen_ids.add(h["point_id"])
        except Exception as e:
            logger.warning("Multi-company vector search failed for %r: %s", q, e)

    return {"vector_results": all_results, "additional_queries": []}


async def analyze_node(state: GeneralChatState) -> dict:
    """Extract entities and decide if graph search is needed."""
    if not settings.neo4j_uri:
        return {"needs_graph": False, "graph_entities": [], "graph_relationships": []}

    prompt = (
        "You are an entity-extraction assistant.\n"
        "Given the user query below, extract named entities that could exist in a knowledge graph "
        "(people, organisations, locations, products, concepts, dates).\n"
        "Also decide whether a graph traversal would add value beyond the vector search results.\n\n"
        "Return ONLY valid JSON, no markdown:\n"
        '{"entities": ["Entity1", "Entity2"], "needs_graph": true}\n\n'
        f"User query: {state['query']}"
    )
    try:
        result = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=256,
        )
        import json
        parsed = json.loads(result["content"])
        entities = parsed.get("entities", [])[:10]
        needs = parsed.get("needs_graph", bool(entities))
    except Exception:
        entities = _simple_entity_extract(state["query"])
        needs = bool(entities)

    return {"needs_graph": needs, "graph_entities": entities}


async def graph_search_node(state: GeneralChatState) -> dict:
    """Traverse Neo4j graph across multiple companies."""
    entity_names = state.get("graph_entities", [])
    if not entity_names:
        return {}

    from app.services.graph_store import query_graph_context

    all_entities = []
    all_relationships = []

    # Search across filtered companies (cap at 10 to avoid overload)
    for company_id in (state.get("filtered_company_ids") or state.get("company_ids", []))[:10]:
        try:
            ctx = query_graph_context(company_id, entity_names)
            all_entities.extend(e.get("name") for e in ctx.get("entities", []))
            all_relationships.extend(ctx.get("relationships", []))
        except Exception as e:
            logger.warning("Graph search failed for company %s: %s", company_id, e)

    # Deduplicate entities
    seen = set()
    unique_entities = []
    for e in all_entities:
        if e and e not in seen:
            seen.add(e)
            unique_entities.append(e)

    return {
        "graph_entities": unique_entities,
        "graph_relationships": all_relationships,
    }


async def evaluate_node(state: GeneralChatState) -> dict:
    """Decide if accumulated context is sufficient."""
    iteration = state.get("iteration", 0)

    if iteration >= MAX_ITERATIONS:
        return {"needs_more_context": False, "iteration": iteration}

    vr = state.get("vector_results", [])
    ge = state.get("graph_entities", [])

    if len(vr) >= 3 or (len(vr) >= 1 and len(ge) >= 2):
        return {"needs_more_context": False, "iteration": iteration}

    snippet = "\n".join(r["content"][:200] for r in vr[:3]) if vr else "(none)"
    prompt = (
        "You are a retrieval evaluator.\n"
        "The user asked: " + state["query"] + "\n"
        "Current retrieved context (first 200 chars each):\n" + snippet + "\n\n"
        "Is this context sufficient to answer the question well? "
        "If not, suggest 1-2 short alternative search queries that might find missing info.\n\n"
        "Return ONLY valid JSON:\n"
        '{"sufficient": true} or {"sufficient": false, "queries": ["alt query 1"]}'
    )
    try:
        result = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=128,
        )
        import json
        parsed = json.loads(result["content"])
        if parsed.get("sufficient", True):
            return {"needs_more_context": False, "iteration": iteration}
        return {
            "needs_more_context": True,
            "additional_queries": parsed.get("queries", [])[:2],
            "iteration": iteration + 1,
        }
    except Exception:
        return {"needs_more_context": False, "iteration": iteration}


async def build_context_node(state: GeneralChatState) -> dict:
    """Assemble final context from portfolio summary + vector + graph results."""
    parts = []

    # Portfolio summary always comes first
    ps = state.get("portfolio_summary", "")
    if ps:
        parts.append(ps)

    mc = state.get("matched_categories", [])
    if mc:
        parts.append(f"\n## Categorie rilevanti: {', '.join(mc)}")

    vr = state.get("vector_results", [])
    if vr:
        parts.append("\n## Relevant document excerpts:")
        for r in vr:
            company_tag = f" [company: {r.get('company_id', '?')}]"
            parts.append(f"- {r['content'][:500]}{company_tag}")

    ge = state.get("graph_entities", [])
    gr = state.get("graph_relationships", [])
    if ge:
        parts.append("\n## Knowledge graph context:")
        for name in ge[:15]:
            parts.append(f"- Entity: {name}")
        for r in gr[:15]:
            parts.append(
                f"- {r.get('source')} --[{r.get('relation')}]--> {r.get('target')}"
            )

    return {"context_text": "\n".join(parts) if parts else "No specific context found."}


# ── Routing ──────────────────────────────────────────────────────────────

def route_after_analyze(state: GeneralChatState) -> str:
    return "graph_search" if state.get("needs_graph") else "evaluate"


def route_after_evaluate(state: GeneralChatState) -> str:
    if state.get("needs_more_context") and state.get("iteration", 0) < MAX_ITERATIONS:
        return "retrieve"
    return "build_context"


# ── Build the graph ──────────────────────────────────────────────────────

def build_general_chat_graph():
    g = StateGraph(GeneralChatState)

    g.add_node("load_portfolio_summary", load_portfolio_summary_node)
    g.add_node("filter_by_category", filter_by_category_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("analyze", analyze_node)
    g.add_node("graph_search", graph_search_node)
    g.add_node("evaluate", evaluate_node)
    g.add_node("build_context", build_context_node)

    g.set_entry_point("load_portfolio_summary")
    g.add_edge("load_portfolio_summary", "filter_by_category")
    g.add_edge("filter_by_category", "retrieve")
    g.add_edge("retrieve", "analyze")
    g.add_conditional_edges("analyze", route_after_analyze)
    g.add_edge("graph_search", "evaluate")
    g.add_conditional_edges("evaluate", route_after_evaluate)
    g.add_edge("build_context", END)

    return g.compile()


_general_graph = None


def get_general_chat_graph():
    global _general_graph
    if _general_graph is None:
        _general_graph = build_general_chat_graph()
    return _general_graph


# ── Public API ───────────────────────────────────────────────────────────

async def run_general_rag_pipeline(
    query: str,
    user_id: str,
    history_messages: list[dict] | None = None,
) -> dict:
    """Run the cross-company RAG pipeline.

    Returns {context_text, vector_results, graph_entities, graph_relationships, iteration, portfolio_summary}.
    """
    graph = get_general_chat_graph()

    initial_state: GeneralChatState = {
        "query": query,
        "user_id": user_id,
        "company_ids": [],
        "filtered_company_ids": [],
        "matched_categories": [],
        "history_messages": history_messages or [],
        "portfolio_summary": "",
        "vector_results": [],
        "graph_entities": [],
        "graph_relationships": [],
        "context_text": "",
        "iteration": 0,
        "additional_queries": [],
        "needs_graph": False,
        "needs_more_context": False,
    }

    final = await graph.ainvoke(initial_state)

    return {
        "context_text": final.get("context_text", ""),
        "vector_results": final.get("vector_results", []),
        "graph_entities": final.get("graph_entities", []),
        "graph_relationships": final.get("graph_relationships", []),
        "iteration": final.get("iteration", 0),
        "portfolio_summary": final.get("portfolio_summary", ""),
        "matched_categories": final.get("matched_categories", []),
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def _simple_entity_extract(query: str) -> list[str]:
    """Fallback: extract capitalised multi-word spans."""
    words = query.split()
    entities, current = [], []
    for w in words:
        if w[0:1].isupper() and len(w) > 1:
            current.append(w)
        elif current:
            entities.append(" ".join(current))
            current = []
    if current:
        entities.append(" ".join(current))
    return entities[:5]
