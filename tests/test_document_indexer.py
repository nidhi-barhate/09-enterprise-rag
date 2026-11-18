"""DocumentIndexer: one Qdrant point per chunk, linked back by document_id.

Throwaway collections (size 4) are used, never the real 'document_chunks' one.
"""

import datetime
import uuid

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.api.dto.document import Document, DocumentType
from app.config.qdrant import get_qdrant_client
from app.services.chunker import chunk_text
from app.services.document_indexer import DOCUMENT_FILTER_FIELDS, DocumentIndexer
from app.services.incident_indexer import ensure_collection

UTC = datetime.timezone.utc
PARAGRAPHS = [
    "Check replica lag on the standby before doing anything else.",
    "Stop writes on the primary so the replica can catch up completely.",
    "Promote the replica to primary and update the connection string.",
    "Verify that writes succeed and the application is healthy again.",
]
CONTENT = "\n\n".join(PARAGRAPHS)
SIZE, OVERLAP = 70, 0  # about one paragraph per chunk


def make_document(**overrides) -> Document:
    data = dict(
        id=uuid.uuid4(),
        title="Runbook",
        doc_type=DocumentType.RUNBOOK,
        service="payment-service",
        content=CONTENT,
        source="runbooks/failover.md",
        tags=[],
        created_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
    data.update(overrides)
    return Document(**data)


class RecordingEmbedder:
    def __init__(self):
        self.calls = []

    def embed_many(self, texts):
        self.calls.append(list(texts))
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def client():
    return get_qdrant_client()


@pytest.fixture
def collection(client):
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=4, keyword_fields=DOCUMENT_FILTER_FIELDS)
    yield name
    client.delete_collection(name)


def chunks_of(client, collection, document_id):
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))]
        ),
        limit=1000,
        with_payload=True,
    )
    return sorted(points, key=lambda p: p.payload["chunk_index"])


def make_indexer(client, collection, embedder=None, **kwargs):
    return DocumentIndexer(
        client, embedder or RecordingEmbedder(), collection=collection,
        chunk_size=SIZE, overlap=OVERLAP, **kwargs,
    )


def test_index_creates_one_point_per_chunk_with_payload(client, collection):
    document = make_document()
    count = make_indexer(client, collection).index(document)

    expected = chunk_text(CONTENT, SIZE, OVERLAP)
    assert count == len(expected) > 1
    points = chunks_of(client, collection, document.id)
    assert [p.payload["text"] for p in points] == expected
    first = points[0].payload
    assert first["document_id"] == str(document.id)
    assert first["chunk_count"] == len(expected)
    assert first["title"] == "Runbook"
    assert first["doc_type"] == "runbook"
    assert first["service"] == "payment-service"
    assert first["source"] == "runbooks/failover.md"


def test_point_ids_are_deterministic_uuid5_of_document_and_chunk_number(client, collection):
    document = make_document()
    make_indexer(client, collection).index(document)
    points = chunks_of(client, collection, document.id)
    assert [str(p.id) for p in points] == [
        str(uuid.uuid5(document.id, str(i))) for i in range(len(points))
    ]


def test_reindexing_is_idempotent(client, collection):
    document = make_document()
    indexer = make_indexer(client, collection)
    first = indexer.index(document)
    indexer.index(document)
    assert len(chunks_of(client, collection, document.id)) == first


def test_shorter_document_removes_stale_chunks(client, collection):
    document = make_document()
    indexer = make_indexer(client, collection)
    indexer.index(document)
    shorter = document.model_copy(update={"content": PARAGRAPHS[0]})
    assert indexer.index(shorter) == 1
    points = chunks_of(client, collection, document.id)
    assert [p.payload["text"] for p in points] == [PARAGRAPHS[0]]


def test_delete_removes_only_that_documents_chunks(client, collection):
    keep, drop = make_document(), make_document()
    indexer = make_indexer(client, collection)
    indexer.index(keep)
    indexer.index(drop)
    indexer.delete(drop.id)
    assert chunks_of(client, collection, drop.id) == []
    assert len(chunks_of(client, collection, keep.id)) > 0


def test_title_is_added_to_the_embedded_text_but_not_to_the_stored_chunk(client, collection):
    embedder = RecordingEmbedder()
    document = make_document(title="DB failover")
    make_indexer(client, collection, embedder).index(document)
    embedded = [t for call in embedder.calls for t in call]
    assert all(t.startswith("DB failover\n\n") for t in embedded)
    stored = chunks_of(client, collection, document.id)
    assert all(not p.payload["text"].startswith("DB failover") for p in stored)


def test_chunks_are_embedded_in_batches(client, collection):
    embedder = RecordingEmbedder()
    indexer = make_indexer(client, collection, embedder, batch_size=2)
    count = indexer.index(make_document())
    assert count == 4
    assert [len(call) for call in embedder.calls] == [2, 2]


def test_whitespace_only_content_clears_the_documents_chunks(client, collection):
    document = make_document()
    indexer = make_indexer(client, collection)
    indexer.index(document)
    blank = document.model_copy(update={"content": "   "})
    assert indexer.index(blank) == 0
    assert chunks_of(client, collection, document.id) == []


def test_embedding_failure_leaves_existing_chunks_untouched(client, collection):
    document = make_document()
    indexer = make_indexer(client, collection)
    indexer.index(document)
    before = [p.payload["text"] for p in chunks_of(client, collection, document.id)]

    class Broken:
        def embed_many(self, texts):
            raise RuntimeError("ollama down")

    broken = make_indexer(client, collection, Broken())
    with pytest.raises(RuntimeError):
        broken.index(document.model_copy(update={"content": "completely new text"}))
    after = [p.payload["text"] for p in chunks_of(client, collection, document.id)]
    assert after == before


def test_app_indexer_takes_chunk_size_and_overlap_from_settings(monkeypatch, client):
    from app.config.settings import settings
    from app.services.document_indexer import create_document_indexer

    monkeypatch.setattr(settings, "document_chunk_size", 123)
    monkeypatch.setattr(settings, "document_chunk_overlap", 7)
    indexer = create_document_indexer(client, RecordingEmbedder())
    assert indexer._chunk_size == 123
    assert indexer._overlap == 7
