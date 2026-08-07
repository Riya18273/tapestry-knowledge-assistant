# Tapestry Knowledge Assistant — Design (v0.1, draft)

A RAG knowledge base over the **Tapestry** product's Confluence spaces **and** Jira,
answering grounded, source-cited questions per persona. Adapted from the MobiFin
Release Assistant engine (ingest → chunk → embed → hybrid retrieve → grounded answer,
personas, RBAC, redaction), with a new Jira source and a single persistent index.

## Sources & scope (from the 2026-08-06 read-only volume spike)

| Source | Site `mobifin-tapestry.atlassian.net` | Volume |
|---|---|---|
| Confluence **TPE** — Tapestry Product Engineering (technical, architecture, release notes, sprint notes) | space `TPE` | 58 pages (dense, ~52k chars/pg), 64 attach / 20 MB |
| Confluence **TPS** — Tapestry (**PRD, PDD**, marketing, research, overview) | space `TPS` | 49 pages, 23 attach / 9 MB |
| **Jira** `MFS5T` — issues, sprint reports, release scope | project `MFS5T` | **8,728 issues**, 82 sprints, 7 fix-versions |

**Key finding:** the year of history lives mostly in **Jira (~65% of the KB)**, not
Confluence (~107 pages). Combined ≈ **20k chunks / ~58 MB index / ~10-min one-time backfill** —
modest, so no heavy infra.

## Architecture

- **Chunks organised in a folder per content type** (see taxonomy below) for inspectability
  and selective re-ingest, all feeding **one persistent vector index** (lightweight embedded
  store — LanceDB / Chroma / FAISS-on-disk) where `type` is a metadata **facet**.
  Retrieval searches the single index and filters by `type` when a question is type-specific.
  Metadata per chunk: `source` (confluence/jira), `space/project`, `type`, `version`, `date`, `sensitivity`.
  *(One index, not N per-type indexes — most questions cross types; siloed indexes hurt recall + latency.)*
- **Source of truth = index + a small manifest** (SQLite/JSONL: chunk → source id, type, version, date,
  content-hash, sensitivity). The per-type folders are a **derived, human-inspectable view**, not the
  database — so they can't drift, and the hash drives incremental re-ingest.
- **Relationship metadata (the real win over type-buckets):** capture the graph —
  `parent_epic`, `fix_version`, `sprint`, and `linked_pages` (Jira issue ↔ Confluence page) — so the
  assistant can answer cross-type questions like *"which stories under epic X shipped in release Y,
  and where's its architecture doc?"* in one hop.
- **Embeddings:** local Ollama `nomic-embed-text` (free); lexical BM25 always-on. Hybrid retrieval via RRF.
- **Ingestion:** one-time backfill, then **incrementals** keyed on Confluence page-version and Jira `updated`.
- **Runs on the Windows host** with Ollama (no DB server needed at this scale).

## Content taxonomy & on-disk layout

```
data/
  chunks/
    prd/            pdd/            release-note/ architecture/
    research/       marketing/      technical/    epic/    story/
    bug/            task/           qa-report/    sprint-report/
    release-scope/
  index/            # ONE vector index over ALL chunks (type is a metadata field)
```

How `type` is assigned at ingest:
- **Jira** → from issue type (Epic / Story / Bug / Task / Sub-task); `sprint-report` from the
  sprints API; `release-scope` from fix-versions.
- **Confluence** → by **label** first (most reliable, e.g. a `release-note` / `architecture`
  label), else title/space heuristics. **PRD & PDD live in the TPS space**; TPE holds
  technical / architecture / release-note / sprint content.
- **QA report** → source TBD (Jira test issues? a Confluence `QA` label? Xray/Zephyr?) — see D4.

## Components

| Reuse (from MobiFin engine) | New for Tapestry |
|---|---|
| `core` chunk/embed/retrieve/answer, personas, RBAC, redaction | **`jira.py`** — issues+comments (incremental), sprints → "sprint report", fix-versions → "release scope" |
| `confluence.py` (whole-space ingest) | **Single-index store** + metadata-filtered retrieval |
| `app` / `cli`, tests, CI, requirements split | **Attachment allowlist**: pdf/docx/pptx/txt/md/csv; skip zip/.sh/images |
| | Config for the new site/spaces/project (`.env`) + Tapestry personas |

## Governance
TPE is mostly **internal** (technical/PDD/architecture/sprints). Sensitivity tagging + RBAC/personas
are the primary control — customer-facing personas must be filtered from internal content.

## Build phases — **UI-first: each step is testable in the Streamlit app before moving on**
1. **Connect & Explore** — preview Confluence (TPE/TPS) + Jira (MFS5T) in the UI (connectivity + counts + samples). ← current
2. **Ingest & chunk** — fetch + normalise to typed records, chunk per type; preview chunks-per-type in the UI.
3. **Embed & index** — single persistent index (backfill ~10 min); show index stats in the UI.
4. **Retrieve & answer** — metadata-filtered hybrid retrieval, personas/RBAC; ask questions in the UI.
5. Incrementals, eval + CI, deploy.

## Platform gotchas (found during the spike)
- Jira `/rest/api/3/search` was **removed (HTTP 410)** → use `POST /rest/api/3/search/approximate-count`
  for counts and `/rest/api/3/search/jql` for issues.
- Confluence space-wide `type=attachment` listing **500s** (containerId NPE) → use CQL `content/search`
  or per-page `child/attachment`.

## Open decisions
- **D1** Ingest both TPE + TPS (recommended) or one? — default: both.
- **D2** Jira scope: issues+comments + sprints + fix-versions (recommended). Include epics/requirements? — default: yes to the first three.
- **D3** Index store: LanceDB (recommended — embedded, typed metadata filters) vs Chroma vs FAISS+SQLite.
- **D4** QA-report source: Jira test issues, a Confluence `QA` label, or a test tool (Xray/Zephyr)? — needs confirmation.

_Nothing built yet. This doc is for review before scaffolding the engine._
