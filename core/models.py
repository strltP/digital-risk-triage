"""Shared validation and plain data structures."""
from dataclasses import dataclass
from datetime import datetime, timezone

SOURCES = ("Website", "Social Media", "Marketplace", "Other")
CATEGORIES = (
    "Potential phishing", "Potential brand impersonation",
    "Potential counterfeit listing", "Potential trademark misuse",
    "Other suspicious content",
)
PRIORITIES = ("Low", "Medium", "High")
STATUSES = ("New", "Reviewing", "Validated", "False Positive", "Escalated")
VERDICTS = ("Pending review", "Confirmed violation", "No violation found", "Inconclusive")
PRELIMINARY_NOTICE = "Preliminary assessment only. Human verification is required; indicators do not prove fraud or a violation."


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def observation_time(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Enter an ISO 8601 observation timestamp with a timezone.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Enter an ISO 8601 observation timestamp with a timezone.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Observation timestamp must include a timezone, for example +00:00.")
    try:
        normalized = parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Observation timestamp is outside the supported UTC date range.") from exc
    if normalized > datetime.now(timezone.utc):
        raise ValueError("Observation timestamp cannot be in the future.")
    return normalized.isoformat()


@dataclass(frozen=True)
class Intake:
    source_type: str
    url: str = ""
    brand: str = ""
    official_domain: str = ""
    title: str = ""
    description: str = ""
    notes: str = ""

    def validated(self) -> "Intake":
        values = {key: str(value).strip() for key, value in vars(self).items()}
        cleaned = Intake(**values)
        if cleaned.source_type not in SOURCES:
            raise ValueError("Choose a supported source type.")
        if cleaned.brand and len(cleaned.brand) < 2:
            raise ValueError("Leave the protected brand blank or enter at least two characters.")
        if not cleaned.url and sum(c.isalnum() for c in cleaned.title + cleaned.description) < 10:
            raise ValueError("Provide a URL or meaningful title/description (at least 10 letters or digits).")
        for key, value in values.items():
            limit = 4096 if key in ("url", "official_domain") else 20000
            if len(value) > limit:
                raise ValueError(f"{key.replace('_', ' ').title()} exceeds the {limit:,}-character limit.")
        return cleaned
