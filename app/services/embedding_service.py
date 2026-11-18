from functools import lru_cache

import httpx2

from app.config.settings import settings


class EmbeddingError(Exception):
    """Raised when text could not be embedded (Ollama down, bad response, ...)."""


class OllamaEmbeddingService:
    """Turns text into vectors using Ollama's POST /api/embed.

    Text is sent as given: Ollama's template for nomic-embed-text is a bare
    `{{ .Prompt }}`, so any task prefix is the caller's decision.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        client: httpx2.Client | None = None,
    ) -> None:
        self._model = model
        # `client` is injectable so tests can pass a MockTransport-backed client.
        self._client = client or httpx2.Client(base_url=base_url, timeout=timeout)

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("Cannot embed empty text")

        try:
            response = self._client.post(
                "/api/embed", json={"model": self._model, "input": texts}
            )
            response.raise_for_status()
            body = response.json()
        except httpx2.HTTPError as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc
        except ValueError as exc:  # body was not valid JSON
            raise EmbeddingError("Ollama returned a non-JSON response") from exc

        embeddings = body.get("embeddings") if isinstance(body, dict) else None
        if (
            not isinstance(embeddings, list)
            or len(embeddings) != len(texts)
            or not all(isinstance(v, list) and v for v in embeddings)
        ):
            raise EmbeddingError(
                f"Unexpected embedding response: expected {len(texts)} non-empty vectors"
            )
        return embeddings


@lru_cache
def get_embedding_service() -> OllamaEmbeddingService:
    """One shared service per process; created lazily, no network on import."""
    return OllamaEmbeddingService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model_embedding,
        timeout=settings.ollama_embedding_timeout,
    )
