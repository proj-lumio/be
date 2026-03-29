import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

if settings.qdrant_url:
    qdrant_client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        port=6333,
        https=True,
    )
else:
    qdrant_client = QdrantClient(":memory:")


async def init_qdrant_collection(collection_name: str, vector_size: int = 4096):
    """Create collection if it doesn't exist, then ensure payload indexes."""
    try:
        collections = qdrant_client.get_collections().collections
        existing = [c.name for c in collections]
        if collection_name not in existing:
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {collection_name}")
        else:
            logger.info(f"Qdrant collection already exists: {collection_name}")

        # Ensure payload indexes for filtering
        for field in ("company_id", "document_id"):
            try:
                qdrant_client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # Index already exists
        logger.info("Qdrant payload indexes ensured")
    except Exception as e:
        logger.warning(f"Qdrant init failed: {e}")
