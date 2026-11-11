"""Streamlit entry point. Run with: python -m streamlit run app.py."""
from pathlib import Path
import os
import sqlite3

import pandas as pd
import streamlit as st

from core.database import Database
from core.demo import load_demo
from core.evidence import evidence_path, save_evidence
from core.models import CATEGORIES, Intake, PRELIMINARY_NOTICE, PRIORITIES, SOURCES, STATUSES, VERDICTS
from core.reporting import export_csv, export_excel
from core.risk_rules import Assessment, assess

BASE = Path(__file__).resolve().parent
# Optional local directory override keeps smoke-test data separate from real cases.
DATA = Path(os.environ.get("DRT_DATA_DIR", str(BASE / "data"))).resolve()
EVIDENCE = DATA / "evidence"
SECTIONS = ("New Investigation", "Case Queue", "Case Review & Evidence", "Dashboard & Reports")
PRIORITY_SYMBOL = {"Low": "🟢", "Medium": "🟠", "High": "🔴"}

st.set_page_config(page_title="Digital Risk | Investigation Desk", page_icon="🔎", layout="wide")


def flash(message: str):
    st.session_state["flash"] = message


def open_case():
    """Run as a button callback, before the next sidebar widget is rendered."""
    st.session_state["case_to_open"] = st.session_state["queue_case"]
    st.session_state["workspace"] = "Case Review & Evidence"


def back_to_queue():
    st.session_state["workspace"] = "Case Queue"


def assessment_view(result: Assessment):
    st.subheader("Preliminary assessment")
    left, right = st.columns([3, 1])
    left.write(f"**{result.category}**")
    right.write(f"{PRIORITY_SYMBOL[result.priority]} **{result.priority} priority**")
    st.info(result.explanation)
    if result.indicators:
        for indicator in result.indicators:
            st.write("• " + indicator)
    else:
        st.write("No configured indicators triggered.")
    with st.expander("Passive URL analysis", expanded=True):
        st.text(f"Normalized URL: {result.url_analysis.normalized_url or 'Not supplied'}")
        st.text(f"Hostname: {result.url_analysis.hostname or 'Not supplied'}")
        st.text(f"Registered domain: {result.url_analysis.registered_domain or 'Not supplied'}")
        st.write(result.url_analysis.comparison)


def case_table(cases: list[dict]):
    if not cases:
        st.info("No cases match these filters.")
        return
    rows = [{"Case ID": c["case_id"], "Data": "SIMULATED" if c["is_demo"] else "Intake",
             "Brand": c["brand"] or "Not supplied", "Title": c["title"], "Category": c["category"],
             "Priority": f"{PRIORITY_SYMBOL[c['priority']]} {c['priority']}",
             "Status": c["status"], "Observed (UTC)": c["observed_at"]} for c in cases]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def filtered_cases(db: Database, key: str) -> list[dict]:
    columns = st.columns(4)
    saved = st.session_state.setdefault("saved_filters", {})
    filters = {}
    for column, (field, label, choices) in zip(columns, (
        ("status", "Status filter", STATUSES), ("priority", "Priority filter", PRIORITIES),
        ("category", "Category filter", CATEGORIES), ("source_type", "Source filter", SOURCES),
    )):
        widget_key = f"{key}_{field}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = saved.get(widget_key, "All")
        value = column.selectbox(label, ("All",) + choices, key=widget_key)
        # Widget state is removed by Streamlit while another section is open.
        saved[widget_key] = value
        filters[field] = None if value == "All" else value
    return db.list_cases(**filters)


def case_queue(db: Database):
    st.header("Case Queue")
    st.caption("Filter the queue, choose a case, and open it directly for review.")
    cases = filtered_cases(db, "queue")
    st.write(f"{len(cases)} case(s)")
    case_table(cases)
    if cases:
        lookup = {case["case_id"]: case for case in cases}
        st.selectbox(
            "Case to review", list(lookup), key="queue_case",
            format_func=lambda cid: f"{cid} · {lookup[cid]['title'][:80] or 'Untitled observation'} · {lookup[cid]['status']}",
        )
        st.button("Open selected case", type="primary", on_click=open_case)


def new_investigation(db: Database):
    st.header("New Investigation")
    st.caption("Record an observation and triage it using transparent rules. Submitted URLs are never fetched.")
    with st.form("intake"):
        left, right = st.columns(2)
        source = left.selectbox("Source type", SOURCES)
        brand = right.text_input("Protected brand name (optional)", max_chars=200)
        url = st.text_input("Suspicious URL", placeholder="https://suspicious.example/page", max_chars=4096)
        official = st.text_input("Official brand domain (optional)", placeholder="brand.example", max_chars=253)
        st.caption("Leave brand fields blank for general phishing or online abuse. Domain comparison needs both a brand name and official domain; other brand checks need the named brand in the page content.")
        title = st.text_input("Listing/page title", max_chars=500)
        description = st.text_area("Description or suspicious content", max_chars=20000)
        notes = st.text_area("Initial investigator notes (optional)", max_chars=20000)
        st.caption("Provide a URL or meaningful title/description. Observation time is recorded in UTC when the case is saved.")
        submitted = st.form_submit_button("Analyze observation", type="primary")
    if submitted:
        # Remove a stale assessment even when the new submission is invalid.
        st.session_state.pop("pending_assessment", None)
        st.session_state.pop("pending_intake", None)
        try:
            intake = Intake(source, url, brand, official, title, description, notes).validated()
            st.session_state["pending_assessment"] = assess(intake)
            st.session_state["pending_intake"] = intake
        except ValueError as exc:
            st.error(str(exc))
    if "pending_assessment" in st.session_state:
        st.caption("Preview of the last analyzed submission. After editing the form, analyze again before saving.")
        with st.expander("Observation being saved"):
            st.json(vars(st.session_state["pending_intake"]))
        assessment_view(st.session_state["pending_assessment"])
        if st.button("Save as new case", type="primary"):
            case_id = db.create_case(st.session_state["pending_intake"])
            st.session_state["last_case_id"] = case_id
            st.session_state.pop("pending_assessment", None)
            st.session_state.pop("pending_intake", None)
            flash(f"Saved {case_id}. Open Case Review & Evidence to investigate.")
            st.rerun()


def case_review(db: Database):
    st.header("Case Review & Evidence")
    cases = db.list_cases()
    if not cases:
        st.info("Create an investigation or load simulated demo cases to begin review.")
        return
    lookup = {case["case_id"]: case for case in cases}
    ids = list(lookup)
    requested = st.session_state.pop("case_to_open", None)
    if requested in ids:
        st.session_state["review_case"] = requested
    elif st.session_state.get("review_case") not in ids:
        preferred = st.session_state.get("last_case_id", ids[0])
        st.session_state["review_case"] = preferred if preferred in ids else ids[0]
    st.button("Back to Case Queue", on_click=back_to_queue)
    selected = st.selectbox("Select case", ids, key="review_case",
                            format_func=lambda cid: f"{'[SIMULATED] ' if lookup[cid]['is_demo'] else ''}{cid} · {lookup[cid]['status']}")
    case = lookup[selected]
    if case["is_demo"]:
        st.warning("SIMULATED DEMO: fictional brand and scenario. No real allegation or automatically collected evidence.")
    left, middle, right = st.columns(3)
    left.metric("Review status", case["status"])
    middle.metric("Preliminary priority", f"{PRIORITY_SYMBOL[case['priority']]} {case['priority']}")
    right.metric("Manual verdict", case["verdict"])
    st.subheader("Observation")
    st.text(case["title"] or "Untitled observation")
    st.text(f"Source: {case['source_type']} | Brand: {case['brand'] or 'Not supplied (general investigation)'}")
    st.text(f"Source URL: {case['source_url'] or 'Not supplied'}")
    st.text(f"Official domain: {case['official_domain'] or 'Not configured'}")
    st.text(f"Observed: {case['observed_at']} | Created: {case['created_at']} | Updated: {case['updated_at']}")
    st.text(case["description"] or "No description supplied.")
    with st.expander("Stored preliminary assessment"):
        st.write(case["category"])
        st.info(case["explanation"])
        for indicator in case["indicators"]:
            st.write("• " + indicator)
        st.write(case["url_analysis"]["comparison"])
        st.json(case["url_analysis"])

    st.subheader("Investigator review")
    st.caption("Validation requires a human Confirmed violation verdict and supporting notes. Save Validated first, then save Escalated. False Positive requires No violation found and notes.")
    with st.form("review_" + selected):
        notes = st.text_area("Investigator notes", value=case["notes"], max_chars=20000, key="notes_" + selected)
        left, right = st.columns(2)
        status = left.selectbox("Review status", STATUSES, index=STATUSES.index(case["status"]), key="status_" + selected)
        verdict = right.selectbox("Manual verdict", VERDICTS, index=VERDICTS.index(case["verdict"]), key="verdict_" + selected)
        if st.form_submit_button("Save review", type="primary"):
            try:
                db.update_review(selected, notes=notes, status=status, verdict=verdict)
                flash("Review saved.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    st.subheader("Evidence")
    st.caption("Upload screenshots you collected manually. PNG/JPG only, up to 5 MiB and 20 megapixels. Files retain their original bytes and a SHA-256 hash. Observation time defaults to the case observation; adjust it to the screenshot's actual observation time.")
    version_key = "evidence_version_" + selected
    version = st.session_state.get(version_key, 0)
    form_suffix = f"{selected}_{version}"
    # Retain user input after validation errors; reset only on a successful upload.
    with st.form("evidence_" + form_suffix):
        upload = st.file_uploader("Screenshot", type=["png", "jpg", "jpeg"], key="upload_" + form_suffix)
        evidence_source = st.text_input("Evidence source URL", value=case["source_url"], max_chars=4096)
        observed = st.text_input("Evidence observation timestamp (UTC ISO 8601)", value=case["observed_at"],
                                 key="evidence_observed_" + form_suffix)
        caption = st.text_input("Evidence description", max_chars=2000)
        if st.form_submit_button("Attach screenshot"):
            try:
                if upload is None:
                    raise ValueError("Choose a screenshot to upload.")
                save_evidence(db, EVIDENCE, selected, original_name=upload.name, content=upload.getvalue(),
                              source_url=evidence_source, observed_at=observed, description=caption)
                st.session_state[version_key] = version + 1
                flash("Manual screenshot attached.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    items = db.list_evidence(selected)
    if not items:
        st.info("No screenshots attached. The application never captures screenshots automatically.")
    for number, item in enumerate(items, 1):
        with st.expander(f"Screenshot {number} · observed {item['observed_at']}", expanded=True):
            st.text(item["original_name"])
            st.text(item["description"] or "No description supplied.")
            try:
                path = evidence_path(EVIDENCE, item["filename"])
                if path.is_file():
                    # Render only locally stored bytes, never the source URL.
                    st.image(path.read_bytes(), caption="Manually uploaded evidence", width=600)
                else:
                    st.warning("Evidence file is missing. Metadata is retained; restore it from a local backup.")
            except ValueError as exc:
                st.error(str(exc))
            st.text(f"Source: {item['source_url'] or 'Not supplied'}")
            st.text(f"Evidence ID: {item['evidence_id']} | Size: {item['size_bytes']:,} bytes | Uploaded: {item['uploaded_at']}")
            st.text(f"SHA-256: {item['sha256']}")


def dashboard(db: Database):
    st.header("Dashboard & Reports")
    cases = db.list_cases()
    metrics = st.columns(4)
    metrics[0].metric("Total cases", len(cases))
    metrics[1].metric("Awaiting review", sum(c["status"] in ("New", "Reviewing") for c in cases))
    metrics[2].metric("Validated cases", sum(c["status"] in ("Validated", "Escalated") for c in cases))
    metrics[3].metric("False positives", sum(c["status"] == "False Positive" for c in cases))
    st.caption("Validated count includes escalated cases. Totals include simulated demos, which are labeled in reports.")
    if cases:
        st.subheader("Cases by preliminary threat category")
        counts = pd.Series([c["category"] for c in cases]).value_counts().rename("Cases")
        st.dataframe(counts.rename_axis("Threat category").reset_index(), hide_index=True, width="stretch")
    st.subheader("Export cases")
    st.caption("Exports use the filters below and include analyst notes, verdicts, UTC timestamps and evidence references. Excel also includes an Evidence sheet. Image files remain in the local evidence directory.")
    filtered = filtered_cases(db, "reports")
    st.write(f"{len(filtered)} case(s) selected for export.")
    left, right = st.columns(2)
    left.download_button("Download CSV", export_csv(db, filtered), file_name="digital-risk-cases.csv", mime="text/csv")
    try:
        right.download_button("Download Excel", export_excel(db, filtered), file_name="digital-risk-cases.xlsx",
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except ValueError as exc:
        right.warning(str(exc))
    st.caption("Potential spreadsheet formulas are prefixed with an apostrophe. Keep reports and evidence private; they may contain investigator-supplied sensitive information.")
    case_table(filtered)


def main():
    st.title("Digital Risk Investigation")
    st.caption("INVESTIGATION DESK · Local case triage · Human judgment at every decision")
    st.sidebar.title("Investigation desk")
    section = st.sidebar.radio("Workspace", SECTIONS, key="workspace")
    st.sidebar.info("Passive analysis only. No URL visits, scraping, live lookups, or automated violation verdicts.")
    st.sidebar.caption("Demo data is fictional and uses reserved .example domains.")
    try:
        db = Database(DATA / "cases.sqlite3")
        if st.sidebar.button("Load 12 simulated demo cases"):
            inserted = load_demo(db)
            flash(f"Loaded {inserted} simulated demo case(s). Existing cases and edits were preserved.")
            st.rerun()
        if message := st.session_state.pop("flash", None):
            st.success(message)
        if section == "New Investigation":
            new_investigation(db)
        elif section == "Case Queue":
            case_queue(db)
        elif section == "Case Review & Evidence":
            case_review(db)
        else:
            dashboard(db)
    except (sqlite3.Error, OSError):
        st.error("Local storage is unavailable. Check that the data directory is writable and has free space, then retry. Your existing records have not been removed.")
    st.divider()
    st.caption(PRELIMINARY_NOTICE)


if __name__ == "__main__":
    main()
