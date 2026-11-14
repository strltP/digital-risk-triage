"""Validate the bundled JSON sample dataset before seeding missing cases."""
from dataclasses import dataclass
import json
from pathlib import Path

from core.database import Database
from core.models import Intake, STATUSES, VERDICTS, observation_time
from core.url_analysis import analyze_url

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "datasets" / "sample_cases.json"
# A small provenance allowlist, not investigation fixtures.
SAMPLE_BRANDS = {
    "Astervale": "astervale.example", "Lumifern": "lumifern.example",
    "Velora Works": "veloraworks.example", "Northpetal": "northpetal.example",
}
SAMPLE_NOTICE = "Sample investigation (fictional). No evidence is supplied with this scenario."
CASE_FIELDS = {
    "case_key", "source_type", "url", "brand", "official_domain", "title", "description",
    "review_status", "review_verdict", "review_notes",
}
# Supported fictional review outcomes in this dataset. Database.update_review
# remains authoritative and enforces actual transitions when importing them.
SAMPLE_VERDICTS = {
    "New": "Pending review", "Reviewing": "Inconclusive",
    "Validated": "Confirmed violation", "Escalated": "Confirmed violation",
    "False Positive": "No violation found",
}


class DatasetError(ValueError):
    """A readable dataset file or validation error, safe to display in the UI."""


@dataclass(frozen=True)
class SampleCase:
    key: str
    intake: Intake
    status: str
    verdict: str
    observed_at: str | None = None


def _validate_case(record: dict) -> SampleCase:
    if not isinstance(record, dict):
        raise ValueError("Each case must be an object.")
    missing, extra = CASE_FIELDS - record.keys(), record.keys() - (CASE_FIELDS | {"observed_at"})
    if missing or extra:
        raise ValueError(f"Missing fields: {', '.join(sorted(missing)) or 'none'}; "
                         f"unsupported fields: {', '.join(sorted(extra)) or 'none'}.")
    if any(not isinstance(value, str) for value in record.values()):
        raise ValueError("All case fields must be strings.")
    key = record["case_key"]
    if not key.strip() or key != key.strip() or len(key) > 128:
        raise ValueError("case_key must be nonempty, at most 128 characters, without surrounding whitespace.")
    if SAMPLE_BRANDS.get(record["brand"]) != record["official_domain"]:
        raise ValueError("Use a supported fictional brand and its matching official .example domain.")
    status, verdict = record["review_status"], record["review_verdict"]
    if status not in STATUSES or verdict not in VERDICTS:
        raise ValueError("Unsupported review_status or review_verdict.")
    if verdict != SAMPLE_VERDICTS[status]:
        raise ValueError(f"Sample status '{status}' requires verdict '{SAMPLE_VERDICTS[status]}'.")
    review_notes = record["review_notes"]
    if status != "New" and not review_notes.strip():
        raise ValueError("Reviewed sample cases require supporting review_notes.")
    notes = SAMPLE_NOTICE + ("\nFictional sample review: " + review_notes if review_notes else "")
    intake = Intake(record["source_type"], record["url"], record["brand"], record["official_domain"],
                    record["title"], record["description"], notes).validated()
    # Reuse the URL module's complete parsing and official-domain validation.
    analysis = analyze_url(intake.url, intake.official_domain)
    if not analysis.hostname.endswith(".example"):
        raise ValueError("Sample URLs must use reserved .example domains.")
    observed = observation_time(record["observed_at"]) if "observed_at" in record else None
    return SampleCase(key, intake, status, verdict, observed)


def read_sample_cases(path: str | Path | None = None) -> list[SampleCase]:
    """Read and validate the entire dataset, without touching SQLite."""
    path = DEFAULT_DATASET if path is None else Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetError(f"Sample dataset not found: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise DatasetError(f"Invalid JSON in sample dataset {path}, line {exc.lineno}, column {exc.colno}.") from exc
    except (OSError, UnicodeError) as exc:
        raise DatasetError(f"Could not read sample dataset {path} as UTF-8: {exc}.") from exc
    if not isinstance(data, dict) or set(data) != {"dataset_version", "description", "cases"}:
        raise DatasetError("Sample dataset must be an object containing dataset_version, description and cases.")
    if data["dataset_version"] != "1.0":
        raise DatasetError("Unsupported sample dataset_version; expected '1.0'.")
    if not isinstance(data["description"], str) or not data["description"].strip():
        raise DatasetError("Sample dataset description must be a nonempty string.")
    if not isinstance(data["cases"], list) or not data["cases"]:
        raise DatasetError("Sample dataset cases must be a nonempty list.")
    cases, keys = [], set()
    for index, record in enumerate(data["cases"], 1):
        try:
            case = _validate_case(record)
            if case.key in keys:
                raise ValueError(f"Duplicate case_key '{case.key}'.")
        except ValueError as exc:
            raise DatasetError(f"Sample case {index}: {exc}") from exc
        keys.add(case.key)
        cases.append(case)
    return cases


def load_sample_dataset(db: Database, path: str | Path | None = None) -> int:
    """Seed only missing stable keys; preserve all existing cases and evidence."""
    cases = read_sample_cases(path)  # Validate every record before the first write.
    inserted = 0
    with db.transaction():
        with db.connection() as conn:
            existing = {row[0] for row in conn.execute("SELECT demo_key FROM cases WHERE demo_key IS NOT NULL")}
        for case in cases:
            if case.key in existing:
                continue
            case_id = db.create_case(case.intake, demo_key=case.key, observed_at=case.observed_at)
            if case.status == "Escalated":
                db.update_review(case_id, notes=case.intake.notes, status="Validated", verdict=case.verdict)
            if case.status != "New":
                db.update_review(case_id, notes=case.intake.notes, status=case.status, verdict=case.verdict)
            inserted += 1
    return inserted
