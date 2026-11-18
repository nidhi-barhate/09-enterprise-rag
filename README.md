# 🛠 OpsMind AI — Enterprise Incident Intelligence

> A production-oriented Enterprise RAG system built using Python, FastAPI, PostgreSQL, Qdrant, and Ollama that helps engineering teams investigate incidents using historical incident reports, runbooks, troubleshooting guides, and technical documentation, with grounded answers and citations.

> **Status:** Phase 1 (Knowledge Foundation) is complete. Phase 2 (RAG Engine) is in progress: semantic search over incidents works end to end. Document indexing, hybrid search, reranking, and grounded answers are **Planned**.

---

# 📌 Overview

During an outage, the answer usually already exists somewhere: a past incident report, a runbook, or a troubleshooting guide. Finding it by hand under pressure is slow.

OpsMind AI is designed to let an on-call engineer ask:

> *"payment-service is returning 503s after the deploy. Has this happened before?"*

and receive a **grounded answer** built only from retrieved company knowledge, with **citations** to the source incidents and documents.

This project is built step by step as a hands-on way to learn **Enterprise RAG engineering**:

- FastAPI
- Pydantic
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Qdrant
- Ollama (`nomic-embed-text` embeddings)
- AWS Bedrock / Claude *(planned)*
- LangGraph *(planned)*

---

# 🚀 Features

## ✅ Implemented

### 🧱 Incident Domain Model

The incident is modelled with Pydantic and enforces business rules at the boundary.

- `Incident`, `IncidentCreate`, and a shared `IncidentBase`
- `Severity` enum (`SEV1` – `SEV4`) and `IncidentStatus` enum (`open`, `mitigated`, `resolved`)
- Timezone-aware datetimes normalized to UTC
- `resolved_at` must not be earlier than `reported_at`
- Status consistency rule: `resolved` ⇔ `resolved_at` is set
- Length limits shared with the database columns, so over-long input is a `422`, not a database `500`

```text
Request JSON
     │
     ▼
IncidentCreate (Pydantic)
     │  validates fields and business rules
     ▼
Incident (server-generated UUID)
```

---

### 📚 Knowledge Documents

Runbooks, troubleshooting guides, and technical docs are stored as `Document`s.

- `DocumentType` enum: `runbook`, `troubleshooting_guide`, `technical_doc`
- Optional `service` (a document can apply to every service)
- Server-generated `id` and UTC `created_at`

---

### 🗄 Persistence Layer

```text
Incident / Document (Pydantic DTO)
              │
              ▼
           Mapper
              │
              ▼
IncidentRecord / DocumentRecord (SQLAlchemy ORM)
              │
              ▼
       PostgreSQL tables
```

- SQLAlchemy 2.x typed ORM (`Mapped` / `mapped_column`)
- `TIMESTAMPTZ` datetimes, native `UUID` primary keys, `ARRAY` tags
- `CHECK` constraints for enums, generated from the domain enums
- Composite index `(service, reported_at)` on incidents for "incidents for service X, newest first"

---

### 🔁 Database Migrations

- Alembic with the DB URL read from application settings (`.env`), not from `alembic.ini`
- Two reviewed migrations (incidents, documents), both reversible

---

### 📦 Repository Pattern

```text
API Endpoint
     │
     ▼
Repository(session)
     │
     ▼
Mapper  ──>  ORM Record  ──>  PostgreSQL
```

- Repositories accept and return domain objects; ORM objects never leave them
- Repositories **flush but never commit**: the caller owns the transaction

---

### 🌐 REST API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Application health |
| `GET` | `/health/database` | Database connectivity check |
| `POST` | `/incidents` | Create an incident (server generates the id) and index it |
| `GET` | `/incidents/{id}` | Fetch one incident (404 if unknown) |
| `GET` | `/incidents` | List incidents: `service`, `severity`, `status`, `limit`, `offset` |
| `POST` | `/documents` | Create a document |
| `GET` | `/documents/{id}` | Fetch one document |
| `GET` | `/documents` | List documents: `service`, `doc_type`, `limit`, `offset` |
| `GET` | `/search/incidents` | Semantic search: `q`, `service`, `severity`, `status`, `limit`, `min_score` |

```text
Request
   │
   ▼
FastAPI Router
   │
   ▼
get_session (one transaction per request)
   │      commit on success / rollback on error
   ▼
Repository
```

---

### 🧠 Embeddings

- `OllamaEmbeddingService` calls Ollama's `POST /api/embed` with `nomic-embed-text` (768 dimensions)
- Single and batch embedding, explicit timeout
- Clear `EmbeddingError` for connection failures, HTTP errors, and malformed responses

---

### 🔎 Semantic Incident Search

```text
Question
   │
   ▼
Embed (Ollama)  ──►  query vector
   │
   ▼
Qdrant search + payload filters (service, severity, status)
   │      returns incident ids + similarity scores
   ▼
Load incidents from PostgreSQL by id (one query)
   │
   ▼
Ranked results: incident + score
```

- Qdrant collection `incidents`: 768 dimensions, cosine distance, keyword indexes on `service`, `severity`, `status`
- The **PostgreSQL UUID is the Qdrant point id**, so the two stores stay linkable and re-indexing is an idempotent upsert
- Only title, description, root cause, and resolution are embedded; service, severity, status, and tags are payload for filtering
- Qdrant hits that no longer exist in PostgreSQL are skipped (index drift is tolerated)
- Backend outages (Ollama or Qdrant down) return `503`, not `500`

---

### 🔁 Indexing and Reindexing

- Creating an incident indexes it in Qdrant **best effort**: PostgreSQL is the source of truth, so an embedding or Qdrant outage never blocks recording an incident (the failure is logged)
- `python -m app.scripts.reindex` rebuilds the vector index from PostgreSQL, healing missed or pre-existing incidents. It is safe to run repeatedly.
- The API ensures the collection exists at startup, without failing if Qdrant is down

---

### 🧪 Testing

- Unit tests for Pydantic models, mappers, and the embedding client (mocked HTTP)
- Repository and API tests against real PostgreSQL, wrapped in a transaction that is always rolled back
- Qdrant and search tests use throwaway collections, deleted afterwards; the real `incidents` collection is never touched
- End-to-end tests with real Ollama, Qdrant, and PostgreSQL, including `POST /incidents` followed by `GET /search/incidents`

> Tests need PostgreSQL, the Qdrant container, and Ollama with `nomic-embed-text` running.

---

## 🔮 Planned

### 📄 Document Indexing

- Chunking long runbooks and guides
- Embedding and indexing chunks with a link back to the source document

### 🔀 Better Retrieval

- Hybrid search (dense + sparse) with payload filters
- Reranking
- Evaluating task prefixes for `nomic-embed-text` and score thresholds on real data

### 💬 Grounded Answers

- Answers generated only from retrieved context (AWS Bedrock / Claude)
- Citations to source incidents and documents

### 🕵️ Investigation Workflow

- Multi-source reasoning with LangGraph

### 🔐 Security

- Authentication, RBAC, and document-level permissions

### 📈 Production Readiness

- Evaluation, observability, and reliability

### 🖥 Application

- React frontend and a full Docker Compose deployment

---

# 🏗 Architecture

## Current

```text
                          Client
                             │
                             ▼
                          FastAPI
                             │
            ┌────────────────┼─────────────────┐
            ▼                ▼                 ▼
     Incident / Doc       Search API      get_session
        endpoints             │          (transaction)
            │                 ▼                │
            │        IncidentSearchService     │
            │           │            │         │
            │           ▼            ▼         ▼
            │        Ollama       Qdrant   PostgreSQL
            │     (embeddings)  (vectors + (source of
            │                    payload)     truth)
            └──── on create: embed + upsert ───┘
```

## Target

```text
                     Client
                        │
                        ▼
                     FastAPI
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   Incident API    Ingestion API     Query API
        │               │                │
        ▼               ▼                ▼
   PostgreSQL ◄──── Embeddings ────► Qdrant
 (source of truth)                  (vectors + payload)
                                         │
                                         ▼
                              Hybrid Retrieval + Rerank
                                         │
                                         ▼
                                LLM (Bedrock / Claude)
                                         │
                                         ▼
                             Grounded Answer + Citations
```

**Design decision:** PostgreSQL stays the source of truth. Qdrant stores vectors and search payloads only, and can always be rebuilt from PostgreSQL.

---

# 📂 Project Structure

```text
enterprise-rag/

├── alembic/
│      env.py
│      versions/
│          9411c4d2a5dd_create_incidents_table.py
│          78ccf1fc6fb9_create_documents_table.py
│
├── app/
│   ├── api/
│   │   ├── deps.py
│   │   ├── dto/
│   │   │      incident.py
│   │   │      document.py
│   │   │      limits.py
│   │   └── routes/
│   │          incidents.py
│   │          documents.py
│   │          search.py
│   │
│   ├── config/
│   │      connection.py
│   │      qdrant.py
│   │      settings.py
│   │
│   ├── model/
│   │      base.py
│   │      incident_record.py
│   │      document_record.py
│   │
│   ├── repository/
│   │      incident_mapper.py
│   │      incident_repository.py
│   │      document_mapper.py
│   │      document_repository.py
│   │
│   ├── services/
│   │      embedding_service.py
│   │      incident_indexer.py
│   │      incident_search_service.py
│   │      reindex.py
│   │
│   └── scripts/
│          reindex.py
│
├── tests/
├── docker-compose.yml
├── alembic.ini
├── main.py
├── pytest.ini
├── requirements.txt
├── CLAUDE.md
└── README.md
```

---

# 🔄 Workflow

## Create an Incident

```text
POST /incidents
      │
      ▼
IncidentCreate validation (422 on rule violation)
      │
      ▼
Generate UUID  →  Incident
      │
      ▼
IncidentRepository.add()  →  INSERT (flush)
      │
      ▼
Index in Qdrant (best effort, failure only logged)
      │
      ▼
get_session commits  →  201 Created
```

## Search Incidents

```text
GET /search/incidents?q=...
      │
      ▼
Embed question  →  Qdrant search (+ filters)
      │
      ▼
Load incidents from PostgreSQL by id
      │
      ▼
200 [{incident, score}, ...]      (503 if Ollama or Qdrant is unavailable)
```

---

# 🧩 Key Design Decisions

## Separate DTO and ORM Models

```text
Incident (Pydantic)         IncidentRecord (SQLAlchemy)
API / domain contract       Database row mapping
Validation rules            Columns, constraints, indexes
```

A schema change does not leak into the API contract, and the reverse. The cost is an explicit mapping step.

## Transaction Boundary

```text
Repository  →  flush only
get_session →  commit / rollback
```

One request is one transaction, similar to `@Transactional` on a service in Spring.

## String + CHECK Instead of a Native ENUM

Severity, status, and document type are stored as strings with `CHECK` constraints generated from the Python enums. This keeps integrity in the database while avoiding the migration pain of changing a native PostgreSQL ENUM.

## PostgreSQL + Qdrant Instead of pgvector

Qdrant provides built-in dense + sparse hybrid search and payload filtering. The trade-off is two stores to keep in sync, which is why PostgreSQL remains the source of truth, the UUID is shared, and a reindex script exists.

## Best-Effort Indexing

Indexing runs when an incident is created, but a failure does not fail the request. Recording an incident must work even when Ollama or Qdrant is down. The cost is that a missed incident is not searchable until `reindex` runs.

## Fail Loudly on Vector Size Mismatch

`ensure_collection` refuses to reuse a collection with a different vector size. Changing the embedding model means recreating the collection and re-embedding everything.

---

# ⚙ Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.14 |
| API | FastAPI |
| Validation | Pydantic |
| ORM | SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL |
| DB Driver | psycopg 3 |
| Vector Store | Qdrant 1.20 (Docker) |
| Embeddings | Ollama, `nomic-embed-text` (768 dimensions) |
| LLM | AWS Bedrock / Claude *(planned)* |
| Orchestration | LangGraph *(planned)* |
| Testing | Pytest, FastAPI TestClient |
| Containers | Docker Compose (Qdrant today, full stack *planned*) |
| Frontend | React *(planned)* |

---

# ▶ Getting Started

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Start the supporting services

PostgreSQL must be running locally. Start Qdrant with Docker:

```bash
docker compose up -d
```

Make sure Ollama is running and has the embedding model:

```bash
ollama pull nomic-embed-text
```

## 3. Create the database

```bash
createdb opsmind
```

## 4. Configure `.env`

```text
DATABASE_URL=postgresql+psycopg://<user>@127.0.0.1:5432/opsmind
QDRANT_URL=http://localhost:6333
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_EMBEDDING=nomic-embed-text:latest
```

`QDRANT_URL`, `OLLAMA_BASE_URL`, and `OLLAMA_MODEL_EMBEDDING` are optional; the values above are the defaults.

## 5. Apply migrations

```bash
alembic upgrade head
```

## 6. Run the API

```bash
python -m uvicorn main:app --reload
```

If port 8000 is already taken, add `--port 8001`. Open `/docs` for the interactive API documentation.

## 7. Index existing incidents

Incidents created through the API are indexed automatically. To index incidents that already exist, or to heal missed ones:

```bash
python -m app.scripts.reindex
```

## 8. Run the tests

```bash
python -m pytest
```

> The database tests run inside a transaction that is rolled back, and the Qdrant tests use throwaway collections, so they leave no data behind.

---

# 🗺 Roadmap

| Phase | Focus | Status |
|---|---|---|
| 1 | Knowledge foundation: incident models, ingestion, APIs | ✅ Complete |
| 2 | RAG engine: embeddings, Qdrant retrieval, grounded answers | 🚧 In progress (incident search done) |
| 3 | Investigation: multi-source reasoning, LangGraph | ⏳ Planned |
| 4 | Security: authentication, RBAC, document permissions | ⏳ Planned |
| 5 | Production: evaluation, observability, reliability | ⏳ Planned |
| 6 | Application: React frontend and deployment | ⏳ Planned |

**Next up in Phase 2:** document chunking and indexing, then hybrid search, reranking, and grounded answers with citations.

---

# 🎯 Learning Outcomes

After completing this project, you will understand:

- Pydantic domain modelling and business-rule validation
- SQLAlchemy 2.x typed ORM mapping
- PostgreSQL types: `TIMESTAMPTZ`, `UUID`, `ARRAY`, `CHECK` constraints
- Alembic setup, autogenerate, and migration review
- Repository pattern and DTO / ORM separation
- Transaction boundaries and the unit-of-work pattern
- FastAPI routers, dependency injection, and dependency overrides in tests
- Testing with transaction-rollback fixtures
- Running Qdrant with Docker Compose
- Embeddings with Ollama and vector dimensions
- Qdrant collections, points, payloads, filters, and cosine similarity
- Keeping a vector index in sync with a source-of-truth database
- Semantic search and ranking
- Graceful degradation when dependent services are down
- Hybrid search, reranking, and citations *(upcoming)*
- LangGraph investigation workflows *(upcoming)*
- RBAC and document-level permissions *(upcoming)*

---

# ⭐ Key Concepts Demonstrated

- Layered architecture (API → repository → database)
- Domain validation with Pydantic
- Explicit DTO ↔ ORM mapping
- Versioned schema migrations
- One-transaction-per-request design
- Source-of-truth plus search-index architecture
- Idempotent re-indexing keyed by a shared UUID
- Database-backed and service-backed integration testing

---

# 🚫 Scope

At this stage the project intentionally does **not** include:

- LLM answer generation or citations
- Document chunking and indexing
- Hybrid search or reranking
- Authentication or authorization
- A frontend
- A full Docker Compose deployment (only Qdrant is containerized)

The purpose of the current stage is specifically:

> **Building a tested knowledge foundation and a working semantic retrieval layer before adding generation.**
