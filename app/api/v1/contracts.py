from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.ranking import compute_client_score

router = APIRouter()


class CriticalityUpdate(BaseModel):
    criticality: int = Field(..., ge=1, le=5)


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    doc["company_id"] = str(doc["company_id"])
    doc["document_id"] = str(doc["document_id"])
    return doc


async def _verify_company(company_id: str, user: dict):
    db = get_db()
    company = await db.companies.find_one({"_id": ObjectId(company_id), "owner_id": user["_id"]})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("")
async def list_contracts(company_id: str, user: dict = Depends(get_current_user)):
    await _verify_company(company_id, user)
    db = get_db()
    oid = ObjectId(company_id)
    items = []
    async for c in db.contract_analyses.find({"company_id": oid}).sort("created_at", -1):
        items.append(_serialize(c))
    return {"items": items, "total": len(items)}


@router.get("/client-score")
async def get_client_score_detail(company_id: str, user: dict = Depends(get_current_user)):
    await _verify_company(company_id, user)
    return await compute_client_score(company_id)


@router.patch("/{contract_id}/criticality")
async def set_criticality(
    company_id: str,
    contract_id: str,
    data: CriticalityUpdate,
    user: dict = Depends(get_current_user),
):
    await _verify_company(company_id, user)
    db = get_db()
    result = await db.contract_analyses.find_one_and_update(
        {"_id": ObjectId(contract_id), "company_id": ObjectId(company_id)},
        {"$set": {"criticality_manual": data.criticality}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Contract analysis not found")
    return _serialize(result)
