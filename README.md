# Digital Risk Investigation & Case Triage System

A local-first Python portfolio MVP for an entry-level Digital Risk Investigator.
It follows an investigation from intake and preliminary analysis to manual review,
evidence attachment, case tracking, and structured reporting. All verdicts remain
human decisions. The rule engine does **not** prove fraud or calculate probabilities.

## Project Overview

This project demonstrates the daily workflow of an entry-level Digital Risk
Investigator: organize incoming observations, prioritize review, document evidence,
exercise judgment, and communicate findings.

| Investigator responsibility | How the project demonstrates it |
| --- | --- |
| Threat intake | Structured website, social-media, marketplace, and general phishing/abuse observations, with source URLs and UTC timestamps. |
| Initial risk assessment | Passive URL inspection and explainable rules suggest a category and review priority without visiting suspicious sites. |
| Evidence collection and organization | Manually uploaded screenshots retain their source, observation time, and SHA-256 hash alongside the case. |
| Human investigation and escalation | Analyst notes, manual verdicts, false-positive examples, and validation before escalation show decisions beyond keyword matches. |
| Case tracking | A filterable queue opens the selected case directly for review; SQLite preserves the investigation across restarts. |
| Reporting | Dashboard counts and structured CSV/Excel exports communicate findings, decisions, and evidence references. |

### Application screenshots

Actual Streamlit captures from a local Chromium browser session, using isolated,
fictional training data and reserved `.example` domains:

![Filtered case queue with a direct Open selected case action](docs/screenshots/case-queue.png)

![Investigator review of a simulated false-positive case](docs/screenshots/case-review.png)

Also view [brandless intake and preliminary analysis](docs/screenshots/new-investigation.png)
and the [dashboard and reports](docs/screenshots/dashboard-reports.png).

## Quick start on Windows

Install **Python 3.11 or newer**, open PowerShell or Command Prompt, and run from
the project directory:

```powershell
cd digital-risk-triage
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

If your terminal is already in `digital-risk-triage`, omit the first command.
The version command must report Python 3.11+. Using the virtual environment's
Python directly avoids PowerShell activation-policy changes. Stop with `Ctrl+C`.
Open the local address printed by Streamlit in your browser. On subsequent runs,
only the final command is needed. If port 8501 is occupied, append
`--server.port 8502`.

Run the tests on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Linux / macOS

```bash
cd digital-risk-triage
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
# In another terminal, or after stopping the app:
.venv/bin/python -m pytest -q
```

Package installation needs Internet access to PyPI. After installation the
investigation workflow needs no API keys, cloud services, DNS, WHOIS, or Internet
connection. The application never visits submitted URLs. Streamlit usage telemetry
is disabled in `.streamlit/config.toml`.

## Investigator workflow

1. **New Investigation**: choose the source and provide a URL or meaningful
   title/description (at least 10 letters/digits). Protected brand and official
   domain are optional for general phishing or online abuse. Supply both to enable
   brand-domain comparison; brand-specific text checks require the named brand
   in the page title/description. Select **Analyze observation** to see indicators, a suggested
   threat category, review priority, plain-English reasoning, and URL parsing.
   Select **Save as new case** to persist the analyzed submission. Observation,
   creation, and update timestamps are recorded in UTC. If you edit the form,
   analyze it again; saving uses the explicitly displayed last analysis.
2. **Case Queue**: filter by status, priority, category, or source. Choose a case in
   **Case to review** and click **Open selected case** to go directly to its review.
   **Back to Case Queue** restores the filters. You can also open **Case Review &
   Evidence** from the sidebar and use its independent case picker as before.
3. **Case Review & Evidence**: inspect the original observation and stored analysis.
   Enter investigator notes and a manual verdict. Save **Reviewing** while checking
   context. **Validated** requires **Confirmed violation** and supporting notes.
   Save that state before saving **Escalated**; a direct escalation is rejected.
   **False Positive** requires **No violation found** and supporting notes.
   Reopening a validated case as New/Reviewing/False Positive clears its validation;
   it must be validated again before escalation. Saving a review never silently
   changes the original rule assessment.
4. Attach a **manually collected** PNG/JPG screenshot to that existing case. Provide
   its source URL (if known), actual observation time including a timezone, and an
   optional description. The default source is the case URL; the default time is
   the case observation time, so replace it when the screenshot was observed at a
   different time. Dates in the future or
   without a timezone are rejected. Images display in the case details. No screenshot
   is automatically captured or generated by the application.
5. **Dashboard & Reports**: see totals, awaiting-review cases (New + Reviewing),
   validated cases (Validated + Escalated), false positives, and category counts.
   Filter cases and download CSV or Excel. Totals include labeled demo cases.

### Five-minute simulated demo

Click **Load 12 simulated demo cases** in the sidebar. Repeated clicks add no
duplicates and preserve investigator edits. All scenarios use fictional brands
and reserved `.example` domains and are labeled **SIMULATED**. There are no seeded
screenshots or automatically confirmed violations.

- Inspect the account-alert case: credential requests and a short deadline produce
  a High preliminary phishing priority.
- Inspect a lookalike store, a marketplace replica listing, and a copied-logo case
  to see the other suggested categories.
- Review the three False Positive examples: an ordinary official login, a
  counterfeit-awareness guide, and an authorized outlet. Their fictional review
  notes explain why initial indicators were insufficient.
- For practice, add a note explicitly saying this is a simulated training decision,
  manually validate one fictional case, then escalate it. Upload your own test
  screenshot labeled as simulated and inspect the source/time/hash metadata.
- Export reports and check the case ID, review decision, and evidence references.
- Stop and restart Streamlit; the stored cases and attached images remain available.

For a fresh analysis example, use brand `Astervale`, official domain
`astervale.example`, URL `https://astervale-security.example/login`, and description
`Verify your account. Enter your password within 2 hours.` These are fictional
strings for passive inspection; do not browse to them.

## Architecture

```text
app.py                    Four native Streamlit sections and local upload/display
core/models.py            Input validation, enums, UTC timestamps, disclaimer
core/url_analysis.py      Offline URL parsing and domain-name comparison
core/risk_rules.py        Transparent category and priority rules
core/database.py          SQLite case/evidence metadata and review transitions
core/evidence.py          Image validation, safe file storage, SHA-256 metadata
core/reporting.py         CSV and Excel generation; formula neutralization
core/demo.py              Twelve idempotent, fictional scenarios
tests/                    Core tests and Streamlit widget workflow test
.streamlit/config.toml    Dark native theme, upload cap, telemetry disabled
data/                     Generated local database and evidence (Git-ignored)
requirements.txt          Tested direct dependency versions
.github/workflows/tests.yml Pytest on pushes and pull requests (Python 3.12)
docs/screenshots/          Actual browser captures using fictional training data
```

The UI calls the same validation/rule functions used by the tests. SQLite stores
input details, raw source URL, normalized URL/domain analysis, indicators,
explanation, preliminary category/priority, notes, status, manual verdict, UTC
timestamps, and demo markers. Evidence rows reference an existing case via a
foreign key. Case IDs and evidence filenames use generated UUIDs. Parameterized
queries prevent user text from becoming SQL. No models are trained or invoked.

### Analysis policy

- URLs accept HTTP(S), default to HTTPS when no scheme is supplied, and normalize
  host casing and IDNs. IP hosts, punycode, deep subdomains, userinfo before `@`,
  embedded destination URLs, and URLs over 200 characters trigger structural notes.
  Invalid schemes, hosts, whitespace, and ports produce validation messages.
- `tldextract` uses its bundled Public Suffix List with fetching and caching disabled.
  For unrecognized suffixes (including `.example`), the displayed registered domain
  uses a best-effort last-two-label fallback. This is not a trust decision.
- With a protected brand name and an **explicitly configured** official domain,
  RapidFuzz compares the registrable name labels. With either field missing,
  brand comparison is skipped; a supplied official domain is still validated.
  Suffix similarity is excluded. An 80/100 similarity with both
  names at least four characters long can flag an outside domain for review.
  An official-domain string embedded in an unrelated hostname is also flagged.
  Boundary-aware official-host matching accepts its subdomains, not substring tricks.
- Page title/description rules always check for credential requests,
  verification/suspension language, and payment urgency. Affiliation, replica,
  and logo/trademark checks only run when a supplied brand name appears in that
  content. Blank brand names never match arbitrary text. Investigator notes are
  excluded from content analysis. Generic marketing and HTTPS alone do not raise priority.
- High priority requires combined credential and verification/urgency signals on
  a host that does not match the configured official domain. Medium identifies
  specific remaining signals/combinations; otherwise priority is Low. These are
  triage rules, not confidence percentages. A match to the configured official host
  is contextual information and does not prove safety.

### Evidence, reports, and local data

Screenshots are capped at **5 MiB**, **20 megapixels**, and one still frame. Pillow
checks actual PNG/JPEG content, extension agreement, image integrity, and decoding
before storage. Browser-supplied MIME labels are not trusted. Files retain original
bytes, use generated filenames under `data/evidence/`, and have SHA-256, original
name, size, source URL, observed time, uploaded time, and description in SQLite.
Failed metadata writes clean up the newly written file. Missing local files produce
a visible warning rather than fabricated evidence. An image hash supports integrity
comparison; it does not establish authenticity or chain of custody.

CSV includes case IDs, source URLs, timestamps, category/priority, indicators,
explanation, domain analysis, notes, status/verdict, and evidence IDs/paths/hashes/
source times. Excel includes the same Cases sheet plus a detailed Evidence sheet.
Reports contain **references**, not embedded images. Spreadsheet formula prefixes
(`=`, `+`, `-`, `@`, including leading whitespace/control variants) are neutralized
with an apostrophe. Unsupported XML controls are removed from exported strings.
Excel cells over 32,767 characters are rejected with a message to use CSV, rather
than silently truncating the report.

The default database is `data/cases.sqlite3`. The optional non-secret environment
variable `DRT_DATA_DIR` selects a different local storage directory; this was used
to isolate smoke tests from the normal empty application database. No other
configuration or credentials are required. Tests use `data/test-tmp/` and may replace
their own temporary test data on each run; do not store investigations there.
Stop the app and back up the database **and** `data/evidence/` together. Exports do
not replace a full backup. No user files are automatically removed by the app.

## Validation and implementation status

Implemented: intake, passive domain analysis, explainable preliminary triage,
persistent cases, human review and escalation gating, local screenshot uploads,
dashboard counts, safe CSV/XLSX exports, and 12 idempotent simulated demos.

Actual verification on Linux with Python 3.12:

- Baseline review: all **55 existing tests passed** before changes.
- `python -m pytest -q`: **67 passed** after improvements, covering URL parsing/offline operation,
  conservative risk rules, persistence/filtering/review transitions, evidence
  validation/cleanup, formula-safe report round trips, demo idempotence, and a
  Streamlit widget workflow including a new session reading existing records.
  Added checks cover optional-brand phishing/abuse intake, conditional brand rules,
  persistence and CSV/Excel exports with a blank brand, opening a selected queue
  case, retaining the selected case during review, and restoring queue filters.
- `python -m pip check`: no broken requirements.
- Streamlit server startup and a local HTTP health check succeeded.
- Headless Chromium exercised real forms: intake → analysis → save → rejected
  premature escalation → validation → escalation → PNG upload/display → CSV/Excel
  downloads → repeat demo loading → dashboard. No browser page errors or external
  HTTP requests occurred. Download contents were checked against the stored evidence.
  A separate JPEG upload retained an explicitly backdated UTC observation, and its
  stored bytes, MIME type and SHA-256 matched. Failed evidence submissions retain
  the investigator's entered timestamp; successful uploads reset the form.
- Stopping/restarting the server preserved cases, review state, and evidence.
- This improvement pass also exercised the running UI in Chromium: brandless
  analysis/save, a filtered queue opening a different case from the latest saved
  one, review of a simulated false positive, return navigation with retained
  filters, brandless case details, and CSV/Excel downloads. The four screenshots
  above were captured during that run. No page errors or external HTTP requests
  occurred during it.
- `.github/workflows/tests.yml` installs the existing requirements and runs
  `python -m pytest -q` on pushes and pull requests. The same test command passed
  locally; the GitHub-hosted workflow has not been executed as part of this change.

The commands above use platform-specific virtual-environment paths. The application
and commands were exercised on Linux; a Windows host was **not** available for a
native Windows run. Earlier browser/evidence/restart checks are recorded above;
this improvement pass did not repeat the evidence-upload or server-restart scenario.
This change was not pushed or deployed. No live suspicious-URL requests were made.

## Known limitations

- This is a two-day portfolio MVP for one local investigator, not a production
  security service. It has no authentication, encryption at rest, immutable review
  history, automatic backup, role permissions, or multi-user conflict handling.
  Bind it to loopback and protect the local data and exported reports.
- Text rules do not understand context, negation, permission, quoted warnings, or
  intent, and can miss unseen wording or flag benign content. Categories and
  priorities are suggestions. Human review and independent evidence are required.
- Domain similarity is character-based, not complete Unicode visual-confusable
  detection. The bundled suffix list ages with the dependency. No live DNS,
  reputation, WHOIS, availability, registration, or ownership claims are made.
- Human-entered notes and verdicts are not independently verified. Case contents
  are preserved as an intake snapshot; only review notes/status/verdict are editable.
- Evidence must be collected manually. There is no automated scraping, screenshot
  capture, OCR, authenticity verification, signed chain of custody, or enforcement.
- There are no migrations for arbitrary older schemas, deletions, or external
  integrations. A browser refresh loses an **unsaved** analysis, while saved cases
  persist. Very large local collections may need a paginated queue in a later version.
