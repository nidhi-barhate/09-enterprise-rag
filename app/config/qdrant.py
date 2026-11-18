from functools import lru_cache

from qdrant_client import QdrantClient

from app.config.settings import settings


@lru_cache
def get_qdrant_client() -> QdrantClient:
    """One shared client per process (it is thread-safe and keeps a connection pool).

    Created lazily, so importing this module never touches the network.
    """
    return QdrantClient(url=settings.qdrant_url)
