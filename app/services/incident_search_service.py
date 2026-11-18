import uuid

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.api.dto.incident import Incident, IncidentStatus, Severity
from app.repository.incident_repository import IncidentRepository
from app.services.incident_indexer import INCIDENTS_COLLECTION, Embedder


class IncidentHit(BaseModel):
    incident: Incident
    score: float  # cosine similarity: closer to 1.0 = more similar


class IncidentSearchService:
    """Finds incidents by meaning.

    Qdrant supplies ids and scores; Postgres (the source of truth) supplies the
    incident data. A hit whose id is no longer in Postgres is skipped.
    """

    def __init__(
        self,
        client: QdrantClient,
        embedder: Embedder,
        repository: IncidentRepository,
        collection: str = INCIDENTS_COLLECTION,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._repository = repository
        self._collection = collection

    def search(
        self,
        query: str,
        *,
        service: str | None = None,
        severity: Severity | None = None,
        status: IncidentStatus | None = None,
        limit: int = 5,
        min_score: float | None = None,
    ) -> list[IncidentHit]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        conditions = []
        if service is not None:
            conditions.append(_match("service", service))
        if severity is not None:
            conditions.append(_match("severity", severity.value))
        if status is not None:
            conditions.append(_match("status", status.value))

        response = self._client.query_points(
            collection_name=self._collection,
            query=self._embedder.embed(query),
            query_filter=Filter(must=conditions) if conditions else None,
            limit=limit,
            score_threshold=min_score,
        )

        scored = [(uuid.UUID(str(point.id)), point.score) for point in response.points]
        incidents = self._repository.get_many(incident_id for incident_id, _ in scored)

        # Keep Qdrant's ranking; drop ids missing from Postgres (index drift).
        return [
            IncidentHit(incident=incidents[incident_id], score=score)
            for incident_id, score in scored
            if incident_id in incidents
        ]


def _match(key: str, value: str) -> FieldCondition:
    return FieldCondition(key=key, match=MatchValue(value=value))
