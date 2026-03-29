"""Skill: search registered trademarks via TMview."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.enrichment.shared.normalize import company_name_words, normalize_company_name

logger = logging.getLogger(__name__)

TMVIEW_SEARCH_URL = "https://www.tmdn.org/tmview/api/search/results?translate=true"
TMVIEW_DETAIL_URL = "https://www.tmdn.org/tmview/api/trademark/detail"
TMVIEW_HOME = "https://www.tmdn.org/tmview/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": TMVIEW_HOME,
    "Origin": "https://www.tmdn.org",
    "X-Requested-With": "XMLHttpRequest",
}


def _score(item: dict, norm: str, words: list[str]) -> int:
    mark = normalize_company_name(item.get("tmName", ""))
    owner = normalize_company_name(" ".join(item.get("applicantName", []) or []))
    s = 0
    if mark == norm:
        s += 100
    elif norm and norm in mark:
        s += 60
    if owner == norm:
        s += 45
    elif norm and norm in owner:
        s += 20
    for w in words:
        s += 10 if w in mark.split() else (4 if w in mark else 0)
    if item.get("tradeMarkStatus") == "Registered":
        s += 3
    return s


async def search_trademarks(company_name: str) -> list[dict[str, Any]]:
    norm = normalize_company_name(company_name)
    words = company_name_words(company_name)

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
            await client.get(TMVIEW_HOME)
            resp = await client.post(TMVIEW_SEARCH_URL, json={
                "basicSearch": company_name, "criteria": "W", "page": 1, "pageSize": 20,
            })
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("tradeMarks", []) if isinstance(data, dict) else []
        if not isinstance(raw, list):
            return []

        ranked = sorted(raw, key=lambda x: _score(x, norm, words), reverse=True)

        results = []
        seen = set()
        for item in ranked[:10]:
            mark = item.get("tmName", "")
            owner = " ".join(item.get("applicantName", []) or [])
            key = (mark.lower(), owner.lower(), item.get("tradeMarkStatus", "").lower())
            if key in seen:
                continue
            seen.add(key)

            classes = item.get("niceClass")
            if isinstance(classes, str):
                classes = [c.strip() for c in classes.split(",") if c.strip()]
            elif not isinstance(classes, list):
                classes = []

            results.append({
                "mark_text": mark,
                "status": item.get("tradeMarkStatus", "Unknown"),
                "filing_date": item.get("applicationDate", ""),
                "registration_date": item.get("registrationDate", ""),
                "nice_classes": [str(c) for c in classes],
                "owner": owner,
                "source": "TMview",
            })

        return results
    except Exception as e:
        logger.warning("TMview search failed: %s", e)
        return []
