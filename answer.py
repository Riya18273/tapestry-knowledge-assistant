# -*- coding: utf-8 -*-
"""Step 4 — compose ONE grounded, persona-tailored answer from retrieved sources.

Engine auto-detect: Anthropic Claude if ANTHROPIC_API_KEY is set (best prose),
otherwise a local Ollama chat model (free). Answers are grounded strictly in the
provided sources and refuse when the content isn't there.
"""
import os
import re
import json
import urllib.request

import config
import personas
import retrieve

_STOP_Q = {"a", "an", "the", "is", "are", "do", "does", "did", "what", "which", "who",
           "how", "why", "when", "where", "of", "in", "on", "for", "to", "and", "or",
           "by", "with", "this", "that", "these", "those", "mean", "meaning", "you",
           "your", "we", "our", "me", "it", "its", "be", "was", "were", "will", "would",
           "can", "could", "should", "about", "tell", "give", "show", "explain", "describe"}


def _sig_terms(text):
    return {w for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 2 and w not in _STOP_Q}


def _sig_bigrams(text):
    """Adjacent word-pairs where BOTH words are significant (not stopwords) — a
    precise signal that the question's actual PHRASE (not just scattered common
    words) is present, e.g. 'payment schedules' or 'financial record'."""
    words = re.findall(r"\w+", (text or "").lower())
    return {f"{a} {b}" for a, b in zip(words, words[1:])
            if a not in _STOP_Q and b not in _STOP_Q and len(a) > 2 and len(b) > 2}


_DEFN_RE = re.compile(
    r"(?:mean(?:s|t)?\s+by|meant\s+by|what\s+(?:do|does|is)\s+.+?\s+mean\b|"
    r"define\b|definition\s+of)\s*(.*)$", re.I)


def _claim_span(question):
    """If the question asks to define/explain a SPECIFIC phrase ('what do you mean
    by X', 'define X', 'what does X mean'), return that phrase — the thing whose
    presence must be verified in the sources before the LLM is allowed to answer.
    Returns None for ordinary questions: most real questions are natural paraphrases
    of the source wording, so requiring a literal phrase match on every question
    would wrongly refuse legitimate, well-grounded answers (the dense-cosine gate
    alone already handles those)."""
    m = _DEFN_RE.search(question or "")
    if not m:
        return None
    claim = m.group(1).strip(" ?.!")
    return claim or question


def _lexical_overlap(claim, hits):
    """Phrase-level grounding check for a SPECIFIC claim: do adjacent significant
    word-pairs from `claim` appear anywhere in the retrieved text — not just its
    individual common words, which show up in unrelated content too. Only invoked
    when `_claim_span` detects a define/explain-this-phrase question; guards
    against high dense-cosine on a topically-similar but factually different chunk
    (which otherwise lets the LLM fabricate an answer to a claim the sources never
    actually make)."""
    qbigrams = _sig_bigrams(claim)
    blob = " ".join((h.get("text") or "") for h in hits).lower()
    if qbigrams:
        return sum(1 for bg in qbigrams if bg in blob) / len(qbigrams)
    qterms = _sig_terms(claim)              # single-significant-word claims: fall back
    return (sum(1 for w in qterms if w in blob) / len(qterms)) if qterms else 1.0

_SYSTEM = (
    "You are the Tapestry Knowledge Assistant. Answer the user's question using ONLY the "
    "SOURCES provided. Hard rules:\n"
    "1) GROUND every statement in the sources. If the answer is not in them, say so plainly — "
    "never invent features, numbers, dates, or names.\n"
    "1b) The user may ask about a SPECIFIC claim, phrase, or term. If the SOURCES do not contain "
    "that specific claim, do NOT substitute a different-but-related feature and present it as if "
    "it explains the claim. Say plainly you don't have that specific detail available, and only "
    "then optionally mention what IS grounded, clearly framed as a separate, related point.\n"
    "2) AUDIENCE: {label}. STYLE: {style}\n"
    "3) {safety}\n"
    "4) STRUCTURE: open with a one-sentence direct answer, then 2-5 short bullets of specifics "
    "(features and their value). For business audiences, lead with the outcome/benefit, not the "
    "mechanism.\n"
    "4b) STAY ON-TOPIC: only include what directly answers the question asked. If a source "
    "chunk also mentions a different, adjacent feature (e.g. it lists several capabilities "
    "together), do NOT include that other feature just because it appeared nearby — only "
    "include it if the user's question actually covers it.\n"
    "5) If the question is about the 'latest'/'next'/'current' release, name the specific version "
    "and its headline items. If multiple versions appear, prefer the newest.\n"
    "6) Keep it tight (under ~140 words). End with a line 'Sources:' listing only the titles you used.\n"
    "7) Tapestry releases are numbered 0.x and 1.x (e.g. 0.3, 1.0, 1.0.1). Version numbers like "
    "5.x belong to a different product and may appear in template pages — do NOT present them as "
    "Tapestry releases; ignore them.\n"
    "8) Write monetary/large numbers in plain text (e.g. 'USD 400B', '15 trillion') — never use "
    "the '$' symbol.\n"
    "9) NEVER state a percentage, dollar figure, or statistic (e.g. 'reduces cost by 50%') "
    "unless that EXACT figure appears in the SOURCES. If you don't have a specific figure for a "
    "benefit, describe it qualitatively instead of inventing one.\n"
    "10) Some sources cite named companies' results achieved with COMPETITOR products (e.g. "
    "Pega, MuleSoft, Fenergo) as market evidence, not as Tapestry customers. NEVER present a "
    "competitor's customer outcome as if Tapestry produced it. If you mention such a company, "
    "you MUST also name the actual vendor from the source — do not imply they use Tapestry."
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
    """(engine, detail) for the answer step, honoring TAPESTRY_LLM_MODE:
      local    -> local Ollama only (ZERO Claude credits) [default]
      claude   -> Claude (uses credits)
      fallback -> local primary; Claude only on low confidence (near-zero)
    Falls back to whatever is actually available."""
    mode = os.getenv("TAPESTRY_LLM_MODE", "local").lower()
    key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("TAPESTRY_LLM_MODEL", "claude-sonnet-4-5")
    if mode == "claude" and key:
        return "anthropic", model
    m = _ollama_chat_model()
    if m:
        return "ollama", m
    if key:                       # local requested but no local model present
        return "anthropic", model
    return "none", ("Enable a local model (`ollama pull llama3.2`) for zero-credit mode, "
                    "or set ANTHROPIC_API_KEY.")


def min_confidence():
    try:
        return float(os.getenv("TAPESTRY_MIN_CONFIDENCE", "0.35"))
    except ValueError:
        return 0.35


_PCT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")

# Named institutions in the MRD's "comparable market evidence" table, and the actual
# (competitor) vendor each result belongs to. The MRD explicitly flags these as
# "competitive-landscape context only" — third-party outcomes, not Tapestry's own.
_COMPETITOR_CASES = {
    "ing": "pega", "wells fargo": "mulesoft", "virgin money": "pega",
    "coast capital": "mulesoft", "first abu dhabi": "fenergo",
}


def _strip_misattributed_case_studies(text):
    """Deterministic safety net for a subtler, more dangerous failure than invented
    numbers: the source MRD has a table of REAL outcomes achieved by named companies
    (ING, Virgin Money, Wells Fargo, Coast Capital, First Abu Dhabi Bank) using
    COMPETITOR products (Pega/MuleSoft/Fenergo) — used only as market-sizing evidence.
    The model can drop the vendor name and present these as if they were Tapestry's own
    results (e.g. 'Adopting Tapestry... Onboarding cut to 15 minutes for Virgin Money'),
    falsely implying a real company is a Tapestry customer. The numbers are real (so the
    percentage-grounding check above doesn't catch it) — this is an ATTRIBUTION error,
    not a fabrication. Strip any line that names one of these institutions without also
    naming the vendor that actually produced the result."""
    lines, dropped = (text or "").split("\n"), False
    kept = []
    for ln in lines:
        lnl = ln.lower()
        # word-boundary match — plain substring would false-positive on e.g. "ing" inside
        # "processing"/"onboarding"/"reducing" (found and fixed during verification)
        company = next((c for c in _COMPETITOR_CASES
                        if re.search(rf"\b{re.escape(c)}\b", lnl)), None)
        if company and not re.search(rf"\b{re.escape(_COMPETITOR_CASES[company])}\b", lnl):
            dropped = True
            continue
        kept.append(ln)
    out = "\n".join(kept).strip()
    if dropped:
        out += ("\n\n_Note: this answer omitted one or more case-study results that were "
                "achieved using a different (competitor) product, not Tapestry._")
    return out, dropped


def _strip_ungrounded_numbers(text, hits):
    """Deterministic post-generation safety net: drop any line/bullet whose percentage
    figure doesn't literally appear in the retrieved sources. Numbers are the most
    decision-critical and most reliably-verifiable class of hallucination — a real
    citation would contain the same digits — and prompting alone isn't reliable enough
    on a local model (observed: llama3.2 invented '50%/75%/30%' ROI stats complete with
    fake '(Source: [n])' tags on an Executive ROI question with no such figures anywhere
    in the KB). Returns (clean_text, whether_anything_was_stripped)."""
    blob = " ".join((h.get("text") or "") for h in hits)
    lines, dropped = (text or "").split("\n"), False
    kept = []
    for ln in lines:
        pcts = _PCT_RE.findall(ln)
        if pcts and not any(p.strip() in blob or p.replace(" ", "") in blob.replace(" ", "")
                            for p in pcts):
            dropped = True
            continue
        kept.append(ln)
    out = "\n".join(kept).strip()
    if dropped:
        out += ("\n\n_Note: this answer omitted one or more specific statistics that "
                "weren't found in the source content._")
    return out, dropped


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
    # confidence gate: best dense cosine among hits. For "what do you mean by X" /
    # "define X" questions specifically, also require X's phrase to actually appear in
    # the sources — damp confidence if not (topic-similar but not on-claim: the exact
    # failure mode that let the LLM fabricate an answer to a phrase the sources never
    # make). Ordinary questions skip this — natural paraphrase shouldn't be penalized.
    confidence = max((h.get("cosine") or 0.0) for h in hits) if hits else 0.0
    claim = _claim_span(question)
    if hits and claim and _lexical_overlap(claim, hits) == 0.0:
        confidence *= 0.5
    if not hits or confidence < min_confidence():
        return {"answer": "I couldn't find sufficient support in the Product KB to answer that "
                          "confidently. Try rephrasing, or narrow it to a specific release/topic.",
                "sources": [], "provider": "refused",
                "confidence": round(confidence, 3), "fallback_used": False}
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
        return {"answer": None, "sources": [], "provider": "none",
                "confidence": round(confidence, 3), "fallback_used": False, "engine_help": detail}

    text, num_stripped = _strip_ungrounded_numbers(text.strip(), hits)
    text, attr_stripped = _strip_misattributed_case_studies(text)
    stripped = num_stripped or attr_stripped
    if not text.strip():          # every line was an ungrounded stat — nothing grounded left
        return {"answer": "I couldn't find sufficient support in the Product KB to answer that "
                          "confidently. Try rephrasing, or narrow it to a specific release/topic.",
                "sources": [], "provider": "refused",
                "confidence": round(confidence, 3), "fallback_used": False}
    return {"answer": text, "provider": f"{eng}:{detail}",
            "confidence": round(confidence, 3), "numbers_stripped": stripped,
            "fallback_used": eng == "anthropic" and os.getenv("TAPESTRY_LLM_MODE", "local") == "fallback",
            "sources": [{"title": h.get("title"), "type": h.get("type"), "url": h.get("url"),
                         "image_path": h.get("image_path") or ""} for h in hits]}
