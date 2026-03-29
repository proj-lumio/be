import logging
from datetime import datetime, timezone
from pathlib import PurePosixPath

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks

from app.db.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.ingestion import detect_doc_type, process_document, process_documents_batch

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024


async def _verify_company(company_id: str, user: dict):
    db = get_db()
    company = await db.companies.find_one({"_id": ObjectId(company_id), "owner_id": user["_id"]})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _display_name(filename: str) -> str:
    return PurePosixPath(filename).stem


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    doc["company_id"] = str(doc["company_id"])
    if "filename" in doc:
        doc["filename"] = _display_name(doc["filename"])
    return doc


@router.get("")
async def list_documents(company_id: str, user: dict = Depends(get_current_user)):
    await _verify_company(company_id, user)
    db = get_db()
    oid = ObjectId(company_id)
    total = await db.documents.count_documents({"company_id": oid})
    cursor = db.documents.find({"company_id": oid}).sort("created_at", -1)
    items = [_serialize(doc) async for doc in cursor]
    return {"items": items, "total": total}


@router.post("", status_code=201)
async def upload_document(
    company_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    await _verify_company(company_id, user)
    db = get_db()

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    doc_type = detect_doc_type(file.filename or "unknown.txt")
    now = datetime.now(timezone.utc)
    doc = {
        "company_id": ObjectId(company_id),
        "filename": file.filename or "unknown",
        "doc_type": doc_type,
        "file_url": "local",
        "file_size": len(file_bytes),
        "raw_text": None,
        "metadata": None,
        "processing_status": "pending",
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.documents.insert_one(doc)
    doc_id = result.inserted_id

    async def _bg():
        try:
            await process_document(str(doc_id), file_bytes)
        except Exception as e:
            logger.exception(f"Background processing failed for {doc_id}: {e}")

    background_tasks.add_task(_bg)

    return {
        "id": str(doc_id),
        "filename": _display_name(doc["filename"]),
        "processing_status": "pending",
        "message": "Document uploaded. Processing started in background.",
    }


@router.post("/multipart", status_code=201)
async def upload_multiple(
    company_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    await _verify_company(company_id, user)
    db = get_db()
    responses = []

    batch: list[tuple[str, bytes]] = []

    for file in files:
        file_bytes = await file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            continue

        doc_type = detect_doc_type(file.filename or "unknown.txt")
        now = datetime.now(timezone.utc)
        doc = {
            "company_id": ObjectId(company_id),
            "filename": file.filename or "unknown",
            "doc_type": doc_type,
            "file_url": "local",
            "file_size": len(file_bytes),
            "processing_status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        result = await db.documents.insert_one(doc)
        doc_id = str(result.inserted_id)
        batch.append((doc_id, file_bytes))
        responses.append({"id": doc_id, "filename": _display_name(doc["filename"]), "processing_status": "pending"})

    skipped = len(files) - len(batch)

    if batch:
        async def _bg():
            try:
                await process_documents_batch(batch)
            except Exception as e:
                logger.exception(f"Batch processing failed: {e}")

        background_tasks.add_task(_bg)

    return {
        "items": responses,
        "total": len(batch),
        "skipped": skipped,
        "message": f"{len(batch)} documents queued for parallel processing (max 10 concurrent).",
    }


@router.get("/{document_id}")
async def get_document(company_id: str, document_id: str, user: dict = Depends(get_current_user)):
    await _verify_company(company_id, user)
    db = get_db()
    doc = await db.documents.find_one({"_id": ObjectId(document_id), "company_id": ObjectId(company_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks_count = await db.document_chunks.count_documents({"document_id": doc["_id"]})
    result = _serialize(doc)
    result["chunks_count"] = chunks_count
    return result


@router.get("/{document_id}/content")
async def get_document_content(company_id: str, document_id: str, user: dict = Depends(get_current_user)):
    await _verify_company(company_id, user)
    db = get_db()
    doc = await db.documents.find_one(
        {"_id": ObjectId(document_id), "company_id": ObjectId(company_id)},
        {"raw_text": 1, "filename": 1, "doc_type": 1, "processing_status": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["processing_status"] != "completed":
        raise HTTPException(status_code=409, detail="Document is still processing")
    return {
        "filename": _display_name(doc["filename"]),
        "doc_type": doc["doc_type"],
        "content": doc.get("raw_text") or "",
    }


@router.delete("/{document_id}", status_code=204)
async def delete_document(company_id: str, document_id: str, user: dict = Depends(get_current_user)):
    await _verify_company(company_id, user)
    db = get_db()
    oid = ObjectId(document_id)
    result = await db.documents.delete_one({"_id": oid, "company_id": ObjectId(company_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.document_chunks.delete_many({"document_id": oid})

    from app.services.vector_store import delete_document_vectors
    await delete_document_vectors(document_id)

    from app.services.graph_store import delete_document_graph
    delete_document_graph(company_id, document_id)
