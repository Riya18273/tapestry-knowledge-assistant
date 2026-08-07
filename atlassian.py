# -*- coding: utf-8 -*-
"""Minimal read-only Atlassian Cloud HTTP client (Confluence + Jira).
Basic auth from config, retry/backoff, corporate-CA friendly. Stdlib only."""
import json, time, base64, ssl, urllib.request, urllib.error
import config

# Best-effort: trust the system/corporate CA store (e.g. Zscaler).
try:
    import pip_system_certs.wrapt_requests  # noqa: F401
except Exception:
    pass

_CTX = ssl.create_default_context()


def _auth_header():
    s = config.settings()
    tok = base64.b64encode(f"{s['email']}:{s['token']}".encode()).decode()
    return f"Basic {tok}"


def request(method, url, payload=None, soft=False):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": _auth_header(), "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=_CTX, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < 4:
                time.sleep(2 * (attempt + 1)); continue
            if soft:
                return None
            raise RuntimeError(f"HTTP {e.code} {method} {url}: "
                               f"{e.read().decode('utf-8', 'replace')[:300]}")
        except urllib.error.URLError as e:
            if attempt < 4:
                time.sleep(2 * (attempt + 1)); continue
            if soft:
                return None
            raise RuntimeError(f"Network/TLS error {method} {url}: {e}")


def get(url, soft=False):
    return request("GET", url, soft=soft)


def post(url, payload, soft=False):
    return request("POST", url, payload, soft=soft)
