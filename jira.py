# -*- coding: utf-8 -*-
"""Jira Cloud connector (read-only) for the Tapestry KB.

Normalises issues / sprints / fix-versions into typed records with relationship
metadata (parent epic, fix version, sprint). Uses the CURRENT Jira Cloud API
(the old /rest/api/3/search was removed):
  POST /rest/api/3/search/jql            issue search (nextPageToken paging)
  POST /rest/api/3/search/approximate-count
  GET  /rest/api/3/field                 locate the Sprint custom field
  GET  /rest/api/3/project/{key}/versions
  GET  /rest/agile/1.0/board?... -> /board/{id}/sprint
"""
import urllib.parse
import atlassian
import config

_FIELDS = ["summary", "description", "issuetype", "status", "priority", "labels",
           "components", "created", "updated", "parent", "fixVersions"]
_TYPE = {"epic": "epic", "story": "story", "bug": "bug",
         "task": "task", "sub-task": "task", "subtask": "task"}


def adf_to_text(node):
    """Flatten Atlassian Document Format (description/comments) to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    out = []
    if isinstance(node, dict):
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        for c in node.get("content", []) or []:
            out.append(adf_to_text(c))
        if node.get("type") in ("paragraph", "heading", "listItem", "blockquote",
                                 "codeBlock", "tableRow", "rule"):
            out.append("\n")
    elif isinstance(node, list):
        for c in node:
            out.append(adf_to_text(c))
    return "".join(out)


def count(jql):
    base = config.settings()["jira_base"]
    d = atlassian.post(f"{base}/rest/api/3/search/approximate-count", {"jql": jql}, soft=True)
    return (d or {}).get("count", 0)


def _sprint_field_id():
    base = config.settings()["jira_base"]
    for f in atlassian.get(f"{base}/rest/api/3/field", soft=True) or []:
        if f.get("name", "").lower() == "sprint":
            return f.get("id")
    return None


def _normalise(iss, sfid):
    f = iss.get("fields", {})
    desc = adf_to_text(f.get("description")).strip()
    parent = f.get("parent") or {}
    fixv = [v.get("name") for v in (f.get("fixVersions") or [])]
    sprint = None
    if sfid and f.get(sfid):
        sp = f.get(sfid)
        if isinstance(sp, list) and sp:
            last = sp[-1]
            sprint = last.get("name") if isinstance(last, dict) else str(last)
    itype = (f.get("issuetype") or {}).get("name", "")
    return {
        "source": "jira", "type": _TYPE.get(itype.lower(), "issue"),
        "id": iss.get("key"), "key": iss.get("key"),
        "title": f.get("summary", ""),
        "text": f"{f.get('summary', '')}\n\n{desc}".strip(),
        "date": f.get("updated") or f.get("created"),
        "status": (f.get("status") or {}).get("name"),
        "issue_type": itype, "labels": f.get("labels") or [],
        "fix_version": ", ".join(fixv), "parent_epic": parent.get("key"),
        "sprint": sprint,
    }


def fetch_issues(updated_since=None, page_size=100, max_issues=None):
    s = config.settings(); base = s["jira_base"]
    jql = f"project = {s['jira_project']}"
    if updated_since:
        jql += f' AND updated >= "{updated_since}"'
    jql += " ORDER BY updated ASC"
    sfid = _sprint_field_id()
    fields = _FIELDS + ([sfid] if sfid else [])
    url = f"{base}/rest/api/3/search/jql"
    token, out = None, []
    while True:
        body = {"jql": jql, "maxResults": page_size, "fields": fields}
        if token:
            body["nextPageToken"] = token
        d = atlassian.post(url, body)
        for iss in d.get("issues", []):
            out.append(_normalise(iss, sfid))
            if max_issues and len(out) >= max_issues:
                return out
        token = d.get("nextPageToken")
        if not token or d.get("isLast"):
            break
    return out


def fetch_versions():
    s = config.settings(); base = s["jira_base"]
    vs = atlassian.get(f"{base}/rest/api/3/project/"
                       f"{urllib.parse.quote(s['jira_project'])}/versions") or []
    return [{"source": "jira", "type": "release-scope", "id": f"version-{v.get('id')}",
             "title": v.get("name"), "released": bool(v.get("released")),
             "release_date": v.get("releaseDate"),
             "text": (f"Release {v.get('name')}: "
                      f"{'released' if v.get('released') else 'unreleased'}. "
                      f"{v.get('description', '')}").strip()}
            for v in vs]


def fetch_sprints(max_per_board=300):
    s = config.settings(); base = s["jira_base"]
    proj = urllib.parse.quote(s["jira_project"])
    out = []
    boards = atlassian.get(f"{base}/rest/agile/1.0/board?projectKeyOrId={proj}"
                           f"&maxResults=50", soft=True) or {}
    for b in boards.get("values", []):
        start = 0
        while start < max_per_board:
            sp = atlassian.get(f"{base}/rest/agile/1.0/board/{b['id']}/sprint"
                               f"?startAt={start}&maxResults=50", soft=True)
            if not sp:
                break
            vals = sp.get("values", [])
            for spr in vals:
                out.append({"source": "jira", "type": "sprint-report",
                            "id": f"sprint-{spr.get('id')}", "title": spr.get("name"),
                            "state": spr.get("state"), "board_id": b["id"],
                            "date": spr.get("endDate") or spr.get("startDate"),
                            "text": (f"Sprint {spr.get('name')} [{spr.get('state')}] "
                                     f"{spr.get('startDate', '')}-{spr.get('endDate', '')}. "
                                     f"Goal: {spr.get('goal') or '-'}")})
            if sp.get("isLast", True) or not vals:
                break
            start += 50
    return out


def overview(sample_issues=12):
    s = config.settings(); p = s["jira_project"]
    by_type = {}
    for t in ("Story", "Bug", "Task", "Epic", "Sub-task"):
        c = count(f'project = {p} AND issuetype = "{t}"')
        if c:
            by_type[t] = c
    versions = fetch_versions()
    sprints = fetch_sprints()
    issues = fetch_issues(max_issues=sample_issues)
    keys = ("key", "type", "title", "status", "parent_epic", "fix_version", "sprint", "date")
    return {
        "total": count(f"project = {p}"),
        "last_year": count(f"project = {p} AND updated >= -365d"),
        "by_type": by_type, "versions": len(versions), "sprints": len(sprints),
        "sample_issues": [{k: i.get(k) for k in keys} for i in issues],
        "versions_list": [{k: v.get(k) for k in ("title", "released", "release_date")} for v in versions],
        "sprints_sample": [{k: sp.get(k) for k in ("title", "state", "date")} for sp in sprints[:15]],
    }
