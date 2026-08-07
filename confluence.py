# -*- coding: utf-8 -*-
"""Confluence Cloud connector (read-only). Space overview + samples for the UI."""
import html as _html
import re
import urllib.parse
from collections import Counter
import atlassian
import config
import classify


_MACRO = re.compile(r"</?(ac|ri):[^>]*>", re.I)          # Confluence storage macros


def _cell_text(cell_html):
    t = re.sub(r"<[^>]+>", " ", cell_html)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _table_to_lines(m):
    """A <table> -> one line per row: 'cellA | cellB | cellC' (empty cells dropped)."""
    rows = []
    for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", m.group(0)):
        cells = [_cell_text(c) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", row)]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows) + "\n"


def html_to_text(h):
    """Confluence storage-format HTML -> readable plain text (tables kept row-wise,
    macros dropped, noise lines removed)."""
    if not h:
        return ""
    h = re.sub(r"(?is)<!\[CDATA\[.*?\]\]>", " ", h)
    h = _MACRO.sub(" ", h)                                # drop macro tags, keep inner text
    h = re.sub(r"(?is)<table[^>]*>.*?</table>", _table_to_lines, h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</p>|</h[1-6]>|</div>", "\n", h)
    h = re.sub(r"(?i)<li[^>]*>", "\n- ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = _html.unescape(h)
    out = []
    for ln in h.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        if not ln:
            out.append("")
            continue
        if re.fullmatch(r"[|\-–—\s]*", ln):    # lone pipes / dashes
            continue
        if re.fullmatch(r"\d{1,6}", ln):                 # stray table numbers/ids
            continue
        out.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text.strip()


def iter_pages(space, progress=None):
    """Yield normalised page records (text + labels + classified type) for a space."""
    base = config.settings()["conf_base"]
    q = urllib.parse.quote(space)
    start, seen = 0, 0
    while True:
        d = atlassian.get(f"{base}/rest/api/content?spaceKey={q}&type=page&status=current"
                          f"&limit=50&start={start}"
                          f"&expand=body.storage,metadata.labels,version")
        for p in d.get("results", []):
            body = (p.get("body", {}).get("storage", {}) or {}).get("value", "")
            text = html_to_text(body)
            labels = [l.get("name", "") for l in
                      ((p.get("metadata", {}).get("labels", {}) or {}).get("results", []) or [])]
            webui = (p.get("_links", {}) or {}).get("webui", "")
            yield {
                "source": "confluence",
                "type": classify.classify_confluence(p.get("title", ""), labels, space),
                "id": f"{space}-{p['id']}", "title": p.get("title", ""), "text": text,
                "space": space, "labels": labels,
                "url": (base + webui) if webui else "",
                "date": (p.get("version", {}) or {}).get("when"),
            }
            seen += 1
            if progress:
                progress(seen)
        if d.get("_links", {}).get("next"):
            start += 50
        else:
            break


def list_spaces():
    base = config.settings()["conf_base"]
    out, start = [], 0
    while True:
        d = atlassian.get(f"{base}/rest/api/space?limit=100&start={start}&type=global")
        for s in d.get("results", []):
            out.append((s.get("key"), s.get("name")))
        if d.get("_links", {}).get("next"):
            start += 100
        else:
            break
    return out


def space_name(space):
    base = config.settings()["conf_base"]
    d = atlassian.get(f"{base}/rest/api/space/{urllib.parse.quote(space)}", soft=True)
    return (d or {}).get("name", space)


def _cql(base, cql, expand=""):
    """Page a CQL content search; None if the endpoint errors (some reject it)."""
    exp = f"&expand={expand}" if expand else ""
    url = f"{base}/rest/api/content/search?cql={urllib.parse.quote(cql)}&limit=100{exp}"
    out = []
    while url:
        d = atlassian.get(url, soft=True)
        if d is None:
            return None
        out.extend(d.get("results", []))
        nxt = d.get("_links", {}).get("next")
        b = d.get("_links", {}).get("base") or base
        url = (b + nxt) if nxt else None
    return out


def space_overview(space, sample_n=10):
    """Counts + a few sample page links for one space (read-only)."""
    base = config.settings()["conf_base"]
    q = urllib.parse.quote(space)

    ids, sample, start = [], [], 0
    while True:
        d = atlassian.get(f"{base}/rest/api/content?spaceKey={q}&type=page"
                          f"&status=current&limit=100&start={start}")
        for p in d.get("results", []):
            ids.append(p["id"])
            if len(sample) < sample_n:
                webui = (p.get("_links", {}) or {}).get("webui", "")
                sample.append({"title": p.get("title", ""),
                               "url": (base + webui) if webui else ""})
        if d.get("_links", {}).get("next"):
            start += 100
        else:
            break

    by_ext = Counter()
    total_bytes = [0]
    att = 0
    estimated = False

    def tally(a):
        size = (a.get("extensions", {}) or {}).get("fileSize", 0) or 0
        total_bytes[0] += size
        title = a.get("title", "")
        ext = title.rsplit(".", 1)[-1].lower() if "." in title else "?"
        by_ext[ext] += 1

    res = _cql(base, f'space="{space}" and type=attachment', "extensions")
    if res is not None:
        for a in res:
            att += 1; tally(a)
    else:
        estimated = True
        probe = ids[:60]; s_att = 0
        for pid in probe:
            d = atlassian.get(f"{base}/rest/api/content/{pid}/child/attachment"
                              f"?limit=100&expand=extensions", soft=True)
            for a in (d or {}).get("results", []):
                s_att += 1; tally(a)
        if probe:
            att = int(s_att * len(ids) / len(probe))

    return {"space": space, "name": space_name(space), "pages": len(ids),
            "attachments": att, "attachments_estimated": estimated,
            "attachment_mb": total_bytes[0] / 1_048_576,
            "by_ext": dict(by_ext.most_common(8)), "sample": sample}
