#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scaffold a NEW Confluence RAG KB from this engine (reusable template).

The engine is product-agnostic — only config + taxonomy differ per product. This copies
the engine + docs into a new folder, writes a ready-to-fill `.env` (local / zero-credit),
and prints the next steps. Runtime data (data/, index, images, .env, .git) is NOT copied.

  python new_kb.py --dest ../acme-kb --name "Acme KB" \
      --conf-base https://acme.atlassian.net/wiki --spaces ACME,DOCS --email you@acme.com \
      [--jira-base https://acme.atlassian.net --jira-project ACME]
"""
import argparse
import os
import shutil
import sys

_IGNORE = shutil.ignore_patterns(
    "data", "reports", "images", "__pycache__", "*.pyc", ".git", ".env",
    "*.exe", ".venv", "venv", "volume_report.json", "*.docx", "*.log")

_ENV = """# {name} — RAG KB config (local, zero-credit by default)
TAPESTRY_CONFLUENCE_BASE_URL={conf_base}
TAPESTRY_CONFLUENCE_SPACES={spaces}
TAPESTRY_JIRA_BASE_URL={jira_base}
TAPESTRY_JIRA_PROJECT={jira_project}
TAPESTRY_EMAIL={email}
TAPESTRY_API_TOKEN=

# --- zero Claude credits ---
TAPESTRY_LLM_MODE=local
TAPESTRY_VISION_MODE=off
OPENAI_BASE_URL=http://localhost:11434/v1
TAPESTRY_EMBED_MODEL=nomic-embed-text
TAPESTRY_CHAT_MODEL=llama3.2
TAPESTRY_MIN_CONFIDENCE=0.35
"""


def main():
    ap = argparse.ArgumentParser(description="Scaffold a new Confluence RAG KB.")
    ap.add_argument("--dest", required=True, help="target folder for the new KB")
    ap.add_argument("--name", default=None, help="display name (defaults to folder name)")
    ap.add_argument("--conf-base", default="https://YOURSITE.atlassian.net/wiki")
    ap.add_argument("--spaces", default="SPACE1,SPACE2")
    ap.add_argument("--jira-base", default="")
    ap.add_argument("--jira-project", default="")
    ap.add_argument("--email", default="you@company.com")
    a = ap.parse_args()

    src = os.path.dirname(os.path.abspath(__file__))
    dest = os.path.abspath(a.dest)
    if dest == src:
        sys.exit("--dest must differ from the template directory.")
    name = a.name or os.path.basename(dest.rstrip("/\\")) or "New KB"

    shutil.copytree(src, dest, ignore=_IGNORE, dirs_exist_ok=True)

    env_path = os.path.join(dest, ".env")
    if os.path.exists(env_path):
        print("(.env already exists in dest — left as-is)")
    else:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(_ENV.format(name=name, conf_base=a.conf_base, spaces=a.spaces,
                                jira_base=a.jira_base, jira_project=a.jira_project, email=a.email))

    print(f"\nScaffolded '{name}'  ->  {dest}\n")
    print("Next steps:")
    print(f"  1) cd \"{dest}\"")
    print("  2) edit .env  -> paste TAPESTRY_API_TOKEN (and confirm site/spaces)")
    print("  3) (optional) tune classify.py + personas.py for this product")
    print("  4) pip install -r requirements.txt")
    print("  5) build the KB:  python -m streamlit run app.py   (Step 2 ingest -> Step 3 index)")
    print("                    or headless: python -m uvicorn api:app --port 8000  then POST /api/v1/ingest")
    print("  6) use it:        http://localhost:8000/   (web chat)   -- $0 with local Ollama")
    print("\nTip: run a read-only volume spike first to size the space (see docs/NEW_KB_GUIDE.md).")


if __name__ == "__main__":
    main()
