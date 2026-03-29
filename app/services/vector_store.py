"""Qdrant vector store operations."""

import uuid

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.db.qdrant import qdrant_client
from app.services.llm import get_embeddings

settings = get_settings()
COLLECTION = settings.qdrant_collection


async def upsert_chunks(
    chunks: list[dict],
    company_id: str,
    document_id: str,
) -> list[str]:
    """Embed and store document chunks in Qdrant.

    Each chunk dict must have 'content' and 'chunk_index'.
    Returns list of point IDs.
    """
    texts = [c["content"] for c in chunks]
    embeddings = await get_embeddings(texts)

    points = []
    point_ids = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        point_ids.append(point_id)
        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "company_id": company_id,
                    "document_id": document_id,
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"],
                },
            )
        )

    qdrant_client.upsert(collection_name=COLLECTION, points=points)
    return point_ids


async def search_similar(
    query: str,
    company_id: str,
    limit: int = 5,
) -> list[dict]:
    """Search for similar chunks within a company's documents."""
    query_embedding = (await get_embeddings([query]))[0]

    results = qdrant_client.query_points(
        collection_name=COLLECTION,
        query=query_embedding,
        query_filter=Filter(
            must=[FieldCondition(key="company_id", match=MatchValue(value=company_id))]
        ),
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "point_id": str(hit.id),
            "score": hit.score,
            "content": hit.payload.get("content", ""),
            "document_id": hit.payload.get("document_id", ""),
            "chunk_index": hit.payload.get("chunk_index", 0),
        }
        for hit in results.points
    ]


async def search_similar_multi_company(
    query: str,
    company_ids: list[str],
    limit: int = 10,
) -> list[dict]:
    """Search for similar chunks across multiple companies' documents."""
    if not company_ids:
        return []

    query_embedding = (await get_embeddings([query]))[0]

    results = qdrant_client.query_points(
        collection_name=COLLECTION,
        query=query_embedding,
        query_filter=Filter(
            should=[
                FieldCondition(key="company_id", match=MatchValue(value=cid))
                for cid in company_ids
            ]
        ),
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "point_id": str(hit.id),
            "score": hit.score,
            "content": hit.payload.get("content", ""),
            "document_id": hit.payload.get("document_id", ""),
            "company_id": hit.payload.get("company_id", ""),
            "chunk_index": hit.payload.get("chunk_index", 0),
        }
        for hit in results.points
    ]


async def delete_document_vectors(document_id: str):
    """Remove all vectors for a specific document."""
    qdrant_client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
    )


async def delete_company_vectors(company_id: str):
    """Remove all vectors for a company."""
    qdrant_client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="company_id", match=MatchValue(value=company_id))]
        ),
    )
