from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

# Session factory: one Session per unit of work (e.g. per request), never shared.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)