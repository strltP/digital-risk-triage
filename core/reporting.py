"""Structured CSV/XLSX reports with spreadsheet formula neutralization."""
import csv
from io import BytesIO
import json
import re

import pandas as pd

from core.database import Database
from core.models import PRELIMINARY_NOTICE

COLUMNS = ["case_id", "data_label", "source_type", "source_url", "observed_at", "created_at",
           "updated_at", "brand", "official_domain", "title", "description", "category", "priority",
           "indicators", "explanation", "domain_analysis", "analyst_notes", "status", "verdict",
           "validated_at", "evidence_references", "assessment_notice"]
EVIDENCE_COLUMNS = ["evidence_id", "case_id", "filename", "original_name", "mime_type", "size_bytes",
                    "sha256", "source_url", "observed_at", "uploaded_at", "description"]


def safe_cell(value):
    """Prefix dangerous text with an apostrophe, for CSV and spreadsheet readers."""
    if not isinstance(value, str):
        return value
    # XML 1.0 forbids these controls. Remove before checking for formula prefixes.
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    candidate = value.lstrip(" \t\r\n\ufeff")
    if candidate.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def report_frames(db: Database, cases: list[dict] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    cases = db.list_cases() if cases is None else cases
    rows, evidence_rows = [], []
    for case in cases:
        evidence = db.list_evidence(case["case_id"])
        evidence_rows.extend(evidence)
        references = [f"{item['evidence_id']} | evidence/{item['filename']} | SHA256 {item['sha256']} | "
                      f"source={item['source_url']} | observed={item['observed_at']}" for item in evidence]
        row = {name: case.get(name, "") for name in COLUMNS}
        row.update(data_label="SIMULATED DEMO" if case["is_demo"] else "Investigator intake",
                   indicators="\n".join(case["indicators"]), domain_analysis=json.dumps(case["url_analysis"], ensure_ascii=False),
                   analyst_notes=case["notes"], evidence_references="\n".join(references), assessment_notice=PRELIMINARY_NOTICE)
        rows.append(row)
    frames = (pd.DataFrame(rows, columns=COLUMNS), pd.DataFrame(evidence_rows, columns=EVIDENCE_COLUMNS))
    return tuple(frame.map(safe_cell) for frame in frames)


def export_csv(db: Database, cases: list[dict] | None = None) -> bytes:
    frame, _ = report_frames(db, cases)
    return frame.to_csv(index=False, quoting=csv.QUOTE_ALL).encode("utf-8-sig")


def export_excel(db: Database, cases: list[dict] | None = None) -> bytes:
    cases_frame, evidence_frame = report_frames(db, cases)
    for frame in (cases_frame, evidence_frame):
        if any(isinstance(value, str) and len(value) > 32767 for value in frame.to_numpy().flat):
            raise ValueError("An Excel cell exceeds 32,767 characters. Export CSV to preserve the complete report.")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in (("Cases", cases_frame), ("Evidence", evidence_frame)):
            frame.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cells in sheet.columns:
                sheet.column_dimensions[cells[0].column_letter].width = min(50, max(18, len(str(cells[0].value)) + 2))
    return output.getvalue()
