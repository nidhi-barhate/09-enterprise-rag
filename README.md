# 🛠 OpsMind AI — Enterprise Incident Intelligence

> A production-oriented Enterprise RAG system built using Python, FastAPI, PostgreSQL, Qdrant, and Ollama that helps engineering teams investigate incidents using historical incident reports, runbooks, troubleshooting guides, and technical documentation, with grounded answers and citations.

> **Status:** Phase 1 (Knowledge Foundation) is complete. Phase 2 (RAG Engine) is in progress: semantic search over incidents works end to end and is measured against a seeded test dataset. Document chunking, indexing, and search exist as a tested service layer but are **not yet exposed through the API**. Hybrid search, reranking, grounded answers, and the UI are **Planned**.

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

📖 **Visual guides** (open in a browser):

- [`docs/opsmind-overview.html`](docs/opsmind-overview.html): step-by-step flows and every file explained
- [`docs/qdrant-story.html`](docs/qdrant-story.html): a short animated story with subtitles explaining what Qdrant does

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
- Create, get, and list through the API (storage only; see *Planned* for search)

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
- `get_many(ids)` loads many records in one query (used to turn Qdrant hits into full records)

---

### 🌐 REST API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Application health |
| `GET` | `/health/database` | Database connectivity check |
| `POST` | `/incidents` | Create an incident (server generates the id) and index it |
| `GET` | `/incidents/{id}` | Fetch one incident (404 if unknown) |
| `GET` | `/incidents` | List incidents: `service`, `severity`, `status`, `limit`, `offset` |
| `POST` | `/documents` | Create a document (stored in PostgreSQL only) |
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
- The API ensures the incident collection exists at startup, without failing if Qdrant is down

---

### ✂️ Document Chunking, Indexing, and Search *(service layer)*

Long runbooks are split into chunks so each chunk gets its own vector and keeps a single topic.

```text
Document (PostgreSQL)
      │
      ▼
chunk_text(size, overlap)   paragraph → line → sentence → space → hard cut
      │
      ▼
embed chunks in batches (title added to the embedded text)
      │
      ▼
Qdrant "document_chunks": one point per chunk
      id      = uuid5(document id, chunk number)   (deterministic)
      payload = document_id, chunk_index, chunk_count, title,
                doc_type, service, source, text
      │
      ▼
search → best chunks → keep the best chunk per document → load documents from PostgreSQL
```

- **Chunker:** a pure function; chunks never exceed `size`, neighbours share about `overlap` characters, and cuts prefer natural boundaries
- **Indexer:** embeds first and writes second (an Ollama failure leaves existing chunks untouched), removes chunks that no longer exist when a document gets shorter, and can delete all chunks of a document
- **Search:** returns the **best passage per document** with its score, so the matched text can be shown as a citation
- A document **without a service applies to every service**, so it stays in results when filtering by service
- ⚠️ Not wired to the API yet: `POST /documents` does not index, there is no `/search/documents` endpoint, and the real `document_chunks` collection has not been created

---

### 🌱 Test Data and Search Evaluation

- `python -m app.scripts.seed_incidents` loads **100 synthetic incidents** (10 scenarios × 10 differently worded incidents) into **PostgreSQL and Qdrant**
  - fixed ids and a `seed` tag, so repeating it never duplicates and `--clean` removes only the seeded incidents
- `python -m app.scripts.evaluate_search` asks 20 questions with known answers and reports whether the **first result** and the **top 5** come from the right scenario
- Example run on the seeded data: the first result was from the right scenario for 18 of 20 questions (90%). Treat this as a baseline for comparing future changes (hybrid search, reranking), not as a real-world accuracy number: the data is synthetic and small.

---

### 🧪 Testing

- Unit tests for Pydantic models, mappers, the chunker, and the embedding client (mocked HTTP)
- Repository and API tests against real PostgreSQL, wrapped in a transaction that is always rolled back
- Qdrant, indexing, and search tests use throwaway collections, deleted afterwards; the real collections are never touched
- End-to-end tests with real Ollama, Qdrant, and PostgreSQL, including `POST /incidents` followed by `GET /search/incidents`
- Tests for the seed data, the seed and clean logic, and the evaluation maths

> Tests need PostgreSQL, the Qdrant container, and Ollama with `nomic-embed-text` running.

---

## 🔮 Planned

### 🔌 Document API Wiring

- Index documents on `POST /documents` (best effort), `GET /search/documents`, and documents in the reindex script

### 🖥 Simple UI

- A single page served by FastAPI: search box, filters, and a results table with match scores. React comes later (Phase 6).

### 🔀 Better Retrieval

- Hybrid search (dense + sparse) with payload filters
- Reranking
- Tuning chunk size, task prefixes for `nomic-embed-text`, and score thresholds against the evaluation script

### 💬 Grounded Answers

- Answers generated only from retrieved context (AWS Bedrock / Claude)
- Citations to source incidents and documents

### 🕵️ Investigation Workflow

- Multi-source reasoning with LangGraph

### 🔐 Security

- Authentication, RBAC, and document-level permissions

### 📈 Production Readiness

- Evaluation, observability, and reliability

### 🚢 Deployment

- Full Docker Compose deployment

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
            └── on incident create: embed + upsert ──┘

   Service layer only (not exposed by the API yet):
   chunker → DocumentIndexer → Qdrant "document_chunks" → DocumentSearchService
```

## Target

```text
                     Client / UI
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
│   │      chunker.py
│   │      document_indexer.py
│   │      document_search_service.py
│   │      reindex.py
│   │
│   └── scripts/
│          reindex.py
│          seed_data.py
│          seed_incidents.py
│          evaluate_search.py
│
├── docs/
│      opsmind-overview.html
│      qdrant-story.html
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

## Index and Search a Document *(service layer)*

```text
DocumentIndexer.index(document)
      │
      ▼
chunk  →  embed (batches)  →  upsert chunk points  →  delete stale chunks

DocumentSearchService.search(question)
      │
      ▼
embed question → Qdrant (document_chunks) → best chunk per document → documents from PostgreSQL
```

## Seed and Evaluate

```text
python -m app.scripts.seed_incidents      100 incidents → PostgreSQL + Qdrant
python -m app.scripts.evaluate_search     20 questions → first result / top-5 correctness
python -m app.scripts.seed_incidents --clean
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

Qdrant provides built-in dense + sparse hybrid search and payload filtering. The trade-off is two stores to keep in sync, which is why PostgreSQL remains the source of truth, the UUID is shared, and a reindex script exists. For today's data size pgvector would also have worked, and would have been simpler.

## Best-Effort Indexing

Indexing runs when an incident is created, but a failure does not fail the request. Recording an incident must work even when Ollama or Qdrant is down. The cost is that a missed incident is not searchable until `reindex` runs.

## Fail Loudly on Vector Size Mismatch

`ensure_collection` refuses to reuse a collection with a different vector size. Changing the embedding model means recreating the collection and re-embedding everything.

## Chunk Documents, Not Incidents

Incidents are short, so one incident is one vector. Documents are long and cover several topics, so each is cut into chunks. In a small test with three questions, the matching chunk scored higher than the whole three-topic document every time.

## Deterministic Chunk Ids

A chunk's point id is `uuid5(document id, chunk number)`, so re-indexing overwrites instead of duplicating. The document's own id travels in the payload as `document_id`, which links a found chunk back to PostgreSQL.

## Global Documents Match Every Service

A document with no `service` applies to every service, so a service filter keeps it in the results.

## Measure Search, Don't Eyeball It

A seeded dataset with known answers and an evaluation script turn "it looks right" into numbers that can be compared before and after each retrieval change.

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
| Frontend | A simple served page first, React later *(planned)* |

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

## 7. Add test data (optional but recommended)

Load 100 synthetic incidents into PostgreSQL and Qdrant, then measure search quality:

```bash
python -m app.scripts.seed_incidents
```

```bash
python -m app.scripts.evaluate_search
```

Remove the seeded incidents again (your own incidents are left alone):

```bash
python -m app.scripts.seed_incidents --clean
```

## 8. Reindex (only when needed)

Incidents created through the API are indexed automatically. To index incidents that already exist, or to heal missed ones:

```bash
python -m app.scripts.reindex
```

## 9. Run the tests

```bash
python -m pytest
```

> The database tests run inside a transaction that is rolled back, and the Qdrant tests use throwaway collections, so they leave no data behind.

---

# 🗺 Roadmap

| Phase | Focus | Status |
|---|---|---|
| 1 | Knowledge foundation: incident models, ingestion, APIs | ✅ Complete |
| 2 | RAG engine: embeddings, Qdrant retrieval, grounded answers | 🚧 In progress (incident search and document chunking done; API wiring and answers pending) |
| 3 | Investigation: multi-source reasoning, LangGraph | ⏳ Planned |
| 4 | Security: authentication, RBAC, document permissions | ⏳ Planned |
| 5 | Production: evaluation, observability, reliability | ⏳ Planned |
| 6 | Application: React frontend and deployment | ⏳ Planned |

**Next up:** a simple UI for search, wiring document indexing and search into the API, then hybrid search, reranking, and grounded answers with citations.

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
- Chunking long documents, overlap, and deterministic chunk ids
- Semantic search, ranking, and returning the best passage per document
- Building a seeded dataset and measuring search quality
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
- Evaluation-driven retrieval development

---

# 🚫 Scope

At this stage the project intentionally does **not** include:

- LLM answer generation or citations
- Document indexing and search through the API (the service layer exists)
- Hybrid search or reranking
- Authentication or authorization
- A frontend
- A full Docker Compose deployment (only Qdrant is containerized)

The purpose of the current stage is specifically:

> **Building a tested knowledge foundation and a measurable semantic retrieval layer before adding generation.**
