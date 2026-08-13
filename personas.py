# -*- coding: utf-8 -*-
"""Tapestry personas — which content types each may see, plus a sensitivity gate.

`sensitivity`: 'public' personas will (from Step 3 on) be restricted to public
content; 'internal' personas may see everything. In Step 2 the `allowed_types`
set is used to filter the lexical prompt-check preview.
"""

PERSONAS = {
    "executive": {
        "label": "Executive / CXO", "sensitivity": "public",
        "allowed_types": ["prd", "release-note", "release-scope", "marketing", "research"],
        "style": "Concise, benefit-led, non-technical. Lead with business value.",
    },
    "product_manager": {
        "label": "Product Manager", "sensitivity": "internal",
        "allowed_types": ["prd", "pdd", "release-note", "release-scope", "architecture",
                          "epic", "story", "research", "marketing", "sprint-report",
                          "meeting-notes", "technical", "qa-report"],
        "style": "Product-focused: scope, rationale, status, roadmap.",
    },
    "engineer": {
        "label": "Engineer / Developer", "sensitivity": "internal",
        "allowed_types": ["pdd", "architecture", "technical", "epic", "story", "bug",
                          "task", "release-note", "sprint-report", "meeting-notes"],
        "style": "Technical and precise; include design and implementation detail.",
    },
    "qa": {
        "label": "QA / Test Engineer", "sensitivity": "internal",
        "allowed_types": ["qa-report", "story", "bug", "task", "release-note",
                          "release-scope", "sprint-report", "meeting-notes", "technical"],
        "style": "Test-oriented: acceptance criteria, defects, coverage.",
    },
    "sales_marketing": {
        "label": "Sales / Marketing", "sensitivity": "public",
        "allowed_types": ["release-note", "release-scope", "marketing", "prd"],
        "style": "Customer-facing, benefit-led; no internal names, code, or IDs.",
    },
    "support": {
        "label": "Support", "sensitivity": "internal",
        "allowed_types": ["release-note", "bug", "story", "architecture", "qa-report",
                          "technical", "meeting-notes"],
        "style": "Troubleshooting-focused: known issues, fixes, workarounds.",
    },
    "customer": {
        "label": "Customer (external)", "sensitivity": "public",
        "allowed_types": ["release-note", "marketing"],
        "style": "External-safe: only released, customer-facing information. Plain, "
                "non-technical language — describe what a capability lets the customer DO "
                "or achieve, not its implementation mechanics. Avoid API/engineering terms "
                "(e.g. 'parent/child parameters', 'JSON payload', 'request body', 'hierarchical "
                "data format') — say what it means in practice instead "
                "(e.g. 'connect to other systems without custom coding').",
    },
}


def options():
    return [(k, v["label"]) for k, v in PERSONAS.items()]


def labels():
    return {k: v["label"] for k, v in PERSONAS.items()}


def allowed_types(persona):
    return set(PERSONAS.get(persona, {}).get("allowed_types", []))


def sensitivity(persona):
    return PERSONAS.get(persona, {}).get("sensitivity", "internal")
