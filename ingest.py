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
              "fix_version", "parent_epic", "sprint", "status", "labels", "image_path")


def _write_record(data_dir, rec, chunks):
    typ = rec["type"]
    d = os.path.join(data_dir, "chunks", typ)
    os.makedirs(d, exist_ok=True)
    obj = {k: rec.get(k) for k in _META_KEYS}
    obj["n_chunks"] = len(chunks)
    obj["chunks"] = [{"chunk_id": f"{rec['id']}#{i}", "text": c} for i, c in enumerate(chunks)]
    json.dump(obj, open(os.path.join(d, f"{_safe(rec['id'])}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def _manifest_path(data_dir):
    return os.path.join(data_dir, "manifest.jsonl")


def _load_manifest(data_dir):
    p = _manifest_path(data_dir)
    out = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _clear_sources(data_dir, sources):
    """Remove chunk files + manifest entries for the given sources only, so a
    per-source re-ingest doesn't wipe the other source."""
    keep = []
    for r in _load_manifest(data_dir):
        if r.get("source") in sources:
            f = os.path.join(data_dir, "chunks", r.get("type", ""), f"{_safe(r.get('id'))}.json")
            try:
                os.remove(f)
            except OSError:
                pass
        else:
            keep.append(r)
    with open(_manifest_path(data_dir), "w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _man_line(rec, chunks):
    """Manifest entry — includes version/parent so incremental ingest can diff."""
    return {"id": rec["id"], "source": rec["source"], "type": rec["type"],
            "title": rec.get("title"), "date": rec.get("date"),
            "n_chunks": len(chunks), "hash": _hash(rec.get("text", "")),
            "version": rec.get("version"), "parent": rec.get("parent"),
            "space": rec.get("space")}


def _remove_chunk_file(data_dir, rec):
    f = os.path.join(data_dir, "chunks", rec.get("type", ""), f"{_safe(rec.get('id'))}.json")
    try:
        os.remove(f)
    except OSError:
        pass


def ingest(sources=("confluence", "jira"), spaces=None, jira_limit=None, progress=None):
    """(Re)build the chunk store for the given sources only. Returns per-type counts."""
    config.require_atlassian()                           # fail clearly if creds missing
    s = config.settings()
    data_dir = s["data_dir"]
    os.makedirs(data_dir, exist_ok=True)
    _clear_sources(data_dir, set(sources))               # replace just these sources
    mf = open(_manifest_path(data_dir), "a", encoding="utf-8")
    counts = Counter()

    def emit(rec):
        chunks = chunking.chunk_record(rec)
        if not chunks:
            return
        _write_record(data_dir, rec, chunks)
        mf.write(json.dumps(_man_line(rec, chunks), ensure_ascii=False) + "\n")
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
                            "title": obj.get("title"), "url": obj.get("url"),
                            "id": obj.get("id"), "image_path": obj.get("image_path")})
    return out


_TYPE_HINTS = {
    "prd": ["requirement", "requirements", "prd"],
    "pdd": ["design document", "pdd"],
    "architecture": ["architecture", "network", "component", "diagram", "design"],
    "release-note": ["release note", "changelog", "what changed", "fixed"],
    "release-scope": ["scope", "version", "planned", "roadmap", "fix version"],
    "sprint-report": ["sprint", "velocity", "backlog"],
    "bug": ["bug", "defect", "error"],
    "qa-report": ["qa", "test", "coverage", "acceptance"],
    "research": ["research", "study", "paper", "findings"],
    "story": ["story", "user story", "feature"],
    "epic": ["epic"],
}


def _intent_types(query):
    q = (query or "").lower()
    return {t for t, kws in _TYPE_HINTS.items() if any(k in q for k in kws)}


def _snippet(text, terms, width=260):
    flat = re.sub(r"\s+", " ", text or "").strip()
    low = flat.lower()
    pos = min([low.find(w) for w in terms if low.find(w) != -1] or [0])
    start = max(0, pos - 60)
    seg = flat[start:start + width]
    return ("…" if start > 0 else "") + seg + ("…" if start + width < len(flat) else "")


def search(chunks, query, allowed=None, k=8):
    """Lexical preview: rank by term coverage, damp long chunks, boost intent types.
    (Semantic retrieval arrives in Step 4.) Returns hits with a clean snippet."""
    terms = [w for w in re.findall(r"\w+", (query or "").lower()) if len(w) > 2]
    if not terms:
        return []
    pref = _intent_types(query)
    scored = []
    for c in chunks:
        if allowed and c["type"] not in allowed:
            continue
        t = (c["text"] or "").lower()
        counts = [t.count(w) for w in terms]
        coverage = sum(1 for x in counts if x > 0)
        if not coverage:
            continue
        length_norm = 1.0 / (1.0 + len(t) / 2000.0)      # keep long noisy pages from dominating
        score = (coverage * 100 + sum(counts)) * length_norm
        if c["type"] in pref:
            score *= 2.0                                  # type-intent boost
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(sc, 1), "snippet": _snippet(c["text"], terms), **c}
            for sc, c in scored[:k]]


def ingest_incremental(spaces=None, progress=None):
    """Confluence incremental refresh: detect new/changed/deleted pages by version,
    re-embed ONLY those (upsert), delete removed ones. Falls back to a full build the
    first time (when the manifest has no version tracking or the index is empty)."""
    import vectorstore
    config.require_atlassian()
    s = config.settings()
    data_dir = s["data_dir"]
    os.makedirs(data_dir, exist_ok=True)
    man = _load_manifest(data_dir)
    page_ver = {r["id"]: r.get("version") for r in man
                if r.get("source") == "confluence" and r.get("version") is not None}

    if not page_ver or vectorstore.stats().get("vectors", 0) == 0:
        counts = ingest(sources=("confluence",), spaces=spaces)     # first time -> full
        return {"mode": "full", "ingested": counts, "vectors": vectorstore.build()}

    by_id = {r["id"]: r for r in man}
    children = {}
    for r in man:
        if r.get("parent"):
            children.setdefault(r["parent"], []).append(r["id"])

    to_delete, to_process = set(), []
    for space in (spaces or s["spaces"]):
        cur = confluence.page_index(space)
        for rid, info in cur.items():
            if page_ver.get(rid) != info["version"]:           # new or changed
                to_process.append((space, info["pid"], rid))
        for rid in [x for x in page_ver if x.startswith(space + "-")]:
            if rid not in cur:                                 # page deleted
                to_delete.add(rid)
                to_delete.update(children.get(rid, []))

    # changed/new: drop the page's old records, fetch fresh
    new_recs = []
    for space, pid, rid in to_process:
        if rid in by_id:
            to_delete.add(rid)
            to_delete.update(children.get(rid, []))
        new_recs.extend(confluence.fetch_page(space, pid))

    del_chunks = []
    for rid in to_delete:
        r = by_id.get(rid)
        if r:
            del_chunks += [f"{rid}#{i}" for i in range(r.get("n_chunks", 0))]
            _remove_chunk_file(data_dir, r)

    upserts, new_entries = [], []
    for rec in new_recs:
        chs = chunking.chunk_record(rec)
        if not chs:
            continue
        _write_record(data_dir, rec, chs)
        for i, c in enumerate(chs):
            upserts.append({"chunk_id": f"{rec['id']}#{i}", "text": c, "type": rec["type"],
                            "source": rec["source"], "title": rec.get("title"),
                            "url": rec.get("url"), "id": rec["id"],
                            "image_path": rec.get("image_path")})
        new_entries.append(_man_line(rec, chs))

    vectorstore.delete(del_chunks)
    vectorstore.upsert(upserts)

    new_ids = {rec["id"] for rec in new_recs}
    keep = [r for r in man if r["id"] not in to_delete and r["id"] not in new_ids]
    with open(_manifest_path(data_dir), "w", encoding="utf-8") as f:
        for r in keep + new_entries:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {"mode": "incremental", "changed_or_new_pages": len(to_process),
            "removed_records": len(to_delete), "upserted_chunks": len(upserts),
            "removed_chunks": len(del_chunks), "vectors": vectorstore.stats().get("vectors", 0)}
