# -*- coding: utf-8 -*-
"""Embeddings via local Ollama (OpenAI-compatible endpoint). Free, offline."""
import json
import urllib.request
import config


def embed_texts(texts, model=None, timeout=300):
    """Return a list of embedding vectors for `texts` (one request; falls back to
    per-item if the server rejects a batched input)."""
    if not texts:
        return []
    s = config.settings()
    url = s["ollama_base"].rstrip("/") + "/embeddings"
    model = model or s["embed_model"]

    def _post(payload):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        d = _post({"model": model, "input": texts})
        items = sorted(d["data"], key=lambda x: x.get("index", 0))
        if len(items) == len(texts):
            return [it["embedding"] for it in items]
    except Exception:
        pass
    # fallback: one at a time
    out = []
    for t in texts:
        d = _post({"model": model, "input": t})
        out.append(d["data"][0]["embedding"])
    return out


def embed_one(text):
    return embed_texts([text])[0]
