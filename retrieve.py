# -*- coding: utf-8 -*-
"""Hybrid retrieval — fuse dense (Chroma) + lexical (keyword) with Reciprocal Rank
Fusion, de-duplicate near-identical chunks, and boost version-relevant content.
This is what lifts Confluence answers to release-agent quality on version/keyword
queries where dense-only retrieval is weak."""
import re
import hashlib

import ingest
import vectorstore

_VER = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")
_LATEST = ("latest", "newest", "current", "next release", "most recent", "upcoming")


def _key(text):
    return hashlib.md5(re.sub(r"\W+", " ", (text or "").lower()).strip()[:400].encode()).hexdigest()


def _versions(s):
    return set(_VER.findall(s or ""))


def _pv(v):
    return tuple(int(x) for x in v.split("."))


def hybrid(query, allowed=None, k=6, pool=20, rrf=60):
    dense = vectorstore.search(query, allowed=allowed, k=pool)
    lex = ingest.search(ingest.load_chunks(), query, allowed=allowed, k=pool)

    scores, meta = {}, {}
    for rank, h in enumerate(dense):
        cid = h.get("chunk_id") or h.get("id")
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf + rank)
        meta[cid] = h
    for rank, h in enumerate(lex):
        cid = h.get("chunk_id")
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf + rank)
        meta.setdefault(cid, h)

    # version awareness
    q_vers = _versions(query)
    want_latest = any(w in (query or "").lower() for w in _LATEST)
    max_ver = None
    if want_latest:
        allv = [v for cid in scores
                for v in _versions((meta[cid].get("title", "") + " " + (meta[cid].get("text", "") or "")))]
        max_ver = max(allv, key=_pv) if allv else None
    for cid in scores:
        blob = (meta[cid].get("title", "") + " " + (meta[cid].get("text", "") or ""))
        cv = _versions(blob)
        if q_vers and (q_vers & cv):
            scores[cid] *= 1.8
        if max_ver and max_ver in cv:
            scores[cid] *= 1.5

    out, seen, per_doc = [], set(), {}
    for cid in sorted(scores, key=lambda c: -scores[c]):
        h = meta[cid]
        key = _key(h.get("text"))
        if key in seen:                       # drop near-duplicate chunks
            continue
        doc = h.get("id") or ""
        if per_doc.get(doc, 0) >= 2:          # at most 2 chunks per source doc -> diverse sources
            continue
        seen.add(key)
        per_doc[doc] = per_doc.get(doc, 0) + 1
        out.append({**h, "chunk_id": cid, "score": round(scores[cid], 4)})
        if len(out) >= k:
            break
    return out
