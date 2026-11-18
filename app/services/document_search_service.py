import uuid

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
)

from app.api.dto.document import Document, DocumentType
from app.repository.document_repository import DocumentRepository
from app.services.document_indexer import DOCUMENT_CHUNKS_COLLECTION
from app.services.incident_indexer import Embedder

# Several top chunks can come from the same document, so ask Qdrant for extra
# candidates, keep the best chunk per document, then trim to `limit`.
CANDIDATE_FACTOR = 5


class DocumentHit(BaseModel):
    document: Document
    chunk_index: int
    chunk_text: str  # the passage that matched: show it as the citation
    score: float


class DocumentSearchService:
    """Finds the best passage of each matching document, by meaning.

    Qdrant supplies chunks and scores; PostgreSQL (the source of truth) supplies
    the documents. A chunk whose document is no longer in Postgres is skipped.
    """

    def __init__(
        self,
        client: QdrantClient,
        embedder: Embedder,
        repository: DocumentRepository,
        collection: str = DOCUMENT_CHUNKS_COLLECTION,
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
        doc_type: DocumentType | None = None,
        limit: int = 5,
        min_score: float | None = None,
    ) -> list[DocumentHit]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        must = []
        if service is not None:
            # A document with no service applies to every service, so it stays
            # in the results when filtering by one.
            must.append(
                Filter(
                    should=[
                        FieldCondition(key="service", match=MatchValue(value=service)),
                        IsEmptyCondition(is_empty=PayloadField(key="service")),
                    ]
                )
            )
        if doc_type is not None:
            must.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type.value)))

        response = self._client.query_points(
            collection_name=self._collection,
            query=self._embedder.embed(query),
            query_filter=Filter(must=must) if must else None,
            limit=limit * CANDIDATE_FACTOR,
            score_threshold=min_score,
        )

        # Points arrive best first, so the first chunk seen per document is its best.
        best = {}
        for point in response.points:
            document_id = uuid.UUID(point.payload["document_id"])
            best.setdefault(document_id, point)

        documents = self._repository.get_many(best.keys())
        hits = [
            DocumentHit(
                document=documents[document_id],
                chunk_index=point.payload["chunk_index"],
                chunk_text=point.payload["text"],
                score=point.score,
            )
            for document_id, point in best.items()
            if document_id in documents
        ]
        return hits[:limit]
