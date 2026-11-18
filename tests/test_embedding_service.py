import json

import httpx2
import pytest

from app.services.embedding_service import (
    EmbeddingError,
    OllamaEmbeddingService,
    get_embedding_service,
)


def make_service(handler) -> OllamaEmbeddingService:
    client = httpx2.Client(
        base_url="http://ollama.test", transport=httpx2.MockTransport(handler)
    )
    return OllamaEmbeddingService(
        base_url="http://ollama.test", model="test-model", timeout=5, client=client
    )


# --- unit tests: no Ollama needed ---


def test_embed_sends_model_and_input_and_returns_vector():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    vector = make_service(handler).embed("hello")
    assert vector == [0.1, 0.2, 0.3]
    assert seen["path"] == "/api/embed"
    assert seen["body"] == {"model": "test-model", "input": ["hello"]}


def test_embed_many_returns_one_vector_per_text_in_order():
    def handler(request):
        return httpx2.Response(200, json={"embeddings": [[1.0], [2.0]]})

    assert make_service(handler).embed_many(["a", "b"]) == [[1.0], [2.0]]


def test_embed_many_empty_list_makes_no_request():
    def handler(request):
        raise AssertionError("no request expected")

    assert make_service(handler).embed_many([]) == []


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_blank_text_is_rejected(text):
    with pytest.raises(ValueError):
        make_service(lambda r: httpx2.Response(200, json={"embeddings": [[1.0]]})).embed(text)


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(500, json={"error": "boom"}),
        httpx2.Response(404, json={"error": "model not found"}),
        httpx2.Response(200, content=b"not json"),
        httpx2.Response(200, json={}),
        httpx2.Response(200, json={"embeddings": []}),
        httpx2.Response(200, json={"embeddings": [[]]}),
        httpx2.Response(200, json={"embeddings": [[1.0], [2.0]]}),  # 2 vectors for 1 text
        httpx2.Response(200, json=["unexpected"]),
    ],
)
def test_bad_responses_raise_embedding_error(response):
    with pytest.raises(EmbeddingError):
        make_service(lambda request: response).embed("hello")


def test_connection_failure_raises_embedding_error():
    def handler(request):
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(EmbeddingError):
        make_service(handler).embed("hello")


# --- integration test: needs Ollama running with nomic-embed-text ---


def test_real_ollama_returns_768_dimensional_vector():
    vector = get_embedding_service().embed("payment-service 503 errors after deploy")
    assert len(vector) == 768
    assert all(isinstance(x, float) for x in vector)


def test_real_ollama_similar_text_is_closer_than_unrelated_text():
    service = get_embedding_service()
    a, b, c = service.embed_many(
        [
            "payment-service is returning 503 errors after the deploy",
            "payments API gives HTTP 503 following a release",
            "recipe for chocolate chip cookies",
        ]
    )

    def dot(x, y):
        return sum(i * j for i, j in zip(x, y))

    def norm(x):
        return dot(x, x) ** 0.5

    def cosine(x, y):
        return dot(x, y) / (norm(x) * norm(y))

    assert cosine(a, b) > cosine(a, c)
