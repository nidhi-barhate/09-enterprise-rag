from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OpsMind AI"
    app_version: str = "0.1.0"
    debug: bool = True

    database_url: str
    qdrant_url: str = "http://localhost:6333"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model_embedding: str = "nomic-embed-text:latest"
    # Embeddings are fast; keep this far below the 300s used for chat models.
    ollama_embedding_timeout: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()