# -*- coding: utf-8 -*-
"""Tapestry Knowledge Assistant — Streamlit UI (built step by step).

Step 1: Connect & Explore — verify connectivity, preview sources.
Step 2: Ingest & Chunk   — bring in Confluence + Jira, sort by type, and check
                           what was captured by asking a question (keyword preview).
The clean, plain-language ANSWER experience for CXO / Sales / Customers is Step 4.
Read-only against Atlassian; content is stored locally under data/.
"""
import os
import streamlit as st

import config
import confluence
import jira
import ingest
import personas
import vectorstore
import answer

st.set_page_config(page_title="Tapestry Knowledge Assistant", layout="wide")

# Friendly, non-technical names for the internal content types.
TYPE_LABELS = {
    "prd": "Product requirement", "pdd": "Product design", "release-note": "Release note",
    "release-scope": "Release scope", "architecture": "Architecture", "research": "Research",
    "marketing": "Marketing", "technical": "Technical doc", "qa-report": "QA report",
    "epic": "Epic", "story": "Story", "bug": "Bug", "task": "Task",
    "sprint-report": "Sprint report", "issue": "Jira item",
    "meeting-notes": "Meeting notes (internal)",
}


def type_label(t):
    return TYPE_LABELS.get(t, (t or "").replace("-", " ").title())


try:
    s = config.settings_safe()
except SystemExit as e:
    st.error(str(e))
    st.stop()


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
step = st.sidebar.radio("Step", ["1 · Connect & Explore", "2 · Ingest & Ask",
                                 "3 · Embed & Search", "4 · Ask (answer)"])
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
            st.markdown("**Sample issues**")
            st.dataframe(o["sample_issues"], use_container_width=True, hide_index=True)
            cA, cB = st.columns(2)
            cA.markdown("**Release scope** (fix versions)")
            cA.dataframe(o["versions_list"], use_container_width=True, hide_index=True)
            cB.markdown("**Sprint reports** (sample)")
            cB.dataframe(o["sprints_sample"], use_container_width=True, hide_index=True)


# ========================= STEP 2 ==========================================
elif step.startswith("2"):
    st.title("Step 2 — Ingest & Ask")
    st.info("This page is an internal **content check** — it confirms we captured the right "
            "material and that each persona only sees what they should. The polished, "
            "plain-language answer for CXO / Sales / Customers (one concise reply with sources) "
            "arrives in **Step 4**.", icon="ℹ️")

    with st.form("ingest_form"):
        c = st.columns([1, 1, 2])
        do_conf = c[0].checkbox("Confluence (TPE/TPS)", value=True)
        do_jira = c[1].checkbox("Jira (MFS5T)", value=False)
        jira_limit = c[2].number_input("Jira sample limit (0 = all)", min_value=0, value=0, step=100)
        run = st.form_submit_button("▶ Run / refresh ingest")
    st.caption("Focusing on **Confluence** first — we'll add Jira once Confluence is classified "
               "and chunked correctly. Re-running one source refreshes only that source.")

    if run:
        srcs = [x for x, f in (("confluence", do_conf), ("jira", do_jira)) if f]
        if not srcs:
            st.warning("Pick at least one source.")
        else:
            with st.spinner("Bringing in content… full Jira can take a few minutes."):
                counts = ingest.ingest(sources=srcs, jira_limit=(int(jira_limit) or None))
            st.success(f"Done — refreshed {sum(counts.values()):,} documents.")

    stt = ingest.stats()
    if not stt["docs"]:
        st.info("No content yet — run an ingest above.")
        st.stop()
    st.caption(f"Knowledge base: **{stt['docs']:,} documents** · {stt['total_chunks']:,} passages "
               f"across {len(stt['chunks_by_type'])} content types.")

    st.subheader("Ask a question")
    pc, qc = st.columns([1, 3])
    plabels = personas.labels()
    persona = pc.selectbox("Who's asking?", list(plabels), format_func=lambda k: plabels[k])
    query = qc.text_input("Question", placeholder="e.g. What is planned for release 1.0?")

    if query:
        allowed = personas.allowed_types(persona)
        hits = ingest.search(chunks_now(), query, allowed=allowed, k=6)
        if not hits:
            st.info(f"Nothing found in the content **{plabels[persona]}** is allowed to see — "
                    "try another question or persona.")
        else:
            st.write(f"Found in **{len(hits)}** document(s):")
            for h in hits:
                with st.container(border=True):
                    st.markdown(
                        f"**{h['title'] or '(untitled)'}** &nbsp;"
                        f"<span style='background:#e8eefb;color:#1e4fb0;padding:2px 9px;"
                        f"border-radius:10px;font-size:0.78em'>{type_label(h['type'])}</span>",
                        unsafe_allow_html=True)
                    st.write(h["snippet"])
                    if h.get("url"):
                        st.markdown(f"[Open source ↗]({h['url']})")
        st.caption("This is a keyword-match preview for checking coverage. In Step 4 the same "
                   "question returns a single, concise, plain-language answer with citations — "
                   "written for the selected persona.")


# ========================= STEP 3 ==========================================
elif step.startswith("3"):
    st.title("Step 3 — Embed & Search (semantic)")
    st.caption("Now matching by **meaning** using a vector index (ChromaDB + local Ollama "
               "embeddings), not just keywords. This is still retrieval — Step 4 turns the top "
               "results into one written answer.")

    vs = vectorstore.stats()
    cta, ctb = st.columns([1, 2])
    if cta.button("⚙️ Build / rebuild vector index"):
        prog = st.progress(0.0, text="Embedding chunks…")
        def _p(done, total):
            prog.progress(done / max(total, 1), text=f"Embedding {done}/{total} chunks…")
        with st.spinner("Building vector index…"):
            n = vectorstore.build(progress=_p)
        prog.empty()
        st.success(f"Vector index built: {n} vectors.")
        vs = vectorstore.stats()
    ctb.metric("Vectors in index", vs["vectors"])

    if not vs["vectors"]:
        st.info("No vectors yet — click **Build vector index** (uses free local Ollama embeddings).")
        st.stop()

    st.subheader("Ask a question (semantic)")
    pc, qc = st.columns([1, 3])
    plabels = personas.labels()
    persona = pc.selectbox("Who's asking?", list(plabels), format_func=lambda k: plabels[k])
    query = qc.text_input("Question", placeholder="e.g. how do we approve transactions manually?")
    if query:
        allowed = personas.allowed_types(persona)
        hits = vectorstore.search(query, allowed=allowed, k=6)
        if not hits:
            st.info(f"Nothing relevant in the content **{plabels[persona]}** may see.")
        else:
            st.write(f"Top {len(hits)} by meaning:")
            for h in hits:
                snippet = " ".join((h.get("text") or "").split())[:300]
                with st.container(border=True):
                    st.markdown(
                        f"**{h['title'] or '(untitled)'}** &nbsp;"
                        f"<span style='background:#e8eefb;color:#1e4fb0;padding:2px 9px;"
                        f"border-radius:10px;font-size:0.78em'>{type_label(h['type'])}</span>"
                        f" &nbsp;<span style='color:#888;font-size:0.78em'>match {h['score']}</span>",
                        unsafe_allow_html=True)
                    st.write(snippet + ("…" if len(snippet) == 300 else ""))
                    if h.get("url"):
                        st.markdown(f"[Open source ↗]({h['url']})")
        st.caption("Semantic retrieval (meaning-based). Step 4 will compose these into one "
                   "concise, cited answer for the persona.")


# ========================= STEP 4 ==========================================
else:
    st.title("Step 4 — Ask (grounded answer)")
    eng, detail = answer.engine_status()
    if eng == "none":
        st.warning("No answer engine enabled yet. " + detail, icon="⚙️")
    else:
        st.caption(f"One concise, source-grounded answer written for the selected persona. "
                   f"Engine: **{eng}** ({detail}). Embeddings/retrieval are local & free.")

    if not vectorstore.stats()["vectors"]:
        st.info("Build the vector index first (Step 3).")
        st.stop()

    pc, qc = st.columns([1, 3])
    plabels = personas.labels()
    persona = pc.selectbox("Who's asking?", list(plabels), format_func=lambda k: plabels[k])
    query = qc.text_input("Question", placeholder="e.g. What's the business value of the next release?")

    if query:
        if eng == "none":
            st.error("Enable an engine to get a written answer: add `ANTHROPIC_API_KEY` to `.env`, "
                     "or run `ollama pull llama3.2` for a free local model. "
                     "(Meanwhile, Step 3 shows the retrieved sources.)")
            st.stop()
        with st.spinner("Composing a grounded answer…"):
            res = answer.answer(query, persona)
        st.markdown("### Answer")
        # escape $ so Streamlit doesn't treat "$15T … $400B" as LaTeX math
        st.markdown((res["answer"] or "_(no answer)_").replace("$", "\\$"))
        # show any referenced diagrams/images
        import os as _os
        shown = 0
        for sdoc in res.get("sources", []):
            ip = sdoc.get("image_path")
            if ip and _os.path.exists(ip) and shown < 3:
                st.image(ip, caption=sdoc["title"], use_column_width=True)
                shown += 1
        if res.get("sources"):
            st.markdown("**Sources**")
            for sdoc in res["sources"]:
                line = f"- {sdoc['title']}  ·  `{type_label(sdoc['type'])}`"
                if sdoc.get("image_path"):
                    line += "  ·  🖼️ diagram"
                if sdoc.get("url"):
                    line += f"  ·  [open ↗]({sdoc['url']})"
                st.markdown(line)
        st.caption(f"Grounded in retrieved Confluence sources · engine {res.get('provider')} · "
                   "persona-filtered.")
