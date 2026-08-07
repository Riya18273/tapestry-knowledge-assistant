# -*- coding: utf-8 -*-
"""Step 2 — Ingest & chunk.

Fetch Confluence pages + Jira (issues, sprints, fix-versions) -> normalise ->
classify by type -> chunk -> write to per-type folders under data/chunks/<type>/,
plus a manifest.jsonl (source of truth for stats + later incrementals).

Attachment/PDF extraction (research papers etc.) is Step 2b.
"""
import os
import re
import json
import hashlib
from collections import Counter

import config
import confluence
import jira
import chunking


def _hash(s):
    return hashlib.sha1((s or "").encode("utf-8", "ignore")).hexdigest()[:12]


def _safe(x):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(x))[:120]


_META_KEYS = ("source", "type", "id", "title", "date", "url", "space",
              "fix_version", "parent_epic", "sprint", "status", "labels")


def _write_record(data_dir, rec, chunks):
    typ = rec["type"]
    d = os.path.join(data_dir, "chunks", typ)
    os.makedirs(d, exist_ok=True)
    obj = {k: rec.get(k) for k in _META_KEYS}
    obj["n_chunks"] = len(chunks)
    obj["chunks"] = [{"chunk_id": f"{rec['id']}#{i}", "text": c} for i, c in enumerate(chunks)]
    json.dump(obj, open(os.path.join(d, f"{_safe(rec['id'])}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def ingest(sources=("confluence", "jira"), spaces=None, jira_limit=None, progress=None):
    """Rebuild the chunk store. Returns per-type document counts."""
    s = config.settings()
    data_dir = s["data_dir"]
    os.makedirs(data_dir, exist_ok=True)
    manifest = os.path.join(data_dir, "manifest.jsonl")
    mf = open(manifest, "w", encoding="utf-8")           # fresh rebuild (incrementals: Step 3+)
    counts = Counter()

    def emit(rec):
        chunks = chunking.chunk_record(rec)
        if not chunks:
            return
        _write_record(data_dir, rec, chunks)
        mf.write(json.dumps({"id": rec["id"], "source": rec["source"], "type": rec["type"],
                             "title": rec.get("title"), "date": rec.get("date"),
                             "n_chunks": len(chunks), "hash": _hash(rec.get("text", ""))},
                            ensure_ascii=False) + "\n")
        counts[rec["type"]] += 1
        if progress:
            progress(sum(counts.values()), rec["type"])

    try:
        if "confluence" in sources:
            for space in (spaces or s["spaces"]):
                for rec in confluence.iter_pages(space):
                    emit(rec)
        if "jira" in sources:
            for rec in jira.fetch_issues(max_issues=jira_limit):
                emit(rec)
            for rec in jira.fetch_versions():
                emit(rec)
            for rec in jira.fetch_sprints():
                emit(rec)
    finally:
        mf.close()
    return dict(counts)


def stats(data_dir=None):
    data_dir = data_dir or config.settings()["data_dir"]
    mpath = os.path.join(data_dir, "manifest.jsonl")
    by_type, chunks_by_type, docs = Counter(), Counter(), 0
    if os.path.exists(mpath):
        for line in open(mpath, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            docs += 1
            by_type[r["type"]] += 1
            chunks_by_type[r["type"]] += r.get("n_chunks", 0)
    return {"docs": docs, "by_type": dict(by_type), "chunks_by_type": dict(chunks_by_type),
            "total_chunks": sum(chunks_by_type.values())}


def load_chunks(data_dir=None):
    data_dir = data_dir or config.settings()["data_dir"]
    root = os.path.join(data_dir, "chunks")
    out = []
    if not os.path.isdir(root):
        return out
    for typ in os.listdir(root):
        d = os.path.join(root, typ)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            try:
                obj = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            except Exception:
                continue
            for ch in obj.get("chunks", []):
                out.append({"chunk_id": ch["chunk_id"], "text": ch["text"],
                            "type": obj.get("type"), "source": obj.get("source"),
                            "title": obj.get("title"), "url": obj.get("url"), "id": obj.get("id")})
    return out


def search(chunks, query, allowed=None, k=10):
    """Simple lexical (keyword) preview search. Semantic retrieval arrives in Step 4."""
    terms = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) > 2]
    if not terms:
        return []
    scored = []
    for c in chunks:
        if allowed and c["type"] not in allowed:
            continue
        t = c["text"].lower()
        score = sum(t.count(w) for w in terms)
        if score:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"score": s, **c} for s, c in scored[:k]]
