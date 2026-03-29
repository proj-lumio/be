"""Skill: search company website via DuckDuckGo with multi-query strategy."""

import re

from app.services.enrichment.shared.duckduckgo import search_duckduckgo, DEFAULT_EXCLUDED_DOMAINS
from app.services.enrichment.shared.normalize import normalize_company_name, extract_domain_from_pec


def search_website(
    company_name: str, vat: str = "", citta: str = "",
    pec: str = "", ateco_description: str = "",
) -> list[dict]:
    norm = normalize_company_name(company_name)
    domain_hint = extract_domain_from_pec(pec) if pec else None

    queries = []
    parts = [norm]
    if citta:
        parts.append(citta)
    parts.append("italia sito web")
    queries.append(" ".join(parts))

    if vat:
        digits = re.sub(r"\D", "", vat)[-11:]
        if len(digits) == 11:
            queries.append(f"{norm} P.IVA {digits[-4:]}")

    if ateco_description and citta:
        words = [w for w in ateco_description.split() if len(w) > 3][:2]
        if words:
            queries.append(f"{norm} {' '.join(words)} {citta}")

    if domain_hint:
        queries.append(f"{norm} {domain_hint}")

    candidates = []
    seen = set()
    for q in queries:
        for r in search_duckduckgo(q, max_results=10, excluded_domains=DEFAULT_EXCLUDED_DOMAINS):
            url = r.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            score = 0.5
            url_lower = url.lower()
            if url_lower.endswith(".it"):
                score += 0.2
            if norm and norm in url_lower:
                score += 0.3
            r["score"] = min(score, 1.0)
            candidates.append(r)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:10]
