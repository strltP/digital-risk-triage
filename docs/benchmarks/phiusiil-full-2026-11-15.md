# Digital Risk Triage — Offline Evaluation

## Executive summary

Evaluated **234,892** local CSV records: 100,043 phishing and 134,849 legitimate. Results for the limited-input diagnostic and URL screening are reported separately.
No detection thresholds were tuned and no model was trained.

## Dataset and provenance

Dataset reference: [PhiUSIIL Phishing URL (Website)](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset).
Attribution: Arvind Prasad and Shalini Chandra (2024), UCI Machine Learning Repository; license: CC BY 4.0.
Official labels: **0 = phishing, 1 = legitimate**; phishing is the positive class in this report.
Locally supplied CSV; its origin is not independently authenticated.
Input file SHA-256: `a236549cd369cd80bd478ff8e1779cbf44c58d5c3f79f7a51a1adbed7d06d1c6`.
Evaluation time (UTC): 2026-11-15T07:02:39.689872+00:00.
Source code: `53e831049800c7563a722482c645ff77f9744e07`; working tree dirty: `False`.
Python: 3.11.9; dependencies: `{'RapidFuzz': '3.14.6', 'tldextract': '5.4.0'}`.

## Methodology and actual inputs

Only the original `URL` string, trimmed at its boundaries, enters the detector. `source_type` is `Website`; brand, official_domain, title and description are empty. `Title` and all numerical features are ignored. Ground-truth labels control stratification and scoring only.
Protocol A (`assessment`) is a limited-input diagnostic calling `assess()`; a positive prediction requires category `Potential phishing`. With empty title/description and no brand, the current rules always predict negative, matching the always-legitimate baseline. Protocol B calls `analyze_url()` with no official domain; any configured URL indicator flags a URL for review. The protocols are never combined into a headline score.

## Preprocessing and sampling

CSV labels must be exactly 0/1 after trimming; invalid labels or malformed CSV abort the run. Empty URLs and URLs that lack an explicit HTTP(S) scheme or fail the existing URL validation are dropped.
Duplicate identity uses the existing `normalize_url()` policy: trim outer whitespace, lowercase the scheme/host, IDNA-normalize hosts, strip a trailing hostname dot and supply `/` for an empty path. Paths, queries, fragments, userinfo and explicit ports are retained; HTTP and HTTPS remain distinct. The first occurrence is retained for an unambiguous key. All rows of a label-conflicting key are excluded.

| Count | Records |
|---|---:|
| original_rows | 235,795 |
| valid_rows | 235,791 |
| empty_urls | 0 |
| invalid_urls | 4 |
| invalid_rows | 4 |
| removed_duplicate_rows | 897 |
| conflicting_url_groups | 1 |
| conflicting_rows | 2 |
| cleaned_rows | 234,892 |

`valid_rows` is before deduplication. Ordinary duplicate removals exclude conflicting groups, so removals are not double-counted. CSV record counts exclude blank lines and the header.
Cleaned classes: `{'phishing': 100043, 'legitimate': 134849}`.
Requested sample size: `None`; seed: `42`; full dataset: `True`.
Balanced samples use equal counts per class with a local seeded RNG; full mode retains the cleaned class balance and does not use the seed.
Selected-record SHA-256: `9b83bfaefd3f5fa057bcddd4a0e60aeaf51f15ec5bb3e49460a53e39c1461752`.

## Protocol results

| Evaluation | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 | Specificity | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| assessment | 0 | 0 | 134849 | 100043 | 0.574089 | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 0.000000 |
| url-screening | 6496 | 227 | 134622 | 93547 | 0.600778 | 0.966235 | 0.064932 | 0.121687 | 0.998317 | 0.001683 |

### Trivial reference baselines

Constant predictions are context only, not competing production systems.

| Evaluation | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 | Specificity | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| always-legitimate | 0 | 0 | 134849 | 100043 | 0.574089 | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 0.000000 |
| always-phishing | 100043 | 134849 | 0 | 0 | 0.425911 | 0.425911 | 1.000000 | 0.597388 | 0.000000 | 1.000000 |

## Confusion matrices

Rows are actual dataset labels; columns use the binary target encoding. Order: legitimate, phishing. For URL screening, the predicted columns mean no structural flag / flagged for review, not a finding of legitimacy or phishing.

### assessment

| Actual / Predicted | Legitimate | Phishing |
|---|---:|---:|
| Legitimate | 134849 | 0 |
| Phishing | 100043 | 0 |

Undefined ratios (reported as 0.0): precision.

### url-screening

| Actual / Predicted | Legitimate | Phishing |
|---|---:|---:|
| Legitimate | 134622 | 227 |
| Phishing | 93547 | 6496 |

Undefined ratios (reported as 0.0): none.

## Interpretation

URL-only assessment has no credential-request text, verification wording or brand context. The current rules always predict negative under those constraints; they do not establish that the URLs are safe. Screening flags structural URL properties, which may also occur on legitimate sites. Compare each protocol separately with the trivial baselines.

## False-positive and false-negative analysis

Indicator counts below can overlap when an error has several indicators. Examples are SHA-256 identifiers plus original CSV record indices, never live URLs or page content.

### assessment: false positives

Errors: 0; without URL indicators: 0.


### assessment: false negatives

Errors: 100043; without URL indicators: 93547.

- Host is an IP address rather than a domain name. — 604
- Hostname has unusually many subdomain levels. — 4925
- Hostname uses punycode/Unicode; visually inspect for lookalike characters. — 150
- URL contains login information before @, which can obscure the actual host. — 10
- URL embeds another URL in its path or query; inspect the destination manually. — 684
- URL is unusually long (over 200 characters). — 1423
- CSV record 130057; URL SHA-256 `a127bba6ffc0a5c837d384184161c32465a0326b1a4984554b5a4d6a3e2d23d1`; 0 indicators.
- CSV record 197455; URL SHA-256 `420be82a2f099d69b647f8d62b8b297eb03ef6fa2c5b3aa55b61eadda414809f`; 0 indicators.
- CSV record 118152; URL SHA-256 `85e78dec3ea8fe21f7ddd54f9f88dc45de037875d4de5d1b8f9c187d8aaaabe3`; 0 indicators.
- CSV record 64189; URL SHA-256 `8e8b034b4459c38358505cd9cc60b8cd0328c66da161018ac6e2cb8c622353b1`; 0 indicators.
- CSV record 194537; URL SHA-256 `318a6349e0ccca2b07819a11f788685593c0d075f5270f9d1659b40738da67bd`; 0 indicators.

### url-screening: false positives

Errors: 227; without URL indicators: 0.

- Hostname has unusually many subdomain levels. — 227
- CSV record 192207; URL SHA-256 `22cadfc288c1e960fb63b2d7d116ff13c29974e6d962aed73e85b8555bbabd7b`; 1 indicators.
- CSV record 89198; URL SHA-256 `5cd57e452e329620dba4b6fdeaaafe1a37c69b03b4e2a6e66bb315659e045cd4`; 1 indicators.
- CSV record 157702; URL SHA-256 `9e1544e7d71c8e2f12d286e3f6672c7847922904ddc7caadb5c4a11043749604`; 1 indicators.
- CSV record 21221; URL SHA-256 `184862c5ce9cb1cc33a4c03c0e324ab42e61cdf972961d308a2cfd626de76778`; 1 indicators.
- CSV record 60457; URL SHA-256 `cb85cfeec752e48e6d72741b090c5b9ed9d26ee23825b64d34ce7428851c71ac`; 1 indicators.

### url-screening: false negatives

Errors: 93547; without URL indicators: 93547.

- CSV record 130057; URL SHA-256 `a127bba6ffc0a5c837d384184161c32465a0326b1a4984554b5a4d6a3e2d23d1`; 0 indicators.
- CSV record 197455; URL SHA-256 `420be82a2f099d69b647f8d62b8b297eb03ef6fa2c5b3aa55b61eadda414809f`; 0 indicators.
- CSV record 118152; URL SHA-256 `85e78dec3ea8fe21f7ddd54f9f88dc45de037875d4de5d1b8f9c187d8aaaabe3`; 0 indicators.
- CSV record 64189; URL SHA-256 `8e8b034b4459c38358505cd9cc60b8cd0328c66da161018ac6e2cb8c622353b1`; 0 indicators.
- CSV record 194537; URL SHA-256 `318a6349e0ccca2b07819a11f788685593c0d075f5270f9d1659b40738da67bd`; 0 indicators.

## Limitations and potential improvements

- Protocol A is a limited-input diagnostic: with empty title/description and no brand context, the current rules always predict negative.
- Protocol B measures passive URL screening; a review flag is not a verified phishing classification.
- No title, description, official brand domain, label-derived content or numerical dataset feature enters either detector.
- Brand context is absent, so domain similarity checks are unavailable. RapidFuzz similarity is not phishing probability.
- High, Medium and Low are review priorities, not probabilities. URL indicators do not prove phishing or safety.
- Undefined metric ratios are reported as 0.0 and named explicitly in undefined_metrics.
- Dataset labels do not evaluate counterfeit, trademark misuse, human review, evidence handling or the full investigation workflow.
- Balanced sampling changes class prevalence; these precision and accuracy values need not represent operational traffic.
- Accuracy alone is insufficient. There is no training split; related domains and near-duplicate URLs can remain after exact-key deduplication.
- These are descriptive results on a fixed labeled dataset, not deployment guarantees or a model-training experiment.

Future work could evaluate independently supplied page titles in a separately named experiment, audit label quality and measure variation across independently sampled or time-separated cohorts. These possibilities are not implemented here and do not justify changing rules based on this benchmark.
