# OpsMind AI — Enterprise Incident Intelligence

A production-oriented Enterprise RAG system that helps engineering teams
investigate incidents using historical incident reports, runbooks,
troubleshooting guides, and technical documentation. Answers are grounded in
retrieved sources and carry citations.

> Learning project: built step by step to learn Enterprise RAG engineering.
> Status: **Phase 1 (knowledge foundation) in progress.**

## Architecture

```
Client ──> FastAPI ──> Pydantic DTOs ──> Repository ──> PostgreSQL (source of truth)
                                              │
                                              └──(Phase 2)──> Qdrant (vectors + payload)
```

- **PostgreSQL** stores incidents (SQLAlchemy 2.x ORM, Alembic migrations).
- **Qdrant** (planned, Phase 2) stores embeddings and search payloads. It
  replaces pgvector. The incident UUID is reused as the Qdrant point ID so the
  two stores stay linkable.
- **LLM**: AWS Bedrock / Claude, optional Ollama for local runs.

## Project layout

```
main.py                  FastAPI app entry point
app/
  api/dto/incident.py    Pydantic Incident (API/domain contract, validation)
  config/                settings (.env) and SQLAlchemy engine
  model/                 SQLAlchemy ORM models (IncidentRecord -> "incidents")
alembic/                 migration environment and versions
tests/                   Pytest suite
```

## Setup

Requirements: Python 3.14, PostgreSQL running locally.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create the database and a `.env` file at the project root:

```bash
createdb opsmind
```

```
DATABASE_URL=postgresql+psycopg://<user>@127.0.0.1:5432/opsmind
OLLAMA_BASE_URL=http://localhost:11434
```

Apply migrations and run the API:

```bash
alembic upgrade head
python -m uvicorn main:app --reload
```

## Tests

```bash
python -m pytest
```

## Roadmap

1. **Knowledge foundation**: incident models, ingestion, APIs (current)
2. **RAG engine**: embeddings, Qdrant retrieval, hybrid search, grounded answers
3. **Investigation**: multi-source reasoning, LangGraph
4. **Security**: authentication, RBAC, document permissions
5. **Production**: evaluation, observability, reliability
6. **Application**: React frontend and deployment
