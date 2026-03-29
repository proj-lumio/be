from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.v1.router import api_router


CORS_HEADERS = [
    (b"access-control-allow-origin", b"*"),
    (b"access-control-allow-credentials", b"true"),
    (b"access-control-allow-methods", b"*"),
    (b"access-control-allow-headers", b"*"),
    (b"access-control-expose-headers", b"X-Refreshed-Token"),
]


class CORSMiddleware:
    """Pure ASGI CORS middleware — zero buffering, safe for SSE / streaming."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Preflight
        if scope["method"] == "OPTIONS":
            await send({"type": "http.response.start", "status": 204, "headers": CORS_HEADERS})
            await send({"type": "http.response.body", "body": b""})
            return

        # Inject CORS headers into the first response message
        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Only add if not already set by the endpoint
                existing = {h[0] for h in headers}
                for k, v in CORS_HEADERS:
                    if k not in existing:
                        headers.append((k, v))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cors)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # MongoDB indexes
    from app.db.mongo import init_indexes
    await init_indexes()

    # Qdrant collection
    if settings.qdrant_url:
        from app.db.qdrant import init_qdrant_collection
        await init_qdrant_collection(settings.qdrant_collection)

    yield

    # Shutdown
    from app.db.mongo import client as mongo_client
    if mongo_client:
        mongo_client.close()

    if settings.qdrant_url:
        from app.db.qdrant import qdrant_client
        qdrant_client.close()

    if settings.neo4j_uri:
        from app.db.neo4j import neo4j_driver
        if neo4j_driver:
            neo4j_driver.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Lumio API",
        description="Backend API for Lumio — multimodal company intelligence dashboard",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(CORSMiddleware)

    app.include_router(api_router, prefix="/api/v1")

    # Serve asset files
    asset_path = Path(__file__).resolve().parent.parent / "asset"
    if asset_path.is_dir():
        app.mount("/asset", StaticFiles(directory=str(asset_path)), name="asset")

    # Serve backoffice static files
    bo_path = Path(__file__).resolve().parent.parent / "back_office"
    if bo_path.is_dir():
        app.mount("/backoffice", StaticFiles(directory=str(bo_path), html=True), name="backoffice")

    return app


app = create_app()
