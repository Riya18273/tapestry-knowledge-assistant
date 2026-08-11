# Create a New RAG KB (reuse this engine, $0)

The pipeline is **product-agnostic** — spinning up a KB for another product/space reuses the
whole engine unchanged. Only **config** and (optionally) **taxonomy** differ. Everything stays
**local and $0** (Ollama embeddings + ChromaDB + local `llama3.2`); Claude is optional.

## Fastest: scaffold script
From this template repo:
```bash
python new_kb.py --dest ../acme-kb --name "Acme KB" \
  --conf-base https://acme.atlassian.net/wiki --spaces ACME,DOCS --email you@acme.com
```
This copies the engine + docs into `../acme-kb`, writes a ready `.env` (local zero-credit), and
prints next steps. It does **not** copy runtime data (`data/`, index, images, `.env`, `.git`) — the
new KB gets its own.

Then:
```bash
cd ../acme-kb
# 1) paste your API token into .env  (TAPESTRY_API_TOKEN=...)
# 2) (optional) tune classify.py + personas.py for this product
pip install -r requirements.txt
python -m streamlit run app.py        # Step 2 ingest -> Step 3 build index
# or: docker compose up -d --build    # then POST /api/v1/ingest
```
Use it at `http://localhost:8000/` (web chat) — **$0**.

## Manual alternative (git clone)
```bash
git clone <this-repo> acme-kb && cd acme-kb
cp .env.example .env      # set BASE_URL / SPACES / EMAIL / token; TAPESTRY_LLM_MODE=local
```
…then the same install/ingest/run steps.

## What to change per product

| Reused as-is (generic, local, $0) | Change per product |
|---|---|
| extract · chunk · embed · index · hybrid retrieve · confidence gate · answer · API · web chat · Docker | **`.env`** (site / spaces / creds) · **`classify.py`** (label→type rules) · **`personas.py`** (who sees what) |

Defaults work out of the box; tuning `classify.py`/`personas.py` just improves classification and
persona scoping for the new product's content (exactly what we did for Tapestry).

## Recommended before a big backfill: volume spike
Size the space first (read-only) so you know chunk count / backfill time:
- Count pages, attachments (MB by type), and — if used — Jira issues.
- A spike script pattern lives in the project history; or just run one ingest of a **single space**
  and check `GET /api/v1/documents`.

## Keep KBs isolated
Run **one instance per product** (its own folder/repo → its own `data/` + ChromaDB collection).
On a shared host, give each a distinct `TAPESTRY_DATA_DIR` and port:
```bash
TAPESTRY_DATA_DIR=/srv/acme/data  uvicorn api:app --port 8001
```

## Cost
Identical to Tapestry: embeddings + index + retrieval + generation all local ⇒ **$0**.
Claude is used only if you set `TAPESTRY_LLM_MODE=fallback|claude` or `TAPESTRY_VISION_MODE=claude`.

## Checklist
- [ ] Scaffold (`new_kb.py`) or clone into a new folder
- [ ] `.env`: site URL, space keys, email, **API token**; `TAPESTRY_LLM_MODE=local`
- [ ] (optional) tune `classify.py` + `personas.py`
- [ ] `pip install -r requirements.txt`
- [ ] Ingest → build index (Streamlit or `POST /api/v1/ingest`)
- [ ] Verify `GET /api/v1/health` (engine: ollama, vectors > 0)
- [ ] Deploy (Docker) + schedule incremental `POST /api/v1/ingest`
