"""'Hello Qdrant': collection, points, vectors, payload, distance, filter.

Integration tests against the real Qdrant server (docker compose up -d).
Each test gets its own throwaway collection, deleted afterwards, so the real
collections are never touched.
"""

import uuid

import pytest
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config.qdrant import get_qdrant_client

# Tiny hand-written 4-dimensional vectors; real embeddings come later.
POINTS = {
    "payment": ([1.0, 0.0, 0.0, 0.0], {"service": "payment-service", "severity": "SEV1"}),
    "payment-similar": ([0.9, 0.1, 0.0, 0.0], {"service": "payment-service", "severity": "SEV3"}),
    "search": ([0.0, 1.0, 0.0, 0.0], {"service": "search-service", "severity": "SEV2"}),
}


@pytest.fixture
def client():
    return get_qdrant_client()


@pytest.fixture
def collection(client):
    name = f"test-{uuid.uuid4()}"
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    # The point id is the Postgres UUID in the real design; fresh UUIDs here.
    ids = {key: str(uuid.uuid4()) for key in POINTS}
    client.upsert(
        collection_name=name,
        points=[
            PointStruct(id=ids[key], vector=vector, payload=payload)
            for key, (vector, payload) in POINTS.items()
        ],
    )
    try:
        yield name, ids
    finally:
        client.delete_collection(name)


def test_server_is_reachable(client):
    assert client.get_collections() is not None


def test_search_returns_nearest_vectors_first(client, collection):
    name, ids = collection
    result = client.query_points(
        collection_name=name, query=[1.0, 0.0, 0.0, 0.0], limit=3
    )
    assert [str(p.id) for p in result.points] == [
        ids["payment"],
        ids["payment-similar"],
        ids["search"],
    ]
    # Cosine similarity: identical = 1.0, orthogonal = 0.0.
    assert result.points[0].score == pytest.approx(1.0)
    assert result.points[2].score == pytest.approx(0.0)


def test_payload_comes_back_with_results(client, collection):
    name, ids = collection
    result = client.query_points(
        collection_name=name, query=[1.0, 0.0, 0.0, 0.0], limit=1, with_payload=True
    )
    assert result.points[0].payload == {"service": "payment-service", "severity": "SEV1"}


def test_payload_filter_restricts_results(client, collection):
    name, ids = collection
    only_search = Filter(
        must=[FieldCondition(key="service", match=MatchValue(value="search-service"))]
    )
    result = client.query_points(
        collection_name=name,
        query=[1.0, 0.0, 0.0, 0.0],  # closest to payment-service, but filtered out
        query_filter=only_search,
        limit=3,
    )
    assert [str(p.id) for p in result.points] == [ids["search"]]


def test_upsert_same_id_overwrites_instead_of_duplicating(client, collection):
    name, ids = collection
    client.upsert(
        collection_name=name,
        points=[
            PointStruct(
                id=ids["payment"], vector=[0.0, 0.0, 1.0, 0.0], payload={"service": "x"}
            )
        ],
    )
    assert client.count(collection_name=name).count == 3
    point = client.retrieve(collection_name=name, ids=[ids["payment"]])[0]
    assert point.payload == {"service": "x"}


def test_wrong_vector_size_is_rejected(client, collection):
    name, _ = collection
    with pytest.raises(Exception):
        client.upsert(
            collection_name=name,
            points=[PointStruct(id=str(uuid.uuid4()), vector=[1.0, 0.0], payload={})],
        )
