"""Streamlit entry point. Run with: python -m streamlit run app.py."""
from pathlib import Path
import hashlib
import os
import sqlite3

import pandas as pd
import streamlit as st

from core.database import Database
from core.dataset_loader import DatasetError, load_sample_dataset
from core.evidence import evidence_path, save_evidence
from core.models import CATEGORIES, Intake, PRELIMINARY_NOTICE, PRIORITIES, SOURCES, STATUSES, VERDICTS, observation_time
from core.presentation import (DATA_SOURCES, SORT_OPTIONS, PRIORITY_SYMBOL, case_option, display_title,
                               filter_data_source, format_timestamp, plain_markdown, queue_view, short_case_id)
from core.reporting import export_csv, export_excel
from core.risk_rules import Assessment, assess

BASE = Path(__file__).resolve().parent
# Optional local directory override keeps smoke-test data separate from real cases.
DATA = Path(os.environ.get("DRT_DATA_DIR", str(BASE / "data"))).resolve()
EVIDENCE = DATA / "evidence"
SECTIONS = ("New Investigation", "Case Queue", "Case Review & Evidence", "Dashboard & Reports")

st.set_page_config(page_title="Digital Risk Triage | Investigation Desk", page_icon="🔎", layout="wide")


def flash(message: str):
    st.session_state["flash"] = message


def open_case():
    """Run as a button callback, before the next sidebar widget is rendered."""
    st.session_state["case_to_open"] = st.session_state["queue_case"]
    st.session_state["workspace"] = "Case Review & Evidence"


def back_to_queue():
    st.session_state["workspace"] = "Case Queue"


def assessment_view(result: Assessment):
    render_assessment(result.category, result.priority, result.indicators,
                      result.explanation, vars(result.url_analysis))


def render_assessment(category: str, priority: str, indicators: list[str], explanation: str, url_analysis: dict):
    st.subheader("Preliminary risk assessment")
    left, right = st.columns([3, 1])
    left.write(f"**{category}**")
    right.write(f"{PRIORITY_SYMBOL[priority]} **{priority} priority**")
    if indicators:
        for indicator in indicators:
            st.write("• " + indicator)
    else:
        st.write("No configured indicators triggered.")
    with st.expander("Assessment reasoning & URL details"):
        st.info(explanation)
        st.write(url_analysis["comparison"])
        st.json(url_analysis)


def case_table(cases: list[dict], *, selection_key: str | None = None, selected_id: str | None = None):
    if not cases:
        st.info("No cases match. Adjust the filters or search to see more investigations.")
        return
    rows = [{"Case ID": short_case_id(c["case_id"]), "Title": display_title(c),
             "Data": "Sample Data" if c["is_demo"] else "Investigator intake",
             "Brand": c["brand"] or "Not supplied", "Source": c["source_type"], "Category": c["category"],
             "Priority": f"{PRIORITY_SYMBOL[c['priority']]} {c['priority']}",
             "Status": c["status"], "Observed (UTC)": format_timestamp(c["observed_at"])} for c in cases]
    options = {}
    if selection_key:
        ids = [case["case_id"] for case in cases]
        default_row = ids.index(selected_id) if selected_id in ids else 0
        options = {"key": selection_key, "on_select": "rerun", "selection_mode": "single-row-required",
                   "selection_default": {"selection": {"rows": [default_row]}}}
    return st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(440, 42 + len(rows) * 38),
                        row_height=38, column_order=("Case ID", "Title", "Priority", "Status", "Category",
                                                     "Brand", "Source", "Data", "Observed (UTC)"),
                        column_config={"Title": st.column_config.TextColumn(width=240),
                                       "Category": st.column_config.TextColumn(width=210),
                                       "Observed (UTC)": st.column_config.TextColumn(width=185)}, **options)


def remembered_selectbox(label: str, choices, key: str, container=st):
    saved = st.session_state.setdefault("saved_filters", {})
    if key not in st.session_state:
        st.session_state[key] = saved.get(key, choices[0])
    value = container.selectbox(label, choices, key=key)
    saved[key] = value
    return value


def filtered_cases(db: Database, key: str, data_source: str) -> list[dict]:
    columns = st.columns(4)
    filters = {}
    for column, (field, label, choices) in zip(columns, (
        ("status", "Status filter", STATUSES), ("priority", "Priority filter", PRIORITIES),
        ("category", "Category filter", CATEGORIES), ("source_type", "Source filter", SOURCES),
    )):
        widget_key = f"{key}_{field}"
        value = remembered_selectbox(label, ("All",) + choices, widget_key, column)
        filters[field] = None if value == "All" else value
    return filter_data_source(db.list_cases(**filters), data_source)


def case_queue(db: Database):
    st.header("Case Queue")
    st.caption("Select a row to open its investigation. Priority ordering places cases awaiting review first within each level.")
    source_column, search_column, sort_column = st.columns([1.1, 2.3, 1.4])
    data_source = remembered_selectbox("Data source", DATA_SOURCES, "queue_data_source", source_column)
    saved = st.session_state.setdefault("saved_filters", {})
    if "queue_search" not in st.session_state:
        st.session_state["queue_search"] = saved.get("queue_search", "")
    query = search_column.text_input("Search cases", key="queue_search", placeholder="Title, Case ID, brand or source URL")
    saved["queue_search"] = query
    sort = remembered_selectbox("Sort cases", SORT_OPTIONS, "queue_sort", sort_column)
    cases = queue_view(filtered_cases(db, "queue", data_source), query, sort)
    st.caption(f"{len(cases):,} cases in view")
    ids = [case["case_id"] for case in cases]
    st.session_state["queue_row_ids"] = ids
    # A new widget identity prevents an old row index mapping to a different case
    # after filtering, sorting or review updates. Selection always resolves to a full ID.
    selection_key = "queue_rows_" + hashlib.sha256("|".join(ids).encode()).hexdigest()[:16]
    event = case_table(cases, selection_key=selection_key, selected_id=st.session_state.get("queue_case"))
    if cases:
        selected_rows = event.selection.rows
        selected_row = selected_rows[0] if selected_rows else None
        selected = cases[selected_row] if selected_row is not None and 0 <= selected_row < len(cases) else None
        if selected:
            st.session_state["queue_case"] = selected["case_id"]
            st.caption("Selected: " + plain_markdown(case_option(selected)))
        st.button("Open selected case", type="primary", on_click=open_case, disabled=selected is None)


def new_investigation(db: Database):
    st.header("New Investigation")
    st.caption("Record an observation, inspect the preliminary assessment, then save the investigation. URLs are never fetched.")
    with st.form("intake", border=False):
        left, right = st.columns(2)
        source = left.selectbox("Source type", SOURCES)
        brand = right.text_input("Protected brand name (optional)", max_chars=200,
                                 help="Leave blank for general phishing or online abuse.")
        url = st.text_input("Suspicious URL", placeholder="https://suspicious.example/page", max_chars=4096)
        official = st.text_input("Official brand domain (optional)", placeholder="brand.example", max_chars=253,
                                 help="Domain comparison needs a brand and official domain. Brand text checks need that brand in the content.")
        left, right = st.columns(2)
        title = left.text_input("Listing/page title", max_chars=500)
        observed_text = right.text_input("Observation time (optional, UTC)", placeholder="2025-01-06T08:00:00Z", max_chars=64,
                                         help="Leave blank to use UTC time when saved. Supply ISO 8601 with Z or an explicit offset; offsets are converted to UTC.")
        description = st.text_area("Description or suspicious content", max_chars=20000, height=120)
        notes = st.text_area("Initial investigator notes (optional)", max_chars=20000, height=90)
        st.caption("Provide a URL or meaningful title/description. After changing any field, analyze again before saving.")
        submitted = st.form_submit_button("Analyze observation", type="primary")
        if submitted:
            clear_pending()
            try:
                intake = Intake(source, url, brand, official, title, description, notes).validated()
                observed = observation_time(observed_text.strip()) if observed_text.strip() else None
                st.session_state["pending_assessment"] = assess(intake)
                st.session_state["pending_intake"] = intake
                st.session_state["pending_observed_at"] = observed
            except ValueError as exc:
                st.error(str(exc))
        if "pending_assessment" in st.session_state:
            st.divider()
            observed = st.session_state["pending_observed_at"]
            st.caption("Preview of the last analyzed observation. Changed fields must be analyzed again.")
            st.caption("Observation time to save: " + (format_timestamp(observed) if observed else "Automatic UTC time when saved"))
            with st.expander("Observation being saved"):
                st.json({**vars(st.session_state["pending_intake"]), "observed_at": observed})
            assessment_view(st.session_state["pending_assessment"])
            # Both actions submit this same form. Saving therefore receives even
            # un-analyzed field edits and cannot silently save a stale preview.
            if st.form_submit_button("Save as new case", type="primary"):
                try:
                    current = Intake(source, url, brand, official, title, description, notes).validated()
                    current_observed = observation_time(observed_text.strip()) if observed_text.strip() else None
                    if current != st.session_state["pending_intake"] or current_observed != observed:
                        st.session_state["intake_feedback"] = ("warning", "Observation changed. Analyze again before saving.")
                    else:
                        case_id = db.create_case(current, observed_at=observed)
                        st.session_state["last_case_id"] = case_id
                        st.session_state["case_to_open"] = case_id
                        flash(f"Saved {short_case_id(case_id)}. Open Case Review & Evidence to investigate.")
                except ValueError as exc:
                    st.session_state["intake_feedback"] = ("error", str(exc))
                clear_pending()
                st.rerun()
    if feedback := st.session_state.pop("intake_feedback", None):
        getattr(st, feedback[0])(feedback[1])


def clear_pending():
    for key in ("pending_intake", "pending_assessment", "pending_observed_at"):
        st.session_state.pop(key, None)


def case_review(db: Database):
    st.header("Case Review & Evidence")
    cases = db.list_cases()
    if not cases:
        st.info("Create an investigation or load the sample dataset to begin review.")
        return
    lookup = {case["case_id"]: case for case in cases}
    ids = list(lookup)
    requested = st.session_state.pop("case_to_open", None)
    if requested in ids:
        st.session_state["review_case"] = requested
    elif st.session_state.get("review_case") not in ids:
        preferred = st.session_state.get("selected_review_case", st.session_state.get("last_case_id", ids[0]))
        st.session_state["review_case"] = preferred if preferred in ids else ids[0]
    st.button("Back to Case Queue", on_click=back_to_queue)
    selected = st.selectbox("Select case", ids, key="review_case",
                            format_func=lambda cid: case_option(lookup[cid]))
    st.session_state["selected_review_case"] = selected
    case = lookup[selected]
    with st.container(border=True):
        st.subheader(plain_markdown(display_title(case)))
        provenance = "Sample Investigation · Fictional scenario and review outcomes" if case["is_demo"] else "Investigator intake"
        st.caption(f"{short_case_id(selected)} · {provenance}")
        left, middle, right = st.columns(3)
        left.metric("Preliminary priority", f"{PRIORITY_SYMBOL[case['priority']]} {case['priority']}")
        middle.metric("Review status", case["status"])
        right.metric("Manual verdict", case["verdict"])
    st.subheader("Observation details")
    left, right = st.columns([1.6, 1])
    left.text(f"Source: {case['source_type']} · Brand: {case['brand'] or 'Not supplied'}")
    left.text(case["description"] or "No description supplied.")
    left.text(f"Source URL: {case['source_url'] or 'Not supplied'}")
    left.text(f"Official domain: {case['official_domain'] or 'Not configured'}")
    right.write("**Observed:** " + format_timestamp(case["observed_at"]))
    right.write("**Created:** " + format_timestamp(case["created_at"]))
    right.write("**Updated:** " + format_timestamp(case["updated_at"]))
    with st.expander("Case metadata"):
        st.code(selected, language=None)
        st.json({field: case[field] for field in ("observed_at", "created_at", "updated_at", "validated_at")})
    render_assessment(case["category"], case["priority"], case["indicators"], case["explanation"], case["url_analysis"])

    st.subheader("Investigator decision")
    st.caption("Use supporting notes for a final verdict. Validate before escalating; mark cleared cases False Positive with a No violation found verdict.")
    with st.form("review_" + selected):
        notes = st.text_area("Investigator notes", value=case["notes"], max_chars=20000,
                             height=140, key="notes_" + selected)
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

    st.subheader("Supporting evidence")
    st.caption("Manually collected PNG/JPG · Up to 5 MiB and 20 megapixels · Original bytes and SHA-256 retained")
    version_key = "evidence_version_" + selected
    version = st.session_state.get(version_key, 0)
    form_suffix = f"{selected}_{version}"
    # Retain user input after validation errors; reset only on a successful upload.
    with st.expander("Attach a screenshot"):
        with st.form("evidence_" + form_suffix):
            upload = st.file_uploader("Screenshot", type=["png", "jpg", "jpeg"], key="upload_" + form_suffix)
            evidence_source = st.text_input("Evidence source URL", value=case["source_url"], max_chars=4096)
            observed = st.text_input("Evidence observation timestamp (UTC ISO 8601)", value=case["observed_at"],
                                     key="evidence_observed_" + form_suffix,
                                     help="Defaults to the case observation. Replace it with the screenshot's actual observation time, including a timezone.")
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
        st.caption("No screenshots attached.")
    for number, item in enumerate(items, 1):
        with st.container(border=True):
            st.write(f"Screenshot {number} · {format_timestamp(item['observed_at'])}")
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
            with st.expander(f"Screenshot {number} metadata"):
                st.json(item)


def dashboard(db: Database):
    st.header("Dashboard & Reports")
    data_source = remembered_selectbox("Data source", DATA_SOURCES, "dashboard_data_source")
    cases = filter_data_source(db.list_cases(), data_source)
    st.caption(f"Overview: {data_source} · Metrics and chart use this subset. Report filters below narrow exports only.")
    metrics = st.columns(4)
    metrics[0].metric("Total cases", len(cases))
    metrics[1].metric("Awaiting review", sum(c["status"] in ("New", "Reviewing") for c in cases))
    metrics[2].metric("Validated cases", sum(c["status"] in ("Validated", "Escalated") for c in cases))
    metrics[3].metric("False positives", sum(c["status"] == "False Positive" for c in cases))
    sample_count = sum(c["is_demo"] for c in cases)
    st.caption(f"{sample_count:,} Sample Data · {len(cases) - sample_count:,} Investigator intake · Validated includes escalated cases.")
    if cases:
        st.subheader("Cases by preliminary threat category")
        counts = pd.Series([c["category"] for c in cases]).value_counts().reindex(CATEGORIES, fill_value=0).rename("Cases")
        st.vega_lite_chart(counts.rename_axis("Threat category").reset_index(), {
            "mark": {"type": "bar", "color": "#53c7b5"},
            "encoding": {
                "x": {"field": "Cases", "type": "quantitative", "axis": {"tickMinStep": 1}},
                "y": {"field": "Threat category", "type": "nominal", "sort": list(CATEGORIES),
                      "axis": {"labelLimit": 280}},
                "tooltip": [{"field": "Threat category"}, {"field": "Cases"}],
            },
        }, width="stretch", height=260)
    else:
        st.info("No cases in this data source yet. Create an investigation or choose another data source.")
    st.subheader("Export cases")
    st.caption("Exports use the filters below and include analyst notes, verdicts, UTC timestamps and evidence references. Excel also includes an Evidence sheet. Image files remain in the local evidence directory.")
    filtered = filtered_cases(db, "reports", data_source)
    st.write(f"{len(filtered)} case(s) selected for export.")
    left, right = st.columns(2)
    left.download_button("Download CSV", export_csv(db, filtered), file_name="digital-risk-cases.csv", mime="text/csv",
                          disabled=not filtered, on_click="ignore")
    try:
        right.download_button("Download Excel", export_excel(db, filtered), file_name="digital-risk-cases.xlsx",
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled=not filtered,
                              on_click="ignore")
    except ValueError as exc:
        right.warning(str(exc))
    st.caption("Potential spreadsheet formulas are prefixed with an apostrophe. Keep reports and evidence private; they may contain investigator-supplied sensitive information.")
    case_table(filtered)


def main():
    st.title("Digital Risk Triage")
    st.caption("Investigation Desk · Local case triage · Investigator-led decisions")
    st.sidebar.title("Digital Risk Triage")
    st.sidebar.caption("Investigation Desk")
    section = st.sidebar.radio("Workspace", SECTIONS, key="workspace")
    st.sidebar.caption("Offline URL analysis · Investigator-led review")
    try:
        db = Database(DATA / "cases.sqlite3")
        with st.sidebar.container(border=True):
            st.caption("Sample Data · 100 fictional investigations using .example domains. Review outcomes are fictional.")
            if st.button("Load Sample Dataset", width="stretch"):
                try:
                    inserted = load_sample_dataset(db)
                except DatasetError as exc:
                    st.error(str(exc))
                else:
                    flash(f"Added {inserted} new sample cases. Existing investigations were preserved.")
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
