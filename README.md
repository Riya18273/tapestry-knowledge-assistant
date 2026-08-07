# Tapestry Knowledge Assistant

A RAG knowledge base over the **Tapestry** Confluence spaces (**TPE**, **TPS**) and
**Jira** (`MFS5T`), answering grounded, source-cited questions per persona.
Design: [docs/DESIGN.md](docs/DESIGN.md).

Built **incrementally, testable from a Streamlit UI at each step** (like the Release KB).

## Setup
1. Python 3.12 · `pip install -r requirements.txt`
2. `copy .env.example .env` and fill in the Confluence/Jira URLs, space keys, email and API token.
3. `streamlit run app.py`

## Status
- [x] **Step 1 — Connect & Explore** sources (Confluence + Jira preview)
- [x] **Step 2 — Ingest & chunk (Confluence)** — classify by type (label/title/ancestor) →
      chunk → per-type folders + manifest; **attachment extraction** (PDF/DOCX/PPTX/txt/md/csv,
      clean RAG text) and **child-page type inheritance**; persona-filtered lexical check in the UI.
      Verified 9/10 (product-requirements content lives in Jira, not Confluence).
  - [ ] Jira ingest (issues/epics/stories/sprints/versions) — also maps custom Jira types
- [x] **Step 3 — Embed & index** — ChromaDB vector index, local Ollama (`nomic-embed-text`)
      embeddings; semantic search with per-persona `type` filtering in the UI
- [x] **Step 4 — Retrieve & answer** — **hybrid retrieval** (dense + lexical, RRF) with
      near-duplicate + per-document diversity and **version awareness** (latest/next);
      composes one grounded, cited, persona-tailored answer via Claude (or local Ollama).
      Customer-safe for public personas. Confluence answering validated at release-agent quality.
- [ ] **Jira** — ingest issues/epics/stories/sprints/fix-versions (+ custom type mapping);
      add embedding batching for the ~10k-chunk backfill

Personas: see `personas.py`. Verification prompts: see `PROMPTS.md`.
All Atlassian access is **read-only**; chunks/manifest are written locally under `data/` (gitignored).
