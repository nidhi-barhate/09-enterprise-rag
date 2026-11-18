from app.repository.incident_repository import IncidentRepository
from app.services.incident_indexer import IncidentIndexer


def reindex_all(
    repository: IncidentRepository, indexer: IncidentIndexer, batch_size: int = 100
) -> int:
    """Rebuild the vector index from Postgres, the source of truth.

    Use it to index incidents that existed before indexing was added, and to
    heal incidents whose best-effort indexing failed. Safe to run repeatedly:
    indexing is an upsert keyed by the incident UUID.
    """
    total = 0
    while True:
        batch = repository.list(limit=batch_size, offset=total)
        if not batch:
            return total
        for incident in batch:
            indexer.index(incident)
        total += len(batch)
