# -*- coding: utf-8 -*-
"""Tapestry "Ask MobiFin" RAG service — a thin FastAPI wrapper over the existing
engine. One shared backend for every channel (Product UI panel, Teams bot, web).

Endpoints:
  GET  /api/v1/health     — status, vector count, active answer engine
  POST /api/v1/chat       — grounded answer (persona-scoped, confidence-gated)
  POST /api/v1/ingest     — (re)build the KB from a source, then rebuild the index
  GET  /api/v1/documents   — indexed KB summary (per content type)

Zero-credit by default: TAPESTRY_LLM_MODE=local uses local Ollama; embeddings are
always local; the confidence gate refuses weak matches so no LLM is called at all.
Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""
import threading
from typing import Optional, List
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import answer
import ingest
import vectorstore

app = FastAPI(title="Tapestry Ask MobiFin API", version="1.0")

# ingest runs in the background (heavy); a lock prevents concurrent rebuilds.
_ingest_lock = threading.Lock()
_ingest_state = {"running": False, "last": None}


def _run_ingest(sources, rebuild):
    try:
        counts = ingest.ingest(sources=tuple(sources))
        vectors = vectorstore.build() if rebuild else vectorstore.stats().get("vectors", 0)
        _ingest_state["last"] = {"ingested": counts, "vectors": vectors}
    except Exception as e:  # noqa: BLE001
        _ingest_state["last"] = {"error": str(e)}
    finally:
        _ingest_state["running"] = False
        _ingest_lock.release()


class ChatIn(BaseModel):
    question: str
    persona: str = "engineer"
    product: Optional[str] = None      # reserved (single-product KB today)
    release: Optional[str] = None      # page context (improves relevance)
    issue_id: Optional[str] = None
    page_url: Optional[str] = None


class ChatOut(BaseModel):
    answer: Optional[str]
    sources: List[dict]
    confidence: float
    fallback_used: bool
    provider: str


class IngestIn(BaseModel):
    sources: List[str] = ["confluence"]
    rebuild: bool = True


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/api/v1/health")
def health():
    eng, detail = answer.engine_status()
    return {"status": "ok",
            "vectors": vectorstore.stats().get("vectors", 0),
            "engine": eng, "engine_detail": detail,
            "min_confidence": answer.min_confidence()}


@app.post("/api/v1/chat", response_model=ChatOut)
def chat(inp: ChatIn):
    # weave any page context (release/issue) into the query for better retrieval
    ctx = " ".join(x for x in (inp.release, inp.issue_id) if x)
    q = f"{inp.question} (context: {ctx})" if ctx else inp.question
    r = answer.answer(q, inp.persona)
    return {"answer": r.get("answer"), "sources": r.get("sources", []),
            "confidence": r.get("confidence", 0.0),
            "fallback_used": r.get("fallback_used", False),
            "provider": r.get("provider", "")}


@app.post("/api/v1/ingest")
def ingest_endpoint(inp: IngestIn, background: BackgroundTasks):
    # Runs in the BACKGROUND (a full build is slow); the response returns at once.
    # A lock prevents concurrent rebuilds. Zero-downtime: /chat keeps serving the
    # live index until the new one is built and flipped.
    if not _ingest_lock.acquire(blocking=False):
        return {"status": "already_running", "documents": ingest.stats()}
    _ingest_state["running"] = True
    background.add_task(_run_ingest, inp.sources, inp.rebuild)
    return {"status": "started",
            "note": "runs in background; poll GET /api/v1/ingest/status or /documents"}


@app.get("/api/v1/ingest/status")
def ingest_status():
    return {"running": _ingest_state["running"], "last": _ingest_state["last"],
            "documents": ingest.stats()}


@app.get("/api/v1/documents")
def documents():
    return ingest.stats()
