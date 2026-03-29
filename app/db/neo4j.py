from neo4j import GraphDatabase

from app.config import get_settings

settings = get_settings()

neo4j_driver = GraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
) if settings.neo4j_uri else None


def get_neo4j_session():
    if neo4j_driver is None:
        raise RuntimeError("Neo4j driver not configured")
    return neo4j_driver.session()
