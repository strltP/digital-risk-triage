"""Pure view helpers; stored case fields and reporting values stay untouched."""
from datetime import datetime, timezone
import re

DATA_SOURCES = ("All cases", "Sample Data", "Investigator intake")
SORT_OPTIONS = ("Priority high to low", "Priority low to high", "Newest observed", "Oldest observed")
PRIORITY_SYMBOL = {"Low": "🟢", "Medium": "🟠", "High": "🔴"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def parsed_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Not recorded"
    parsed = parsed_time(value)
    if parsed is None:
        return "Unrecognized time"
    return (f"{parsed.day:02d} {MONTHS[parsed.month - 1]} {parsed.year:04d}, "
            f"{parsed.hour:02d}:{parsed.minute:02d} UTC")


def short_case_id(case_id: str) -> str:
    return case_id[:12]


def plain_markdown(value: str) -> str:
    """Show investigator text literally in native headings and captions."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", value)


def display_title(case: dict) -> str:
    title = case["title"]
    if case["is_demo"]:
        title = title.removeprefix("[SIMULATED]").lstrip()
    return title or "Untitled observation"


def case_option(case: dict) -> str:
    provenance = "Sample Data" if case["is_demo"] else "Investigator intake"
    return (f"{display_title(case)[:80]} · {PRIORITY_SYMBOL[case['priority']]} {case['priority']}"
            f" · {case['status']} · {provenance} · {short_case_id(case['case_id'])}")


def filter_data_source(cases: list[dict], data_source: str) -> list[dict]:
    if data_source not in DATA_SOURCES:
        raise ValueError("Choose a supported data source.")
    return [case for case in cases if data_source == "All cases"
            or bool(case["is_demo"]) == (data_source == "Sample Data")]


def queue_view(cases: list[dict], search: str = "", sort: str = SORT_OPTIONS[0]) -> list[dict]:
    """Search metadata and sort deterministically without mutating the records."""
    if sort not in SORT_OPTIONS:
        raise ValueError("Choose a supported case ordering.")
    query = search.strip().casefold()
    cases = [case for case in cases if not query or any(query in str(case[field]).casefold()
             for field in ("title", "case_id", "brand", "source_url"))]
    cases.sort(key=lambda case: case["case_id"])
    cases.sort(key=lambda case: parsed_time(case["observed_at"]) or datetime.min.replace(tzinfo=timezone.utc),
               reverse=sort != "Oldest observed")
    if sort.startswith("Priority"):
        rank = {"High": 0, "Medium": 1, "Low": 2}
        cases.sort(key=lambda case: (rank[case["priority"]] if sort == SORT_OPTIONS[0] else -rank[case["priority"]],
                                     case["status"] not in ("New", "Reviewing")))
    return cases
