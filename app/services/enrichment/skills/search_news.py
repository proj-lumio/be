"""Skill: find recent news via Google News RSS."""

import re
import logging
from datetime import datetime
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from app.services.enrichment.shared.normalize import normalize_company_name

logger = logging.getLogger(__name__)


def _parse_date(date_str: str) -> str:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str[:10] if len(date_str) >= 10 else ""


def _is_relevant(title: str, company_name: str, norm_name: str) -> bool:
    title_lower = title.lower()
    if company_name.lower() in title_lower:
        return True
    if norm_name and len(norm_name) >= 4:
        pattern = r'(?:^|[\s,.\-:;("])' + re.escape(norm_name) + r'(?:[\s,.\-:;)"]|$)'
        if re.search(pattern, title_lower):
            return True
    return False


async def search_news(company_name: str, citta: str = "") -> list[dict]:
    norm = normalize_company_name(company_name)
    queries = [f'"{company_name}"']
    if citta:
        queries.append(f'"{norm}" {citta}')

    items = []
    seen = set()

    for q in queries:
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=it&gl=IT&ceid=IT:it"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
        except Exception as e:
            logger.debug("News search failed: %s", e)
            continue

        try:
            root = ElementTree.fromstring(resp.text)
        except ElementTree.ParseError:
            continue

        for item in root.findall(".//item")[:15]:
            title = re.sub(r"<[^>]+>", "", item.findtext("title", "")).strip()
            if title in seen or not _is_relevant(title, company_name, norm):
                continue
            seen.add(title)
            items.append({
                "titolo": title,
                "url": item.findtext("link", ""),
                "fonte": item.findtext("source", ""),
                "data": _parse_date(item.findtext("pubDate", "")),
            })
        if len(items) >= 5:
            break

    return items[:10]
