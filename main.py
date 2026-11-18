import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config.settings import settings
from app.config.connection import engine
from app.api.routes.documents import router as documents_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.search import router as search_router
from app.config.qdrant import get_qdrant_client
from app.services.incident_indexer import ensure_collection

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Non-fatal: the API (and Postgres-backed endpoints) must start even if
    # Qdrant is down; search will report 503 until it is back.
    try:
        ensure_collection(get_qdrant_client())
    except Exception:
        logger.warning("Could not ensure the Qdrant collection at startup", exc_info=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(incidents_router)
app.include_router(documents_router)
app.include_router(search_router)


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