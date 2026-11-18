from fastapi import FastAPI
from sqlalchemy import text

from app.config.settings import settings
from app.config.connection import engine
from app.api.routes.documents import router as documents_router
from app.api.routes.incidents import router as incidents_router


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(incidents_router)
app.include_router(documents_router)


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