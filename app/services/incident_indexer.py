from collections.abc import Sequence
from typing import Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.api.dto.incident import Incident

INCIDENTS_COLLECTION = "incidents"
# nomic-embed-text produces 768-dimensional vectors (verified against Ollama).
EMBEDDING_DIMENSIONS = 768
# Payload fields that incident searches filter on (they get a keyword index).
INCIDENT_FILTER_FIELDS = ("service", "severity", "status")


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def ensure_collection(
    client: QdrantClient,
    name: str = INCIDENTS_COLLECTION,
    size: int = EMBEDDING_DIMENSIONS,
    keyword_fields: Sequence[str] = INCIDENT_FILTER_FIELDS,
) -> None:
    """Create the collection if missing. Fail loudly if it exists with another size.

    Changing the embedding model changes the vector size, which means the
    collection must be recreated and everything re-embedded; silently
    reusing a mismatched collection would make every upsert fail or, worse,
    mix incompatible vectors.
    """
    if client.collection_exists(name):
        existing = client.get_collection(name).config.params.vectors
        if existing.size != size:
            raise RuntimeError(
                f"Collection '{name}' has vector size {existing.size}, expected {size}"
            )
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=size, distance=Distance.COSINE),
    )
    # Keyword indexes make payload filtering fast once the collection grows.
    for field in keyword_fields:
        client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )


def incident_to_text(incident: Incident) -> str:
    """The text that represents an incident in vector space.

    Title, description, root cause and resolution carry the meaning people
    search for. Service, severity and tags are kept as payload for filtering
    instead of being embedded.
    """
    parts = [incident.title, incident.description]
    if incident.root_cause:
        parts.append(f"Root cause: {incident.root_cause}")
    if incident.resolution:
        parts.append(f"Resolution: {incident.resolution}")
    return "\n\n".join(parts)


def incident_to_payload(incident: Incident) -> dict:
    return {
        "service": incident.service,
        "severity": incident.severity.value,
        "status": incident.status.value,
        "tags": list(incident.tags),
        "reported_at": incident.reported_at.isoformat(),
    }


class IncidentIndexer:
    """Writes incidents into Qdrant. Postgres stays the source of truth.

    The Postgres UUID is the Qdrant point id, so upserting the same incident
    again overwrites its point (safe to re-index) instead of duplicating it.
    """

    def __init__(
        self,
        client: QdrantClient,
        embedder: Embedder,
        collection: str = INCIDENTS_COLLECTION,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._collection = collection

    def index(self, incident: Incident) -> None:
        vector = self._embedder.embed(incident_to_text(incident))
        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=str(incident.id),
                    vector=vector,
                    payload=incident_to_payload(incident),
                )
            ],
        )

    def delete(self, incident_id) -> None:
        self._client.delete(
            collection_name=self._collection,
            points_selector=[str(incident_id)],
        )
