"""Public landing page endpoints — no authentication required."""

from fastapi import APIRouter

router = APIRouter()

# ── Mock graph for landing page hero section ──
# All data is fictional — no real customer data is ever exposed.

MOCK_GRAPH = {
    "nodes": [
        # Companies
        {"id": "company:A", "label": "Meridian Srl", "group": "company"},
        {"id": "company:B", "label": "Vortex SpA", "group": "company"},
        # Documents — Meridian
        {"id": "doc:A1", "label": "Contratto Fornitura 2025", "group": "document"},
        {"id": "doc:A2", "label": "Report Trimestrale Q3", "group": "document"},
        {"id": "doc:A3", "label": "Verbale CdA Ottobre", "group": "document"},
        # Documents — Vortex
        {"id": "doc:B1", "label": "Accordo Quadro Cloud", "group": "document"},
        {"id": "doc:B2", "label": "Audit Sicurezza 2025", "group": "document"},
        # Entities — People
        {"id": "entity:p1", "label": "Marco Rinaldi", "group": "entity", "type": "PERSON"},
        {"id": "entity:p2", "label": "Elena Ferrara", "group": "entity", "type": "PERSON"},
        {"id": "entity:p3", "label": "Luca De Santis", "group": "entity", "type": "PERSON"},
        # Entities — Organizations
        {"id": "entity:o1", "label": "Meridian Srl", "group": "entity", "type": "ORGANIZATION"},
        {"id": "entity:o2", "label": "Vortex SpA", "group": "entity", "type": "ORGANIZATION"},
        {"id": "entity:o3", "label": "CloudBase EU", "group": "entity", "type": "ORGANIZATION"},
        # Entities — Products
        {"id": "entity:pr1", "label": "Piattaforma Atlas", "group": "entity", "type": "PRODUCT"},
        {"id": "entity:pr2", "label": "Suite Sentinel", "group": "entity", "type": "PRODUCT"},
        # Entities — Concepts / Metrics
        {"id": "entity:c1", "label": "SLA 99.9%", "group": "entity", "type": "METRIC"},
        {"id": "entity:c2", "label": "GDPR Compliance", "group": "entity", "type": "CONCEPT"},
        {"id": "entity:c3", "label": "Canone Annuale", "group": "entity", "type": "METRIC"},
        # Entities — Locations / Dates
        {"id": "entity:l1", "label": "Milano", "group": "entity", "type": "LOCATION"},
        {"id": "entity:d1", "label": "15/09/2025", "group": "entity", "type": "DATE"},
    ],
    "edges": [
        # Company → Documents
        {"source": "company:A", "target": "doc:A1", "relation": "HAS_DOCUMENT"},
        {"source": "company:A", "target": "doc:A2", "relation": "HAS_DOCUMENT"},
        {"source": "company:A", "target": "doc:A3", "relation": "HAS_DOCUMENT"},
        {"source": "company:B", "target": "doc:B1", "relation": "HAS_DOCUMENT"},
        {"source": "company:B", "target": "doc:B2", "relation": "HAS_DOCUMENT"},
        # Documents → Entities (MENTIONS)
        {"source": "doc:A1", "target": "entity:p1", "relation": "MENTIONS"},
        {"source": "doc:A1", "target": "entity:o1", "relation": "MENTIONS"},
        {"source": "doc:A1", "target": "entity:pr1", "relation": "MENTIONS"},
        {"source": "doc:A1", "target": "entity:c3", "relation": "MENTIONS"},
        {"source": "doc:A2", "target": "entity:p2", "relation": "MENTIONS"},
        {"source": "doc:A2", "target": "entity:c1", "relation": "MENTIONS"},
        {"source": "doc:A2", "target": "entity:d1", "relation": "MENTIONS"},
        {"source": "doc:A3", "target": "entity:p1", "relation": "MENTIONS"},
        {"source": "doc:A3", "target": "entity:p2", "relation": "MENTIONS"},
        {"source": "doc:A3", "target": "entity:l1", "relation": "MENTIONS"},
        {"source": "doc:B1", "target": "entity:p3", "relation": "MENTIONS"},
        {"source": "doc:B1", "target": "entity:o2", "relation": "MENTIONS"},
        {"source": "doc:B1", "target": "entity:o3", "relation": "MENTIONS"},
        {"source": "doc:B1", "target": "entity:pr1", "relation": "MENTIONS"},
        {"source": "doc:B1", "target": "entity:c2", "relation": "MENTIONS"},
        {"source": "doc:B2", "target": "entity:pr2", "relation": "MENTIONS"},
        {"source": "doc:B2", "target": "entity:c1", "relation": "MENTIONS"},
        {"source": "doc:B2", "target": "entity:c2", "relation": "MENTIONS"},
        # Entity → Entity (RELATED_TO)
        {"source": "entity:p1", "target": "entity:o1", "relation": "CEO_OF"},
        {"source": "entity:p3", "target": "entity:o2", "relation": "CTO_OF"},
        {"source": "entity:o2", "target": "entity:o3", "relation": "PARTNER"},
        {"source": "entity:pr1", "target": "entity:pr2", "relation": "INTEGRATES"},
        {"source": "entity:p2", "target": "entity:l1", "relation": "BASED_IN"},
    ],
}


@router.get("/graph")
async def landing_graph():
    """Public mock knowledge graph for the landing page hero visualization.

    Returns a realistic-looking graph with fictional companies, documents,
    and entities. No real customer data is exposed.
    """
    return MOCK_GRAPH
