"""Rebuild the Qdrant incident index from Postgres.

Run from the project root (venv active, Qdrant and Ollama running):
    python -m app.scripts.reindex
"""

from app.config.connection import SessionLocal
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import IncidentIndexer, ensure_collection
from app.services.reindex import reindex_all


def main() -> None:
    client = get_qdrant_client()
    ensure_collection(client)
    indexer = IncidentIndexer(client, get_embedding_service())
    with SessionLocal() as session:
        total = reindex_all(IncidentRepository(session), indexer)
    print(f"Indexed {total} incident(s).")


if __name__ == "__main__":
    main()
