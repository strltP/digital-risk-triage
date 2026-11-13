"""Local PhiUSIIL CSV adapter: official 0=phishing, 1=legitimate labels."""
import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path
import random
from urllib.parse import urlsplit

from core.url_analysis import normalize_url

SOURCE = "https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset"
NAME = "PhiUSIIL Phishing URL (Website)"


class DatasetError(ValueError):
    """Invalid local input or an unsatisfiable sampling request."""


@dataclass(frozen=True)
class Record:
    url: str
    normalized_url: str
    phishing: bool
    record_index: int

    @property
    def identifier(self) -> str:
        # Reports contain only hashes, never URL hosts, paths, userinfo or queries.
        return hashlib.sha256(self.normalized_url.encode("utf-8")).hexdigest()


@dataclass
class Dataset:
    records: list[Record]
    sha256: str
    statistics: dict


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def class_counts(records: list[Record]) -> dict:
    phishing = sum(record.phishing for record in records)
    return {"phishing": phishing, "legitimate": len(records) - phishing}


def load_dataset(path: str | Path) -> Dataset:
    """Validate labels, drop unusable URLs, then deduplicate globally.

    An ambiguous URL loses *all* of its rows. Ordinary duplicate counts exclude
    conflicting groups, so every dropped row has exactly one reported reason.
    No website features (including Title) are retained or passed to the engine.
    """
    path = Path(path)
    counts = {"original_rows": 0, "empty_urls": 0, "invalid_urls": 0,
              "removed_duplicate_rows": 0, "conflicting_url_groups": 0, "conflicting_rows": 0}
    groups = {}
    original_classes = {"phishing": 0, "legitimate": 0}
    try:
        digest = fingerprint(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            columns = reader.fieldnames or []
            if not {"URL", "label"}.issubset(columns):
                raise DatasetError("PhiUSIIL CSV requires exact columns 'URL' and 'label'.")
            if len(columns) != len(set(columns)):
                raise DatasetError("CSV header contains duplicate column names.")
            for index, row in enumerate(reader, 1):
                counts["original_rows"] += 1
                if None in row or any(value is None for value in row.values()):
                    raise DatasetError(f"CSV record {index} has a different field count from the header.")
                label = row["label"].strip()
                if label not in ("0", "1"):
                    raise DatasetError(f"CSV record {index}: label must be 0 (phishing) or 1 (legitimate).")
                phishing = label == "0"
                original_classes["phishing" if phishing else "legitimate"] += 1
                url = row["URL"].strip()
                if not url:
                    counts["empty_urls"] += 1
                    continue
                try:
                    # Do not invent a protocol for missing/incomplete source URLs.
                    if urlsplit(url).scheme.lower() not in ("http", "https"):
                        raise ValueError("An explicit HTTP(S) scheme is required.")
                    normalized, _ = normalize_url(url)
                except ValueError:
                    counts["invalid_urls"] += 1
                    continue
                record = Record(url, normalized, phishing, index)
                if normalized not in groups:
                    groups[normalized] = [record, {phishing}, 1]
                else:
                    group = groups[normalized]
                    group[1].add(phishing)
                    group[2] += 1
    except FileNotFoundError as exc:
        raise DatasetError(f"Dataset file not found: {path}") from exc
    except UnicodeError as exc:
        raise DatasetError("Dataset must be UTF-8 CSV; a UTF-8 BOM is supported.") from exc
    except csv.Error as exc:
        # CSV contents may contain credentials or live URLs; do not echo cells.
        raise DatasetError("Invalid CSV syntax or oversized field; check quoting and field lengths.") from exc
    except OSError as exc:
        raise DatasetError(f"Cannot read dataset file: {exc.strerror or type(exc).__name__}.") from exc
    records = []
    for key in sorted(groups):
        record, labels, size = groups[key]
        if len(labels) > 1:
            counts["conflicting_url_groups"] += 1
            counts["conflicting_rows"] += size
        else:
            records.append(record)
            counts["removed_duplicate_rows"] += size - 1
    counts["invalid_rows"] = counts["empty_urls"] + counts["invalid_urls"]
    counts["valid_rows"] = counts["original_rows"] - counts["invalid_rows"]
    counts["cleaned_rows"] = len(records)
    counts["original_class_distribution"] = original_classes
    counts["cleaned_class_distribution"] = class_counts(records)
    if not records:
        raise DatasetError(f"No usable records remain: original={counts['original_rows']}, "
                           f"invalid={counts['invalid_rows']}, conflicting={counts['conflicting_rows']}.")
    return Dataset(records, digest, counts)


def select_records(records: list[Record], sample_size: int | None = 1000, seed: int = 42) -> list[Record]:
    """None selects all cleaned rows; otherwise require an exactly balanced sample."""
    if not records:
        raise DatasetError("Cannot sample an empty dataset.")
    if sample_size is None:
        return list(records)
    if sample_size <= 0 or sample_size % 2:
        raise DatasetError("Sample size must be a positive even integer for equal class balance.")
    classes = {True: [], False: []}
    for record in records:
        classes[record.phishing].append(record)
    per_class = sample_size // 2
    if any(len(group) < per_class for group in classes.values()):
        available = class_counts(records)
        raise DatasetError(f"Requested {per_class} per class; only {available['phishing']} phishing "
                           f"and {available['legitimate']} legitimate cleaned records are available.")
    rng = random.Random(seed)
    selected = rng.sample(classes[True], per_class) + rng.sample(classes[False], per_class)
    rng.shuffle(selected)
    return selected
