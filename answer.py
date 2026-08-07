# -*- coding: utf-8 -*-
"""Step 4 — compose ONE grounded, persona-tailored answer from retrieved sources.

Engine auto-detect: Anthropic Claude if ANTHROPIC_API_KEY is set (best prose),
otherwise a local Ollama chat model (free). Answers are grounded strictly in the
provided sources and refuse when the content isn't there.
"""
import os
import json
import urllib.request

import config
import personas
import retrieve

_SYSTEM = (
    "You are the Tapestry Knowledge Assistant. Answer the user's question using ONLY the "
    "SOURCES provided. Hard rules:\n"
    "1) GROUND every statement in the sources. If the answer is not in them, say so plainly — "
    "never invent features, numbers, dates, or names.\n"
    "2) AUDIENCE: {label}. STYLE: {style}\n"
    "3) {safety}\n"
    "4) STRUCTURE: open with a one-sentence direct answer, then 2-5 short bullets of specifics "
    "(features and their value). For business audiences, lead with the outcome/benefit, not the "
    "mechanism.\n"
    "5) If the question is about the 'latest'/'next'/'current' release, name the specific version "
    "and its headline items. If multiple versions appear, prefer the newest.\n"
    "6) Keep it tight (under ~140 words). End with a line 'Sources:' listing only the titles you used.\n"
    "7) Tapestry releases are numbered 0.x and 1.x (e.g. 0.3, 1.0, 1.0.1). Version numbers like "
    "5.x belong to a different product and may appear in template pages — do NOT present them as "
    "Tapestry releases; ignore them.\n"
    "8) Write monetary/large numbers in plain text (e.g. 'USD 400B', '15 trillion') — never use "
    "the '$' symbol."
)
_SAFE_PUBLIC = ("CUSTOMER-SAFE: do not expose internal Jira IDs/keys, code, table/column/method "
                "names, or internal person names; share only released, customer-appropriate information.")
_SAFE_INTERNAL = "Internal audience: technical detail is fine."


def _ollama_chat_model():
    try:
        base = config.settings()["ollama_base"].split("/v1")[0].rstrip("/")
        req = urllib.request.Request(base + "/api/tags")
        with urllib.request.urlopen(req, timeout=15) as r:
            models = [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
        pref = os.getenv("TAPESTRY_CHAT_MODEL")
        if pref:
            return pref
        chat = [m for m in models if "embed" not in m.lower()]
        return chat[0] if chat else None
    except Exception:
        return None


def engine_status():
    """(engine, detail) — what Step 4 will use, or ('none', how-to-enable)."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", os.getenv("TAPESTRY_LLM_MODEL", "claude-sonnet-4-5")
    m = _ollama_chat_model()
    if m:
        return "ollama", m
    return "none", ("Enable an engine: add ANTHROPIC_API_KEY to .env, "
                    "or `ollama pull llama3.2` for a free local model.")


def _prompt(question, hits):
    lines = []
    for i, h in enumerate(hits, 1):
        body = (h.get("text") or "").strip()[:1500]
        lines.append(f"[{i}] ({h.get('type')}) {h.get('title')}\n{body}")
    return f"QUESTION: {question}\n\nSOURCES:\n" + "\n\n".join(lines)


def _call_anthropic(system, user, model):
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=700, system=system,
        messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _call_ollama(system, user, model):
    base = config.settings()["ollama_base"].rstrip("/")
    body = json.dumps({"model": model, "temperature": 0.2, "stream": False,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"]


def answer(question, persona, k=6):
    """Retrieve (persona-filtered) + compose one grounded answer. Returns a dict."""
    allowed = personas.allowed_types(persona)
    hits = retrieve.hybrid(question, allowed=allowed, k=k)
    if not hits:
        return {"answer": "I don't have information on that in the content available to this persona.",
                "sources": [], "provider": "none"}
    p = personas.PERSONAS.get(persona, {})
    safety = _SAFE_PUBLIC if p.get("sensitivity") == "public" else _SAFE_INTERNAL
    system = _SYSTEM.format(label=p.get("label", persona), style=p.get("style", ""), safety=safety)
    user = _prompt(question, hits)

    eng, detail = engine_status()
    if eng == "anthropic":
        text = _call_anthropic(system, user, detail)
    elif eng == "ollama":
        text = _call_ollama(system, user, detail)
    else:
        return {"answer": None, "sources": hits, "provider": "none", "engine_help": detail}
    return {"answer": text.strip(), "provider": f"{eng}:{detail}",
            "sources": [{"title": h.get("title"), "type": h.get("type"), "url": h.get("url")}
                        for h in hits]}
