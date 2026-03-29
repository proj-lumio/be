"""Skill: extract contacts and social profiles from a company website."""

import re
from urllib.parse import urljoin

from app.services.enrichment.shared.http_client import fetch_url

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+39|0039)?[\s.-]*(?:3[0-9]{2}|0[0-9]{2,3})[\s.-]?[0-9]{6,7}", re.I)
SOCIAL_PATTERNS = {
    "linkedin": re.compile(r"linkedin\.com/(?:company/|in/)([a-zA-Z0-9-]+)", re.I),
    "facebook": re.compile(r"facebook\.com/([a-zA-Z0-9.-]+)", re.I),
    "instagram": re.compile(r"instagram\.com/([a-zA-Z0-9._]+)", re.I),
    "twitter": re.compile(r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)", re.I),
}
CONTACT_PAGES = ["/contatti", "/contact", "/chi-siamo", "/about"]


def _find_emails(text: str) -> list[str]:
    emails = set(EMAIL_RE.findall(text))
    return [e for e in emails if not e.startswith("info@") or len(emails) == 1]


def _find_phones(text: str) -> list[str]:
    seen = set()
    result = []
    for p in PHONE_RE.findall(text):
        phone = re.sub(r"[^\d+]", "", p)
        if len(phone) >= 9 and phone not in seen:
            seen.add(phone)
            if phone.startswith("39"):
                phone = "+" + phone
            result.append(phone)
    return result


def _find_socials(html: str, base_url: str) -> dict:
    socials = {"linkedin_url": None, "facebook_url": None, "instagram_url": None, "twitter_url": None}
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>', html, re.I):
        href = match.group(1)
        full = href if href.startswith("http") else urljoin(base_url, href)
        for platform, pat in SOCIAL_PATTERNS.items():
            if pat.search(full) and socials.get(f"{platform}_url") is None:
                socials[f"{platform}_url"] = full
    return socials


async def scrape(website_url: str) -> dict:
    result = {"email": None, "phone": None, "linkedin_url": None, "facebook_url": None,
              "instagram_url": None, "twitter_url": None, "source": None}
    sources = []
    all_emails, all_phones, all_socials = [], [], {}

    html = await fetch_url(website_url)
    if html:
        sources.append("homepage")
        all_emails.extend(_find_emails(html))
        all_phones.extend(_find_phones(html))
        all_socials.update(_find_socials(html, website_url))

    base = website_url.rstrip("/")
    for path in CONTACT_PAGES:
        if result["email"] and result["phone"] and all(all_socials.values()):
            break
        page = await fetch_url(base + path)
        if page:
            sources.append(path)
            all_emails.extend(_find_emails(page))
            all_phones.extend(_find_phones(page))
            for k, v in _find_socials(page, base + path).items():
                if all_socials.get(k) is None and v:
                    all_socials[k] = v

    if all_emails:
        biz = [e for e in all_emails if not e.startswith(("info@", "contatti@"))]
        result["email"] = biz[0] if biz else all_emails[0]
    if all_phones:
        result["phone"] = all_phones[0]
    for k in all_socials:
        if result.get(k) is None:
            result[k] = all_socials.get(k)
    result["source"] = "+".join(sources) if sources else "none"
    return result
