"""Skill: find related websites (fallback if search_website fails)."""

from app.services.enrichment.shared.duckduckgo import search_duckduckgo, EXTENDED_EXCLUDED_DOMAINS
from app.services.enrichment.shared.normalize import normalize_company_name, extract_domain_from_pec


def search_sites_by_vat(company_name: str, vat: str = "", citta: str = "", pec: str = "") -> list[dict]:
    norm = normalize_company_name(company_name)
    domain_hint = extract_domain_from_pec(pec) if pec else None

    queries = [
        f"{norm} {citta} sito web" if citta else f"{norm} sito web",
        f"{norm} .it",
    ]
    if domain_hint:
        queries.append(f"{norm} {domain_hint}")
    queries.append(f'"{norm}" azienda italiana')
    if vat:
        queries.append(f'"P.IVA {vat}"')

    candidates = []
    seen = set()
    for q in queries[:4]:
        for r in search_duckduckgo(q, max_results=10, excluded_domains=EXTENDED_EXCLUDED_DOMAINS):
            url = r.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            score = 0.5
            if url.lower().endswith(".it"):
                score += 0.15
            if norm and norm in url.lower():
                score += 0.25
            r["score"] = min(score, 1.0)
            candidates.append(r)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:10]
