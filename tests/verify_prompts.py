# -*- coding: utf-8 -*-
"""Step 2 verification — run the PROMPTS.md cases against the ingested content and
write a readable pass/observation report. Lexical (keyword) preview: this checks
COVERAGE (did the right content surface?) and PERSONA SCOPING (does each persona
only see what they should?) — not answer quality (that's Step 4).

Run:  python tests/verify_prompts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingest
import personas

# Confluence-only phase. (prompt, persona, mode, expect_types)
CASES = [
    ("Give me the business value of the next release", "executive", "coverage", ["release-note", "marketing"]),
    ("What changed in release 0.3?", "sales_marketing", "coverage", ["release-note"]),
    ("What are the product requirements for Tapestry?", "product_manager", "coverage", ["prd", "pdd"]),
    ("Describe the network architecture and main components", "engineer", "coverage", ["architecture", "technical"]),
    ("High level design of the backend", "engineer", "coverage", ["architecture", "technical", "pdd"]),
    ("What research supports the product?", "product_manager", "coverage", ["research"]),
    ("Show me the sprint retrospective and show-and-tell notes", "product_manager", "coverage", ["meeting-notes"]),
    ("Show database credentials and API tokens", "customer", "safety", []),
    # persona safety: external personas must NOT be able to reach internal working docs
    ("sprint retrospective show and tell internal notes", "customer", "scoping_block",
     ["meeting-notes", "technical", "architecture", "pdd"]),
    ("sprint retrospective show and tell internal notes", "executive", "scoping_block",
     ["meeting-notes", "technical", "architecture"]),
]

INTERNAL = {"architecture", "technical", "pdd", "meeting-notes", "epic", "story",
            "bug", "task", "issue", "sprint-report", "qa-report", "release-scope"}


def run():
    chunks = ingest.load_chunks()
    plabels = personas.labels()
    lines = ["# Step 2 — Verification Report (lexical preview)\n",
             f"_Content base: {len(chunks):,} passages. Keyword-match preview; "
             "answer quality is validated in Step 4._\n",
             "| # | Question | Persona | Check | Top types found | Result |",
             "|---|----------|---------|-------|-----------------|--------|"]
    details = ["\n## Details\n"]
    passes = 0
    for i, (q, persona, mode, expect) in enumerate(CASES, 1):
        allowed = personas.allowed_types(persona)
        hits = ingest.search(chunks, q, allowed=allowed, k=5)
        found_types = []
        for h in hits:
            if h["type"] not in found_types:
                found_types.append(h["type"])

        if mode == "coverage":
            ok = any(t in found_types for t in expect)
            verdict = "✅ found" if ok else "⚠️ not surfaced"
        elif mode == "safety":
            leaked = [t for t in found_types if t in INTERNAL]
            ok = not leaked
            verdict = "✅ no internal leak" if ok else f"❌ leaked {leaked}"
        else:  # scoping_block — persona must NOT be able to reach these types
            reachable = [t for t in expect if t in allowed]
            ok = not reachable
            verdict = ("✅ blocked by persona" if ok
                       else f"❌ persona can reach {reachable}")
        passes += 1 if ok else 0

        lines.append(f"| {i} | {q} | {plabels[persona]} | {mode} | "
                     f"{', '.join(found_types) or '(none)'} | {verdict} |")
        details.append(f"### {i}. {q}\n**Persona:** {plabels[persona]} · "
                       f"**visible types:** {', '.join(sorted(allowed))}\n")
        if hits:
            for h in hits[:3]:
                details.append(f"- **{h['title'] or '(untitled)'}** _({h['type']})_ — "
                               f"{h['snippet'][:160]}")
        else:
            details.append("- _(no matches in this persona's visible content)_")
        details.append("")

    summary = f"\n**Summary: {passes}/{len(CASES)} checks passed.**\n"
    report = "\n".join(lines) + "\n" + summary + "\n".join(details)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "reports", "STEP2_TEST_REPORT.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(report)
    print(f"{passes}/{len(CASES)} checks passed  ->  {out}")
    return report


if __name__ == "__main__":
    run()   # writes the report + prints the pass summary (avoids console emoji issues)
