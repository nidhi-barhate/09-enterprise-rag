"""Rebuild the Qdrant indexes (incidents and document chunks) from PostgreSQL.

Run from the project root (venv active, Qdrant and Ollama running):
    python -m app.scripts.reindex
"""

from app.config.connection import SessionLocal
from app.config.qdrant import get_qdrant_client
from app.repository.document_repository import DocumentRepository
from app.repository.incident_repository import IncidentRepository
from app.services.document_indexer import (
    DOCUMENT_CHUNKS_COLLECTION,
    DOCUMENT_FILTER_FIELDS,
    create_document_indexer,
)
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import (
    EMBEDDING_DIMENSIONS,
    IncidentIndexer,
    ensure_collection,
)
from app.services.reindex import reindex_all, reindex_all_documents


def main() -> None:
    client = get_qdrant_client()
    embedder = get_embedding_service()
    ensure_collection(client)
    ensure_collection(client, DOCUMENT_CHUNKS_COLLECTION, EMBEDDING_DIMENSIONS, DOCUMENT_FILTER_FIELDS)
    with SessionLocal() as session:
        incidents = reindex_all(IncidentRepository(session), IncidentIndexer(client, embedder))
        documents = reindex_all_documents(DocumentRepository(session), create_document_indexer(client, embedder))
    print(f"Indexed {incidents} incident(s) and {documents} document(s).")


if __name__ == "__main__":
    main()
