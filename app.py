# -*- coding: utf-8 -*-
"""Tapestry Knowledge Assistant — Streamlit UI.

Step 1: Connect & Explore. Verify Confluence + Jira connectivity and preview the
data (counts + samples) before we ingest/index anything. Read-only.
"""
import streamlit as st
import config
import confluence
import jira

st.set_page_config(page_title="Tapestry KB — Connect & Explore", layout="wide")


@st.cache_data(show_spinner=False)
def confluence_overview(space):
    return confluence.space_overview(space)


@st.cache_data(show_spinner=False)
def jira_overview():
    return jira.overview()


try:
    s = config.settings_safe()
except SystemExit as e:
    st.error(str(e))
    st.stop()

st.title("Tapestry Knowledge Assistant")
st.caption("Step 1 — Connect & Explore. Verify connectivity and preview the data "
           "before ingesting. Everything here is read-only.")

with st.sidebar:
    st.subheader("Connection")
    st.write(f"**Confluence**\n\n{s['conf_base']}")
    st.write("**Spaces:** " + ", ".join(s["spaces"]))
    st.write(f"**Jira**\n\n{s['jira_base']}")
    st.write(f"**Project:** {s['jira_project']}")
    st.write(f"**User:** {s['email']}")
    st.write(f"**Token:** {s['token_mask']}")
    st.info("Step 1 of 4 · next: Ingest & chunk", icon="🧭")

tab_conf, tab_jira = st.tabs(["📘 Confluence", "🧩 Jira"])

with tab_conf:
    st.subheader("Confluence spaces")
    if st.button("Fetch Confluence overview"):
        for space in s["spaces"]:
            try:
                ov = confluence_overview(space)
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
                st.caption("Sample pages")
                st.dataframe(ov["sample"], use_container_width=True, hide_index=True)
            st.divider()

with tab_jira:
    st.subheader(f"Jira project {s['jira_project']}")
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
        st.markdown("**Sample issues** (normalised records with relationships)")
        st.dataframe(o["sample_issues"], use_container_width=True, hide_index=True)
        colA, colB = st.columns(2)
        with colA:
            st.markdown("**Release scope** (fix versions)")
            st.dataframe(o["versions_list"], use_container_width=True, hide_index=True)
        with colB:
            st.markdown("**Sprint reports** (sample)")
            st.dataframe(o["sprints_sample"], use_container_width=True, hide_index=True)
