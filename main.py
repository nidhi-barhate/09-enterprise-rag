import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config.settings import settings
from app.config.connection import engine
from app.api.routes.documents import router as documents_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.search import router as search_router
from app.config.qdrant import get_qdrant_client
from app.services.document_indexer import DOCUMENT_CHUNKS_COLLECTION, DOCUMENT_FILTER_FIELDS
from app.services.incident_indexer import EMBEDDING_DIMENSIONS, ensure_collection

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Non-fatal: the API (and Postgres-backed endpoints) must start even if
    # Qdrant is down; search will report 503 until it is back.
    try:
        client = get_qdrant_client()
        ensure_collection(client)
        ensure_collection(
            client, DOCUMENT_CHUNKS_COLLECTION, EMBEDDING_DIMENSIONS, DOCUMENT_FILTER_FIELDS
        )
    except Exception:
        logger.warning("Could not ensure the Qdrant collections at startup", exc_info=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(incidents_router)
app.include_router(documents_router)
app.include_router(search_router)

# The UI is one static page that calls the JSON API on the same origin (no CORS needed).
app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "app" / "static", html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/")


@app.get("/health")
def health():
    return {
        "status": "UP",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health/database")
def database_health():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        return {
            "database": "UP",
            "result": result.scalar(),
        }