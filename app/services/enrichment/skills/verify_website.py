"""Skill: verify website ownership by finding P.IVA on pages."""

import re

from app.services.enrichment.shared.http_client import fetch_url

VAT_PATTERN = re.compile(
    r"(?:P\.?\s*IVA|partita\s*IVA|VAT(?:\s*(?:Number|No\.?|N\.?|ID|Code))?)[\s:.]*(IT)?\s*(\d{11})",
    re.IGNORECASE,
)

_VAT_PAGES = ["/privacy-policy", "/contatti", "/cookie-policy", "/chi-siamo"]


def normalize_vat(vat: str) -> str:
    digits = re.sub(r"\D", "", vat or "")
    return digits[-11:] if len(digits) >= 11 else ""


def find_vat_in_text(text: str) -> list[str]:
    return [m[1] for m in VAT_PATTERN.findall(text) if m[1]]


async def verify(website_url: str, vat: str, company_name: str = "") -> dict:
    vat_normalized = normalize_vat(vat)
    if not vat_normalized:
        return {"verified": False, "error": "Invalid P.IVA"}

    html = await fetch_url(website_url)
    if not html:
        return {"verified": False, "error": "Could not fetch website"}

    vats_found = find_vat_in_text(html)
    confidence = 0.0
    vat_found = None

    if vat_normalized in vats_found:
        confidence = 0.95
        vat_found = vat_normalized
    else:
        for fv in vats_found:
            if fv[-4:] == vat_normalized[-4:]:
                confidence = 0.5

    if confidence < 0.5:
        base = website_url.rstrip("/")
        fails = 0
        for path in _VAT_PAGES:
            page_html = await fetch_url(f"{base}{path}")
            if not page_html:
                fails += 1
                if fails >= 2:
                    break
                continue
            fails = 0
            page_vats = find_vat_in_text(page_html)
            if vat_normalized in page_vats:
                confidence = 0.90
                vat_found = vat_normalized
                vats_found = page_vats
                break

    if confidence == 0.0 and company_name:
        text_lower = html.lower()
        for variant in [company_name.lower(), company_name.lower().replace(".", "")]:
            if variant in text_lower:
                confidence = 0.3
                break

    return {
        "verified": confidence >= 0.5,
        "vat_found": vat_found,
        "confidence": round(confidence, 2),
        "vats_found": vats_found[:5],
        "homepage_text": html,
    }
