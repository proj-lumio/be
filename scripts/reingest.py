"""Re-ingest all documents from mock_data/ with full pipeline (parallel).

Usage: python -m scripts.reingest
"""

import asyncio
import logging
import time
from pathlib import Path

from bson import ObjectId

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reingest")


async def main():
    from app.db.mongo import get_db, init_indexes
    from app.config import get_settings

    settings = get_settings()
    db = get_db()
    await init_indexes()

    # 1. Get all companies
    companies = []
    async for c in db.companies.find():
        companies.append(c)
    logger.info(f"Found {len(companies)} companies")

    for company in companies:
        cid = company["_id"]
        cid_str = str(cid)
        cname = company.get("name", cid_str)
        logger.info(f"\n{'='*60}\nCompany: {cname} ({cid_str})\n{'='*60}")

        # 2. Wipe derived data
        logger.info("Wiping document_chunks...")
        r = await db.document_chunks.delete_many({"company_id": cid})
        logger.info(f"  Deleted {r.deleted_count} chunks")

        logger.info("Wiping contract_analyses...")
        r = await db.contract_analyses.delete_many({"company_id": cid})
        logger.info(f"  Deleted {r.deleted_count} contract analyses")

        logger.info("Wiping Qdrant vectors...")
        if settings.qdrant_url:
            try:
                from app.services.vector_store import delete_company_vectors
                await delete_company_vectors(cid_str)
                logger.info("  Qdrant cleared")
            except Exception as e:
                logger.warning(f"  Qdrant wipe failed: {e}")

        logger.info("Wiping Neo4j graph...")
        if settings.neo4j_uri:
            try:
                from app.services.graph_store import delete_company_graph
                delete_company_graph(cid_str)
                logger.info("  Neo4j cleared")
            except Exception as e:
                logger.warning(f"  Neo4j wipe failed: {e}")

        # 3. Find documents and match to files on disk
        docs = []
        async for d in db.documents.find({"company_id": cid}):
            docs.append(d)
        logger.info(f"Found {len(docs)} documents to re-process")

        # Try to find files in mock_data/
        mock_dirs = list(Path("mock_data").glob("*")) if Path("mock_data").exists() else []
        file_map = {}
        for d in mock_dirs:
            for f in d.glob("*.docx"):
                file_map[f.name] = f

        batch = []
        for doc in docs:
            fname = doc["filename"]
            fpath = file_map.get(fname)
            if fpath and fpath.exists():
                file_bytes = fpath.read_bytes()
                batch.append((str(doc["_id"]), file_bytes))
            elif doc.get("raw_text"):
                # No file on disk but raw_text exists — re-process from raw_text
                # Reset status so process_document can re-extract from stored text
                logger.warning(f"  {fname}: no file on disk, will use stored raw_text")
                batch.append((str(doc["_id"]), None))
            else:
                logger.warning(f"  {fname}: no file on disk and no raw_text, skipping")

        # Reset all document statuses
        await db.documents.update_many(
            {"company_id": cid},
            {"$set": {"processing_status": "pending", "error_message": None}},
        )

        # 4. Re-ingest in parallel
        if batch:
            from app.services.ingestion import process_documents_batch, process_document

            # Filter out None bytes — those need special handling
            real_batch = [(did, fb) for did, fb in batch if fb is not None]
            text_only = [(did, fb) for did, fb in batch if fb is None]

            if real_batch:
                logger.info(f"Starting parallel ingestion of {len(real_batch)} documents (from files)...")
                t0 = time.time()
                await process_documents_batch(real_batch)
                elapsed = time.time() - t0
                logger.info(f"Batch ingestion completed in {elapsed:.1f}s ({len(real_batch)} docs, {elapsed/len(real_batch):.1f}s avg)")

            # For docs with only raw_text, re-run just the contract analysis + graph steps
            for did, _ in text_only:
                doc = await db.documents.find_one({"_id": ObjectId(did)})
                if doc and doc.get("raw_text"):
                    raw_text = doc["raw_text"]
                    company_id = str(doc["company_id"])

                    # Re-run entity extraction
                    if settings.neo4j_uri:
                        try:
                            from app.services.llm import extract_entities
                            from app.services.graph_store import store_entities_and_relations
                            extracted = await extract_entities(raw_text[:8000])
                            entities = extracted.get("entities", [])
                            relationships = extracted.get("relationships", [])
                            if entities:
                                store_entities_and_relations(company_id, did, entities, relationships)
                        except Exception as e:
                            logger.warning(f"  GraphRAG failed for {did}: {e}")

                    # Re-run contract analysis
                    try:
                        from app.services.llm import extract_contract_data
                        contract = await extract_contract_data(raw_text)
                        if contract:
                            from datetime import datetime, timezone
                            contract.update({
                                "document_id": ObjectId(did),
                                "company_id": doc["company_id"],
                                "created_at": datetime.now(timezone.utc),
                                "updated_at": datetime.now(timezone.utc),
                                "criticality_manual": None,
                            })
                            await db.contract_analyses.update_one(
                                {"document_id": ObjectId(did)},
                                {"$set": contract},
                                upsert=True,
                            )
                    except Exception as e:
                        logger.warning(f"  Contract analysis failed for {did}: {e}")

                    await db.documents.update_one(
                        {"_id": ObjectId(did)},
                        {"$set": {"processing_status": "completed"}},
                    )

        # 5. Recompute rankings
        from app.services.ranking import compute_ranking, compute_client_score
        score = await compute_ranking(cid_str)
        client = await compute_client_score(cid_str)
        logger.info(f"Rankings: data_richness={score}, client_score={client['client_score']}, contracts={client['contract_count']}")

    logger.info("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
