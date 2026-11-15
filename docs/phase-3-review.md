# Phase 3 — Evaluation and repository review

Base: `polish/phase-2-ui-ux`, commit
`b22f8fe8c6c9e552c1b9bab319126f3349caba46`, including Phase 1 `84811cf`.
Remote `main` was still `c369511` when this review began. The Phase 2 baseline
was independently executed: **253 passed, 0 failed, 0 skipped**.

This document separates the historical 14 November Cloud review from the
successful 15 November Windows benchmark. The latter's committed artifacts, linked
below, supersede the earlier pending-results status; the detection logic is unchanged.

## Evaluation audit

| Area | Finding and decision |
|---|---|
| Ground truth | Official UCI convention is `0 = phishing`, `1 = legitimate`. The adapter correctly maps phishing to the positive class; invalid labels abort without echoing cells. |
| Inputs and leakage | Only trimmed original URL text enters the existing detector. Labels control sampling/scoring only. Title, precomputed features and numerical dataset columns are ignored. No training, tuning or test-driven rule changes occur. |
| Preprocessing | Explicit HTTP(S), existing URL validation, counted empty/invalid exclusions. Headers, CSV shape and labels are validated before results are produced. Cloud acquisition failed on 14 November; the successful 15 November local run subsequently exercised the adapter with the supplied original CSV. |
| Duplicates/conflicts | Global normalized-key deduplication precedes sampling. First unambiguous occurrence retained; all conflicting-label rows removed. Removal counts reconcile without overlap. Path/query/fragment, explicit ports and HTTP/HTTPS distinctions remain; related domains and near duplicates can survive. |
| Sampling | Sorted normalized keys, local seeded RNG, no replacement, exactly half of each class or an explicit error. Full mode keeps cleaned prevalence. No random-state or database side effects. |
| Protocol A | Confirmed always negative with current URL-only inputs. The phishing condition reads title/description; both are empty. URL indicators do not change that category. Retained `assessment` as a limited-input diagnostic, with explicit purpose and always-legitimate baseline interpretation. |
| Protocol B | Any configured passive URL indicator is a review flag. FP/FN compare flags with dataset labels; they do not establish human verdicts or priority. Reports explain the binary matrix encoding. |
| Metrics | TP/FP/TN/FN, accuracy, precision, recall, F1, specificity and FPR agree with hand-calculated tests. Zero denominators yield `0.0` and explicit `undefined_metrics`. Matrix axes are documented. |
| Reproducibility | Input-byte SHA-256, ordered selection hash, seed, classes, exclusions, protocol, Git commit/dirty flag, Python and detector dependency versions are already recorded. Preserve the exact input and a clean committed environment. |
| Error analysis | Separate FP/FN counts and overlapping indicator counts; examples are normalized-URL hashes and one-based CSV record indices. No live dataset URLs, titles, credentials or hosts are published. |
| Output safety | Confirmed a late symlink error could occur after an earlier report had been overwritten. Added a preflight of all three paths, rejecting symlinks, extra hard links and non-regular files before any replacement. This is not a transactional multi-file writer or protection against concurrent filesystem changes. |
| Independence | Existing tests block network and SQLite calls and check a fresh CLI subprocess imports neither Streamlit nor `core.database`. No investigator data or sample fixtures enter the benchmark. |

The adapter, metric formulas, sampling and detector rules required no changes.
Report schema `1.1` adds a protocol `purpose` field while retaining protocol names,
metric keys and CLI options. No URL-plus-title extension was added: raw Title
availability and suitability were not verified during the Cloud review; the later
benchmark also ignores Title and retains the URL-only limitation.

## Official acquisition attempt — 14 November 2026

The [official UCI page](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset)
was readable through the web reader. It lists 235,795 instances, 134,850 legitimate
and 100,945 phishing URLs, the original `PhiUSIIL_Phishing_URL_Dataset.csv` (54.2 MB),
label direction and **CC BY 4.0** attribution to Arvind Prasad and Shalini Chandra
(2024). These are published metadata, not counts measured from a downloaded CSV.

Workspace command:

```bash
curl --location --max-time 45 --output phiusiil.zip \
  'https://archive.ics.uci.edu/static/public/967/phiusiil+phishing+url+dataset.zip'
```

Actual result: **exit 56, `CONNECT tunnel failed, response 403`**, reported transfer
HTTP code `000`, **0 dataset bytes**. The proxy returned `HTTP/1.1 403 Forbidden`
before a UCI response could be obtained. The official metadata API request to
`https://archive.ics.uci.edu/api/dataset?id=967` failed identically. The separate web
reader reached the official ZIP link but rejected its response above its 4 MiB
limit; it did not provide a CSV to the workspace.

**No real benchmark ran during that 14 November Cloud attempt.** At that point,
cleaned counts, input fingerprint, original-CSV compatibility and metrics were
unavailable. No third-party mirror or synthetic substitute was used. This is a
historical acquisition record, not the current benchmark status.

The initial proposed follow-up was a balanced sample from a clean Phase 3 checkout:

```bash
python -m evaluation.evaluate \
  --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv \
  --sample-size 1000 --seed 42 --protocol both \
  --output evaluation/results/phiusiil-1000
```

That command requests 1,000 unique usable records, 500 per class. The later local
experiment instead used **full mode**, as recorded below. At the Cloud-review stage,
report generation was checked using synthetic reserved-domain unit fixtures only;
their scores were never presented as real-data results.

## Successful local full benchmark — 15 November 2026

The owner subsequently executed both unchanged protocols on Windows with the
original locally supplied PhiUSIIL CSV. The committed
[report](benchmarks/phiusiil-full-2026-11-15.md),
[JSON](benchmarks/phiusiil-full-2026-11-15.json) and
[confusion matrices](benchmarks/phiusiil-full-2026-11-15.md#confusion-matrices)
are the authoritative results. The Markdown matches the unchanged report renderer's
output for that JSON, and preprocessing totals and metric formulas reconcile.

At documentation review, the branch contained the Markdown and JSON artifacts;
the separately named `phiusiil-full-confusion-matrix.csv` was not committed.
Documentation therefore links to the existing Markdown matrix section and JSON
without creating or changing benchmark result files.

- Original records: **235,795**; excluded **4** invalid URLs, **897** duplicate rows,
  and **2** conflicting-label rows in one group; no empty URLs.
- Evaluated: **234,892**, including **100,043 phishing** and **134,849 legitimate**.
- Full mode retains every cleaned record and the resulting class distribution.
  The metadata records seed **42**, which full mode does not use.
- Source: clean commit [`53e831049800c7563a722482c645ff77f9744e07`](https://github.com/strltP/digital-risk-triage/commit/53e831049800c7563a722482c645ff77f9744e07).
- Python **3.11.9**, RapidFuzz **3.14.6**, tldextract **5.4.0**.
- Recorded evaluation timestamp: `2026-11-15T07:02:39.689872+00:00`.
- CSV SHA-256: `a236549cd369cd80bd478ff8e1779cbf44c58d5c3f79f7a51a1adbed7d06d1c6`.
- Ordered selection SHA-256: `9b83bfaefd3f5fa057bcddd4a0e60aeaf51f15ec5bb3e49460a53e39c1461752`.

Attribution remains **Arvind Prasad and Shalini Chandra (2024), UCI Machine Learning
Repository**, **CC BY 4.0**, with `0 = phishing`, `1 = legitimate`. The evaluator's
provenance note remains: the CSV is locally supplied and its origin is not
independently authenticated. Publication validates the committed artifacts; it
does not claim a new Cloud download, raw-file hash verification or benchmark rerun.

| Protocol | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: `assessment` | 0 | 0 | 134,849 | 100,043 | Undefined* | 0.00% | 0.00% | 0.00% |
| B: `url-screening` | 6,496 | 227 | 134,622 | 93,547 | 96.62% | 6.49% | 12.17% | 0.17% |

*Protocol A stores undefined precision as `0.0` with an explicit metadata entry.
With no text inputs, it always predicts negative and equals the always-legitimate
baseline. Protocol B has high precision on this dataset, but misses **93,547 of
100,043 phishing URLs (93.51%)**. Every recorded false negative had no configured
URL indicator; all **227** false positives had the many-subdomain-levels indicator.
These are aggregate observations, not grounds to tune rules on this benchmark.

Neither protocol measures overall investigation-application accuracy, human review,
evidence authenticity, counterfeit/trademark detection or platform-wide brand
impersonation performance. Full mode avoids balanced resampling, but this fixed
dataset's prevalence and correlated URLs still limit operational interpretation.
High precision does not compensate for the very low recall or establish safety
for unflagged URLs. No rule, UI, database or evaluation-logic change accompanies
publication, and the existing result artifacts are preserved.

To reproduce the local full run with the recorded input and source versions:

```bash
python -m evaluation.evaluate \
  --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv \
  --full --seed 42 --protocol both \
  --output evaluation/results/phiusiil-full
```

Generated runtime outputs remain ignored; curated aggregate artifacts are committed
under `docs/benchmarks/`. The raw CSV and full phishing URLs are not published.

## Quality and compatibility

Ruff **0.11.13** is pinned in `requirements-dev.txt`, separately from runtime
requirements. `pyproject.toml` uses its small default baseline: **E4, E7, E9, F**,
targeting Python 3.11 and excluding generated/local data. Existing application code
already passes this baseline; no style-only rewrites or rule suppressions were needed.
The existing GitHub Actions workflow installs pinned development requirements,
runs Ruff, then Pytest, with `contents: read` permissions. It requires no external
dataset and does not visit dataset URLs.

Fourteen evaluation regressions cover URL-only negative predictions, diagnostic
interpretation, symlink preflight and hard-link/directory destinations. The full
suite also retains all Phase 1/2 loading, persistence, timestamp, navigation,
review, evidence and export tests. Actual local final results are recorded in the
main README; hosted CI results must be checked on GitHub after pushing.

Application source, core logic, sample JSON, theme and Phase 2 screenshots are
unchanged. No database migration, fixture correction, evidence rewrite or rule
tuning was performed. Phase 2's Chromium checks remain historical verification;
Phase 3 adds regression/static checks rather than another UI redesign.

## Repository metadata and licensing

GitHub metadata inspection found an empty description, no topics and no declared
license. The available connector can read repository metadata but has no metadata
mutation tool; the shell GitHub API request returned HTTP 403. These settings were
not changed. Recommended values for the owner to apply:

- **Description:** Local-first digital risk investigation and case triage tool with explainable rule-based assessment, evidence tracking, and offline evaluation.
- **Topics:** `digital-risk`, `brand-protection`, `phishing-analysis`, `streamlit`, `python`, `sqlite`, `cybersecurity`, `rule-based-system`.

No `LICENSE` file exists and none was added. Public visibility does not itself
grant an open-source reuse license. **MIT** is a simple option if the owner wants
an open-source portfolio; the final choice and authorization belong to the owner.
The external dataset's CC BY 4.0 license is separate from the application's license.

## Remaining boundaries

- **MVP design:** one local investigator, static explainable rules, manual evidence,
  no authentication or immutable audit history; hashes support integrity comparison,
  not authenticity. Human investigation and rights/ownership context remain necessary.
- **Unverified:** Windows application UI execution, independent authentication of
  the supplied CSV's origin and generalization to current traffic. The Windows
  offline benchmark is complete; no overall project accuracy is claimed.
- **Optional later work:** owner-approved licensing/metadata,
  independent/time-separated cohorts and carefully specified text
  protocols. These do not justify tuning on the requested benchmark sample.
