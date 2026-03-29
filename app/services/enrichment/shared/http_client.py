"""Shared async HTTP client for enrichment skills."""

from __future__ import annotations

import logging

import httpx

from app.services.enrichment.shared.duckduckgo import _next_user_agent

logger = logging.getLogger(__name__)


async def fetch_url(url: str, timeout: float = 10.0) -> str:
    """Fetch a URL and return its text content. Returns empty string on failure."""
    headers = {
        "User-Agent": _next_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.debug("fetch_url failed for %s: %s", url, e)
        return ""
