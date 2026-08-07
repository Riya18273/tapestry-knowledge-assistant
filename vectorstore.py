# -*- coding: utf-8 -*-
"""Persistent vector index on ChromaDB, embedded with local Ollama.
Native cosine + metadata filtering (used for per-persona `type` scoping)."""
import os
import json

import config
import embed
import ingest

_COLL = "tapestry"


def _client():
    import chromadb
    from chromadb.config import Settings
    path = os.path.join(config.settings()["data_dir"], "index", "chroma")
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))


def _meta(c):
    return {"type": c.get("type") or "", "title": c.get("title") or "",
            "url": c.get("url") or "", "doc_id": c.get("id") or ""}


def _precomputed(chunks):
    """Reuse embeddings from a prior numpy build if aligned to the same chunks."""
    idir = os.path.join(config.settings()["data_dir"], "index")
    vp, mp = os.path.join(idir, "vectors.npy"), os.path.join(idir, "meta.jsonl")
    if not (os.path.exists(vp) and os.path.exists(mp)):
        return None
    try:
        import numpy as np
        meta = [json.loads(l) for l in open(mp, encoding="utf-8")]
        if [m.get("chunk_id") for m in meta] == [c["chunk_id"] for c in chunks]:
            return np.load(vp)
    except Exception:
        pass
    return None


def build(progress=None, batch=64):
    """(Re)build the Chroma collection. Reuses precomputed vectors when available."""
    chunks = ingest.load_chunks()
    pre = _precomputed(chunks)
    client = _client()
    try:
        client.delete_collection(_COLL)
    except Exception:
        pass
    coll = client.get_or_create_collection(_COLL, metadata={"hnsw:space": "cosine"})
    n = len(chunks)
    for i in range(0, n, batch):
        part = chunks[i:i + batch]
        embs = pre[i:i + batch].tolist() if pre is not None \
            else embed.embed_texts([c["text"] for c in part])
        coll.add(ids=[c["chunk_id"] for c in part], embeddings=embs,
                 documents=[c["text"] for c in part],
                 metadatas=[_meta(c) for c in part])
        if progress:
            progress(min(i + batch, n), n)
    return coll.count()


def stats():
    try:
        return {"vectors": _client().get_collection(_COLL).count()}
    except Exception:
        return {"vectors": 0}


def search(query, allowed=None, k=6):
    """Semantic top-k (cosine), filtered to a persona's allowed types."""
    try:
        coll = _client().get_collection(_COLL)
    except Exception:
        return []
    where = {"type": {"$in": sorted(allowed)}} if allowed else None
    res = coll.query(query_embeddings=[embed.embed_one(query)], n_results=k,
                     where=where, include=["documents", "metadatas", "distances"])
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out = []
    for doc, m, dist in zip(docs, metas, dists):
        out.append({"score": round(1.0 - float(dist), 3), "text": doc,
                    "type": m.get("type"), "title": m.get("title"),
                    "url": m.get("url"), "id": m.get("doc_id")})
    return out
