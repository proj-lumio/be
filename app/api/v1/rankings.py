from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.db.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.ranking import get_rankings, compute_ranking, compute_client_score

router = APIRouter()


@router.get("")
async def list_rankings(limit: int = 50, offset: int = 0, user: dict = Depends(get_current_user)):
    return await get_rankings(user["_id"], limit, offset)


@router.post("/{company_id}/recompute")
async def recompute(company_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    company = await db.companies.find_one({"_id": ObjectId(company_id), "owner_id": user["_id"]})
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    score = await compute_ranking(company_id)
    client = await compute_client_score(company_id)
    return {
        "company_id": company_id,
        "ranking_score": score,
        "client": client,
    }
