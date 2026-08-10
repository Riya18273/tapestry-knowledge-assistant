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
from typing import Optional, List
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import answer
import ingest
import vectorstore

app = FastAPI(title="Tapestry Ask MobiFin API", version="1.0")


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
def ingest_endpoint(inp: IngestIn):
    # NOTE: synchronous + slow for a full build. For production, run behind a
    # background worker/queue. Kept simple here for the MVP.
    counts = ingest.ingest(sources=tuple(inp.sources))
    vectors = vectorstore.build() if inp.rebuild else vectorstore.stats().get("vectors", 0)
    return {"ingested": counts, "vectors": vectors, "rebuilt": inp.rebuild}


@app.get("/api/v1/documents")
def documents():
    return ingest.stats()
