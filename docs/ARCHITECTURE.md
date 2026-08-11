# Tapestry Knowledge Assistant — Architecture & Tools

A self-contained RAG (Retrieval-Augmented Generation) system over the Tapestry
Confluence spaces. **Local-first and zero-cost by default** — embeddings, vector search,
and answer generation all run locally (Ollama + ChromaDB); Anthropic Claude is *optional*.

No proprietary RAG framework (no LangChain / LlamaIndex / Pinecone / OpenAI) — a lean stack
you fully control.

---

## 1. Two flows

### Ingest (build the knowledge base)
```
Confluence (TPE, TPS)
   │  REST (urllib, Basic auth)                      atlassian.py / confluence.py
   ▼
Extract text  ── PDF/DOCX/PPTX/txt/md/csv + storage-HTML   extract.py / html_to_text
   │           (optional: diagram captions via Claude vision — off by default)  vision.py
   ▼
Classify by type  (label → title → ancestor → space)       classify.py
   ▼
Chunk  (paragraph-aware, overlap, title-dedup)             chunking.py
   ▼
Embed  (Ollama nomic-embed-text, 768-dim, LOCAL)           embed.py
   ▼
Index  (ChromaDB, cosine) + per-type chunk store + manifest  vectorstore.py / ingest.py
```
Incremental: only new/changed/deleted pages (by version) are re-embedded (upsert/delete).

### Query (answer a question)
```
Question + persona
   ▼
Hybrid retrieval  = dense (Chroma) + lexical (keyword), fused by RRF     retrieve.py
   │  version-aware · per-document diversity · persona type-filter
   ▼
Confidence gate  (refuse weak matches — no LLM call)                     answer.py
   ▼
Generate answer  (Ollama llama3.2 LOCAL  |  Claude optional)             answer.py
   ▼
Grounded answer + sources + confidence  (+ inline diagram if asked)
```

---

## 2. Tools by stage

| Stage | Tool / library | Local? |
|---|---|---|
| Language | Python 3.12 | — |
| Source connector | Confluence Cloud REST via stdlib `urllib` | ✅ |
| Text extraction | `pdfplumber`, `python-docx`, `python-pptx`, stdlib decode; custom `html_to_text` | ✅ |
| Diagram captioning *(optional, off)* | Anthropic **Claude vision** (`anthropic`) | ✗ (opt-in) |
| Chunking | custom (`chunking.py`) | ✅ |
| Classification | custom rules (`classify.py`) | ✅ |
| **Embeddings** | **Ollama `nomic-embed-text`** (768-dim) via OpenAI-compatible API | ✅ |
| **Vector index** | **ChromaDB** (PersistentClient, cosine) | ✅ |
| Retrieval | Hybrid dense + lexical, **Reciprocal Rank Fusion (RRF)** | ✅ |
| Confidence gate | custom (`answer.py`) | ✅ |
| **Answer LLM** | **Ollama `llama3.2`** (default) · Anthropic **Claude** (opt-in) | ✅ / ✗ |
| Personas / scoping | custom (`personas.py`) | ✅ |
| API service | **FastAPI + Uvicorn** | ✅ |
| Admin/test UI | **Streamlit** + built-in vanilla-JS web chat | ✅ |
| Deployment | **Docker + docker-compose** (API + Ollama) | ✅ |
| Config / secrets | `.env` (custom loader) | ✅ |

**Zero-credit posture:** embeddings + index + retrieval + default generation are 100% local
→ **$0**. Claude is used only if `TAPESTRY_LLM_MODE=fallback|claude` or `TAPESTRY_VISION_MODE=claude`.

---

## 3. Module map

| File | Responsibility |
|---|---|
| `config.py` | `.env` loader + settings; `require_atlassian()` gates ingest |
| `atlassian.py` | read-only Cloud HTTP client (auth, retry, binary fetch) |
| `confluence.py` | pages + attachments → records; `page_index`/`fetch_page` (incremental) |
| `extract.py` | attachment text extraction (PDF/DOCX/PPTX/…), cleanup |
| `vision.py` | optional Claude-vision diagram captions |
| `classify.py` | assign content `type` (release-note, prd, architecture, meeting-notes, …) |
| `chunking.py` | paragraph-aware chunking with overlap |
| `embed.py` | Ollama embeddings (batched) |
| `vectorstore.py` | ChromaDB build / upsert / delete / search; zero-downtime rebuild |
| `retrieve.py` | hybrid retrieval (RRF) + version boost + diversity |
| `answer.py` | engine selection, confidence gate, grounded generation |
| `personas.py` | persona → allowed content types + tone |
| `ingest.py` | orchestration: full + **incremental** ingest, chunk store, manifest, lexical search |
| `api.py` | FastAPI service (`/chat`, `/ingest`, `/health`, `/documents`, `/teams`) + web chat |
| `app.py` | Streamlit admin/testing UI |

---

## 4. Storage layout (`data/`, git-ignored)
```
data/
  chunks/<type>/<doc>.json    # per-type chunk store (human-inspectable)
  manifest.jsonl              # source of truth: id, type, version, parent, hash, n_chunks
  index/chroma/               # ChromaDB persistent index
  index/active.txt            # which collection is live (a/b swap)
  images/                     # captioned diagram images
```

## 5. Configuration (key env)
| Var | Default | Effect |
|---|---|---|
| `TAPESTRY_LLM_MODE` | `local` | `local` = $0 (Ollama) · `fallback` · `claude` |
| `TAPESTRY_VISION_MODE` | `off` | `claude` to caption diagrams (uses credits) |
| `TAPESTRY_MIN_CONFIDENCE` | `0.35` | refuse below this retrieval confidence |
| `OPENAI_BASE_URL` | `http://localhost:11434/v1` | Ollama endpoint |
| `TAPESTRY_EMBED_MODEL` / `TAPESTRY_CHAT_MODEL` | `nomic-embed-text` / `llama3.2` | local models |

## 6. Deployment & channels
- **Docker Compose** brings up API + Ollama in one command (see `docs/DEPLOYMENT.md`).
- Channels are thin clients of the same API: built-in **web chat** (`/`), **Teams Outgoing
  Webhook** (`/api/v1/teams`), or a Product-UI panel.
- Refresh: schedule `POST /api/v1/ingest` (incremental) — new Confluence docs flow in at $0.

## 7. Design choices
- **Local-first** to keep cost at $0 and data on-prem.
- **Hybrid retrieval + confidence gate** for grounded, on-topic answers (refuses when unsure).
- **Per-persona type scoping** so customer-facing users never see internal content.
- **Zero-downtime rebuilds** and **incremental ingest** for a living KB.
- **Lean, framework-free** stack — easy to audit, extend, and self-host.
