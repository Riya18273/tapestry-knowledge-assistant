# -*- coding: utf-8 -*-
"""Assign a content `type` to each record — drives the per-type folders and the
retrieval `type` facet. Confluence: label-first, then title, then space default."""

_CONF_LABELS = {
    "release-note": "release-note", "releasenote": "release-note", "release-notes": "release-note",
    "architecture": "architecture", "network-architecture": "architecture",
    "functional-architecture": "architecture", "system-architecture": "architecture",
    "pdd": "pdd", "product-design": "pdd", "product-design-document": "pdd",
    "prd": "prd", "product-requirement": "prd", "product-requirements": "prd",
    "research": "research", "research-paper": "research", "whitepaper": "research",
    "marketing": "marketing", "technical": "technical",
    "qa": "qa-report", "qa-report": "qa-report", "test-report": "qa-report", "test": "qa-report",
}


def classify_confluence(title, labels, space):
    for l in labels or []:
        key = l.strip().lower().replace(" ", "-")
        if key in _CONF_LABELS:
            return _CONF_LABELS[key]
    t = (title or "").lower()
    if "prd" in t or "product requirement" in t:
        return "prd"
    if "pdd" in t or "product design" in t:
        return "pdd"
    if "architecture" in t:
        return "architecture"
    if "release note" in t or "release-note" in t:
        return "release-note"
    if "research" in t or "whitepaper" in t:
        return "research"
    if "qa" in t or "test report" in t:
        return "qa-report"
    return "marketing" if str(space).upper() == "TPS" else "technical"
