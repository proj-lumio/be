"""Neo4j graph operations for GraphRAG."""

from app.db.neo4j import get_neo4j_session


def delete_company_graph(company_id: str):
    """Delete all graph data for a company (entities, relationships, document nodes)."""
    with get_neo4j_session() as session:
        session.run(
            """
            MATCH (e:Entity {company_id: $company_id})
            DETACH DELETE e
            """,
            company_id=company_id,
        )
        session.run(
            """
            MATCH (c:Company {id: $company_id})
            DETACH DELETE c
            """,
            company_id=company_id,
        )
        # Clean up orphaned Categoria nodes
        session.run(
            """
            MATCH (cat:Categoria)
            WHERE NOT (cat)<-[:APPARTIENE_A]-()
            DELETE cat
            """
        )


def delete_document_graph(company_id: str, document_id: str):
    """Delete graph data tied to a specific document.

    Removes the Document node, its MENTIONS edges, RELATED_TO edges that
    came from this document, and any Entity nodes left with no remaining
    MENTIONS from other documents.
    """
    with get_neo4j_session() as session:
        # Remove RELATED_TO edges that were created by this document
        session.run(
            """
            MATCH (a:Entity {company_id: $company_id})-[r:RELATED_TO]->(b:Entity {company_id: $company_id})
            WHERE r.document_id = $document_id
            DELETE r
            """,
            company_id=company_id,
            document_id=document_id,
        )
        # Remove Document node (and its MENTIONS edges)
        session.run(
            """
            MATCH (d:Document {id: $document_id})
            DETACH DELETE d
            """,
            document_id=document_id,
        )
        # Remove orphaned entities (no longer mentioned by any document)
        session.run(
            """
            MATCH (e:Entity {company_id: $company_id})
            WHERE NOT (e)<-[:MENTIONS]-(:Document)
            DETACH DELETE e
            """,
            company_id=company_id,
        )


def store_entities_and_relations(
    company_id: str,
    document_id: str,
    entities: list[dict],
    relationships: list[dict],
):
    """Store extracted entities and relationships in Neo4j.

    entities: [{name, type, description}]
    relationships: [{source, target, relation, description}]
    """
    with get_neo4j_session() as session:
        # Create company node if not exists
        session.run(
            "MERGE (c:Company {id: $company_id})",
            company_id=company_id,
        )

        # Create entity nodes and link to company
        for entity in entities:
            session.run(
                """
                MERGE (e:Entity {name: $name, company_id: $company_id})
                SET e.type = $type, e.description = $description
                WITH e
                MATCH (c:Company {id: $company_id})
                MERGE (c)-[:HAS_ENTITY]->(e)
                WITH e
                MERGE (d:Document {id: $document_id})
                MERGE (d)-[:MENTIONS]->(e)
                """,
                name=entity["name"],
                type=entity.get("type", "UNKNOWN"),
                description=entity.get("description", ""),
                company_id=company_id,
                document_id=document_id,
            )

        # Create relationships between entities
        for rel in relationships:
            session.run(
                """
                MATCH (s:Entity {name: $source, company_id: $company_id})
                MATCH (t:Entity {name: $target, company_id: $company_id})
                MERGE (s)-[r:RELATED_TO {type: $relation}]->(t)
                SET r.description = $description, r.document_id = $document_id
                """,
                source=rel["source"],
                target=rel["target"],
                relation=rel.get("relation", "RELATED_TO"),
                description=rel.get("description", ""),
                company_id=company_id,
                document_id=document_id,
            )


def store_company_categories(company_id: str, categories: list[str]):
    """Store macro-categories for a company in Neo4j.

    Creates unique Categoria nodes (MERGE) and links them to the company.
    Multiple companies sharing the same category point to the same node.
    """
    with get_neo4j_session() as session:
        session.run(
            "MERGE (c:Company {id: $company_id})",
            company_id=company_id,
        )
        for cat_name in categories:
            session.run(
                """
                MERGE (cat:Categoria {nome: $nome})
                WITH cat
                MATCH (c:Company {id: $company_id})
                MERGE (c)-[:APPARTIENE_A]->(cat)
                """,
                nome=cat_name,
                company_id=company_id,
            )


def get_companies_by_categories(category_names: list[str]) -> list[str]:
    """Return company IDs that belong to any of the given categories."""
    with get_neo4j_session() as session:
        result = session.run(
            """
            MATCH (c:Company)-[:APPARTIENE_A]->(cat:Categoria)
            WHERE cat.nome IN $category_names
            RETURN DISTINCT c.id AS company_id
            """,
            category_names=category_names,
        )
        return [record["company_id"] for record in result]


def get_company_categories(company_id: str) -> list[str]:
    """Return category names for a company."""
    with get_neo4j_session() as session:
        result = session.run(
            """
            MATCH (c:Company {id: $company_id})-[:APPARTIENE_A]->(cat:Categoria)
            RETURN cat.nome AS nome
            """,
            company_id=company_id,
        )
        return [record["nome"] for record in result]


def query_graph_context(company_id: str, entity_names: list[str], depth: int = 2) -> dict:
    """Traverse the graph to get context around given entities.

    Returns entities and their relationships up to `depth` hops.
    """
    with get_neo4j_session() as session:
        result = session.run(
            """
            MATCH (e:Entity {company_id: $company_id})
            WHERE e.name IN $entity_names
            CALL apoc.path.subgraphAll(e, {maxLevel: $depth})
            YIELD nodes, relationships
            UNWIND nodes AS n
            WITH COLLECT(DISTINCT {name: n.name, type: n.type, description: n.description}) AS entities,
                 relationships
            UNWIND relationships AS r
            RETURN entities,
                   COLLECT(DISTINCT {
                       source: startNode(r).name,
                       target: endNode(r).name,
                       relation: type(r),
                       description: r.description
                   }) AS relationships
            """,
            company_id=company_id,
            entity_names=entity_names,
            depth=depth,
        )
        record = result.single()
        if record:
            return {
                "entities": record["entities"],
                "relationships": record["relationships"],
            }
        return {"entities": [], "relationships": []}


def get_company_graph_summary(company_id: str) -> dict:
    """Get a summary of the company's knowledge graph."""
    with get_neo4j_session() as session:
        result = session.run(
            """
            MATCH (c:Company {id: $company_id})-[:HAS_ENTITY]->(e:Entity)
            WITH c, COLLECT({name: e.name, type: e.type}) AS entities, COUNT(e) AS entity_count
            OPTIONAL MATCH (e1:Entity {company_id: $company_id})-[r]->(e2:Entity {company_id: $company_id})
            WHERE type(r) <> 'HAS_ENTITY'
            RETURN entity_count,
                   entities[..20] AS top_entities,
                   COUNT(r) AS relationship_count
            """,
            company_id=company_id,
        )
        record = result.single()
        if record:
            return {
                "entity_count": record["entity_count"],
                "top_entities": record["top_entities"],
                "relationship_count": record["relationship_count"],
            }
        return {"entity_count": 0, "top_entities": [], "relationship_count": 0}


def get_company_graph_visualization(company_id: str) -> dict:
    """Return full graph data (nodes + edges) for frontend visualization.

    Structure:
        - Center: Company node
        - Secondary: Document nodes
        - Tertiary: Entity nodes (PERSON, ORGANIZATION, etc.)
        - Edges: HAS_DOCUMENT, MENTIONS, RELATED_TO
    """
    nodes = []
    edges = []
    seen_nodes: set[str] = set()

    with get_neo4j_session() as session:
        # Company node
        nodes.append({
            "id": f"company:{company_id}",
            "label": "",  # enriched by the endpoint with the real name
            "group": "company",
        })
        seen_nodes.add(f"company:{company_id}")

        # Categoria nodes linked to the company
        result = session.run(
            """
            MATCH (c:Company {id: $cid})-[:APPARTIENE_A]->(cat:Categoria)
            RETURN cat.nome AS nome
            """,
            cid=company_id,
        )
        for rec in result:
            nid = f"categoria:{rec['nome']}"
            if nid not in seen_nodes:
                nodes.append({
                    "id": nid,
                    "label": rec["nome"],
                    "group": "categoria",
                })
                seen_nodes.add(nid)
            edges.append({
                "source": f"company:{company_id}",
                "target": nid,
                "relation": "APPARTIENE_A",
            })

        # Entities linked to the company
        result = session.run(
            """
            MATCH (c:Company {id: $cid})-[:HAS_ENTITY]->(e:Entity)
            RETURN e.name AS name, e.type AS type, e.description AS desc
            """,
            cid=company_id,
        )
        for rec in result:
            nid = f"entity:{rec['name']}"
            if nid not in seen_nodes:
                nodes.append({
                    "id": nid,
                    "label": rec["name"],
                    "group": "entity",
                    "type": rec["type"] or "UNKNOWN",
                    "description": rec["desc"] or "",
                })
                seen_nodes.add(nid)

        # Documents that mention entities of this company
        result = session.run(
            """
            MATCH (d:Document)-[:MENTIONS]->(e:Entity {company_id: $cid})
            RETURN DISTINCT d.id AS doc_id, COLLECT(DISTINCT e.name) AS entity_names
            """,
            cid=company_id,
        )
        for rec in result:
            did = f"doc:{rec['doc_id']}"
            if did not in seen_nodes:
                nodes.append({
                    "id": did,
                    "label": rec["doc_id"],  # enriched by endpoint
                    "group": "document",
                })
                seen_nodes.add(did)
            # HAS_DOCUMENT edge
            edges.append({
                "source": f"company:{company_id}",
                "target": did,
                "relation": "HAS_DOCUMENT",
            })
            # MENTIONS edges
            for ename in rec["entity_names"]:
                edges.append({
                    "source": did,
                    "target": f"entity:{ename}",
                    "relation": "MENTIONS",
                })

        # Entity-to-entity relationships
        result = session.run(
            """
            MATCH (a:Entity {company_id: $cid})-[r:RELATED_TO]->(b:Entity {company_id: $cid})
            RETURN a.name AS src, b.name AS tgt, r.type AS rel, r.description AS desc
            """,
            cid=company_id,
        )
        for rec in result:
            edges.append({
                "source": f"entity:{rec['src']}",
                "target": f"entity:{rec['tgt']}",
                "relation": rec["rel"] or "RELATED_TO",
                "description": rec["desc"] or "",
            })

    return {"nodes": nodes, "edges": edges}


def get_national_graph_visualization(company_ids: list[str] | None = None) -> dict:
    """Return the full national graph across all (or selected) companies.

    Shows companies, categories, and inter-company relationships via shared categories.
    Entity-level detail is omitted to keep the graph manageable at national scale.
    """
    nodes = []
    edges = []
    seen_nodes: set[str] = set()

    with get_neo4j_session() as session:
        # Company + Categoria nodes and APPARTIENE_A edges
        if company_ids:
            result = session.run(
                """
                MATCH (c:Company)-[:APPARTIENE_A]->(cat:Categoria)
                WHERE c.id IN $cids
                RETURN c.id AS cid, cat.nome AS cat_nome
                """,
                cids=company_ids,
            )
        else:
            result = session.run(
                """
                MATCH (c:Company)-[:APPARTIENE_A]->(cat:Categoria)
                RETURN c.id AS cid, cat.nome AS cat_nome
                """
            )

        for rec in result:
            cid = f"company:{rec['cid']}"
            if cid not in seen_nodes:
                nodes.append({"id": cid, "label": rec["cid"], "group": "company"})
                seen_nodes.add(cid)

            cat_id = f"categoria:{rec['cat_nome']}"
            if cat_id not in seen_nodes:
                nodes.append({"id": cat_id, "label": rec["cat_nome"], "group": "categoria"})
                seen_nodes.add(cat_id)

            edges.append({
                "source": cid,
                "target": cat_id,
                "relation": "APPARTIENE_A",
            })

        # Entity counts per company (for sizing)
        if company_ids:
            result = session.run(
                """
                MATCH (c:Company)-[:HAS_ENTITY]->(e:Entity)
                WHERE c.id IN $cids
                RETURN c.id AS cid, COUNT(e) AS cnt
                """,
                cids=company_ids,
            )
        else:
            result = session.run(
                """
                MATCH (c:Company)-[:HAS_ENTITY]->(e:Entity)
                RETURN c.id AS cid, COUNT(e) AS cnt
                """
            )

        for rec in result:
            nid = f"company:{rec['cid']}"
            # Attach entity_count metadata to existing node
            for node in nodes:
                if node["id"] == nid:
                    node["entity_count"] = rec["cnt"]
                    break

        # Companies without any categories (still show them)
        if company_ids:
            result = session.run(
                """
                MATCH (c:Company)
                WHERE c.id IN $cids AND NOT (c)-[:APPARTIENE_A]->(:Categoria)
                RETURN c.id AS cid
                """,
                cids=company_ids,
            )
        else:
            result = session.run(
                """
                MATCH (c:Company)
                WHERE NOT (c)-[:APPARTIENE_A]->(:Categoria)
                RETURN c.id AS cid
                """
            )

        for rec in result:
            cid = f"company:{rec['cid']}"
            if cid not in seen_nodes:
                nodes.append({"id": cid, "label": rec["cid"], "group": "company"})
                seen_nodes.add(cid)

    return {"nodes": nodes, "edges": edges}


def get_document_connections(company_id: str) -> list[dict]:
    """Find connections between documents via shared entities."""
    with get_neo4j_session() as session:
        result = session.run(
            """
            MATCH (d1:Document)-[:MENTIONS]->(e:Entity {company_id: $company_id})<-[:MENTIONS]-(d2:Document)
            WHERE d1.id < d2.id
            RETURN d1.id AS doc1, d2.id AS doc2,
                   COLLECT(DISTINCT e.name) AS shared_entities,
                   COUNT(e) AS strength
            ORDER BY strength DESC
            LIMIT 50
            """,
            company_id=company_id,
        )
        return [
            {
                "doc1": record["doc1"],
                "doc2": record["doc2"],
                "shared_entities": record["shared_entities"],
                "strength": record["strength"],
            }
            for record in result
        ]
