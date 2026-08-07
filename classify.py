# -*- coding: utf-8 -*-
"""Assign a content `type` to each Confluence page — drives per-type folders, the
retrieval facet, and (critically) persona visibility. Label-first, then ordered
title rules, then a space default. Internal working docs (retrospectives, show-and-
tells, standups) get `meeting-notes` so they never leak into external personas.
"""

# Confluence labels -> type (labels are the most reliable signal).
_LABELS = {
    "release-note": "release-note", "releasenote": "release-note", "release-notes": "release-note",
    "prd": "prd", "product-requirement": "prd", "product-requirements": "prd", "brd": "prd",
    "pdd": "pdd", "product-design": "pdd", "product-description": "pdd", "solution-design": "pdd",
    "architecture": "architecture", "hld": "architecture", "lld": "architecture",
    "high-level-design": "architecture", "system-design": "architecture",
    "research": "research", "whitepaper": "research", "spike": "research", "poc": "research",
    "qa": "qa-report", "qa-report": "qa-report", "test-report": "qa-report",
    "test-plan": "qa-report", "test-cases": "qa-report",
    "meeting-notes": "meeting-notes", "retrospective": "meeting-notes",
    "show-and-tell": "meeting-notes", "standup": "meeting-notes", "minutes": "meeting-notes",
    "roadmap": "release-scope", "release-plan": "release-scope",
    "marketing": "marketing", "technical": "technical",
}

# Ordered title rules — FIRST match wins. Meeting notes are checked before
# "release" so "Retrospective … Release Sprint" is internal, not a release note.
_TITLE_RULES = [
    ("meeting-notes", ["show and tell", "show-and-tell", "retrospective", "retro ",
                       "stand up", "standup", "sprint review", "sprint planning",
                       "minutes of meeting", "sync up", "sync-up", "weekly sync",
                       "daily scrum", "grooming", "refinement", "kick off", "kick-off",
                       "kickoff", "catch up", "catch-up", " demo", "walkthrough"]),
    ("release-note", ["release of", "release note", "release notes", "changelog", "what's new"]),
    ("prd", ["product requirement", "prd", "business requirement", "brd"]),
    ("pdd", ["product design", "product description", "pdd", "solution design"]),
    ("architecture", ["architecture", "high level design", "high-level design", "hld",
                      "low level design", "low-level design", "lld", "system design",
                      "network diagram", "deployment diagram", "design document",
                      "technical design"]),
    ("research", ["research", "whitepaper", "white paper", "feasibility",
                  "proof of concept", "poc", "spike"]),
    ("qa-report", ["test plan", "test report", "test case", "test strategy",
                   "qa report", "quality report"]),
    ("release-scope", ["roadmap", "release plan", "release scope"]),
]


def classify_confluence(title, labels, space):
    for l in labels or []:
        key = l.strip().lower().replace(" ", "-")
        if key in _LABELS:
            return _LABELS[key]
    t = f" {(title or '').lower()} "
    for typ, kws in _TITLE_RULES:
        if any(k in t for k in kws):
            return typ
    return "marketing" if str(space).upper() == "TPS" else "technical"
