"""Skill: find social profiles via DuckDuckGo search."""

import re

from app.services.enrichment.shared.duckduckgo import search_duckduckgo
from app.services.enrichment.shared.normalize import normalize_company_name, name_matches_handle

SOCIAL_QUERIES = [
    ("linkedin", "{company} linkedin azienda italiana"),
    ("facebook", "{company} facebook pagina ufficiale"),
    ("instagram", "{company} instagram"),
    ("twitter", "{company} twitter x"),
]

SOCIAL_PATTERNS = {
    "linkedin": r"linkedin\.com/company/([a-zA-Z0-9-]+)",
    "facebook": r"facebook\.com/([a-zA-Z0-9._-]+)",
    "instagram": r"instagram\.com/([a-zA-Z0-9._]+)",
    "twitter": r"(twitter|x)\.com/([a-zA-Z0-9_]+)",
}


def search_socials(company_name: str) -> dict:
    norm = normalize_company_name(company_name)
    urls = {"linkedin_url": None, "facebook_url": None, "instagram_url": None, "twitter_url": None}

    for social_type, tmpl in SOCIAL_QUERIES:
        results = search_duckduckgo(tmpl.format(company=norm), max_results=10)
        pat = SOCIAL_PATTERNS.get(social_type)
        if not pat:
            continue

        for r in results:
            url = r.get("url", "").lower()
            match = re.search(pat, url)
            if not match:
                continue
            handle = match.group(2).lower() if social_type == "twitter" else match.group(1).lower()
            if name_matches_handle(company_name, handle) or norm in r.get("nome", "").lower():
                key = f"{social_type}_url"
                if urls.get(key) is None:
                    urls[key] = r.get("url")
                break
            if social_type == "linkedin" and "/company/" in url:
                if urls["linkedin_url"] is None:
                    urls["linkedin_url"] = r.get("url")

    return urls
