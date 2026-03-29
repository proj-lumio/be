"""Disambiguation engine for company website candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_COMMON_NAMES = frozenset({
    "rossi", "bianchi", "verdi", "ferrari", "russo", "romano", "colombo",
    "ricci", "marino", "greco", "bruno", "gallo", "conti", "costa",
    "giordano", "mancini", "rizzo", "lombardi", "moretti", "barbieri",
    "fontana", "caruso", "mariani", "ferrara", "santoro", "rinaldi",
    "leone", "villa", "longo", "gentile", "martinelli", "vitale",
    "alfa", "beta", "gamma", "delta", "omega", "euro", "italia",
    "global", "tech", "group", "service", "services", "system",
    "systems", "solutions", "consulting", "management", "trading",
})


@dataclass
class DisambiguationResult:
    status: str  # "confirmed" | "ambiguous" | "low_confidence"
    best_url: str | None
    best_score: float
    runner_up_score: float
    candidates_found: int
    signals_used: list[str] = field(default_factory=list)
    scored_candidates: list[dict[str, Any]] = field(default_factory=list)


def score_candidate(
    url: str, title: str, homepage_text: str | None,
    company_name: str, normalized_name: str,
    vat: str = "", citta: str = "", provincia: str = "", regione: str = "",
    ateco_description: str = "", forma_giuridica: str = "",
    vat_verified: bool = False,
) -> tuple[float, list[str]]:
    score = 0.0
    signals = []
    url_lower = url.lower()
    title_lower = (title or "").lower()
    text_lower = (homepage_text or "").lower()

    if vat_verified:
        score += 0.45
        signals.append("vat_match")
    if citta and (citta.lower() in text_lower or citta.lower() in title_lower or citta.lower() in url_lower):
        score += 0.15
        signals.append("city_match")
    if ateco_description and text_lower:
        words = [w.lower() for w in ateco_description.split() if len(w) > 4]
        if words:
            matches = sum(1 for w in words if w in text_lower)
            if matches:
                score += 0.10 * min(matches / len(words), 1.0)
                signals.append("ateco_match")
    if normalized_name and normalized_name in title_lower:
        score += 0.10
        signals.append("name_in_title")
    if forma_giuridica and forma_giuridica.lower() in text_lower:
        score += 0.05
        signals.append("legal_form_match")
    if text_lower:
        if provincia and provincia.lower() in text_lower:
            score += 0.05
            signals.append("province_match")
        elif regione and regione.lower() in text_lower:
            score += 0.05
            signals.append("region_match")
    if normalized_name:
        slug = re.sub(r"[^a-z0-9]", "", normalized_name)
        if slug and slug in url_lower.replace("www.", ""):
            score += 0.05
            signals.append("name_in_url")
    if normalized_name and (len(normalized_name) < 5 or normalized_name in _COMMON_NAMES):
        score -= 0.15
        signals.append("common_name_penalty")

    return max(score, 0.0), signals


def disambiguate(
    candidates: list[dict], company_name: str, normalized_name: str,
    vat: str = "", citta: str = "", provincia: str = "", regione: str = "",
    ateco_description: str = "", forma_giuridica: str = "",
) -> DisambiguationResult:
    if not candidates:
        return DisambiguationResult("low_confidence", None, 0.0, 0.0, 0)

    any_vat = any(c.get("vat_verified") for c in candidates)
    scored = []
    for c in candidates:
        s, sigs = score_candidate(
            c.get("url", ""), c.get("nome", ""), c.get("homepage_text"),
            company_name, normalized_name, vat, citta, provincia, regione,
            ateco_description, forma_giuridica, c.get("vat_verified", False),
        )
        if vat and any_vat and not c.get("vat_verified"):
            s = max(s - 0.20, 0.0)
            sigs.append("no_vat_penalty")
        scored.append({"url": c.get("url"), "nome": c.get("nome"), "disambiguation_score": round(s, 3), "signals": sigs})

    scored.sort(key=lambda x: x["disambiguation_score"], reverse=True)
    best = scored[0]["disambiguation_score"]
    runner = scored[1]["disambiguation_score"] if len(scored) > 1 else 0.0

    if best < 0.3:
        status = "low_confidence"
    elif len(scored) > 1 and (best - runner) < 0.1:
        status = "ambiguous"
    else:
        status = "confirmed"

    return DisambiguationResult(status, scored[0]["url"], round(best, 3), round(runner, 3), len(scored), scored[0]["signals"], scored[:5])
