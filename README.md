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
- [x] **Step 2 — Ingest & chunk** — classify by type → chunk → per-type folders (`data/chunks/<type>/`)
      + manifest; preview + persona-filtered **lexical** prompt check in the UI
  - [ ] Step 2b — attachment/PDF extraction (research papers, PDDs); refine custom Jira issue types
- [ ] Step 3 — Embed & index (single persistent index)
- [ ] Step 4 — Retrieve & answer (semantic, personas, RBAC)

Personas: see `personas.py`. Verification prompts: see `PROMPTS.md`.
All Atlassian access is **read-only**; chunks/manifest are written locally under `data/` (gitignored).
