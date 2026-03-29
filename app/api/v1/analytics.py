from pathlib import PurePosixPath

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.db.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.analytics_service import get_analytics_dashboard

router = APIRouter()
settings = get_settings()


@router.get("")
async def analytics_dashboard(days: int = 30, user: dict = Depends(get_current_user)):
    return await get_analytics_dashboard(user["_id"], days)


@router.get("/graph/national")
async def national_graph(user: dict = Depends(get_current_user)):
    """Return the full national knowledge graph across all user companies."""
    db = get_db()
    settings_ = get_settings()

    if not settings_.neo4j_uri:
        return {"nodes": [], "edges": [], "message": "Neo4j not configured"}

    # Get all company IDs owned by this user
    cursor = db.companies.find({"owner_id": user["_id"]}, {"_id": 1, "name": 1})
    companies = {}
    async for c in cursor:
        companies[str(c["_id"])] = c.get("name", str(c["_id"]))

    if not companies:
        return {"nodes": [], "edges": []}

    from app.services.graph_store import get_national_graph_visualization

    data = get_national_graph_visualization(list(companies.keys()))

    # Enrich company labels with real names
    for node in data["nodes"]:
        if node["group"] == "company":
            raw_id = node["id"].replace("company:", "")
            node["label"] = companies.get(raw_id, raw_id)

    return data


@router.get("/graph/{company_id}")
async def company_graph(company_id: str, user: dict = Depends(get_current_user)):
    """Return the knowledge graph for a company, structured for visualization.

    - Center: company node
    - Secondary: document nodes
    - Tertiary: entity nodes
    - Edges: HAS_DOCUMENT, MENTIONS, RELATED_TO
    """
    db = get_db()

    # Verify company belongs to user
    company = await db.companies.find_one({"_id": ObjectId(company_id), "owner_id": user["_id"]})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not settings.neo4j_uri:
        return {"nodes": [], "edges": [], "message": "Neo4j not configured"}

    from app.services.graph_store import get_company_graph_visualization

    data = get_company_graph_visualization(company_id)

    # Enrich company node label
    for node in data["nodes"]:
        if node["group"] == "company":
            node["label"] = company.get("name", company_id)
            break

    # Enrich document labels with filenames from MongoDB
    doc_node_ids = [n["id"] for n in data["nodes"] if n["group"] == "document"]
    if doc_node_ids:
        mongo_doc_ids = [n.replace("doc:", "") for n in doc_node_ids]
        # Try to fetch document metadata
        try:
            oids = [ObjectId(did) for did in mongo_doc_ids]
            cursor = db.documents.find({"_id": {"$in": oids}}, {"filename": 1})
            name_map = {}
            async for doc in cursor:
                raw = doc.get("filename", str(doc["_id"]))
                name_map[str(doc["_id"])] = PurePosixPath(raw).stem
            for node in data["nodes"]:
                if node["group"] == "document":
                    raw_id = node["id"].replace("doc:", "")
                    node["label"] = name_map.get(raw_id, raw_id)
        except Exception:
            pass  # keep raw IDs as labels

    return data
