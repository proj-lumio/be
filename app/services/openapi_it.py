"""OpenAPI IT Company Advanced — async client for Italian company lookup by P.IVA."""

import logging
from datetime import datetime, timezone

import httpx
from bson import ObjectId

from app.config import get_settings
from app.db.mongo import get_db

logger = logging.getLogger(__name__)
settings = get_settings()

TIMEOUT = 10


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def _format_company_data(raw_data: dict) -> dict:
    """Map OpenAPI camelCase response to our snake_case schema."""
    data_list = raw_data.get("data", [])
    if not data_list:
        return {}

    c = data_list[0]

    addr = c.get("address", {}).get("registeredOffice", {}) or {}
    ateco_data = c.get("atecoClassification", {}) or {}
    balance_sheets = c.get("balanceSheets", {}) or {}
    last_balance = balance_sheets.get("last", {}) if isinstance(balance_sheets, dict) else {}

    gps = addr.get("gps", {}) or {}
    coords = gps.get("coordinates", [None, None]) or [None, None]

    street_parts = []
    if addr.get("toponym"):
        street_parts.append(addr["toponym"])
    if addr.get("street"):
        street_parts.append(addr["street"])
    if addr.get("streetNumber"):
        street_parts.append(addr["streetNumber"])

    ateco_main = ateco_data.get("ateco", {}) or {}
    ateco_2022 = ateco_data.get("ateco2022", {}) or {}
    ateco_2007 = ateco_data.get("ateco2007", {}) or {}

    bilanci = []
    if isinstance(balance_sheets.get("all"), list):
        for b in balance_sheets["all"]:
            bilanci.append({
                "year": b.get("year"),
                "employees": b.get("employees"),
                "balanceSheetDate": b.get("balanceSheetDate"),
                "turnover": b.get("turnover"),
                "netWorth": b.get("netWorth"),
                "shareCapital": b.get("shareCapital"),
                "totalStaffCost": b.get("totalStaffCost"),
                "totalAssets": b.get("totalAssets"),
                "avgGrossSalary": b.get("avgGrossSalary"),
            })

    azionisti = []
    if isinstance(c.get("shareHolders"), list):
        for s in c["shareHolders"]:
            azionisti.append({
                "companyName": s.get("companyName"),
                "name": s.get("name"),
                "surname": s.get("surname"),
                "taxCode": s.get("taxCode"),
                "percentShare": s.get("percentShare"),
            })

    gruppo_iva_raw = c.get("gruppo_iva", {})

    return {
        "piva": c.get("vatCode", c.get("taxCode", "")),
        "ragione_sociale": c.get("companyName", ""),
        "forma_giuridica": (c.get("detailedLegalForm", {}) or {}).get("description", ""),
        "data_costituzione": _parse_date(c.get("registrationDate")),
        "indirizzo": " ".join(street_parts) if street_parts else addr.get("streetName", ""),
        "cap": addr.get("zipCode", ""),
        "citta": addr.get("town", ""),
        "provincia": addr.get("province", ""),
        "regione": (addr.get("region", {}) or {}).get("description", ""),
        "ateco": ateco_main.get("code", ""),
        "ateco_description": ateco_main.get("description", ""),
        "ateco_2022": f"{ateco_2022.get('code', '')} - {ateco_2022.get('description', '')}".strip(" -"),
        "ateco_2007": f"{ateco_2007.get('code', '')} - {ateco_2007.get('description', '')}".strip(" -"),
        "dipendenti": last_balance.get("employees", 0),
        "fatturato": last_balance.get("turnover", 0),
        "capitale_sociale": last_balance.get("shareCapital", 0),
        "pec": c.get("pec", ""),
        "sdi": c.get("sdiCode", ""),
        "stato_attivita": c.get("activityStatus", ""),
        "rea_code": c.get("reaCode", ""),
        "cciaa": c.get("cciaa", ""),
        "codice_catastale": addr.get("townCode", ""),
        "latitude": coords[1] if len(coords) > 1 else None,
        "longitude": coords[0] if len(coords) > 0 else None,
        "data_inizio_attivita": _parse_date(c.get("startDate")),
        "data_chiusura": _parse_date(c.get("endDate")),
        "cessata": c.get("cessata", False),
        "gruppo_iva": {
            "vatGroupParticipation": gruppo_iva_raw.get("vatGroupParticipation", False),
            "isVatGroupLeader": gruppo_iva_raw.get("isVatGroupLeader", False),
            "registryOk": gruppo_iva_raw.get("registryOk", True),
        } if gruppo_iva_raw else None,
        "bilanci": bilanci,
        "azionisti": azionisti,
    }


async def lookup_by_vat(vat_number: str, user_id: str | None = None) -> dict:
    """Lookup Italian company by P.IVA. Returns {success, error, message, data}."""
    db = get_db()

    # Check cache
    if user_id:
        cached = await db.company_lookup_cache.find_one(
            {"user_id": user_id, "vat_number": vat_number}
        )
        if cached:
            logger.info("Cache hit for P.IVA %s", vat_number)
            return {"success": True, "error": None, "message": "Dati dalla cache", "data": cached["response_data"]}

    api_key = settings.openapi_it_api_key
    if not api_key:
        return {"success": False, "error": "API_KEY_MISSING", "message": "OpenAPI IT API key not configured", "data": None}

    url = f"{settings.openapi_it_base_url}/{vat_number}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 200:
            formatted = _format_company_data(resp.json())
            if not formatted.get("ragione_sociale") and not formatted.get("piva"):
                return {"success": False, "error": "DATA_INCOMPLETE", "message": "P.IVA found but company data incomplete", "data": None}

            # Save to cache
            if user_id:
                await db.company_lookup_cache.update_one(
                    {"user_id": user_id, "vat_number": vat_number},
                    {"$set": {"response_data": formatted, "updated_at": datetime.now(timezone.utc)}},
                    upsert=True,
                )

            return {"success": True, "error": None, "message": "OK", "data": formatted}

        error_map = {
            404: ("NOT_FOUND", "P.IVA not found in Registro Imprese"),
            401: ("UNAUTHORIZED", "Invalid or expired API key"),
            429: ("RATE_LIMIT", "Rate limit exceeded (30/month)"),
            403: ("FORBIDDEN", "Access denied — check your OpenAPI subscription"),
        }
        code, msg = error_map.get(resp.status_code, (f"HTTP_{resp.status_code}", f"Server error: {resp.text[:200]}"))
        return {"success": False, "error": code, "message": msg, "data": None}

    except httpx.TimeoutException:
        return {"success": False, "error": "TIMEOUT", "message": "Request timeout", "data": None}
    except httpx.ConnectError:
        return {"success": False, "error": "CONNECTION_ERROR", "message": "Connection error", "data": None}
    except Exception as e:
        logger.exception("OpenAPI IT lookup failed")
        return {"success": False, "error": "EXCEPTION", "message": str(e), "data": None}


async def enrich_company(company_id: str, vat_number: str, user_id: str | None = None) -> dict:
    """Lookup P.IVA and update company document with all OpenAPI fields.

    Returns {success, error, message, data} where data is the enrichment fields.
    """
    result = await lookup_by_vat(vat_number, user_id=user_id)
    if not result["success"]:
        return result

    db = get_db()
    enrichment = result["data"]
    enrichment["openapi_enriched_at"] = datetime.now(timezone.utc).isoformat()

    # Also set top-level name from ragione_sociale when available
    company = await db.companies.find_one({"_id": ObjectId(company_id)})
    if company and enrichment.get("ragione_sociale"):
        current_name = (company.get("name") or "").strip()
        ragione = enrichment["ragione_sociale"].strip()
        # Always prefer the official ragione_sociale over a user-typed name
        if ragione and current_name.lower() != ragione.lower():
            enrichment["name"] = ragione

    await db.companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {**enrichment, "updated_at": datetime.now(timezone.utc)}},
    )

    return {"success": True, "error": None, "message": "Company enriched", "data": enrichment}
