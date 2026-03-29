"""
Enrichment Agent — async pipeline for Italian company data enrichment.

Flow:
1. Validate P.IVA via VIES
2. Search for company website (DuckDuckGo)
3. Verify website (P.IVA on pages) + disambiguate
4. Scrape contacts (email, phone, social)
5. Search trademarks (TMview)
6. Search news (Google News RSS)
7. Fallback social search if needed
8. Synthesize description (Regolo AI)

All steps are async. Uses Regolo AI (gpt-oss-120b) for description synthesis.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.config import get_settings
from app.db.mongo import get_db
from app.services.llm import chat_completion
from app.services.enrichment.shared.normalize import normalize_company_name
from app.services.enrichment.shared.vies import validate_vat, extract_city_from_address
from app.services.enrichment.shared.disambiguator import disambiguate
from app.services.enrichment.shared.http_client import fetch_url
from app.services.enrichment.skills.verify_website import find_vat_in_text, normalize_vat
from app.services.enrichment.skills.search_website import search_website
from app.services.enrichment.skills.verify_website import verify as verify_website
from app.services.enrichment.skills.scrape_contacts import scrape as scrape_contacts
from app.services.enrichment.skills.search_socials import search_socials
from app.services.enrichment.skills.search_news import search_news
from app.services.enrichment.skills.search_trademarks import search_trademarks
from app.services.enrichment.skills.search_sites_by_vat import search_sites_by_vat

logger = logging.getLogger(__name__)
settings = get_settings()

_SYNTHESIS_PROMPT = """Genera una descrizione aziendale professionale in italiano (150-250 parole).

FONTI: Usa SOLO il testo del sito web e il settore ATECO forniti. NON inventare.

STILE:
- Descrivi cosa fa l'azienda, i servizi/prodotti, il settore e i clienti target
- Tono professionale ma scorrevole
- Niente frasi vuote tipo "si distingue per", "all'avanguardia"

Rispondi SOLO in JSON:
{"descrizione": "...", "punti_chiave": ["fatto 1", "fatto 2"], "settore_label": "max 5 parole"}"""


async def _quick_verify_homepage(url: str, vat: str) -> dict:
    """Quick homepage-only P.IVA check for disambiguation."""
    vat_norm = normalize_vat(vat)
    if not vat_norm:
        return {"verified": False, "homepage_text": ""}
    html = await fetch_url(url)
    if not html:
        return {"verified": False, "homepage_text": ""}
    vats = find_vat_in_text(html)
    verified = vat_norm in vats
    return {"verified": verified, "confidence": 0.90 if verified else 0.0, "homepage_text": html}


async def _synthesize_description(company_name: str, ateco: str, homepage_text: str) -> dict:
    """Generate company description using Regolo AI."""
    parts = [f"Azienda: {company_name}"]
    if ateco:
        parts.append(f"Settore ATECO: {ateco}")
    if homepage_text:
        parts.append(f"Testo sito web:\n{homepage_text[:3000]}")

    try:
        import re
        result = await chat_completion(
            [
                {"role": "system", "content": _SYNTHESIS_PROMPT},
                {"role": "user", "content": "\n\n".join(parts)},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        raw = (result.get("content") or "").strip()
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        data = json.loads(raw)
        return {
            "descrizione": data.get("descrizione", ""),
            "punti_chiave": data.get("punti_chiave", []),
            "settore_label": data.get("settore_label", ateco),
        }
    except Exception as e:
        logger.warning("Description synthesis failed: %s", e)
        return {"descrizione": "", "punti_chiave": [], "settore_label": ateco}


async def run_enrichment(
    company_name: str,
    vat: str = "",
    citta: str = "",
    provincia: str = "",
    regione: str = "",
    ateco_description: str = "",
    pec: str = "",
    forma_giuridica: str = "",
) -> dict[str, Any]:
    """Run the full enrichment pipeline. Returns {success, error, data}."""
    start = time.monotonic()
    norm_name = normalize_company_name(company_name)

    result: dict[str, Any] = {
        "website": None,
        "linkedin_url": None,
        "facebook_url": None,
        "instagram_url": None,
        "twitter_url": None,
        "email_aziendale": None,
        "telefono_aziendale": None,
        "descrizione": None,
        "marchi_registrati": [],
        "news_recenti": [],
        "punti_chiave": [],
        "settore_label": ateco_description,
        "confidence_scores": {},
        "disambiguation": {},
    }
    homepage_text = ""

    # ── Step 1: VIES validation ──
    if vat:
        try:
            vies = await validate_vat(vat)
            if vies.valid:
                result["confidence_scores"]["vies_validated"] = 0.9
                logger.info("VIES valid: %s", vies.name)
                if not citta and vies.address:
                    extracted = extract_city_from_address(vies.address)
                    if extracted:
                        citta = extracted
        except Exception as e:
            logger.warning("VIES failed: %s", e)

    # ── Step 2: Search website ──
    try:
        candidates = search_website(company_name, vat, citta, pec, ateco_description)

        if candidates and vat:
            # Quick-verify top 3 candidates
            for c in candidates[:3]:
                try:
                    v = await _quick_verify_homepage(c["url"], vat)
                    c["vat_verified"] = v.get("verified", False)
                    c["homepage_text"] = v.get("homepage_text", "")
                    if v.get("verified"):
                        result["confidence_scores"]["website_verified"] = v["confidence"]
                except Exception:
                    c["vat_verified"] = False

            disambiguation = disambiguate(
                candidates, company_name, norm_name, vat, citta, provincia,
                regione, ateco_description, forma_giuridica,
            )
            result["disambiguation"] = {
                "status": disambiguation.status,
                "candidates_found": disambiguation.candidates_found,
                "top_score": disambiguation.best_score,
                "runner_up_score": disambiguation.runner_up_score,
                "signals_used": disambiguation.signals_used,
            }
            if disambiguation.best_url:
                result["website"] = disambiguation.best_url
                result["confidence_scores"]["website_search"] = disambiguation.best_score
                for c in candidates:
                    if c.get("url") == disambiguation.best_url and c.get("homepage_text"):
                        homepage_text = c["homepage_text"]
                        break
        elif candidates:
            best = candidates[0]
            result["website"] = best.get("url")
            result["confidence_scores"]["website_search"] = best.get("score", 0.5)
    except Exception as e:
        logger.warning("Website search failed: %s", e)

    # ── Step 3: Verify + Scrape contacts ──
    if result["website"]:
        # Verify if not already done during disambiguation
        if vat and "website_verified" not in result["confidence_scores"]:
            try:
                v = await verify_website(result["website"], vat, company_name)
                if v.get("verified"):
                    result["confidence_scores"]["website_verified"] = v.get("confidence", 0.5)
                    if not homepage_text:
                        homepage_text = v.get("homepage_text", "")
            except Exception as e:
                logger.warning("Website verify failed: %s", e)

        # Scrape contacts
        try:
            contacts = await scrape_contacts(result["website"])
            result["email_aziendale"] = contacts.get("email")
            result["telefono_aziendale"] = contacts.get("phone")
            for key in ["linkedin_url", "facebook_url", "instagram_url", "twitter_url"]:
                if contacts.get(key):
                    result[key] = contacts[key]
            result["confidence_scores"]["contacts"] = 0.8 if contacts.get("email") else 0.3
        except Exception as e:
            logger.warning("Contact scrape failed: %s", e)

    # ── Step 4: Fallback — search sites by VAT ──
    if not result["website"]:
        try:
            sites = search_sites_by_vat(company_name, vat, citta, pec)
            for site in sites[:3]:
                if site.get("score", 0) > 0.4:
                    result["website"] = site["url"]
                    result["confidence_scores"]["website_search"] = site.get("score", 0.4)
                    # Try scraping this fallback site
                    try:
                        contacts = await scrape_contacts(site["url"])
                        result["email_aziendale"] = contacts.get("email")
                        result["telefono_aziendale"] = contacts.get("phone")
                        for key in ["linkedin_url", "facebook_url", "instagram_url", "twitter_url"]:
                            if contacts.get(key) and not result.get(key):
                                result[key] = contacts[key]
                    except Exception:
                        pass
                    break
        except Exception as e:
            logger.warning("Sites by VAT search failed: %s", e)

    # ── Step 5: Fallback social search ──
    if not result.get("linkedin_url"):
        try:
            socials = search_socials(company_name)
            for key in ["linkedin_url", "facebook_url", "instagram_url", "twitter_url"]:
                if socials.get(key) and not result.get(key):
                    result[key] = socials[key]
                    result["confidence_scores"][key] = 0.5
        except Exception as e:
            logger.warning("Social search failed: %s", e)

    # ── Step 6: Trademarks ──
    try:
        trademarks = await search_trademarks(company_name)
        result["marchi_registrati"] = [{"nome": t.get("mark_text"), "stato": t.get("status")} for t in trademarks]
        result["confidence_scores"]["trademarks"] = 0.7 if trademarks else 0.2
    except Exception as e:
        logger.warning("Trademark search failed: %s", e)

    # ── Step 7: News ──
    try:
        news = await search_news(company_name, citta)
        result["news_recenti"] = news[:5]
        result["confidence_scores"]["news"] = 0.6 if news else 0.2
    except Exception as e:
        logger.warning("News search failed: %s", e)

    # ── Step 8: Description synthesis ──
    try:
        synth = await _synthesize_description(company_name, ateco_description, homepage_text)
        result["descrizione"] = synth.get("descrizione", "")
        result["punti_chiave"] = synth.get("punti_chiave", [])
        result["settore_label"] = synth.get("settore_label", ateco_description)
        result["confidence_scores"]["description"] = 0.8 if synth.get("descrizione") else 0.3
    except Exception as e:
        logger.warning("Description synthesis failed: %s", e)

    # ── Finalize ──
    duration = round(time.monotonic() - start, 1)
    result["enrichment_duration_seconds"] = duration
    result["enriched_at"] = datetime.now(timezone.utc).isoformat()
    result["enrichment_source"] = "lumio_pipeline_v1"

    enriched = [k for k, v in result.items() if v and k in [
        "website", "email_aziendale", "telefono_aziendale", "linkedin_url",
        "descrizione", "marchi_registrati", "news_recenti",
    ]]
    result["enriched_categories"] = enriched

    logger.info("Enrichment done in %ss. Categories: %s", duration, enriched)
    return {"success": True, "error": None, "data": result}


async def enrich_and_update_company(company_id: str, user_id: str | None = None) -> dict:
    """Run enrichment and save results to the company document in MongoDB."""
    db = get_db()
    company = await db.companies.find_one({"_id": ObjectId(company_id)})
    if not company:
        return {"success": False, "error": "Company not found"}

    result = await run_enrichment(
        company_name=company.get("ragione_sociale") or company.get("name", ""),
        vat=company.get("piva", ""),
        citta=company.get("citta", ""),
        provincia=company.get("provincia", ""),
        regione=company.get("regione", ""),
        ateco_description=company.get("ateco_description", ""),
        pec=company.get("pec", ""),
        forma_giuridica=company.get("forma_giuridica", ""),
    )

    if not result["success"]:
        return result

    data = result["data"]
    update_fields = {}
    for key in ["website", "linkedin_url", "facebook_url", "instagram_url", "twitter_url",
                 "email_aziendale", "telefono_aziendale", "descrizione", "marchi_registrati",
                 "news_recenti", "punti_chiave", "settore_label", "confidence_scores",
                 "disambiguation", "enrichment_duration_seconds", "enriched_at",
                 "enrichment_source", "enriched_categories"]:
        if data.get(key) is not None:
            update_fields[key] = data[key]

    update_fields["updated_at"] = datetime.now(timezone.utc)

    await db.companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": update_fields},
    )

    return result
