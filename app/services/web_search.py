"""DuckDuckGo web search wrapper for client discovery."""

import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 10) -> list[dict]:
    """Search the web using DuckDuckGo.

    Returns list of {title, href, body}.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        logger.warning("DuckDuckGo search failed for %r: %s", query, e)
        return []


def search_prospects(query: str, max_results: int = 8) -> list[dict]:
    """Search for potential Italian clients with targeted queries.

    Generates multiple search queries in Italian and English, deduplicates results.
    """
    queries = [
        f"aziende italiane {query}",
        f"{query} companies Italy",
        f"imprese {query} Italia elenco",
    ]

    all_results = []
    seen_urls: set[str] = set()

    for q in queries:
        for r in search_web(q, max_results=max_results):
            url = r.get("href", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    return all_results
