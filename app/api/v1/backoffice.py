from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime

from app.config import get_settings
from app.db.mongo import db as mongodb

router = APIRouter()

# ── Auth ──

class BOLoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def bo_login(req: BOLoginRequest):
    s = get_settings()
    if req.email != s.bo_email or req.password != s.bo_password:
        raise HTTPException(401, "Invalid credentials")
    return {"ok": True}


# ── Generic collection helpers ──

def _serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            doc[k] = v.isoformat()
        elif isinstance(v, list):
            doc[k] = [str(i) if isinstance(i, ObjectId) else i for i in v]
    return doc


# ── Collections list ──

@router.get("/collections")
async def list_collections():
    names = await mongodb.list_collection_names()
    result = []
    for name in sorted(names):
        count = await mongodb[name].estimated_document_count()
        result.append({"name": name, "count": count})
    return {"collections": result}


# ── CRUD on any collection ──

@router.get("/collections/{name}/documents")
async def list_documents_in_collection(
    name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    coll = mongodb[name]
    cursor = coll.find().sort("_id", -1).skip(skip).limit(limit)
    items = [_serialize(doc) async for doc in cursor]
    total = await coll.estimated_document_count()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/collections/{name}/documents/{doc_id}")
async def get_document_in_collection(name: str, doc_id: str):
    doc = await mongodb[name].find_one({"_id": ObjectId(doc_id)})
    if not doc:
        raise HTTPException(404, "Document not found")
    return _serialize(doc)


@router.put("/collections/{name}/documents/{doc_id}")
async def update_document_in_collection(name: str, doc_id: str, body: dict):
    body.pop("_id", None)
    result = await mongodb[name].update_one(
        {"_id": ObjectId(doc_id)}, {"$set": body}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Document not found")
    return {"ok": True, "modified": result.modified_count}


@router.delete("/collections/{name}/documents/{doc_id}")
async def delete_document_in_collection(name: str, doc_id: str):
    result = await mongodb[name].delete_one({"_id": ObjectId(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Document not found")
    return {"ok": True}


# ── Knowledge Graph (no auth — BO proxy) ──

@router.get("/graph/national")
async def bo_national_graph():
    settings = get_settings()
    if not settings.neo4j_uri:
        return {"nodes": [], "edges": [], "message": "Neo4j not configured"}

    cursor = mongodb.companies.find({}, {"_id": 1, "name": 1})
    companies = {}
    async for c in cursor:
        companies[str(c["_id"])] = c.get("name", str(c["_id"]))

    if not companies:
        return {"nodes": [], "edges": []}

    from app.services.graph_store import get_national_graph_visualization
    data = get_national_graph_visualization(list(companies.keys()))

    for node in data["nodes"]:
        if node["group"] == "company":
            raw_id = node["id"].replace("company:", "")
            node["label"] = companies.get(raw_id, raw_id)

    return data


@router.get("/graph/{company_id}")
async def bo_company_graph(company_id: str):
    settings = get_settings()
    company = await mongodb.companies.find_one({"_id": ObjectId(company_id)})
    if not company:
        raise HTTPException(404, "Company not found")

    if not settings.neo4j_uri:
        return {"nodes": [], "edges": [], "message": "Neo4j not configured"}

    from app.services.graph_store import get_company_graph_visualization
    data = get_company_graph_visualization(company_id)

    for node in data["nodes"]:
        if node["group"] == "company":
            node["label"] = company.get("name", company_id)
            break

    doc_node_ids = [n["id"] for n in data["nodes"] if n["group"] == "document"]
    if doc_node_ids:
        mongo_doc_ids = [n.replace("doc:", "") for n in doc_node_ids]
        try:
            oids = [ObjectId(did) for did in mongo_doc_ids]
            cursor = mongodb.documents.find({"_id": {"$in": oids}}, {"filename": 1})
            name_map = {}
            async for doc in cursor:
                raw = doc.get("filename", str(doc["_id"]))
                name_map[str(doc["_id"])] = PurePosixPath(raw).stem
            for node in data["nodes"]:
                if node["group"] == "document":
                    raw_id = node["id"].replace("doc:", "")
                    node["label"] = name_map.get(raw_id, raw_id)
        except Exception:
            pass

    return data
