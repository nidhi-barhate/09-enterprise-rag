"""Load 100 synthetic incidents into PostgreSQL *and* Qdrant, or remove them again.

Run from the project root (venv active; Postgres, Qdrant and Ollama running):
    python -m app.scripts.seed_incidents           # add (safe to repeat)
    python -m app.scripts.seed_incidents --clean   # remove only the seeded incidents

Seeded incidents have fixed ids and the tag "seed", so repeating the command
never duplicates them and --clean never touches your real incidents.
"""

import argparse

from app.config.connection import SessionLocal
from app.config.qdrant import get_qdrant_client
from app.repository.incident_repository import IncidentRepository
from app.scripts.seed_data import build_seed_incidents
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import IncidentIndexer, ensure_collection


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--clean", action="store_true", help="remove the seeded incidents instead of adding them")
    args = parser.parse_args()

    client = get_qdrant_client()
    ensure_collection(client)
    indexer = IncidentIndexer(client, get_embedding_service())
    with SessionLocal() as session:
        repository = IncidentRepository(session)
        try:
            if args.clean:
                count = clean_incidents(repository, indexer)
                print(f"Removed {count} seeded incident(s) from PostgreSQL and Qdrant.")
            else:
                count = seed_incidents(repository, indexer)
                print(f"Seeded {count} incident(s) into PostgreSQL and Qdrant.")
            session.commit()
        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    main()
