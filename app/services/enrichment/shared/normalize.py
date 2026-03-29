"""Company name normalization and PEC domain extraction."""

from __future__ import annotations

import re

_LEGAL_SUFFIXES = [
    r"\s*s\.?r\.?l\.?s?\.?", r"\s*s\.?c\.?a\.?r\.?l\.?", r"\s*s\.?c\.?r\.?l\.?",
    r"\s*s\.?p\.?a\.?", r"\s*s\.?a\.?s\.?", r"\s*s\.?n\.?c\.?", r"\s*d\.?i\.?",
    r"\s*s\.?s\.?", r"\s*coop(?:erativa)?\.?", r"\s*onlus", r"\s*consorzio",
    r"\s*associazione", r"\s*fondazione", r"\s*impresa\s", r"\s*società\s",
]


def normalize_company_name(name: str) -> str:
    if not name:
        return ""
    result = name.lower().strip()
    for suffix in _LEGAL_SUFFIXES:
        result = re.sub(suffix, " ", result, flags=re.IGNORECASE)
    result = re.sub(r"[^\w\s]", " ", result)
    return " ".join(result.split()).strip()


def company_name_words(name: str, min_length: int = 3) -> list[str]:
    return [w for w in normalize_company_name(name).split() if len(w) >= min_length]


def name_matches_handle(company_name: str, handle: str) -> bool:
    norm = normalize_company_name(company_name)
    if not norm:
        return False
    handle_lower = handle.lower()
    segments = re.split(r"[-_.\s]+", handle_lower)
    for word in norm.split():
        if len(word) < 3:
            continue
        if word in segments:
            return True
        if norm.replace(" ", "") == handle_lower.replace("-", "").replace("_", "").replace(".", ""):
            return True
    return False


_PEC_PROVIDERS = frozenset({
    "arubapec.it", "pec.aruba.it", "legalmail.it", "postecert.it", "pec.it",
    "sicurezzapostale.it", "pec.buffetti.it", "registerpec.it", "pec.cgn.it",
    "pec.infocamere.it", "pec.actalis.it", "pecprofessionisti.it", "pec.libero.it",
    "pec.namirial.com", "pecsicura.it",
})


def extract_domain_from_pec(pec: str) -> str | None:
    if not pec or "@" not in pec:
        return None
    domain = pec.split("@")[-1].lower()
    if domain in _PEC_PROVIDERS:
        return None
    for provider in _PEC_PROVIDERS:
        if domain.endswith("." + provider):
            return None
    if domain.endswith(".pec.it"):
        base = domain.replace(".pec.it", "")
        if base in ("aruba", "legalmail", "postecert"):
            return None
        return base
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.split(".")[0] if "." in domain else domain
