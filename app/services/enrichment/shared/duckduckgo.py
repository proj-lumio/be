"""Shared DuckDuckGo scraper with retry, rate limiting, and multiple parsing strategies."""

from __future__ import annotations

import re
import logging
import time
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_ua_index = 0
_last_request_time: float = 0.0
_MIN_REQUEST_INTERVAL = 1.0


def _next_user_agent() -> str:
    global _ua_index
    ua = _USER_AGENTS[_ua_index % len(_USER_AGENTS)]
    _ua_index += 1
    return ua


def _rate_limit() -> None:
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if _last_request_time > 0 and elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


DEFAULT_EXCLUDED_DOMAINS = ["wikipedia", "youtube.com"]
EXTENDED_EXCLUDED_DOMAINS = ["wikipedia", "youtube.com", "gov.it", "camera.it", "senato.it"]


def _parse_result_a(html: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>')
    results = []
    for match in pattern.finditer(html):
        url = _extract_url(match.group(1))
        if url:
            results.append({"url": url, "nome": match.group(2).strip()})
    return results


def _parse_result_url(html: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<a[^>]+class="result__url"[^>]+href="([^"]+)"[^>]*>([^<]*)</a>')
    results = []
    for match in pattern.finditer(html):
        url = _extract_url(match.group(1))
        if url:
            results.append({"url": url, "nome": match.group(2).strip() or url})
    return results


def _parse_generic_links(html: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]*)</a>')
    results = []
    seen = set()
    for match in pattern.finditer(html):
        href = match.group(1)
        if "duckduckgo.com" in href or href in seen:
            continue
        seen.add(href)
        results.append({"url": href, "nome": match.group(2).strip() or href})
    return results


def _parse_lite_results(html: str) -> list[dict[str, str]]:
    pattern = re.compile(r'<a[^>]+class="result-link"[^>]+href="([^"]+)"[^>]*>([^<]*)</a>')
    results = []
    for match in pattern.finditer(html):
        href = match.group(1)
        if href.startswith("http") and "duckduckgo.com" not in href:
            results.append({"url": href, "nome": match.group(2).strip() or href})
    return results or _parse_generic_links(html)


def _extract_url(href: str) -> str | None:
    if href.startswith("//duckduckgo"):
        return None
    url_match = re.search(r"uddg=([^&]+)", href)
    if url_match:
        actual = unquote(url_match.group(1))
        return actual if actual.startswith("http") else "https://" + actual
    return href if href.startswith("http") else None


_RETRY_DELAYS = [1.0, 2.0, 4.0]
_RETRYABLE = {403, 429, 500, 502, 503, 504}


def search_duckduckgo(
    query: str,
    max_results: int = 10,
    excluded_domains: list[str] | None = None,
) -> list[dict]:
    """Search DuckDuckGo with retries and fallback to lite endpoint."""
    if excluded_domains is None:
        excluded_domains = DEFAULT_EXCLUDED_DOMAINS

    for endpoint, is_lite in [
        ("https://html.duckduckgo.com/html/", False),
        ("https://lite.duckduckgo.com/lite/", True),
    ]:
        results = _try_endpoint(endpoint, query, is_lite)
        if results:
            filtered = [r for r in results if not any(d in r.get("url", "") for d in excluded_domains)]
            return filtered[:max_results]
    return []


def _try_endpoint(endpoint: str, query: str, is_lite: bool) -> list[dict]:
    data = {"q": query, "b": ""}
    for attempt, delay in enumerate([0.0] + _RETRY_DELAYS):
        if delay > 0:
            time.sleep(delay)
        _rate_limit()
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(endpoint, data=data, headers={"User-Agent": _next_user_agent()})
                if resp.status_code in _RETRYABLE and attempt < len(_RETRY_DELAYS):
                    continue
                resp.raise_for_status()
        except Exception:
            if attempt < len(_RETRY_DELAYS):
                continue
            return []

        html = resp.text
        if is_lite:
            return _parse_lite_results(html)
        results = _parse_result_a(html) or _parse_result_url(html) or _parse_generic_links(html)
        if results:
            return results
    return []
