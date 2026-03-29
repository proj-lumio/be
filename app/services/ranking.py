"""Company ranking — MongoDB version with client scoring.

Perspective: YOU are the seller. Companies in the system are YOUR CLIENTS.
- client_score: how important/risky this client is to you (revenue, retention, SLA exposure, criticality)
- data richness: how much structured data you have about this client
"""

import math

from bson import ObjectId

from app.config import get_settings
from app.db.mongo import get_db

settings = get_settings()


# ── Data Richness Score (how well you know this client) ──

async def compute_ranking(company_id: str) -> float:
    db = get_db()
    oid = ObjectId(company_id)

    doc_count = await db.documents.count_documents({"company_id": oid, "processing_status": "completed"})

    entity_count, rel_count = 0, 0
    if settings.neo4j_uri:
        try:
            from app.services.graph_store import get_company_graph_summary
            graph = get_company_graph_summary(company_id)
            entity_count = graph.get("entity_count", 0)
            rel_count = graph.get("relationship_count", 0)
        except Exception:
            pass

    doc_score = min(math.log2(doc_count + 1) / 5, 1.0) * 40
    entity_score = min(math.log2(entity_count + 1) / 8, 1.0) * 30
    rel_score = min(math.log2(rel_count + 1) / 8, 1.0) * 30
    total = round(doc_score + entity_score + rel_score, 2)

    await db.companies.update_one({"_id": oid}, {"$set": {"ranking_score": total}})
    return total


# ── Client Score (how important/risky this client is to you) ──

def _compute_single_client_score(contract: dict, max_canone: float) -> dict:
    """Compute client score for a single contract.

    Components (seller perspective):
    - Revenue (35%): how much this client pays you — higher = more important
    - Retention (25%): how locked-in the client is — longer contract, auto-renewal = more secure
    - SLA Exposure (25%): your SLA risk — less protection for you = higher exposure
    - Criticality (15%): strategic importance of this client
    """
    fin = contract.get("financials") or {}
    sla = contract.get("sla") or {}
    terms = contract.get("terms") or {}

    # Revenue (35%) — what this client pays you
    canone = fin.get("canone_annualizzato_eur") or 0
    revenue_score = (canone / max_canone * 35) if max_canone > 0 else 0

    # Retention (25%) — how locked-in the client is to you
    duration = terms.get("duration_months") or 0
    notice = terms.get("notice_days") or 0
    auto_renew = 1.0 if terms.get("auto_renewal") else 0.0
    retention_score = (
        min(duration / 36, 1.0) * 0.4 +
        min(notice / 90, 1.0) * 0.3 +
        auto_renew * 0.3
    ) * 25

    # SLA Exposure (25%) — your risk: less protection = higher exposure
    credit_cap = sla.get("credit_cap_pct") or 0
    uptime_min = sla.get("uptime_minimum_pct") or 0
    liability_cap = terms.get("liability_cap_pct") or 0
    sla_exposure_score = (
        max(1 - credit_cap / 30, 0) * 0.4 +
        max(1 - uptime_min / 100, 0) * 0.3 +
        max(1 - liability_cap / 50, 0) * 0.3
    ) * 25

    # Criticality (15%) — strategic importance of this client
    crit = contract.get("criticality_manual") or contract.get("criticality_auto")
    criticality_score = (crit / 5 * 15) if crit else 0

    total = round(revenue_score + retention_score + sla_exposure_score + criticality_score, 2)

    return {
        "vendor_name": contract.get("vendor_name", "Unknown"),
        "client_score": total,
        "breakdown": {
            "revenue": round(revenue_score, 2),
            "retention": round(retention_score, 2),
            "sla_exposure": round(sla_exposure_score, 2),
            "criticality": round(criticality_score, 2),
        },
        "canone_annualizzato_eur": canone,
    }


async def compute_client_score(company_id: str) -> dict:
    """Compute aggregate client score for a company (your client) from its contracts."""
    db = get_db()
    oid = ObjectId(company_id)

    contracts = []
    async for c in db.contract_analyses.find({"company_id": oid}):
        contracts.append(c)

    if not contracts:
        return {"client_score": 0, "contract_count": 0, "contracts": []}

    max_canone = max(
        (c.get("financials", {}).get("canone_annualizzato_eur") or 0) for c in contracts
    )

    scored = [_compute_single_client_score(c, max_canone) for c in contracts]
    avg_score = round(sum(v["client_score"] for v in scored) / len(scored), 2)
    total_revenue = sum(v["canone_annualizzato_eur"] for v in scored)

    await db.companies.update_one({"_id": oid}, {"$set": {
        "client_score": avg_score,
        "total_annual_revenue_eur": total_revenue,
    }})

    return {
        "client_score": avg_score,
        "total_annual_revenue_eur": total_revenue,
        "contract_count": len(contracts),
        "contracts": sorted(scored, key=lambda v: v["client_score"], reverse=True),
    }


# ── Rankings list ──

async def get_rankings(owner_id, limit: int = 50, offset: int = 0) -> dict:
    db = get_db()
    pipeline = [
        {"$match": {"owner_id": owner_id}},
        {"$lookup": {"from": "documents", "localField": "_id", "foreignField": "company_id", "as": "docs"}},
        {"$lookup": {"from": "contract_analyses", "localField": "_id", "foreignField": "company_id", "as": "contracts"}},
        {"$project": {
            "company_name": "$name",
            "ranking_score": 1,
            "client_score": 1,
            "total_annual_revenue_eur": 1,
            "document_count": {"$size": "$docs"},
            "contract_count": {"$size": "$contracts"},
        }},
        {"$sort": {"client_score": -1, "ranking_score": -1}},
        {"$skip": offset},
        {"$limit": limit},
    ]
    cursor = db.companies.aggregate(pipeline)
    items = []
    async for row in cursor:
        items.append({
            "company_id": str(row["_id"]),
            "company_name": row["company_name"],
            "ranking_score": row.get("ranking_score", 0),
            "client_score": row.get("client_score", 0),
            "total_annual_revenue_eur": row.get("total_annual_revenue_eur", 0),
            "document_count": row["document_count"],
            "contract_count": row["contract_count"],
            "completeness": min(row.get("ranking_score", 0) / 100, 1.0),
        })
    return {"items": items, "total": len(items)}
