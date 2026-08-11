# -*- coding: utf-8 -*-
"""Central config — loads .env once and exposes settings for the connectors/UI."""
import os

_LOADED = False


def _load_env():
    global _LOADED
    if _LOADED:
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    _LOADED = True


def _req(k):
    v = os.getenv(k)
    if not v:
        raise SystemExit(f"Missing {k} — copy .env.example to .env and fill it in.")
    return v


def settings():
    """Config for serving + ingest. Atlassian creds are OPTIONAL (only needed for
    ingest), so a serve-only deployment runs with just Ollama + a prebuilt index."""
    _load_env()
    spaces = os.getenv("TAPESTRY_CONFLUENCE_SPACES") or os.getenv("TAPESTRY_CONFLUENCE_SPACE", "")
    here = os.path.dirname(os.path.abspath(__file__))
    return {
        "conf_base": (os.getenv("TAPESTRY_CONFLUENCE_BASE_URL", "") or "").rstrip("/"),
        "spaces": [s.strip() for s in spaces.split(",") if s.strip()],
        "jira_base": (os.getenv("TAPESTRY_JIRA_BASE_URL", "") or "").rstrip("/"),
        "jira_project": os.getenv("TAPESTRY_JIRA_PROJECT", ""),
        "email": os.getenv("TAPESTRY_EMAIL", ""),
        "token": os.getenv("TAPESTRY_API_TOKEN", ""),
        "data_dir": os.getenv("TAPESTRY_DATA_DIR", os.path.join(here, "data")),
        "ollama_base": os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        "embed_model": os.getenv("TAPESTRY_EMBED_MODEL", "nomic-embed-text"),
    }


def require_atlassian():
    """Call before an ingest — fail clearly if Atlassian creds are missing."""
    s = settings()
    missing = [k for k in ("conf_base", "jira_base", "email", "token") if not s[k]]
    if missing:
        raise SystemExit("Ingest needs Atlassian config: set "
                         "TAPESTRY_CONFLUENCE_BASE_URL / JIRA_BASE_URL / EMAIL / API_TOKEN.")
    return s


def settings_safe():
    """Same as settings() but the token is removed entirely — never rendered.
    Exposes only a presence flag and length (length is not sensitive)."""
    s = settings()
    tok = s.pop("token", "")
    s["token_set"] = bool(tok)
    s["token_len"] = len(tok)
    return s
