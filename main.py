from fastapi import FastAPI
from sqlalchemy import text

from app.config.settings import settings
from app.database.connection import engine


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)


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