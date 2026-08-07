# -*- coding: utf-8 -*-
"""Chunk a record's text into overlapping, paragraph-aware pieces.
Long Confluence pages (some ~52k chars) split into many; short Jira issues stay whole."""
import re

TARGET = 3000     # ~800 tokens
OVERLAP = 300


def _split(text, target=TARGET, overlap=OVERLAP):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= target:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            if len(p) > target:                       # hard-split an over-long paragraph
                for i in range(0, len(p), target - overlap):
                    chunks.append(p[i:i + target])
                cur = ""
            else:
                cur = p
    if cur:
        chunks.append(cur)
    if overlap and len(chunks) > 1:                   # stitch a little context across boundaries
        out = [chunks[0]]
        for i in range(1, len(chunks)):
            out.append((chunks[i - 1][-overlap:] + "\n" + chunks[i]).strip())
        return out
    return chunks


def chunk_record(rec):
    """Return a list of chunk texts, each prefixed with the title for standalone context."""
    title = (rec.get("title") or "").strip()
    parts = _split(rec.get("text", ""))
    if not parts:
        return [title] if title else []
    return [(f"{title}\n\n{p}" if title and title not in p[:len(title) + 5] else p) for p in parts]
