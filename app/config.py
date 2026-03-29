from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # MongoDB
    mongodb_url: str = ""
    mongodb_db_name: str = "lumio"

    # Qdrant
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "lumio_documents"

    # Neo4j
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # Regolo AI
    regolo_api_key: str = ""
    regolo_base_url: str = "https://api.regolo.ai/v1"
    regolo_model: str = "gpt-oss-120b"

    # JWT Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 10080  # 7 days

    # OpenAPI IT (Company Advanced)
    openapi_it_api_key: str = ""
    openapi_it_base_url: str = "https://company.openapi.com/IT-advanced"

    # Backoffice
    bo_email: str = "admin@lumio.local"
    bo_password: str = "admin"

    # Dev mode
    dev_auth_bypass: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
