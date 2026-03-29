"""EU VIES VAT validation (free API)."""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"


@dataclass
class VIESResult:
    valid: bool
    name: str | None
    address: str | None
    country_code: str
    vat_number: str
    error: str | None = None


async def validate_vat(vat: str, country_code: str = "IT") -> VIESResult:
    vat_digits = re.sub(r"\D", "", vat)
    if len(vat_digits) != 11:
        return VIESResult(False, None, None, country_code, vat_digits, "P.IVA must be 11 digits")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(_VIES_URL, json={"countryCode": country_code, "vatNumber": vat_digits})
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return VIESResult(False, None, None, country_code, vat_digits, "VIES timeout")
    except Exception as e:
        logger.warning("VIES validation error: %s", e)
        return VIESResult(False, None, None, country_code, vat_digits, str(e))

    return VIESResult(
        valid=data.get("valid", False),
        name=(data.get("name", "") or "").strip() or None,
        address=(data.get("address", "") or "").strip() or None,
        country_code=country_code,
        vat_number=vat_digits,
    )


def extract_city_from_address(address: str | None) -> str | None:
    if not address:
        return None
    for line in reversed([l.strip() for l in address.split("\n") if l.strip()]):
        m = re.match(r"\d{5}\s+(.+?)(?:\s+[A-Z]{2})?$", line)
        if m:
            return m.group(1).strip()
    return None
