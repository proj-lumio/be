from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.db.mongo import get_db
from app.middleware.auth import get_current_user
from app.schemas.company import CompanyCreate, CompanyUpdate

router = APIRouter()


async def _enrich_background(company_id: str, piva: str, user_id: str):
    """Background task: OpenAPI IT registry + full web enrichment."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.services.openapi_it import enrich_company
        await enrich_company(company_id, piva, user_id=user_id)
        logger.info("Registry enrichment done for %s", company_id)
    except Exception as e:
        logger.warning("Registry enrichment failed for %s: %s", company_id, e)
    try:
        from app.services.enrichment.agent import enrich_and_update_company
        await enrich_and_update_company(company_id, user_id=user_id)
        logger.info("Web enrichment done for %s", company_id)
    except Exception as e:
        logger.warning("Web enrichment failed for %s: %s", company_id, e)


def _s(doc: dict) -> dict:
    """Serialize MongoDB doc → JSON-safe dict."""
    doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@router.get("")
async def list_companies(page: int = 1, page_size: int = 20, search: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    query = {"owner_id": user["_id"]}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    total = await db.companies.count_documents(query)
    cursor = db.companies.find(query).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    items = [_s(doc) async for doc in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_company(data: CompanyCreate, bg: BackgroundTasks, user: dict = Depends(get_current_user)):
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {**data.model_dump(), "owner_id": user["_id"], "ranking_score": 0.0, "created_at": now, "updated_at": now}
    result = await db.companies.insert_one(doc)
    doc["_id"] = result.inserted_id
    company_id = str(result.inserted_id)
    user_id = str(user["_id"])

    # Auto-enrich in background if P.IVA is provided
    if data.piva:
        bg.add_task(_enrich_background, company_id, data.piva, user_id)

    return _s(doc)


@router.get("/{company_id}")
async def get_company(company_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.companies.find_one({"_id": ObjectId(company_id), "owner_id": user["_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Company not found")
    return _s(doc)


@router.patch("/{company_id}")
async def update_company(company_id: str, data: CompanyUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db.companies.find_one_and_update(
        {"_id": ObjectId(company_id), "owner_id": user["_id"]},
        {"$set": updates}, return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Company not found")
    return _s(result)


@router.post("/{company_id}/enrich")
async def enrich_company(company_id: str, data: dict = None, user: dict = Depends(get_current_user)):
    """Enrich company with OpenAPI IT registry data (by P.IVA) + full web enrichment
    (website, contacts, social, news, trademarks, description)."""
    db = get_db()
    data = data or {}
    company = await db.companies.find_one({"_id": ObjectId(company_id), "owner_id": user["_id"]})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    vat_number = data.get("vat_number") or company.get("piva")
    if not vat_number:
        raise HTTPException(status_code=400, detail="vat_number is required (or company must have piva set)")

    # Step 1: OpenAPI IT registry enrichment
    from app.services.openapi_it import enrich_company as registry_enrich
    registry_result = await registry_enrich(company_id, vat_number, user_id=str(user["_id"]))
    if not registry_result["success"]:
        raise HTTPException(status_code=502, detail=registry_result["message"])

    # Step 2: Full web enrichment (website, contacts, social, news, trademarks, description)
    from app.services.enrichment.agent import enrich_and_update_company
    await enrich_and_update_company(company_id, user_id=str(user["_id"]))

    updated = await db.companies.find_one({"_id": ObjectId(company_id)})
    return _s(updated)


@router.delete("/{company_id}", status_code=204)
async def delete_company(company_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    oid = ObjectId(company_id)
    result = await db.companies.delete_one({"_id": oid, "owner_id": user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.documents.delete_many({"company_id": oid})
    await db.document_chunks.delete_many({"company_id": oid})
    await db.chat_sessions.delete_many({"company_id": oid})

    from app.services.vector_store import delete_company_vectors
    await delete_company_vectors(company_id)

    from app.services.graph_store import delete_company_graph
    delete_company_graph(company_id)
