# Lumio API

Backend for Lumio — SaaS intelligence dashboard for Italian companies. Combines multimodal document ingestion, GraphRAG, AI-powered client discovery, and full company enrichment from the Italian business registry.

## Tech Stack

- **Python 3.13** + FastAPI + Uvicorn
- **MongoDB Atlas** (Motor async) — application data
- **Qdrant Cloud** — vector store (4096-dim, Qwen3-Embedding-8B)
- **Neo4j Aura** — knowledge graph (GraphRAG)
- **Regolo AI** — LLM, embeddings, transcription, OCR
- **LangGraph** — agentic RAG + client discovery orchestration
- **DuckDuckGo** — web search for client discovery and website finding
- **OpenAPI IT Company Advanced** — Italian business registry (P.IVA lookup)
- **VIES** — EU VAT validation (free)
- **TMview** — EU trademark search (free)
- **Google News RSS** — company news search (free)

---

## Cloud Services

| Service | Tier | Purpose |
|---------|------|---------|
| **MongoDB Atlas** | M0 (free) | Application data, company profiles, chat, cache |
| **Qdrant Cloud** | Free | Vector store, 4096-dim cosine |
| **Neo4j Aura** | Free | Knowledge graph (entities, relationships, categories) |
| **Regolo AI** | API key | LLM (gpt-oss-120b), embeddings (Qwen3-Embedding-8B), OCR, transcription |
| **OpenAPI IT** | API key | Italian company registry, 30 req/month free |

---

## Environment Variables

```env
APP_ENV=development
APP_DEBUG=true

MONGODB_URL=mongodb+srv://...
MONGODB_DB_NAME=lumio

QDRANT_URL=https://...cloud.qdrant.io
QDRANT_API_KEY=...
QDRANT_COLLECTION=lumio_documents

NEO4J_URI=neo4j+s://...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

REGOLO_API_KEY=sk-...
REGOLO_BASE_URL=https://api.regolo.ai/v1
REGOLO_MODEL=gpt-oss-120b

OPENAPI_IT_API_KEY=...
OPENAPI_IT_BASE_URL=https://company.openapi.com/IT-advanced

JWT_SECRET_KEY=...
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=10080

DEV_AUTH_BYPASS=false
```

---

## API Endpoints

Base: `/api/v1`

### Auth (public)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register with email + password |
| POST | `/auth/login` | Login, returns JWT |

### Companies

| Method | Path | Description |
|--------|------|-------------|
| GET | `/companies` | List (paginated, searchable) |
| POST | `/companies` | Create (auto-enriches if P.IVA provided) |
| GET | `/companies/{id}` | Full detail with all enrichment data |
| PATCH | `/companies/{id}` | Update fields |
| POST | `/companies/{id}/enrich` | Manual enrichment: registry + web (by P.IVA) |
| DELETE | `/companies/{id}` | Delete with cascade |

### Documents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/companies/{id}/documents` | List |
| POST | `/companies/{id}/documents` | Upload single file |
| POST | `/companies/{id}/documents/multipart` | Upload multiple |
| GET | `/companies/{id}/documents/{doc_id}` | Detail + chunks |
| DELETE | `/companies/{id}/documents/{doc_id}` | Delete + vectors |

### Chat (company-scoped RAG)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/chat/sessions` | List |
| POST | `/chat/sessions` | Create |
| GET | `/chat/sessions/{id}` | Session + messages |
| POST | `/chat/sessions/{id}/messages` | Send message (SSE streaming) |
| DELETE | `/chat/sessions/{id}` | Delete |

### General Chat (cross-company)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/general-chat/sessions` | List |
| POST | `/general-chat/sessions` | Create |
| GET | `/general-chat/sessions/{id}` | Session + messages |
| POST | `/general-chat/sessions/{id}/messages` | Send (SSE streaming) |
| DELETE | `/general-chat/sessions/{id}` | Delete |

### Client Discovery

| Method | Path | Description |
|--------|------|-------------|
| GET | `/web-search/sessions` | List |
| POST | `/web-search/sessions` | Create |
| GET | `/web-search/sessions/{id}` | Session + messages |
| DELETE | `/web-search/sessions/{id}` | Delete |
| POST | `/web-search/sessions/{id}/messages` | Send (SSE streaming) |
| POST | `/web-search/sessions/{id}/add-client` | Add prospect manually |

### Contracts

| Method | Path | Description |
|--------|------|-------------|
| GET | `/companies/{id}/contracts` | List analyses |
| GET | `/companies/{id}/contracts/client-score` | Client score breakdown |
| PATCH | `/companies/{id}/contracts/{cid}/criticality` | Set criticality (1-5) |

### Documents (continued)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/companies/{id}/documents/{doc_id}/content` | Raw text content |

### Rankings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rankings` | Company rankings by client score |
| POST | `/rankings/{id}/recompute` | Recompute scores |

### Analytics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/analytics` | Token usage + Lumio Credits |
| GET | `/analytics/graph/national` | National knowledge graph (all user companies) |
| GET | `/analytics/graph/{id}` | Knowledge graph data (single company) |

### Settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings` | Get user preferences |
| PATCH | `/settings` | Update user preferences |

### Onboarding

| Method | Path | Description |
|--------|------|-------------|
| POST | `/onboarding/analyze` | Analyze company from URL or description |
| POST | `/onboarding/confirm` | Confirm profile, create company |
| GET | `/onboarding/status` | Check onboarding completion |

### Health & Public

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/health/sse-test` | SSE streaming test |
| GET | `/landing/graph` | Public mock graph |

---

## Features

### Document Ingestion
Multimodal pipeline: PDF, DOCX, XLSX, PPTX, TXT, CSV, audio, video, images. Each document goes through: text extraction, chunking (1000/200 overlap), Qdrant embedding, Neo4j entity extraction, macro-category classification, and contract analysis. Parallel processing with semaphore (max 10 concurrent).

### Chat (Agentic GraphRAG)
LangGraph agent that orchestrates vector search (Qdrant) and graph traversal (Neo4j) to answer questions about a company's documents. SSE streaming via fetch + ReadableStream.

### General Chat (Cross-Company Intelligence)
Strategic AI assistant with full portfolio awareness. Pre-filters companies by macro-category, aggregates client scores, revenue, contracts across the entire portfolio.

### Client Discovery
LangGraph agent that searches the web for potential Italian clients. Flow: LLM generates search queries (Italian + English) -> DuckDuckGo search -> LLM extracts prospects with fit scores -> deduplication against existing clients -> LLM recommends with tool calling to add prospects. Added prospects get auto-enriched.

### Company Enrichment
Two-phase pipeline triggered automatically when creating a company with P.IVA, or manually via `/enrich`:

**Phase 1 — Registry (OpenAPI IT Company Advanced):**
- Legal name, form, address with GPS coordinates
- ATECO classification (main, 2007, 2022)
- PEC, SDI code, REA, CCIAA
- Balance sheets history (turnover, employees, net worth, assets)
- Shareholders with ownership percentages
- Cached per user+P.IVA in MongoDB (avoids repeat API calls)

**Phase 2 — Web enrichment (async, ~40-50s):**
- VIES P.IVA validation (free EU API)
- Website search via DuckDuckGo (4 query variants: locality, VAT, sector, PEC domain)
- P.IVA verification on homepage + /privacy-policy, /contatti, /cookie-policy, /chi-siamo
- Disambiguation engine scoring candidates by: VAT match (+0.45), city (+0.15), ATECO keywords (+0.10), name in title (+0.10), legal form (+0.05), province (+0.05)
- Contact scraping: email, phone, LinkedIn, Facebook, Instagram, Twitter
- Fallback social search via DuckDuckGo if scraping misses profiles
- TMview trademark search (public EU database)
- Google News RSS with word-boundary relevance filtering
- AI description synthesis (Regolo AI, 150-250 words Italian, JSON output)

When creating a company with P.IVA, the API returns immediately and enrichment runs in the background via FastAPI BackgroundTasks.

### Contract Analysis
LLM extracts structured data from uploaded contracts: financials (canone, pricing model), SLA (uptime, credits), terms (duration, notice, auto-renewal, liability cap), risk flags, and auto-criticality scoring.

### Rankings
Client scoring: spend weight (35%), lock-in (25%), SLA risk (25%), criticality (15%). Plus data richness score based on documents, entities, and relationships.

### Backoffice UI
Single-page HTML backoffice (`index.html`) with: auth, company CRUD with structured enrichment view (registry data, financials, contacts, AI description, enrichment status), document upload, chat, general chat, client discovery, rankings, analytics, knowledge graph visualization, settings, and onboarding.

---

## AI Models (Regolo AI)

| Model | Use |
|-------|-----|
| `gpt-oss-120b` | Chat, entity extraction, contract analysis, client discovery, description synthesis |
| `Qwen3-Embedding-8B` | Text embeddings (4096-dim, cosine) |
| `qwen3-vl-32b` | Image OCR |
| `faster-whisper-large-v3` | Audio/video transcription |

---

## Project Structure

```
app/
  api/v1/            API routes (auth, companies, documents, chat, etc.)
  db/                Database clients (MongoDB, Qdrant, Neo4j)
  middleware/         JWT auth
  schemas/            Pydantic models
  services/
    llm.py           Regolo AI client (chat, embeddings, extraction)
    ingestion.py     Document processing pipeline
    vector_store.py  Qdrant operations
    graph_store.py   Neo4j operations
    ranking.py       Client scoring + data richness
    openapi_it.py    OpenAPI IT Company Advanced client
    vendor_discovery_agent.py   Client discovery LangGraph agent
    web_search.py               DuckDuckGo prospect search
    web_search_chat_service.py  Streaming client discovery service
    chat_service.py             Company chat service
    general_chat_agent.py       Cross-company chat agent
    enrichment/
      agent.py       Main enrichment pipeline (8 async steps)
      shared/
        duckduckgo.py      DuckDuckGo scraper (retry, rate limiting)
        http_client.py     Async HTTP client
        normalize.py       Company name normalization, PEC parsing
        vies.py            EU VIES VAT validation
        disambiguator.py   Website candidate scoring engine
      skills/
        search_website.py       Multi-query website search
        verify_website.py       P.IVA verification on web pages
        scrape_contacts.py      Email, phone, social extraction
        search_socials.py       Social profile search (fallback)
        search_news.py          Google News RSS
        search_trademarks.py    TMview trademark search
        search_sites_by_vat.py  Fallback website search
```

---

## MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `users` | Auth (email, password_hash, display_name) |
| `companies` | Company profiles with registry + enrichment data |
| `documents` | Uploaded document metadata |
| `document_chunks` | Chunked text for RAG |
| `chat_sessions` | Company-scoped + web search + general chat sessions |
| `chat_messages` | All chat messages |
| `contract_analyses` | Extracted contract data |
| `company_lookup_cache` | OpenAPI IT cache (user_id + vat_number, unique) |
| `token_usage` | LLM token tracking |
| `user_settings` | User preferences |
| `onboarding_profiles` | Onboarding state |
| `web_search_results` | Client discovery history |

---

## Setup

```bash
git clone <repo-url> && cd be
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Fill in credentials
uvicorn app.main:app --reload
```

Verify: `curl http://localhost:8000/api/v1/health`

Requirements: Python 3.12+, ffmpeg (for audio/video).

---

RUN SYNC -> uvicorn src.main:app --host 0.0.0.0 --port 8000
RUN ASYNC -> nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 &  
STOP -> kill $(pgrep -f uvicorn)

source /opt/lumio/be/.venv/bin/activate && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
