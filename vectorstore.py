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


def _active_path():
    return os.path.join(config.settings()["data_dir"], "index", "active.txt")


def _active_name():
    p = _active_path()
    if os.path.exists(p):
        return (open(p, encoding="utf-8").read().strip() or _COLL)
    return _COLL


def _set_active(name):
    p = _active_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(name)


def _meta(c):
    return {"type": c.get("type") or "", "title": c.get("title") or "",
            "url": c.get("url") or "", "doc_id": c.get("id") or "",
            "image_path": c.get("image_path") or ""}


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
    # build into the inactive collection, then flip — readers keep hitting the live
    # one until the new index is fully built (no mid-rebuild "Error finding id").
    current = _active_name()
    target = "tapestry_b" if current == "tapestry_a" else "tapestry_a"
    try:
        client.delete_collection(target)
    except Exception:
        pass
    coll = client.get_or_create_collection(target, metadata={"hnsw:space": "cosine"})
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
    _set_active(target)                                  # flip AFTER fully built
    if current != target:                                # drop the old one
        try:
            client.delete_collection(current)
        except Exception:
            pass
    return coll.count()


def upsert(chunks, batch=64):
    """Add/replace chunks in the live collection (incremental — embeds only these)."""
    chunks = list(chunks or [])
    if not chunks:
        return 0
    coll = _client().get_or_create_collection(_active_name(), metadata={"hnsw:space": "cosine"})
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        coll.upsert(ids=[c["chunk_id"] for c in part],
                    embeddings=embed.embed_texts([c["text"] for c in part]),
                    documents=[c["text"] for c in part],
                    metadatas=[_meta(c) for c in part])
    return len(chunks)


def delete(chunk_ids):
    """Remove chunk ids from the live collection."""
    ids = list(chunk_ids or [])
    if not ids:
        return 0
    try:
        _client().get_collection(_active_name()).delete(ids=ids)
    except Exception:
        return 0
    return len(ids)


def stats():
    try:
        return {"vectors": _client().get_collection(_active_name()).count()}
    except Exception:
        return {"vectors": 0}


def search(query, allowed=None, k=6):
    """Semantic top-k (cosine), filtered to a persona's allowed types.
    Returns [] (never raises) if the index is missing or mid-rebuild."""
    try:
        coll = _client().get_collection(_active_name())
        where = {"type": {"$in": sorted(allowed)}} if allowed else None
        res = coll.query(query_embeddings=[embed.embed_one(query)], n_results=k,
                         where=where, include=["documents", "metadatas", "distances"])
    except Exception:
        return []
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out = []
    for cid, doc, m, dist in zip(ids, docs, metas, dists):
        out.append({"chunk_id": cid, "score": round(1.0 - float(dist), 3), "text": doc,
                    "type": m.get("type"), "title": m.get("title"),
                    "url": m.get("url"), "id": m.get("doc_id"),
                    "image_path": m.get("image_path") or ""})
    return out
