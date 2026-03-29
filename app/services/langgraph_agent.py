"""Agentic GraphRAG pipeline built on LangGraph.

The agent autonomously decides:
1. Whether to search Qdrant (vector similarity)
2. Whether to traverse Neo4j (entity/relationship lookup)
3. Whether to iterate (re-query with refined terms) or proceed to generation

The graph:
    retrieve → analyze → (graph_search?) → evaluate → (loop|generate) → END
"""

import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.services.llm import chat_completion, get_embeddings

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_ITERATIONS = 2


# ── State ────────────────────────────────────────────────────────────────

class GraphRAGState(TypedDict, total=False):
    query: str
    company_id: str
    history_messages: list          # prior conversation [{role, content}]
    vector_results: list            # accumulated Qdrant hits
    graph_entities: list            # accumulated graph entities
    graph_relationships: list       # accumulated graph relationships
    context_text: str               # built context for generation
    iteration: int
    additional_queries: list        # extra queries decided by the agent
    needs_graph: bool
    needs_more_context: bool
    response: str                   # final LLM answer
    total_tokens: int


# ── Nodes ────────────────────────────────────────────────────────────────

async def retrieve_node(state: GraphRAGState) -> dict:
    """Vector search on Qdrant for the current query + any additional queries."""
    if not settings.qdrant_url:
        return {"vector_results": state.get("vector_results", [])}

    from app.services.vector_store import search_similar

    queries_to_run = [state["query"]] + state.get("additional_queries", [])
    all_results = list(state.get("vector_results", []))
    seen_ids: set[str] = {r["point_id"] for r in all_results}

    for q in queries_to_run:
        try:
            hits = await search_similar(q, state["company_id"], limit=5)
            for h in hits:
                if h["point_id"] not in seen_ids:
                    all_results.append(h)
                    seen_ids.add(h["point_id"])
        except Exception as e:
            logger.warning("Vector search failed for %r: %s", q, e)

    return {"vector_results": all_results, "additional_queries": []}


async def analyze_node(state: GraphRAGState) -> dict:
    """Use LLM to extract entities from the query and decide if graph search is needed."""
    if not settings.neo4j_uri:
        return {"needs_graph": False, "graph_entities": [], "graph_relationships": []}

    # Ask the LLM to extract entities and decide
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
        # Fallback: simple capitalized-word extraction
        entities = _simple_entity_extract(state["query"])
        needs = bool(entities)

    return {"needs_graph": needs, "graph_entities": entities}


async def graph_search_node(state: GraphRAGState) -> dict:
    """Traverse Neo4j graph for the extracted entities."""
    entity_names = state.get("graph_entities", [])
    if not entity_names:
        return {}

    try:
        from app.services.graph_store import query_graph_context
        ctx = query_graph_context(state["company_id"], entity_names)
        return {
            "graph_entities": [e.get("name") for e in ctx.get("entities", [])],
            "graph_relationships": ctx.get("relationships", []),
        }
    except Exception as e:
        logger.warning("Graph search failed: %s", e)
        return {}


async def evaluate_node(state: GraphRAGState) -> dict:
    """Decide whether the accumulated context is sufficient or we need another retrieval pass."""
    iteration = state.get("iteration", 0)

    if iteration >= MAX_ITERATIONS:
        return {"needs_more_context": False, "iteration": iteration}

    vr = state.get("vector_results", [])
    ge = state.get("graph_entities", [])

    # If we already have decent context, don't iterate
    if len(vr) >= 3 or (len(vr) >= 1 and len(ge) >= 2):
        return {"needs_more_context": False, "iteration": iteration}

    # Ask LLM if more context would help
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


async def build_context_node(state: GraphRAGState) -> dict:
    """Assemble the final context string from vector results + graph data."""
    parts = []
    vr = state.get("vector_results", [])
    if vr:
        parts.append("## Relevant document excerpts:")
        for r in vr:
            parts.append(f"- {r['content'][:500]}")

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


# ── Routing functions ────────────────────────────────────────────────────

def route_after_analyze(state: GraphRAGState) -> str:
    return "graph_search" if state.get("needs_graph") else "evaluate"


def route_after_evaluate(state: GraphRAGState) -> str:
    if state.get("needs_more_context") and state.get("iteration", 0) < MAX_ITERATIONS:
        return "retrieve"
    return "build_context"


# ── Build the graph ──────────────────────────────────────────────────────

def build_rag_graph():
    g = StateGraph(GraphRAGState)

    g.add_node("retrieve", retrieve_node)
    g.add_node("analyze", analyze_node)
    g.add_node("graph_search", graph_search_node)
    g.add_node("evaluate", evaluate_node)
    g.add_node("build_context", build_context_node)

    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "analyze")
    g.add_conditional_edges("analyze", route_after_analyze)
    g.add_edge("graph_search", "evaluate")
    g.add_conditional_edges("evaluate", route_after_evaluate)
    g.add_edge("build_context", END)

    return g.compile()


# Singleton compiled graph
_rag_graph = None


def get_rag_graph():
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = build_rag_graph()
    return _rag_graph


# ── Public API ───────────────────────────────────────────────────────────

async def run_rag_pipeline(
    query: str,
    company_id: str,
    history_messages: list[dict] | None = None,
) -> dict:
    """Run the full agentic RAG pipeline.

    Returns {context_text, vector_results, graph_entities, graph_relationships, iteration}.
    """
    graph = get_rag_graph()

    initial_state: GraphRAGState = {
        "query": query,
        "company_id": company_id,
        "history_messages": history_messages or [],
        "vector_results": [],
        "graph_entities": [],
        "graph_relationships": [],
        "context_text": "",
        "iteration": 0,
        "additional_queries": [],
        "needs_graph": False,
        "needs_more_context": False,
        "response": "",
        "total_tokens": 0,
    }

    final = await graph.ainvoke(initial_state)

    return {
        "context_text": final.get("context_text", ""),
        "vector_results": final.get("vector_results", []),
        "graph_entities": final.get("graph_entities", []),
        "graph_relationships": final.get("graph_relationships", []),
        "iteration": final.get("iteration", 0),
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
