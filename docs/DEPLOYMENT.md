# Deployment Guide — "Ask MobiFin" RAG Service (FastAPI, zero-credit)

A shared **FastAPI** service (`api.py`) wrapping the existing engine, so every channel
(Product UI panel, Teams bot, web chat) is a thin client of **one backend**. Runs
**local-first** (Ollama embeddings + local answer model) with a **confidence gate**, so
**Anthropic/Claude spend is $0** by default.

```
Channel (Product UI / Teams / Web)
        │  HTTPS
        ▼
FastAPI  /api/v1/chat · /ingest · /health · /documents
        │
        ├─ retrieve (hybrid: Ollama embeddings + keyword, RRF)   ← local, $0
        ├─ confidence gate (refuse weak matches)                 ← no LLM call
        └─ answer: local Ollama (default)  |  Claude (opt-in)
        ▼
Chroma vector KB (local)  +  data/chunks + images
```

---

## 1. Endpoints

| Method | Path | Purpose | Body / Result |
|---|---|---|---|
| GET | `/` | **built-in internal "Ask Tapestry" web chat** (HTML) | — |
| GET | `/api/v1/personas` | persona list for the UI | → `[{id,label}]` |
| GET | `/api/v1/image/{name}` | serve a captioned diagram | → image file |
| GET | `/api/v1/health` | liveness + engine | → `{status, vectors, engine, engine_detail, min_confidence}` |
| POST | `/api/v1/chat` | grounded answer | `{question, persona, release?, issue_id?, page_url?}` → `{answer, sources[], confidence, fallback_used, provider}` |
| POST | `/api/v1/ingest` | (re)build KB + index — **runs in background** | `{sources:["confluence"], rebuild:true}` → `{status:"started"}` |
| GET | `/api/v1/ingest/status` | ingest progress | → `{running, last, documents}` |
| GET | `/api/v1/documents` | KB summary | → per-type doc/chunk counts |

> `/ingest` returns immediately and rebuilds in the background (a full build is slow);
> `/chat` keeps serving the live index until the new one is flipped in. Poll `/ingest/status`.

`persona` is one of `personas.py` (executive, sales_marketing, customer, product_manager,
engineer, qa, support) — it scopes which content the answer may use.

---

## 2. Prerequisites

**Runtime**
- **Python 3.12**
- **Ollama** running locally with the models pulled:
  - `ollama pull nomic-embed-text` (embeddings — required)
  - `ollama pull llama3.2` (local answer model — required for zero-credit answers)
  - *(optional, for local diagram captions)* `ollama pull llama3.2-vision` or `llava`
- Python deps: `pip install -r requirements.txt` (adds `fastapi`, `uvicorn`).

**Data / config**
- A built KB + vector index (`data/` present, `/health` shows `vectors > 0`).
  If empty, run an ingest first (Streamlit Step 2/3, or `POST /api/v1/ingest`).
- `.env` (see below). For read/ingest from Atlassian you still need the Confluence creds;
  for **serving answers** you need only Ollama.

**Network**
- Ollama reachable at `OPENAI_BASE_URL` (default `http://localhost:11434/v1`).
- If a channel must reach the API from outside the host (e.g. Teams cloud), a
  **public HTTPS endpoint** (see §6/§7).

---

## 3. Zero-credit configuration (`.env`)

```ini
# --- answer engine ---
TAPESTRY_LLM_MODE=local          # local = $0 Claude (Ollama only)  [default]
                                 # claude = always Claude   |   fallback = local, Claude only on low confidence
TAPESTRY_CHAT_MODEL=llama3.2     # local model for answers (optional; auto-detected)
TAPESTRY_MIN_CONFIDENCE=0.35     # refuse below this dense-cosine confidence

# --- embeddings (always local) ---
OPENAI_BASE_URL=http://localhost:11434/v1
TAPESTRY_EMBED_MODEL=nomic-embed-text

# --- diagrams (ingest-time only) ---
TAPESTRY_VISION_MODE=off         # off = zero-credit (no captioning). "claude" = caption
                                 # diagrams via Claude vision (small one-time token cost).

# ANTHROPIC_API_KEY=...          # ONLY if TAPESTRY_LLM_MODE=claude|fallback or VISION_MODE=claude

# --- Teams Outgoing Webhook (see §7a) ---
TAPESTRY_TEAMS_SECRET=           # the security token Teams shows when you create the webhook
TAPESTRY_TEAMS_PERSONA=engineer  # default persona for Teams questions
```

**Guarantee $0 Claude:** set `TAPESTRY_LLM_MODE=local` (or simply don't set
`ANTHROPIC_API_KEY`). Then: embeddings = local, answers = local, confidence gate
refuses weak matches (no LLM at all), and nothing calls Anthropic. `/health` will show
`engine: ollama`.

---

## 4. Run it

**Local / dev**
```bash
cd D:\tapestry-knowledge-assistant
pip install -r requirements.txt
python -m uvicorn api:app --host 0.0.0.0 --port 8000
# check:  http://localhost:8000/api/v1/health   and  /docs (Swagger UI)
```

**Smoke test**
```bash
curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" ^
  -d "{\"question\":\"What is new in release 1.0.1?\",\"persona\":\"sales_marketing\"}"
```

### Docker (recommended for IT — one command)
Files in the repo: **`Dockerfile`**, **`docker-compose.yml`**, **`.dockerignore`**. Compose
brings up **Ollama + the API together** in local zero-credit mode.

```bash
cp .env.example .env          # add TAPESTRY_TEAMS_SECRET + Confluence creds (for ingest) as needed
docker compose up -d --build
# one-time: pull the local models into the Ollama volume
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3.2
# build the KB index once (needs Atlassian creds in .env), OR copy a prebuilt ./data
curl -X POST http://localhost:8000/api/v1/ingest -H "Content-Type: application/json" -d "{}"
# watch progress, then verify
curl http://localhost:8000/api/v1/ingest/status
curl http://localhost:8000/api/v1/health        # -> engine: ollama, vectors > 0
```
- `./data` is a bind mount (KB + index persist / can be pre-seeded); Ollama models persist
  in the `ollama_models` volume. GPU is optional (uncomment the `deploy` block).
- Put a **TLS reverse proxy** in front for the public endpoint (see §7a). Zero-credit vars
  (`TAPESTRY_LLM_MODE=local`, `VISION_MODE=off`) are set by compose.

> `POST /api/v1/ingest` runs in the **background** (`/ingest/status` to watch) — it never
> blocks `/chat`, which keeps serving the live index until the rebuild flips.

---

## IT hand-off checklist
- [ ] **Host** the container(s) on an approved VM (existing internal Docker host is fine).
      ~4 vCPU / 8–16 GB RAM / ~10 GB disk. `docker compose up -d --build`.
- [ ] **Pull models** (`nomic-embed-text`, `llama3.2`) into the Ollama volume (one-time).
- [ ] **Seed the KB**: run one `POST /api/v1/ingest` (needs Atlassian creds), or copy a prebuilt `./data`.
- [ ] **Public HTTPS endpoint** for Teams: reverse proxy (TLS via Let's Encrypt) on a stable
      domain, or the corporate API gateway. Only `/api/v1/teams` must be public; `/` can stay internal.
- [ ] **Secrets** in `.env` (not committed): `TAPESTRY_TEAMS_SECRET`, Confluence creds for ingest.
- [ ] **Teams Outgoing Webhook** → Callback URL `https://<host>/api/v1/teams` → paste its token
      into `TAPESTRY_TEAMS_SECRET` → restart the `api` service.
- [ ] **Scheduled refresh**: cron `POST /api/v1/ingest` off-peak.
- [ ] **Monitoring**: log confidence/provider; alert if `/health` is down.
- **Cost:** $0 Claude, $0 bot licensing; only a ~USD 10–15/yr domain if not using the gateway.

---

## 5. Channels (all clients of this one API)

- **Product UI panel** ("Ask MobiFin" button) — deepest integration: the page can pass
  `release`/`issue_id`/`page_url` for context. Needs product-team dev work.
- **Teams bot** — fastest adoption, built-in identity → persona/RBAC. See §6/§7.
- **Web chat** — **built in**: the service serves an "Ask Tapestry" page at `/`
  (persona selector, grounded answers, sources, inline diagrams). No Teams/Azure required,
  $0 — ideal for internal use and stakeholder demos.

---

## 6. Teams — with Azure Bot (recommended path)

- **Azure Bot Service registration is FREE** (F0 tier) for standard channels incl. Teams —
  it is a *registration*, not a paid product. You need an **Azure subscription** + an
  **Azure AD app registration** + a **Teams admin** to publish/sideload the app.
- The bot is a thin adapter: receive the Teams message → call `POST /api/v1/chat` → reply.
- The API must be reachable from the Teams cloud over **public HTTPS**.

**Cost with Azure Bot:** ~**$0 licensing** (F0). Real costs = the compute you already run
+ a public HTTPS endpoint (below).

---

## 7a. Teams quick test — Outgoing Webhook (no Azure, $0)

Endpoint is built in: **`POST /api/v1/teams`** (HMAC-verified; replies with a grounded
answer + sources; `[persona]` prefix supported, e.g. `[sales] what's new in 1.0.1?`).

**Prerequisites:** you own (or can edit) a Team; you can run an outbound **public tunnel**;
the API is running locally.

1. **Expose the API over public HTTPS** (Teams' cloud must reach it). Easiest for testing:
   ```bash
   # option A — cloudflared (no account needed for a temp URL)
   cloudflared tunnel --url http://localhost:8000
   # option B — ngrok
   ngrok http 8000
   ```
   Copy the `https://…` URL it prints.
2. **Create the webhook in Teams:** target Team → **••• → Manage team → Apps →
   "Create an outgoing webhook"** (bottom). Name = `AskTapestry`, **Callback URL** =
   `https://<your-tunnel>/api/v1/teams`, add a description/icon → **Create**. Teams shows a
   **security token** (base64) — copy it.
3. **Wire the secret:** put it in `.env` as `TAPESTRY_TEAMS_SECRET=…`, then **restart** the API.
4. **Ask in the team:** `@AskTapestry what changed in release 1.0.1?`
   (optionally `@AskTapestry [customer] what's new for me?`).

**Limits (Outgoing Webhook):** only in the team it's added to; **@mention required**; no 1:1
DM, no proactive messages, no store publishing. For those, use an Azure Bot (§6).

---

## 7. Teams — **if Azure Bot is NOT available** (and the extra cost)

If you can't register an Azure Bot (no Azure subscription / org policy), you do **not** need
a paid product — two no-Azure options:

| Option | How | Extra licensing cost | Limitations |
|---|---|---|---|
| **A. Teams Outgoing Webhook** | A *team owner* adds an Outgoing Webhook pointing at your HTTPS endpoint (HMAC-verified). Users **@mention** the bot in that team; you reply. | **$0** (no Azure, no license) | Only in teams where it's added; @mention required; **no 1:1 DM, no proactive messages, no store publishing** |
| **B. Standalone Web Chat** | Serve a small chat page from FastAPI (or embed in Product UI). | **$0** | Not inside Teams; users open a URL |
| C. Copilot Studio / Power Virtual Agents | Microsoft low-code bot | **Paid** (message-pack / per-user licensing) | **Avoid for cost** |

**So the only real "additional cost" without Azure Bot is a public HTTPS endpoint** (needed
so the Teams cloud — or external users — can reach the API):

| Item | Typical cost |
|---|---|
| Domain name | ~USD 10–15 / year |
| TLS certificate | **$0** (Let's Encrypt) |
| Reverse proxy (nginx/Caddy) on existing host | **$0** (software) |
| Compute (FastAPI + Ollama) | **$0 extra** if on an existing VM/server; GPU optional for speed |
| Dev-only public tunnel (ngrok / VS Code dev tunnel) | free tier available |

- **Internal-only web chat** needs **no public endpoint** at all → **$0 additional**.
- **Teams (either Azure Bot or Outgoing Webhook)** needs the API reachable from Microsoft's
  cloud → the domain + TLS above (~USD 10–15/yr), nothing more.

**Bottom line:** zero Claude spend, zero bot-licensing spend. The only marginal cost to put
this in Teams is a ~USD 10–15/yr domain (TLS free); a standalone/internal web chat is free.

---

## 8. Cost model summary

| Component | Claude cost? | Notes |
|---|---|---|
| Embeddings + retrieval | **No** | local Ollama |
| Confidence gate | **No** | pure math; refuses weak matches |
| Answers (`TAPESTRY_LLM_MODE=local`) | **No** | local llama3.2 |
| Answers (`claude`/`fallback`) | Yes (token-based) | opt-in; log input/output tokens + reason; cap chunks & output; set monthly budget |
| Diagram captions | Only if Claude vision at ingest | one-time; use local vision or skip for $0 |

---

## 9. Security & ops (MVP)
- **Auth**: put the API behind the enterprise identity/gateway; derive `persona` from the
  authenticated user (don't trust a client-supplied persona in production).
- **Logging**: log question, persona, confidence, provider, and (if Claude) token counts +
  fallback reason — enables a monthly budget + alert.
- **Persistence**: keep `data/` (chunks, images, Chroma index) on durable storage.
- **Rebuilds** are zero-downtime (index builds into an inactive collection, then flips).

---

## 10. Phase plan (from the HLD)
1. **FastAPI RAG service** (this) — `/chat` `/ingest` `/health`, local zero-credit + gate. ✅
2. First channel — **Teams bot** (Azure Bot *or* Outgoing Webhook) or **Product UI panel**.
3. Auth → persona mapping from identity.
4. Optional Claude **fallback** with token logging + monthly budget (near-zero).
5. Second channel reuses the same API.
