import uuid
from typing import Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    HasIdCondition,
    MatchValue,
    PointStruct,
)

from app.api.dto.document import Document
from app.services.chunker import chunk_text

DOCUMENT_CHUNKS_COLLECTION = "document_chunks"
# Payload fields that document searches filter on (they get a keyword index).
DOCUMENT_FILTER_FIELDS = ("document_id", "service", "doc_type")


class BatchEmbedder(Protocol):
    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


def _document_filter(document_id: uuid.UUID) -> Filter:
    return Filter(
        must=[FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))]
    )


class DocumentIndexer:
    """Splits a document into chunks and stores one Qdrant point per chunk.

    Point ids are uuid5(document id, chunk number): the same document always
    produces the same ids, so re-indexing overwrites instead of duplicating.
    The document's own id travels in the payload as `document_id`, which is how a
    found chunk leads back to its document in PostgreSQL (the source of truth).
    """

    def __init__(
        self,
        client: QdrantClient,
        embedder: BatchEmbedder,
        collection: str = DOCUMENT_CHUNKS_COLLECTION,
        chunk_size: int = 800,
        overlap: int = 100,
        batch_size: int = 32,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._collection = collection
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._batch_size = batch_size

    def index(self, document: Document) -> int:
        """(Re)index a document and return how many chunks it has."""
        chunks = chunk_text(document.content, self._chunk_size, self._overlap)
        if not chunks:
            self.delete(document.id)
            return 0

        # Embed first: if Ollama fails, nothing has been changed in Qdrant yet.
        # The title is added to each chunk's embedded text so a chunk keeps its context.
        texts = [f"{document.title}\n\n{chunk}" for chunk in chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            vectors.extend(self._embedder.embed_many(texts[i : i + self._batch_size]))

        ids = [str(uuid.uuid5(document.id, str(i))) for i in range(len(chunks))]
        points = [
            PointStruct(
                id=ids[i],
                vector=vectors[i],
                payload={
                    "document_id": str(document.id),
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                    "title": document.title,
                    "doc_type": document.doc_type.value,
                    "service": document.service,
                    "source": document.source,
                    "text": chunks[i],
                },
            )
            for i in range(len(chunks))
        ]
        self._client.upsert(collection_name=self._collection, points=points)

        # If the document got shorter, remove the chunks that no longer exist.
        stale = Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=str(document.id)))],
            must_not=[HasIdCondition(has_id=ids)],
        )
        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(filter=stale),
        )
        return len(chunks)

    def delete(self, document_id: uuid.UUID) -> None:
        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(filter=_document_filter(document_id)),
        )
