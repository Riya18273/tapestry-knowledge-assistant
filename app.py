# -*- coding: utf-8 -*-
"""Tapestry Knowledge Assistant — Streamlit UI (built step by step).

Step 1: Connect & Explore — verify connectivity, preview sources.
Step 2: Ingest & Chunk   — fetch -> classify -> chunk (per-type folders), preview,
                           and check by prompt (lexical, persona-filtered).
Read-only against Atlassian; chunks are written locally under data/.
"""
import os
import streamlit as st

import config
import confluence
import jira
import ingest
import personas

st.set_page_config(page_title="Tapestry KB", layout="wide")

try:
    s = config.settings_safe()
except SystemExit as e:
    st.error(str(e))
    st.stop()


# ---- cached fetchers -------------------------------------------------------
@st.cache_data(show_spinner=False)
def conf_overview(space):
    return confluence.space_overview(space)


@st.cache_data(show_spinner=False)
def jira_overview():
    return jira.overview()


@st.cache_data(show_spinner=False)
def load_chunks(_mtime):
    return ingest.load_chunks()


def chunks_now():
    m = os.path.join(config.settings()["data_dir"], "manifest.jsonl")
    return load_chunks(os.path.getmtime(m) if os.path.exists(m) else 0)


# ---- sidebar ---------------------------------------------------------------
st.sidebar.title("Tapestry KB")
step = st.sidebar.radio("Step", ["1 · Connect & Explore", "2 · Ingest & Chunk"])
st.sidebar.divider()
st.sidebar.caption("Connection")
st.sidebar.write(s["conf_base"])
st.sidebar.write("Spaces: " + ", ".join(s["spaces"]))
st.sidebar.write(s["jira_base"] + "  ·  " + s["jira_project"])
st.sidebar.write(s["email"])
st.sidebar.write("Token: " + ("✅ configured" if s["token_set"] else "❌ missing"))


# ========================= STEP 1 ==========================================
if step.startswith("1"):
    st.title("Step 1 — Connect & Explore")
    st.caption("Verify connectivity and preview the data before ingesting. Read-only.")
    t_conf, t_jira = st.tabs(["📘 Confluence", "🧩 Jira"])

    with t_conf:
        if st.button("Fetch Confluence overview"):
            for space in s["spaces"]:
                try:
                    ov = conf_overview(space)
                except Exception as ex:
                    st.error(f"{space}: {ex}")
                    continue
                st.markdown(f"### {space} — {ov['name']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Pages", ov["pages"])
                c2.metric("Attachments" + (" (est.)" if ov["attachments_estimated"] else ""),
                          ov["attachments"])
                c3.metric("Attachment size", f"{ov['attachment_mb']:.1f} MB")
                if ov["by_ext"]:
                    st.caption("Attachment types: "
                               + "  ".join(f"`.{k}`×{v}" for k, v in ov["by_ext"].items()))
                if ov["sample"]:
                    st.dataframe(ov["sample"], use_container_width=True, hide_index=True)
                st.divider()

    with t_jira:
        if st.button("Fetch Jira overview"):
            try:
                o = jira_overview()
            except Exception as ex:
                st.error(str(ex))
                st.stop()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Issues (all)", o["total"])
            c2.metric("Updated < 365d", o["last_year"])
            c3.metric("Fix versions", o["versions"])
            c4.metric("Sprints", o["sprints"])
            if o["by_type"]:
                st.caption("By type: " + "  ".join(f"**{k}** {v}" for k, v in o["by_type"].items()))
            st.markdown("**Sample issues** (normalised, with relationships)")
            st.dataframe(o["sample_issues"], use_container_width=True, hide_index=True)
            cA, cB = st.columns(2)
            cA.markdown("**Release scope** (fix versions)")
            cA.dataframe(o["versions_list"], use_container_width=True, hide_index=True)
            cB.markdown("**Sprint reports** (sample)")
            cB.dataframe(o["sprints_sample"], use_container_width=True, hide_index=True)


# ========================= STEP 2 ==========================================
else:
    st.title("Step 2 — Ingest & Chunk")
    st.caption("Fetch → classify by type → chunk. Chunks are written to per-type folders "
               "under `data/chunks/`. Preview them and check by prompt below. "
               "(PDF/attachment extraction is Step 2b.)")

    with st.form("ingest_form"):
        c = st.columns([1, 1, 2])
        do_conf = c[0].checkbox("Confluence (TPE/TPS)", value=True)
        do_jira = c[1].checkbox("Jira (MFS5T)", value=True)
        jira_limit = c[2].number_input("Jira sample limit (0 = all 8,735 — slower)",
                                       min_value=0, value=300, step=100)
        run = st.form_submit_button("▶ Run ingest")

    if run:
        srcs = [x for x, f in (("confluence", do_conf), ("jira", do_jira)) if f]
        if not srcs:
            st.warning("Pick at least one source.")
        else:
            with st.spinner("Ingesting… (first full Jira run can take a few minutes)"):
                counts = ingest.ingest(sources=srcs, jira_limit=(int(jira_limit) or None))
            st.success("Ingest complete: "
                       + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))

    stt = ingest.stats()
    if not stt["docs"]:
        st.info("No chunks yet — run an ingest above.")
        st.stop()

    st.subheader("Chunks by type")
    rows = [{"type": t, "documents": stt["by_type"].get(t, 0),
             "chunks": stt["chunks_by_type"].get(t, 0)}
            for t in sorted(stt["chunks_by_type"])]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(f"{stt['docs']} documents · {stt['total_chunks']} chunks")

    all_chunks = chunks_now()
    types = sorted(stt["chunks_by_type"])

    with st.expander("🔎 Browse chunks by type"):
        ty = st.selectbox("Type", types)
        shown = [c for c in all_chunks if c["type"] == ty][:15]
        for cch in shown:
            st.markdown(f"**{cch['title']}**  ·  `{cch['type']}`  ·  {cch['id']}")
            st.text((cch["text"] or "")[:800])
            st.divider()

    st.subheader("✅ Check by prompt (lexical preview)")
    st.caption("Keyword match over ingested chunks — semantic answering comes in Step 4. "
               "The persona limits which content types are visible.")
    pc, qc = st.columns([1, 3])
    plabels = personas.labels()
    persona = pc.selectbox("Persona", list(plabels), format_func=lambda k: plabels[k])
    query = qc.text_input("Prompt", placeholder="e.g. what is the release scope for 1.0?")
    if query:
        allowed = personas.allowed_types(persona)
        st.caption(f"Persona **{plabels[persona]}** sees types: {', '.join(sorted(allowed))}")
        hits = ingest.search(all_chunks, query, allowed=allowed, k=10)
        if not hits:
            st.info("No lexical matches in this persona's visible content types.")
        for h in hits:
            link = f"  ·  [open]({h['url']})" if h.get("url") else ""
            st.markdown(f"**{h['title']}**  ·  `{h['type']}`  ·  score {h['score']}  ·  {h['id']}{link}")
            st.text((h["text"] or "")[:500])
            st.divider()
