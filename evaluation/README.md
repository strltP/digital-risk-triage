# Offline Rule-Based Evaluation

This module measures the existing Digital Risk Triage rules against an external
phishing/legitimate dataset. It is separate from Streamlit, the SQLite case store
and the 100 fictional sample investigations. It does not train a model, tune rules,
visit dataset URLs or fetch website content. It needs only the existing project
requirements and Python 3.11+.

## Dataset and acquisition

The adapter targets the original [PhiUSIIL Phishing URL (Website) dataset at
UCI](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset), contributed
by Arvind Prasad and Shalini Chandra (2024), under **CC BY 4.0**. UCI documents
235,795 instances: 100,945 phishing and 134,850 legitimate. Its original label
convention is **`0 = phishing`, `1 = legitimate`**. Internally the evaluation maps
phishing to the positive boolean class. It does not follow reversed encodings
sometimes used in third-party copies.

Download the ZIP from the official page and extract
`PhiUSIIL_Phishing_URL_Dataset.csv` into `evaluation/data/` or another private local
directory. `evaluation/data/` and generated results are Git-ignored. The benchmark
reads a local UTF-8/UTF-8-BOM CSV and never downloads anything at runtime.

Required, case-sensitive columns are **`URL`** and **`label`**. Additional columns
are allowed but ignored. In particular, `Title`, domain metadata, precomputed
similarity values and numerical webpage features are not inputs. There is no
URL-plus-title experiment in this implementation. Missing fields are not invented.
The adapter validates the header and labels rather than guessing a different schema.

**Real-data execution is pending.** During implementation the official UCI metadata
and label documentation were inspected, but the Cloud proxy rejected the official
ZIP request with HTTP 403. The raw release could not be downloaded or inspected,
and no real PhiUSIIL benchmark was run. Tests use small synthetic reserved-domain
CSV fixtures; their metrics are not published as benchmark results. Raw-release
compatibility and actual metrics remain checks to perform after a local download.

## Run

From the repository root, using the Python environment described in the main README:

```bash
python -m evaluation.evaluate --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv --sample-size 1000 --seed 42 --output evaluation/results/phiusiil-1000
```

The default is exactly **500 phishing + 500 legitimate**, seed **42**, with both
protocols. `--sample-size` supports other positive even totals while retaining equal
class balance. Insufficient examples in either class cause an explicit error;
the command does not shrink or rebalance the requested sample.

Evaluate every cleaned record, retaining the dataset's class balance:

```bash
python -m evaluation.evaluate --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv --full --output evaluation/results/phiusiil-full
```

`--full` and `--sample-size` are mutually exclusive. `--protocol assessment` or
`--protocol url-screening` runs only one protocol; default `both` keeps their results
separate. `--output` defaults to `evaluation/results/latest`. Reusing an output
directory replaces its three report files. The input CSV cannot be an output file.
Run `python -m evaluation.evaluate --help` for arguments and errors.

## Two protocols

| Protocol | Existing function and inputs | Positive prediction | Interpretation |
|---|---|---|---|
| A: `assessment` | `assess(Intake(source_type="Website", url=URL))`; brand, official_domain, title, description and notes are empty | Category equals `Potential phishing` | Existing classification behavior with limited inputs |
| B: `url-screening` | `analyze_url(URL, official="")` | At least one configured URL indicator | A structural URL review flag, not a verified phishing finding |

The URL column, with boundary whitespace trimmed, is the only detector input.
Ground-truth labels are used solely for sampling and scoring. Neither protocol
uses precomputed dataset features. The rules remain unchanged.

URL-only assessment has no credential-request text, account-verification wording,
or official brand reference. Poor recall or zero phishing predictions are valid
findings under those constraints. Domain similarity needs brand context and is not
measured here. Priorities and RapidFuzz similarity are not probabilities; a URL
indicator alone proves neither phishing nor safety.

## Preprocessing and reproducibility

1. Validate exact required columns, unique header names and CSV record structure.
   Labels must be the strings `0` or `1` after trimming. Invalid labels or malformed
   CSV abort the run with the record index, without echoing potentially sensitive cells.
2. Count and drop empty URLs. Count and drop URLs without an explicit HTTP(S)
   scheme or failing the existing `normalize_url()` validation. No URL is visited.
3. Deduplicate globally, before sampling. Identity uses the existing normalizer:
   trim outer whitespace, lowercase scheme/host, IDNA-normalize the hostname,
   remove a trailing hostname dot, and use `/` for an empty path. Preserve path
   case, queries, fragments, userinfo and explicit ports; HTTP and HTTPS remain
   distinct. This is conservative string normalization, not a claim that all
   semantically equivalent URLs have been merged.
4. Retain the first occurrence of a key with one label. If a key has conflicting
   labels, exclude **all** rows for that key. Ordinary duplicate removals exclude
   conflict groups so dropped-row counts do not overlap.
5. Sort retained keys, then use a local `random.Random(seed)` for balanced sampling
   without replacement and a deterministic shuffle. Full mode uses sorted cleaned
   records without randomness. The seed does not affect full mode.

Reports record parsed row counts before cleaning, invalid counts by reason,
duplicate removals, conflicting groups and rows, cleaned classes, and final sampled
classes. `valid_rows` is before deduplication. Blank lines and the header are not
counted as data records. The counts reconcile as:

```text
original_rows = invalid_rows + removed_duplicate_rows + conflicting_rows + cleaned_rows
```

A SHA-256 fingerprint identifies the actual input bytes, including the header and
ignored features. A second fingerprint identifies the ordered selected URL hashes.
Reports also include the seed, protocol, timestamp, Git commit/dirty flag, Python
version and relevant dependency versions. A local file matching the schema is not
automatically authenticated as the official UCI release. Preserve the exact CSV,
code commit and pinned environment to reproduce a run; timestamps naturally differ.
Commit code before benchmarking: a dirty working tree cannot be reproduced from
the commit SHA alone.

## Metrics and reports

Phishing is positive throughout. Each protocol receives its own TP, FP, TN, FN,
accuracy, precision, recall, F1, specificity and false-positive rate (FPR).

| Metric | Formula |
|---|---|
| Accuracy | `(TP + TN) / N` |
| Precision | `TP / (TP + FP)` |
| Recall | `TP / (TP + FN)` |
| F1 | `2TP / (2TP + FP + FN)` |
| Specificity | `TN / (TN + FP)` |
| FPR | `FP / (FP + TN)` |

Zero denominators produce **0.0**, and the affected metric names appear in
`undefined_metrics`. In particular, no positive predictions means undefined
precision, reported as zero; recall is zero when phishing examples are present.
Do not interpret the zero precision convention as a measured positive predictive value.

The command creates:

- **`summary.json`**: provenance, preprocessing/sampling, separate protocol metrics,
  trivial baselines and aggregate error analysis.
- **`report.md`**: methodology, interpretation, limitations, false-positive and
  false-negative indicator counts, and up to five hash-only examples per error type.
- **`confusion_matrix.csv`**: long-format matrices for protocols and baselines,
  with columns `evaluation,actual,predicted,count`.

Matrix order is legitimate, phishing for both axes: `[[TN, FP], [FN, TP]]`.
Always-legitimate and always-phishing baselines are constant reference predictions,
not production systems. Protocol scores are never averaged or combined.

No dataset URLs, dataset hostnames, query strings, userinfo, titles or page content appear in
reports. Error examples contain only normalized-URL SHA-256 identifiers and
one-based CSV record indices (excluding the header, not physical line numbers).
The original CSV must remain private if it contains sensitive information.

## Verification and limits

```bash
python -m pytest -q
```

Automated tests use synthetic fixtures only; ordinary pytest needs no dataset
download. They cover label direction, malformed input, duplicate conflicts,
deterministic stratification, hand-calculated metrics, zero denominators, protocol
mapping, label isolation, report generation and unchanged SQLite bytes. A fresh
subprocess verifies the CLI imports neither Streamlit nor `core.database`.
Network calls are blocked during isolation tests.

This benchmark does not evaluate counterfeit or trademark detection, the complete
taxonomy, investigator decisions, evidence management or case workflow quality.
Balanced samples change prevalence, so their precision and accuracy do not predict
operational traffic performance. It does not estimate confidence intervals, audit
label truth or establish generalization to current traffic. A separate,
independently specified URL-plus-title experiment or multiple/time-separated cohorts
could be future work; no such experiments or rule adjustments are made here.
