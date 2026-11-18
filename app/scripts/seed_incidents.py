"""Load synthetic incidents AND runbooks into PostgreSQL and Qdrant, or remove them.

Run from the project root (venv active; Postgres, Qdrant and Ollama running):
    python -m app.scripts.seed_incidents           # add (safe to repeat)
    python -m app.scripts.seed_incidents --clean   # remove only the seeded data

Seeded rows have fixed ids and the tag "seed", so repeating the command never
duplicates them and --clean never touches your real incidents or documents.
"""

import argparse

from app.config.connection import SessionLocal
from app.config.qdrant import get_qdrant_client
from app.repository.document_repository import DocumentRepository
from app.repository.incident_repository import IncidentRepository
from app.scripts.seed_data import build_seed_documents, build_seed_incidents
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


def seed_incidents(repository: IncidentRepository, indexer: IncidentIndexer) -> int:
    """Save every seed incident in Postgres (if missing) and (re)index it in Qdrant."""
    incidents = build_seed_incidents()
    for incident in incidents:
        if repository.get(incident.id) is None:
            repository.add(incident)
        indexer.index(incident)  # an upsert: safe to repeat
    return len(incidents)


def clean_incidents(repository: IncidentRepository, indexer: IncidentIndexer) -> int:
    """Remove the seed incidents from Postgres and Qdrant. Returns how many were in Postgres."""
    removed = 0
    for incident in build_seed_incidents():
        if repository.delete(incident.id):
            removed += 1
        indexer.delete(incident.id)
    return removed


def seed_documents(repository: DocumentRepository, indexer: DocumentIndexer) -> int:
    """Save every seed runbook in Postgres (if missing) and (re)index its chunks."""
    documents = build_seed_documents()
    for document in documents:
        if repository.get(document.id) is None:
            repository.add(document)
        indexer.index(document)
    return len(documents)


def clean_documents(repository: DocumentRepository, indexer: DocumentIndexer) -> int:
    removed = 0
    for document in build_seed_documents():
        if repository.delete(document.id):
            removed += 1
        indexer.delete(document.id)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--clean", action="store_true", help="remove the seeded data instead of adding it")
    args = parser.parse_args()

    client = get_qdrant_client()
    embedder = get_embedding_service()
    ensure_collection(client)
    ensure_collection(client, DOCUMENT_CHUNKS_COLLECTION, EMBEDDING_DIMENSIONS, DOCUMENT_FILTER_FIELDS)
    incident_indexer = IncidentIndexer(client, embedder)
    document_indexer = create_document_indexer(client, embedder)
    with SessionLocal() as session:
        incidents, documents = IncidentRepository(session), DocumentRepository(session)
        try:
            if args.clean:
                i = clean_incidents(incidents, incident_indexer)
                d = clean_documents(documents, document_indexer)
                print(f"Removed {i} seeded incident(s) and {d} seeded document(s) from PostgreSQL and Qdrant.")
            else:
                i = seed_incidents(incidents, incident_indexer)
                d = seed_documents(documents, document_indexer)
                print(f"Seeded {i} incident(s) and {d} document(s) into PostgreSQL and Qdrant.")
            session.commit()
        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    main()
