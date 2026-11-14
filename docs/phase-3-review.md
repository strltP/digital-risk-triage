# Phase 3 — Evaluation and repository review

Base: `polish/phase-2-ui-ux`, commit
`b22f8fe8c6c9e552c1b9bab319126f3349caba46`, including Phase 1 `84811cf`.
Remote `main` was still `c369511` when this review began. The Phase 2 baseline
was independently executed: **253 passed, 0 failed, 0 skipped**.

## Evaluation audit

| Area | Finding and decision |
|---|---|
| Ground truth | Official UCI convention is `0 = phishing`, `1 = legitimate`. The adapter correctly maps phishing to the positive class; invalid labels abort without echoing cells. |
| Inputs and leakage | Only trimmed original URL text enters the existing detector. Labels control sampling/scoring only. Title, precomputed features and numerical dataset columns are ignored. No training, tuning or test-driven rule changes occur. |
| Preprocessing | Explicit HTTP(S), existing URL validation, counted empty/invalid exclusions. Headers, CSV shape and labels are validated before results are produced. Original CSV compatibility is still unverified because acquisition failed. |
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
availability and suitability could not be verified, and the URL-only limitation
should remain explicit.

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

**No real benchmark ran.** There is no measured cleaned size, dataset fingerprint,
class distribution after exclusions, sampled metric, confusion matrix or real-data
error-pattern analysis to publish. No third-party mirror or synthetic substitute
was used. Original-release header compatibility remains unverified.

After obtaining the original CSV, use a clean Phase 3 checkout and pinned runtime:

```bash
python -m evaluation.evaluate \
  --dataset evaluation/data/PhiUSIIL_Phishing_URL_Dataset.csv \
  --sample-size 1000 --seed 42 --protocol both \
  --output evaluation/results/phiusiil-1000
```

This requests 1,000 unique usable records, 500 per class. It creates `summary.json`,
`report.md` and `confusion_matrix.csv`; all are locally ignored. Inspect preprocessing
and provenance before interpreting scores. The report generator was verified using
synthetic reserved-domain unit fixtures only, without publishing fixture scores as
real-data results.

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
- **Unverified:** real original-CSV compatibility/results, native Windows execution
  and any hosted CI run not yet observed. No overall project accuracy is claimed.
- **Optional later work:** owner-approved licensing/metadata, official-data benchmark
  once available, independent/time-separated cohorts and carefully specified text
  protocols. These do not justify tuning on the requested benchmark sample.
