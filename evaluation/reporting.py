"""Aggregate reports with hash-only error examples; no dataset URLs or page text."""
import csv
from io import StringIO
import json
from pathlib import Path

LIMITATIONS = [
    "Protocol A measures the existing full assessment with URL-only inputs; positive means category Potential phishing.",
    "Protocol B measures passive URL screening; a review flag is not a verified phishing classification.",
    "No title, description, official brand domain, label-derived content or numerical dataset feature enters either detector.",
    "Brand context is absent, so domain similarity checks are unavailable. RapidFuzz similarity is not phishing probability.",
    "High, Medium and Low are review priorities, not probabilities. URL indicators do not prove phishing or safety.",
    "Undefined metric ratios are reported as 0.0 and named explicitly in undefined_metrics.",
    "Dataset labels do not evaluate counterfeit, trademark misuse, human review, evidence handling or the full investigation workflow.",
    "Balanced sampling changes class prevalence; these precision and accuracy values need not represent operational traffic.",
    "These are descriptive results on a fixed labeled dataset, not deployment guarantees or a model-training experiment.",
]


def metric_table(results: dict) -> list[str]:
    rows = ["| Evaluation | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 | Specificity | FPR |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, metrics in results.items():
        values = [str(metrics[key]) for key in ("tp", "fp", "tn", "fn")]
        values += [f"{metrics[key]:.6f}" for key in ("accuracy", "precision", "recall", "f1", "specificity", "false_positive_rate")]
        rows.append("| " + " | ".join([name, *values]) + " |")
    return rows


def render_markdown(summary: dict) -> str:
    dataset, sampling, stats = summary["dataset"], summary["sampling"], summary["preprocessing"]
    classes = sampling["class_distribution"]
    lines = [
        "# Digital Risk Triage — Offline Evaluation", "", "## Executive summary", "",
        f"Evaluated **{sampling['evaluated_records']:,}** local CSV records: {classes['phishing']:,} phishing and "
        f"{classes['legitimate']:,} legitimate. Results for classification and URL screening are reported separately.",
        "No detection thresholds were tuned and no model was trained.", "", "## Dataset and provenance", "",
        f"Dataset reference: [{dataset['name']}]({dataset['source']}).",
        f"Attribution: {dataset['attribution']}; license: {dataset['license']}.",
        "Official labels: **0 = phishing, 1 = legitimate**; phishing is the positive class in this report.",
        dataset["provenance"], f"Input file SHA-256: `{dataset['sha256']}`.",
        f"Evaluation time (UTC): {summary['evaluation_timestamp']}.",
        f"Source code: `{summary['source_code']['git_commit'] or 'unavailable'}`; "
        f"working tree dirty: `{summary['source_code']['working_tree_dirty']}`.",
        f"Python: {summary['source_code']['python']}; dependencies: `{summary['source_code']['dependencies']}`.",
        "", "## Methodology and actual inputs", "",
        "Only the original `URL` string, trimmed at its boundaries, enters the detector. `source_type` is `Website`; "
        "brand, official_domain, title and description are empty. `Title` and all numerical features are ignored. "
        "Ground-truth labels control stratification and scoring only.",
        "Protocol A calls `assess()`; a positive prediction requires category `Potential phishing`. "
        "Protocol B calls `analyze_url()` with no official domain; any configured URL indicator flags a URL for review. "
        "The protocols are never combined into a headline score.",
        "", "## Preprocessing and sampling", "",
        "CSV labels must be exactly 0/1 after trimming; invalid labels or malformed CSV abort the run. "
        "Empty URLs and URLs that lack an explicit HTTP(S) scheme or fail the existing URL validation are dropped.",
        "Duplicate identity uses the existing `normalize_url()` policy: trim outer whitespace, lowercase the scheme/host, "
        "IDNA-normalize hosts, strip a trailing hostname dot and supply `/` for an empty path. "
        "Paths, queries, fragments, userinfo and explicit ports are retained; HTTP and HTTPS remain distinct. "
        "The first occurrence is retained for an unambiguous key. All rows of a label-conflicting key are excluded.",
        "", "| Count | Records |", "|---|---:|",
    ]
    for key in ("original_rows", "valid_rows", "empty_urls", "invalid_urls", "invalid_rows",
                "removed_duplicate_rows", "conflicting_url_groups", "conflicting_rows", "cleaned_rows"):
        lines.append(f"| {key} | {stats[key]:,} |")
    lines += ["", "`valid_rows` is before deduplication. Ordinary duplicate removals exclude conflicting groups, "
              "so removals are not double-counted. CSV record counts exclude blank lines and the header.",
              f"Cleaned classes: `{stats['cleaned_class_distribution']}`.",
              f"Requested sample size: `{sampling['requested_sample_size']}`; seed: `{sampling['random_seed']}`; "
              f"full dataset: `{sampling['full_dataset']}`.",
              "Balanced samples use equal counts per class with a local seeded RNG; full mode retains the cleaned class balance and does not use the seed.",
              f"Selected-record SHA-256: `{sampling['selection_sha256']}`.",
              "", "## Protocol results", ""]
    lines += metric_table({name: result["metrics"] for name, result in summary["protocols"].items()})
    lines += ["", "### Trivial reference baselines", "",
              "Constant predictions are context only, not competing production systems.", ""]
    lines += metric_table(summary["baselines"])
    lines += ["", "## Confusion matrices", "",
              "Rows are actual labels; columns are predicted labels. Order: legitimate, phishing."]
    for name, result in summary["protocols"].items():
        metrics = result["metrics"]
        lines += ["", f"### {name}", "", "| Actual / Predicted | Legitimate | Phishing |", "|---|---:|---:|",
                  f"| Legitimate | {metrics['tn']} | {metrics['fp']} |",
                  f"| Phishing | {metrics['fn']} | {metrics['tp']} |",
                  "", f"Undefined ratios (reported as 0.0): {', '.join(metrics['undefined_metrics']) or 'none'}."]
    lines += ["", "## Interpretation", "",
              "URL-only assessment has no credential-request text, verification wording or brand context. "
              "Zero phishing predictions and poor recall are legitimate findings under those input constraints; "
              "they do not establish that the URLs are safe. Screening flags structural URL properties, which may "
              "also occur on legitimate sites. Compare each protocol separately with the trivial baselines.",
              "", "## False-positive and false-negative analysis", "",
              "Indicator counts below can overlap when an error has several indicators. "
              "Examples are SHA-256 identifiers plus original CSV record indices, never live URLs or page content."]
    for name, result in summary["protocols"].items():
        for kind, errors in result["error_analysis"].items():
            lines += ["", f"### {name}: {kind.replace('_', ' ')}", "",
                      f"Errors: {errors['count']}; without URL indicators: {errors['without_url_indicators']}.", ""]
            for indicator, count in errors["indicator_counts"].items():
                lines.append(f"- {indicator} — {count}")
            for example in errors["examples"]:
                lines.append(f"- CSV record {example['csv_record_index']}; URL SHA-256 `{example['url_sha256']}`; "
                             f"{example['indicator_count']} indicators.")
    lines += ["", "## Limitations and potential improvements", ""]
    lines += ["- " + notice for notice in summary["interpretation"]]
    lines += ["", "Future work could evaluate independently supplied page titles in a separately named experiment, "
              "audit label quality and measure variation across independently sampled or time-separated cohorts. "
              "These possibilities are not implemented here and do not justify changing rules based on this benchmark.", ""]
    return "\n".join(lines)


def write_reports(summary: dict, output: str | Path) -> None:
    output = Path(output)
    markdown = render_markdown(summary)
    serialized = json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    matrix_csv = StringIO(newline="")
    writer = csv.writer(matrix_csv)
    writer.writerow(["evaluation", "actual", "predicted", "count"])
    evaluations = {name: result["metrics"] for name, result in summary["protocols"].items()}
    evaluations.update({"baseline/" + name: metrics for name, metrics in summary["baselines"].items()})
    for name, metrics in evaluations.items():
        matrix = metrics["confusion_matrix"]
        for row, actual in enumerate(matrix["labels"]):
            for column, prediction in enumerate(matrix["labels"]):
                writer.writerow([name, actual, prediction, matrix["values"][row][column]])
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in (("summary.json", serialized), ("report.md", markdown),
                              ("confusion_matrix.csv", matrix_csv.getvalue())):
        path = output / filename
        if path.is_symlink():
            raise OSError(f"Report destination is a symbolic link: {path}")
        path.write_text(content, encoding="utf-8")
