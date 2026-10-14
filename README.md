# CodeLens AI — AI Codebase Intelligence Platform

**CodeLens AI** is an intelligent developer platform designed to understand, index, and visualize software repositories. A developer registers a repository, and the platform inspects the codebase using native AST analysis, extracts structural entities (modules, classes, methods, functions, decorators, parameters, and docstrings), builds a persistent relational code knowledge graph, extracts deterministic function call relationships, generates contextual 384-dimensional vector embeddings stored in PostgreSQL with `pgvector`, renders interactive call graphs and execution traces, and delivers evidence-grounded AI question answering.

---

## System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend (Port 3000)                    │
│  - Repository & File Explorer      - Symbol Detail Inspector          │
│  - Interactive @xyflow/react Graph - Architecture Trace Visualization  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON
┌───────────────────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend Service (Port 8000)                   │
│  - Python AST Parsing Engine       - Bounded Graph Trace Service       │
│  - Relational Knowledge Graph      - Grounded Evidence RAG Pipeline    │
│  - Hardened Non-Root Execution     - Deterministic Symbol Resolver     │
│  - sentence-transformers (MiniLM)  - Path Traversal Confinement        │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │ (Optional)
┌───────────────────▼──────────────────┐   ┌─────────▼───────────────────┐
│     PostgreSQL 16 + pgvector         │   │      Configured LLM         │
│     (Host: 5434, Docker: 5432)       │   │    (OpenAI / gpt-4o-mini)   │
│  - CodeFile, CodeSymbol, Relational  │   │  - Evidence-Grounded Q&A    │
│  - 384-dim Vector Embeddings         │   │  - Strict Citation Checker  │
└──────────────────────────────────────┘   └─────────────────────────────┘
```

### Core Architecture Components
1. **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS v4, and `@xyflow/react` interactive canvas. Provides live repository indexing, searchable symbol exploration, 1-hop/2-hop focused call graph visualization, and architecture trace step highlighting. Runs on port `3000`.
2. **Backend**: FastAPI REST API running on Python 3.12 with CPU-only PyTorch optimization (`torch==2.6.0+cpu`) and a dedicated non-root application user (`appuser`, UID/GID `10001`). Enforces path confinement with `ALLOWED_REPO_ROOTS`. Runs on port `8000`.
3. **Database**: PostgreSQL 16 with the `pgvector` extension (`pgvector/pgvector:pg16`). Persists relational code entities, structural relationships (`contains`, `inherits`, `imports`, `calls`), code chunks, and 384-dimensional dense vector embeddings.
4. **Deterministic Analysis Engine**: Native Python AST analysis extracts symbols and function calls without code execution.
5. **Deterministic Architecture Tracer**: Purely graph-driven call flow reconstitution (`POST /api/v1/repositories/{id}/architecture/trace`) requiring **zero LLM calls** or API keys.
6. **Evidence-Grounded LLM Layer**: Optional pluggable LLM provider for natural-language Q&A (`/ask`) and architecture explanation (`/architecture/explain`) with strict evidence grounding and citation validation.

---

## Service URLs and Port Reference

| Service | Host URL / Endpoint | Docker Internal URL | Description |
|---|---|---|---|
| **Frontend Web Dashboard** | [http://localhost:3000](http://localhost:3000) | `http://frontend:3000` | Next.js interactive developer dashboard |
| **Backend REST API** | [http://localhost:8000](http://localhost:8000) | `http://backend:8000` | FastAPI application endpoints |
| **Interactive API Documentation** | [http://localhost:8000/docs](http://localhost:8000/docs) | N/A | Swagger UI with interactive endpoint schema |
| **API Health Check** | [http://localhost:8000/health](http://localhost:8000/health) | `http://localhost:8000/health` | Backend and database connectivity check |
| **PostgreSQL + pgvector** | `127.0.0.1:5434` | `db:5432` | Relational and vector database |

> **Note on Database Host Port (5434):**
> The PostgreSQL container maps container port `5432` to host port **`5434`** (`127.0.0.1:5434:5432`) to prevent conflicts with native local PostgreSQL instances running on ports 5432 or 5433. Inside Docker Compose, the backend connects directly to `db:5432`. If connecting from the host machine (e.g. database client or host scripts), use port `5434`.

---

## Prerequisites and Environment Variables

### Prerequisites
- **Docker & Docker Compose**: Docker Engine 24+ and Docker Compose v2.
- **Node.js**: v20+ (only required if running or building the frontend locally outside Docker).
- **Python**: 3.11 or 3.12 (only required if running backend scripts or tests locally outside Docker).
- **Git**: For cloning repositories.

### Configuration Setup
Copy the environment template before starting the services:

```bash
cp .env.example .env
```

### Environment Variables Reference

| Variable | Type | Default | Description |
|---|---|---|---|
| `PROJECT_NAME` | string | `CodeLens AI — AI Codebase Intelligence Platform` | Platform title |
| `API_V1_STR` | string | `/api/v1` | Base API route prefix |
| `DATABASE_URL` | string | `postgresql://postgres:postgres@localhost:5432/codelens` | Database connection string (internal Docker uses `db:5432`, host tools use `localhost:5434`) |
| `POSTGRES_USER` | string | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | string | `postgres` | PostgreSQL password |
| `POSTGRES_DB` | string | `codelens` | PostgreSQL database name |
| `CORS_ORIGINS` | JSON list / string | `["http://localhost:3000","http://127.0.0.1:3000"]` | Allowed CORS origins for the frontend |
| `ALLOWED_REPO_ROOTS` | string | `/app/repositories` | Restricts allowed repository paths for registration. Empty allows any local path in dev mode. |
| `MAX_FILE_SIZE_BYTES` | integer | `1000000` (1 MB) | Maximum individual file size for AST analysis |
| `MAX_FILES_PER_REPO` | integer | `5000` | Maximum files indexed per repository |
| `EMBEDDING_MODEL_NAME` | string | `sentence-transformers/all-MiniLM-L6-v2` | Model used for semantic code chunk embeddings |
| `EMBEDDING_DIMENSION` | integer | `384` | Embedding vector dimension |
| `SEARCH_DEFAULT_LIMIT` | integer | `5` | Default number of semantic search results |
| `SEARCH_MAX_LIMIT` | integer | `20` | Maximum allowed semantic search results |
| `LLM_PROVIDER` | string | `openai` | LLM provider backend |
| `LLM_API_KEY` | string | `""` (empty) | API key for LLM provider. **Required only for `/ask` and `/architecture/explain`**. |
| `LLM_MODEL` | string | `gpt-4o-mini` | Model identifier for LLM generation |
| `RAG_TOP_K_SEMANTIC` | integer | `8` | Number of semantic retrieval candidates |
| `RAG_MAX_EVIDENCE_ITEMS` | integer | `12` | Hard cap on final evidence items passed to LLM |
| `MAX_QUESTION_LENGTH` | integer | `1000` | Maximum character length for user questions |
| `ARCHITECTURE_TRACE_MAX_DEPTH` | integer | `8` | Maximum call traversal depth for architecture traces |
| `ARCHITECTURE_TRACE_MAX_NODES` | integer | `20` | Maximum nodes returned in an architecture trace |
| `NEXT_PUBLIC_API_URL` | string | `http://localhost:8000/api/v1` | Backend API base URL consumed by the frontend client |

---

## Docker Compose Startup and Shutdown

CodeLens AI provides a containerized stack configured in `docker-compose.yml`.

### 1. Build and Start the Stack
Start all three services in detached mode:

```bash
docker compose up -d
```

To force a rebuild of the application images (e.g. after code changes):

```bash
docker compose up -d --build
```

### 2. Verify Service Status and Health
Check that all three containers are running and healthy:

```bash
docker compose ps
```

Expected healthy output:
```text
NAME                IMAGE                        COMMAND                  SERVICE    STATUS
codelens_backend    ai_resuem_project-backend    "uvicorn app.main:ap…"   backend    Up (healthy)
codelens_frontend   ai_resuem_project-frontend   "docker-entrypoint.s…"   frontend   Up (healthy)
codelens_postgres   pgvector/pgvector:pg16       "docker-entrypoint.s…"   db         Up (healthy)
```

Verify backend health directly:
```bash
curl http://localhost:8000/health
```
Response: `{"status":"ok","service":"CodeLens AI Repository Analyzer"}`

### 3. Inspect Service Logs
Follow logs across all services:
```bash
docker compose logs -f
```

Or view logs for a specific service:
```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```

### 4. Stop and Shutdown the Stack
Stop all running containers while preserving persisted database data in the `postgres_data` volume:

```bash
docker compose down
```

To stop containers and delete the database volume (clean reset):
```bash
docker compose down -v
```

---

## Core Workflows and API Capabilities

### 1. Repository Registration
Registers a codebase directory for indexing. When running in Docker, repositories placed in `./evaluation_repos` are mounted read-only into `/app/repositories`.

**Endpoint:** `POST /api/v1/repositories`
```json
{
  "name": "tinydb",
  "path": "/app/repositories/tinydb"
}
```

### 2. Codebase Analysis and Indexing
Performs native Python AST parsing, builds the code knowledge graph (`contains`, `inherits`, `imports`, `calls`), creates contextual code chunks, and generates 384-dimensional vector embeddings stored in `pgvector`. This workflow is completely idempotent.

**Endpoint:** `POST /api/v1/repositories/{id}/analyze`

### 3. Symbol Exploration
Query and inspect indexed symbols with type filters and search queries.

**Endpoints:**
- `GET /api/v1/repositories/{id}/symbols?symbol_type=function&search=insert`
- `GET /api/v1/repositories/{id}/symbols/{symbol_id}`: Detailed symbol view with signatures, line intervals, docstrings, and graph edges.
- `GET /api/v1/repositories/{id}/relationships?relationship_type=calls`: Filter structural relationships.

### 4. Semantic Code Search
Uses cosine similarity search over vector embeddings to find relevant code snippets conceptually without requiring exact keyword matches.

**Endpoint:** `POST /api/v1/repositories/{id}/search`
```json
{
  "query": "Where is data persisted to disk?",
  "limit": 5
}
```

### 5. Interactive Function Call Graph
The Next.js frontend (`http://localhost:3000`) renders an interactive directed graph canvas using `@xyflow/react`:
- Nodes represent functions and methods; directed edges represent AST-verified `calls` relationships with call-site line numbers (`L<line>`).
- Supports 1-hop and 2-hop neighborhood extraction around a focused symbol.
- Automatically focuses on the highest-degree call hub when no focus symbol is selected.
- Clicking any node opens the Symbol Detail Inspector.

### 6. Deterministic Architecture Tracing (No LLM Required)
Reconstructs static execution flow starting from any qualified symbol using only persisted AST `calls` relationships.

**Endpoint:** `POST /api/v1/repositories/{id}/architecture/trace`
```json
{
  "start_symbol": "tinydb.table.Table.insert"
}
```

**Key Properties:**
- **Zero LLM Dependency**: Does NOT use an LLM, embeddings, or probabilistic models.
- **Cycle-Safe**: Enforces `ARCHITECTURE_TRACE_MAX_DEPTH` (default 8) and `ARCHITECTURE_TRACE_MAX_NODES` (default 20), terminating safely on recursive or cyclic calls.
- **Deterministic Ordering**: Edges are ordered by caller source line number, with same-line ties broken deterministically by target qualified name.

---

## LLM Explanation Requirements

CodeLens AI cleanly separates deterministic graph capabilities from probabilistic language model features:

### Deterministic Features (No API Key Needed)
The following capabilities run entirely locally and require **no external API calls or API keys**:
- Repository registration and AST parsing.
- Symbol extraction and relational graph persistence.
- Function call graph extraction (`calls` edges).
- Semantic search using the local `sentence-transformers/all-MiniLM-L6-v2` embedding model.
- Interactive call graph visualization.
- Deterministic architecture trace (`POST /api/v1/repositories/{id}/architecture/trace`).

### LLM-Powered Features (API Key Required)
An API key for the configured provider (default: `LLM_PROVIDER=openai`, model `gpt-4o-mini`) is required for:
1. **Evidence-Grounded Question Answering**: `POST /api/v1/repositories/{id}/ask`
2. **Architecture-Aware Explain**: `POST /api/v1/repositories/{id}/architecture/explain`

To enable LLM explanations, set your API key in `.env`:
```bash
LLM_API_KEY="sk-..."
```

### Graceful Fallback Behavior
- If `LLM_API_KEY` is not set or invalid, endpoints requiring an LLM return a clear `503 Service Unavailable` error explaining that the LLM provider is not configured.
- The UI displays an informative notice and allows the user to continue using deterministic architecture tracing without disruption.
- LLM outputs are verified by a strict citation validator. Every factual claim must reference an evidence citation (`[E1]`, `[E2]`). Ungrounded claims or hallucinated citations are stripped or rejected.

---

## Running Tests, Linting, and Production Build

### 1. Backend Test Suite
The backend test suite runs with pytest using an in-memory SQLite database and deterministic mock fixtures, requiring no external network connectivity:

```bash
# From repository root with virtual environment:
pytest -v backend/tests
```

**Result: 144/144 tests passing**:
- Phase 1 (Repository API & Python Analyzer): 13 tests
- Phase 2A (Code Graph Persistence): 15 tests
- Phase 2B (Call Graph Extraction): 12 tests
- Phase 3A (Semantic Search & Embeddings): 16 tests
- Phase 3B-1 (Retrieval Evaluation): 12 tests
- Phase 3B-2 (Evidence-Grounded RAG): 16 tests
- Phase 3C & 3C.1 (Architecture Trace): 18 tests
- Phase 3D (Architecture Explain): 13 tests
- Phase 3D.1 (Architecture Evaluation): 10 tests
- Phase 3E (Real-Repository Validation): 6 tests
- Phase 3G.1 (Reliability, Security, & Confinement): 12 tests
- Phase 1 Files & Analyzer: 1 test

### 2. Frontend Test Suite
The frontend uses the Node.js native test runner to test the API client and graph layout utilities:

```bash
cd frontend
npm test
```

**Result: 17/17 tests passing (2 test suites, 0 failures)**.

### 3. Frontend Linting
Run ESLint across the Next.js application:

```bash
cd frontend
npm run lint
```

**Result: 0 errors, 0 warnings**.

### 4. Frontend Production Build
Validates TypeScript compilation and builds the optimized Next.js Turbopack production bundle:

```bash
cd frontend
npm run build
```

**Result: Static route compilation succeeded with 0 errors**.

---

## Real-Repository Validation & TinyDB Benchmark

To validate CodeLens AI against an unfamiliar, real open-source Python codebase, the platform was benchmarked on **TinyDB** (`https://github.com/msiemens/tinydb.git`, commit `6d7c4fc3e04d398b1282876514660a33a7897b41`, MIT License).

### Ingestion Statistics (TinyDB)
- **Files Analyzed**: 21 Python files
- **Classes Indexed**: 15 classes
- **Functions & Methods**: 286 functions and methods
- **CALLS Edges Discovered**: 226 static call edges
- **Code Chunks Created**: 314 chunks
- **Embeddings Generated**: 314 vector embeddings (384-dimensional)
- **Ingestion Errors**: 0 errors

### Benchmark Scope
A benchmark of 13 developer questions (`backend/app/evaluation/real_repo_queries.json`) verified against TinyDB source code:
- **Table Operations**: `Table.insert` $\to$ `Table._get_next_id`, `Table._read_table`, `Table._update_table`, `Table.clear_cache`; `Table.search` $\to$ `Table._read_table`; `Table.count` $\to$ `Table.search`; `Table.truncate` $\to$ `Table._update_table`; `Table.remove` $\to$ `Table._update_table`.
- **Data Persistence**: `JSONStorage.write` (JSON serialization and disk write), `JSONStorage.read`.
- **Resource Management**: `Storage.close` / `TinyDB.close`.
- **Filesystem Utilities**: `storages.touch` (directory creation).
- **Document Operations**: `operations.delete` (document transformation).
- **Negative / Out-of-Domain Queries**: Graceful refusal for absent domains (OAuth2 tokens, Kafka event streaming, Redis clustering).

### Measured Results
```text
Real-Repository Validation Evaluation (TinyDB)
===============================================
Repository: https://github.com/msiemens/tinydb.git
Version:    v4.8.2 (commit 6d7c4fc3e04d398b1282876514660a33a7897b41)
License:    MIT License

Ingestion Statistics:
  Files Analyzed:            21
  Classes Indexed:           15
  Functions & Methods:       286
  CALLS Edges Discovered:    226
  Code Chunks Created:       314
  Embeddings Generated:      314
  Ingestion Errors:          0

Queries Evaluated: 13 (10 positive, 3 negative)

Evaluation Metrics:
  Start Symbol Accuracy:     1.00 (100%)
  Edge Precision:            1.00 (100%)
  Edge Recall:               1.00 (100%)
  Edge F1:                   1.00 (100%)
  Exact Trace Match:         1.00 (100%)
  Negative Query Accuracy:   1.00 (100%)

Latency Measurements:
  Avg Semantic Retrieval:    ~110–155 ms
  Avg Architecture Tracing:  ~2–3 ms
```

### Reproducible Evaluation Command
To run the evaluation independently from the repository root, Python must be able to import the `backend/app` package (as `app` is located inside the `backend/` directory). Set `PYTHONPATH` to include `backend`:

```powershell
# From repository root (Windows PowerShell):
$env:PYTHONPATH="backend"
python -m app.evaluation.run_real_repo_evaluation
```

```bash
# From repository root (Linux / macOS Bash):
PYTHONPATH=backend python -m app.evaluation.run_real_repo_evaluation
```

> **Database Note:** When running outside Docker against the containerized PostgreSQL database, set `DATABASE_URL` to host port `5434` (e.g., `$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5434/codelens"`), or allow the runner to automatically evaluate using its built-in in-memory fallback.


---

## Known Limitations

1. **Static Traces Are Not Runtime Traces**:
   - Architecture traces are derived from static Python AST call-site analysis and graph traversal.
   - They represent structural code relationships declared in the source code, **NOT** dynamic runtime execution traces.
   - Static analysis does **not** model:
     - Runtime branching conditions (e.g. `if condition:` evaluated at runtime).
     - Late dynamic dispatch or runtime polymorphism (e.g. duck typing, runtime subclass selection).
     - Dynamic exception throwing and catch unwinding.
     - Asynchronous concurrency scheduling, thread execution, or event loop interleaving.
     - Dynamic invocation using `getattr()`, `eval()`, `exec()`, or runtime reflection.
2. **Language Support**: Native AST extraction currently indexes Python (`.py`) files. Other supported file types (`.ts`, `.tsx`, `.js`, etc.) are cataloged in file discovery, but full AST entity extraction and call-graph analysis are Python-specific.
3. **Docker Repository Path Confinement**: When running inside Docker, repositories to be analyzed must reside within directories mounted into the container (default: `./evaluation_repos` mounted to `/app/repositories`). Attempting to register paths outside `ALLOWED_REPO_ROOTS` is rejected for security.
4. **File and Repository Limits**: To protect container resources, files larger than 1 MB (`MAX_FILE_SIZE_BYTES`) and repositories with more than 5,000 files (`MAX_FILES_PER_REPO`) are capped by default.
