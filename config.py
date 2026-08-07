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
    _load_env()
    spaces = os.getenv("TAPESTRY_CONFLUENCE_SPACES") or os.getenv("TAPESTRY_CONFLUENCE_SPACE", "")
    here = os.path.dirname(os.path.abspath(__file__))
    return {
        "conf_base": _req("TAPESTRY_CONFLUENCE_BASE_URL").rstrip("/"),
        "spaces": [s.strip() for s in spaces.split(",") if s.strip()],
        "jira_base": _req("TAPESTRY_JIRA_BASE_URL").rstrip("/"),
        "jira_project": _req("TAPESTRY_JIRA_PROJECT"),
        "email": _req("TAPESTRY_EMAIL"),
        "token": _req("TAPESTRY_API_TOKEN"),
        "data_dir": os.getenv("TAPESTRY_DATA_DIR", os.path.join(here, "data")),
        "ollama_base": os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        "embed_model": os.getenv("TAPESTRY_EMBED_MODEL", "nomic-embed-text"),
    }


def settings_safe():
    """Same as settings() but the token is removed entirely — never rendered.
    Exposes only a presence flag and length (length is not sensitive)."""
    s = settings()
    tok = s.pop("token", "")
    s["token_set"] = bool(tok)
    s["token_len"] = len(tok)
    return s
