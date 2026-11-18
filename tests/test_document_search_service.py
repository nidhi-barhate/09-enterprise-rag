"""Document search: question -> best chunks in Qdrant -> documents from Postgres."""

import datetime
import uuid

import pytest

from app.api.dto.document import Document, DocumentType
from app.config.qdrant import get_qdrant_client
from app.repository.document_repository import DocumentRepository
from app.services.document_indexer import DOCUMENT_FILTER_FIELDS, DocumentIndexer
from app.services.document_search_service import DocumentSearchService
from app.services.embedding_service import get_embedding_service
from app.services.incident_indexer import EMBEDDING_DIMENSIONS, ensure_collection

UTC = datetime.timezone.utc


def make_document(**overrides) -> Document:
    data = dict(
        id=uuid.uuid4(),
        title="Runbook",
        doc_type=DocumentType.RUNBOOK,
        service="payments",
        content="Promote the replica to primary.",
        tags=[],
        created_at=datetime.datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
    data.update(overrides)
    return Document(**data)


class KeywordEmbedder:
    """Deterministic 4-d vectors: replica -> x, cache -> y, logs -> z, else w."""

    def embed(self, text):
        t = text.lower()
        if "replica" in t or "failover" in t:
            return [1.0, 0.0, 0.0, 0.0]
        if "cache" in t:
            return [0.0, 1.0, 0.0, 0.0]
        if "logs" in t or "disk" in t:
            return [0.0, 0.0, 1.0, 0.0]
        return [0.0, 0.0, 0.0, 1.0]

    def embed_many(self, texts):
        return [self.embed(t) for t in texts]


@pytest.fixture
def client():
    return get_qdrant_client()


@pytest.fixture
def collection(client):
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=4, keyword_fields=DOCUMENT_FILTER_FIELDS)
    yield name
    client.delete_collection(name)


@pytest.fixture
def setup(client, collection, session):
    repo = DocumentRepository(session)
    indexer = DocumentIndexer(client, KeywordEmbedder(), collection=collection, chunk_size=60, overlap=0)
    search = DocumentSearchService(client, KeywordEmbedder(), repo, collection=collection)

    def add(document, *, in_postgres=True):
        if in_postgres:
            repo.add(document)
        indexer.index(document)
        return document

    return add, search


def test_returns_the_best_passage_with_its_document(setup):
    add, search = setup
    document = add(make_document(
        title="Ops",
        content="Failover: promote the replica to primary.\n\nCache: flush the cache nodes.",
    ))
    hits = search.search("how do I promote the replica")
    assert [h.document.id for h in hits] == [document.id]
    assert "replica" in hits[0].chunk_text
    assert hits[0].score == pytest.approx(1.0)
    assert hits[0].document == document


def test_one_hit_per_document_even_when_many_chunks_match(setup):
    add, search = setup
    document = add(make_document(
        content="Replica step one: check lag.\n\nReplica step two: stop writes.\n\nReplica step three: promote.",
    ))
    hits = search.search("replica")
    assert [h.document.id for h in hits] == [document.id]


def test_ranks_documents_by_best_chunk(setup):
    add, search = setup
    failover = add(make_document(content="Promote the replica now.", service="a"))
    cache = add(make_document(content="Flush the cache nodes.", service="b"))
    hits = search.search("replica", limit=2)
    assert [h.document.id for h in hits] == [failover.id, cache.id]
    assert hits[0].score > hits[1].score


def test_service_filter_keeps_global_documents(setup):
    add, search = setup
    mine = add(make_document(content="Promote the replica.", service="payments"))
    global_doc = add(make_document(content="Flush the cache nodes.", service=None))
    add(make_document(content="Rotate the logs when disk is full.", service="other"))
    hits = search.search("replica", service="payments")
    assert {h.document.id for h in hits} == {mine.id, global_doc.id}


def test_doc_type_filter(setup):
    add, search = setup
    add(make_document(content="Promote the replica.", doc_type=DocumentType.RUNBOOK))
    guide = add(make_document(content="Promote the replica.", doc_type=DocumentType.TECHNICAL_DOC))
    hits = search.search("replica", doc_type=DocumentType.TECHNICAL_DOC)
    assert [h.document.id for h in hits] == [guide.id]


def test_limit_caps_documents(setup):
    add, search = setup
    for _ in range(3):
        add(make_document(content="Promote the replica."))
    assert len(search.search("replica", limit=2)) == 2


def test_min_score_drops_weak_matches(setup):
    add, search = setup
    strong = add(make_document(content="Promote the replica."))
    add(make_document(content="Flush the cache nodes."))
    hits = search.search("replica", min_score=0.5)
    assert [h.document.id for h in hits] == [strong.id]


def test_document_missing_from_postgres_is_skipped(setup):
    add, search = setup
    kept = add(make_document(content="Promote the replica."))
    add(make_document(content="Promote the replica ghost."), in_postgres=False)
    assert [h.document.id for h in search.search("replica")] == [kept.id]


def test_invalid_limit_is_rejected():
    with pytest.raises(ValueError):
        DocumentSearchService(None, KeywordEmbedder(), None).search("x", limit=0)


# --- real Ollama + Qdrant + Postgres ---


def test_real_embeddings_find_the_right_passage(client, session):
    name = f"test-{uuid.uuid4()}"
    ensure_collection(client, name=name, size=EMBEDDING_DIMENSIONS, keyword_fields=DOCUMENT_FILTER_FIELDS)
    try:
        embedder = get_embedding_service()
        repo = DocumentRepository(session)
        indexer = DocumentIndexer(client, embedder, collection=name, chunk_size=200, overlap=30)
        search = DocumentSearchService(client, embedder, repo, collection=name)

        runbook = make_document(
            title="Operations runbook",
            content=(
                "Database failover. Check replica lag on the standby. Stop writes on the primary. "
                "Promote the replica to primary with pg_ctl promote, then point the application at it.\n\n"
                "Cache flush. When stale data is served, connect to the Redis cluster and run FLUSHDB. "
                "Warm the cache by replaying the most visited pages.\n\n"
                "Log rotation. When the disk is full, run logrotate, compress old files and delete "
                "archives older than thirty days."
            ),
        )
        repo.add(runbook)
        assert indexer.index(runbook) >= 3

        hit = search.search("how do I promote the replica database")[0]
        assert hit.document.id == runbook.id
        assert "promote" in hit.chunk_text.lower()
    finally:
        client.delete_collection(name)
