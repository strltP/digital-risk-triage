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

**The full benchmark succeeded on Windows on 15 November 2026**, using the original
locally supplied PhiUSIIL CSV. The earlier Cloud acquisition attempt on 14 November
failed at the outbound proxy's CONNECT step with HTTP 403; that historical failure
does not describe the later local execution. See the
[Phase 3 review](../docs/phase-3-review.md) for the separate acquisition and execution records.

## Verified full-dataset results — 15 November 2026

Committed artifacts: [full report](../docs/benchmarks/phiusiil-full-2026-11-15.md),
[JSON metadata and metrics](../docs/benchmarks/phiusiil-full-2026-11-15.json), and
[confusion matrices](../docs/benchmarks/phiusiil-full-2026-11-15.md#confusion-matrices).
These artifacts are the source of the figures below; publication checks compare
their counts and metrics rather than rerunning the raw dataset in Cloud.

| Preprocessing | Records |
|---|---:|
| Original | 235,795 |
| Empty URLs | 0 |
| Invalid URLs | 4 |
| Duplicate rows removed | 897 |
| Conflicting-label rows removed (one group) | 2 |
| Evaluated, unique usable records | 234,892 |
| Evaluated phishing | 100,043 |
| Evaluated legitimate | 134,849 |

This is **full mode**, not the default balanced 1,000-record sample. All cleaned
records were evaluated; the recorded seed of **42** is unused in full mode.

| Protocol | TP | FP | TN | FN | Precision | Recall | F1 | Specificity | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A: `assessment` | 0 | 0 | 134,849 | 100,043 | Undefined* | 0.00% | 0.00% | 100.00% | 0.00% |
| B: `url-screening` | 6,496 | 227 | 134,622 | 93,547 | 96.62% | 6.49% | 12.17% | 99.83% | 0.17% |

*Protocol A has no positive predictions: precision is stored as `0.0` and listed
in `undefined_metrics`. Its zero recall/F1 reflect missing title/description inputs,
and its metrics match the always-legitimate baseline.

Protocol B's **96.62% precision** applies to flags on this dataset; its **6.49%
recall** means **93,547 of 100,043 phishing URLs (93.51%) were unflagged**. All 227
false positives had the many-subdomain-levels indicator. All 93,547 false negatives
had no configured URL indicators. These aggregate patterns do not establish
ownership, intent, safety or the accuracy of the complete investigation workflow.
No rules were tuned on these results.

Recorded execution metadata:

- Clean source commit: [`53e831049800c7563a722482c645ff77f9744e07`](https://github.com/strltP/digital-risk-triage/commit/53e831049800c7563a722482c645ff77f9744e07).
- Windows execution on 15 November 2026; JSON timestamp: `2026-11-15T07:02:39.689872+00:00`.
- Python **3.11.9**, RapidFuzz **3.14.6**, tldextract **5.4.0**.
- CSV SHA-256: `a236549cd369cd80bd478ff8e1779cbf44c58d5c3f79f7a51a1adbed7d06d1c6`.
- Ordered selection SHA-256: `9b83bfaefd3f5fa057bcddd4a0e60aeaf51f15ec5bb3e49460a53e39c1461752`.

The successful run validates adapter use with this locally supplied CSV. Preserve
the report's provenance qualification: its origin is not independently
authenticated by the evaluator. The raw CSV is not committed; its fingerprint
above is taken from the benchmark metadata. Unit tests still use synthetic
reserved-domain fixtures and are separate from these real-data results.

## Run

From the repository root, using the Python environment described in the main README:

```bash
python -m evaluation.evaluate --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv --sample-size 1000 --seed 42 --output evaluation/results/phiusiil-1000
```

The default is exactly **500 phishing + 500 legitimate**, seed **42**, with both
protocols. `--sample-size` supports other positive even totals while retaining equal
class balance. Insufficient examples in either class cause an explicit error;
the command does not shrink or rebalance the requested sample.

Reproduce the published full run with the recorded source commit, versions and CSV
fingerprint, retaining the cleaned dataset's class balance:

```bash
python -m evaluation.evaluate --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv --full --seed 42 --protocol both --output evaluation/results/phiusiil-full
```

`--full` and `--sample-size` are mutually exclusive. `--protocol assessment` or
`--protocol url-screening` runs only one protocol; default `both` keeps their results
separate. `--output` defaults to `evaluation/results/latest`. Reusing an output
directory replaces its three report files. The input CSV cannot be an output file.
All three destinations are checked before any report is replaced: symbolic links,
files with extra hard links and non-regular files are rejected. This preflight does
not make multiple writes atomic against later disk failures or concurrent changes.
Run `python -m evaluation.evaluate --help` for arguments and errors.

## Two protocols

| Protocol | Existing function and inputs | Positive prediction | Interpretation |
|---|---|---|---|
| A: `assessment` | `assess(Intake(source_type="Website", url=URL))`; brand, official_domain, title, description and notes are empty | Category equals `Potential phishing` | Limited-input diagnostic: always negative under the current rules |
| B: `url-screening` | `analyze_url(URL, official="")` | At least one configured URL indicator | A structural URL review flag, not a verified phishing finding |

The URL column, with boundary whitespace trimmed, is the only detector input.
Ground-truth labels are used solely for sampling and scoring. Neither protocol
uses precomputed dataset features. The rules remain unchanged.

**Protocol A always predicts the negative class for every accepted URL under the
current rules.** The only phishing category condition is a credential request or
verification plus urgency in title/description. Both text fields are empty;
URL path/query wording never enters those regexes. No brand reference is supplied
either. The assessment falls back to `Other suspicious content`, even when URL
indicators are present. Its metrics equal the always-legitimate baseline; this is
an input-sufficiency diagnostic, not an effective phishing detector. The CLI name
`assessment` is retained for compatibility, and reports identify its purpose.

Protocol B compares structural review flags against the dataset's phishing labels.
A flagged legitimate record is a false positive **for that binary comparison**;
an unflagged phishing record is a false negative. Neither outcome decides a case's
human verdict, and a flag does not determine the application's review priority.
Brand/domain similarity is not measured without brand context. Priorities and
RapidFuzz similarity are not probabilities; absence of indicators is not safety.

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

There is no training or tuning stage and no train/test split. Labels enter only
stratified sampling, scoring and error aggregation. Global exact-key deduplication
prevents duplicate rows from dominating the sample, but related domains and
near-duplicate URL variants can remain correlated. The result is a descriptive
fixed-dataset experiment, not evidence of performance on independent current traffic.

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
For `url-screening`, predicted negative/positive mean unflagged/flagged; these
column encodings are not findings of legitimate/phishing activity.
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
mapping, always-negative URL-only assessment, label isolation, safe output
destinations, report generation and unchanged SQLite bytes. A fresh
subprocess verifies the CLI imports neither Streamlit nor `core.database`.
Network calls are blocked during isolation tests.

This benchmark does not evaluate counterfeit or trademark detection, the complete
taxonomy, investigator decisions, evidence management or case workflow quality.
Balanced samples change prevalence, so their precision and accuracy do not predict
operational traffic performance. Accuracy alone can conceal zero phishing recall;
undefined precision is a convention rather than a measured predictive value.
It does not estimate confidence intervals, audit
label truth or establish generalization to current traffic. A separate,
independently specified URL-plus-title experiment or multiple/time-separated cohorts
could be future work; no such experiments or rule adjustments are made here.
