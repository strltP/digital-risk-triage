"""Offline CLI: python -m evaluation.evaluate --dataset local.csv."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import subprocess

from core.models import Intake
from core.risk_rules import assess
from core.url_analysis import analyze_url
from evaluation.adapters.phiusiil import DatasetError, NAME, SOURCE, class_counts, load_dataset, select_records
from evaluation.metrics import binary_metrics
from evaluation.reporting import LIMITATIONS, write_reports

PROTOCOLS = ("assessment", "url-screening")


def predict(url: str, protocol: str) -> tuple[bool, list[str]]:
    """The detector receives only source URL text, never labels or dataset features."""
    if protocol == "assessment":
        result = assess(Intake(source_type="Website", url=url, brand="", official_domain="",
                              title="", description=""))
        return result.category == "Potential phishing", result.indicators
    if protocol == "url-screening":
        result = analyze_url(url, official="")
        return bool(result.indicators), result.indicators
    raise ValueError("Unknown evaluation protocol.")


def source_version() -> dict:
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                                capture_output=True, text=True, timeout=5).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True,
                                capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        commit, status = None, None
    return {"git_commit": commit, "working_tree_dirty": bool(status) if status is not None else None,
            "python": platform.python_version(),
            "dependencies": {name: version(name) for name in ("RapidFuzz", "tldextract")}}


def error_analysis(records, predictions, indicators, positive):
    errors = [(record, signals) for record, prediction, signals in zip(records, predictions, indicators)
              if prediction != record.phishing and prediction == positive]
    return {
        "count": len(errors),
        "without_url_indicators": sum(not signals for _, signals in errors),
        "indicator_counts": dict(sorted(Counter(signal for _, signals in errors for signal in signals).items())),
        "examples": [{"url_sha256": record.identifier, "csv_record_index": record.record_index,
                      "indicator_count": len(signals)} for record, signals in errors[:5]],
    }


def run_benchmark(dataset_path: str | Path, *, sample_size: int | None = 1000,
                  seed: int = 42, protocol: str = "both") -> dict:
    if protocol not in ("both", *PROTOCOLS):
        raise ValueError("Unknown evaluation protocol.")
    dataset = load_dataset(dataset_path)
    records = select_records(dataset.records, sample_size, seed)
    actual = [record.phishing for record in records]
    protocols = {}
    for name in PROTOCOLS if protocol == "both" else (protocol,):
        outcomes = [predict(record.url, name) for record in records]
        predictions = [prediction for prediction, _ in outcomes]
        indicators = [signals for _, signals in outcomes]
        protocols[name] = {
            "positive_definition": "category == Potential phishing" if name == "assessment" else "one or more passive URL indicators",
            "metrics": binary_metrics(actual, predictions),
            "error_analysis": {
                "false_positives": error_analysis(records, predictions, indicators, True),
                "false_negatives": error_analysis(records, predictions, indicators, False),
            },
        }
    return {
        "report_version": "1.0", "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": {"name": NAME, "source": SOURCE, "license": "CC BY 4.0",
                    "attribution": "Arvind Prasad and Shalini Chandra (2024), UCI Machine Learning Repository",
                    "label_convention": {"0": "phishing", "1": "legitimate"}, "sha256": dataset.sha256,
                    "provenance": "Locally supplied CSV; its origin is not independently authenticated."},
        "inputs_used": {"source_type": "Website", "url": "original URL column, trimmed",
                        "brand": "", "official_domain": "", "title": "", "description": ""},
        "preprocessing": dataset.statistics,
        "sampling": {"requested_sample_size": sample_size, "full_dataset": sample_size is None,
                     "random_seed": seed, "evaluated_records": len(records), "class_distribution": class_counts(records),
                     "selection_sha256": hashlib.sha256("\n".join(record.identifier for record in records).encode()).hexdigest()},
        "source_code": source_version(), "protocols": protocols, "interpretation": LIMITATIONS,
        "baselines": {"always-legitimate": binary_metrics(actual, [False] * len(records)),
                      "always-phishing": binary_metrics(actual, [True] * len(records))},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline PhiUSIIL evaluation; no URL visits, training or SQLite access.")
    parser.add_argument("--dataset", type=Path, required=True, help="Locally downloaded official UTF-8 CSV")
    sampling = parser.add_mutually_exclusive_group()
    sampling.add_argument("--sample-size", type=int, help="Balanced even sample size (default: 1000)")
    sampling.add_argument("--full", action="store_true", help="Evaluate every cleaned record, retaining class imbalance")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--protocol", choices=("both", *PROTOCOLS), default="both")
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/latest"))
    args = parser.parse_args(argv)
    sample_size = None if args.full else 1000 if args.sample_size is None else args.sample_size
    if sample_size is not None and (sample_size <= 0 or sample_size % 2):
        parser.error("Sample size must be a positive even integer for equal class balance.")
    destinations = [args.output / name for name in ("summary.json", "report.md", "confusion_matrix.csv")]
    if args.dataset.resolve() in [path.resolve() for path in destinations]:
        parser.error("Output directory would overwrite the input dataset; choose a different directory.")
    try:
        summary = run_benchmark(args.dataset, sample_size=sample_size, seed=args.seed, protocol=args.protocol)
        write_reports(summary, args.output)
    except (DatasetError, OSError) as exc:
        parser.error(str(exc))
    print(f"Evaluated {summary['sampling']['evaluated_records']} records. Reports: {args.output}")
    for name, result in summary["protocols"].items():
        metrics = result["metrics"]
        print(f"{name}: precision={metrics['precision']:.4f}, recall={metrics['recall']:.4f}, "
              f"F1={metrics['f1']:.4f}; TP={metrics['tp']} FP={metrics['fp']} TN={metrics['tn']} FN={metrics['fn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
