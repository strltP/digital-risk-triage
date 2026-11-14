# Phase 1 — Core quality and sample data audit

Baseline: `c369511` from `main`. All 100 records were examined systematically:
title/description and source fit, fictional brand/domain pair, review status and
verdict, stated rationale, provenance, and actual rule outputs. All source domains
remain reserved `.example` addresses; the four fictional brands are unchanged.
Marketplace educational guides are intentional examples of context-sensitive
false positives, rather than product sales. No real website was visited.

## Findings and targeted corrections

The 100 stable keys, titles, descriptions, URLs, source types, brands, official
domains, statuses and verdicts are preserved. Nine review notes were clarified;
the other 91 notes were retained.

| Stable key | Correction and reason |
|---|---|
| `demo-v2-authorized-official-store` | Explain the reported impersonation concern and the exercise's authorized-store context. An official host or Low priority alone does not clear every possible allegation. |
| `demo-v2-official-size-guide` | Explain why a routine sizing guide was reported and why the fictional authorized-page context clears that specific copying concern. |
| `demo-v2-order-card` | State the fictional marketplace policy supporting the finding; outside-checkout wording alone does not prove theft. |
| `demo-v2-staff-sso` | Distinguish the stipulated unaffiliated collector from an approved identity provider before validation/escalation. |
| `demo-v2-qr-login` | Identify the exercise's unauthorized password recipient; the QR format itself is not proof. |
| `demo-v2-shared-project` | Supply the fictional collector/authorization context; an outside document-sharing host alone is insufficient. |
| `demo-v2-profile-copyright` | Distinguish the stipulated password-collection pretext from a normal appeal sign-in flow. |
| `demo-v2-velora-reseller` | Make lack of authority an explicit exercise premise; a missing agreement alone is not proof of unauthorized affiliation. |
| `demo-v2-copy-watch` | Avoid overstating “indistinguishable from authentic stock” as an explicit genuine-origin claim; scope the fictional finding to the stipulated unauthorized branded copy. |

The other 11 False Positive rationales already describe a reported keyword,
educational, authentication or affiliation concern and its fictional resolution.
The remaining confirmed outcomes explicitly stipulate unauthorized conduct,
permission context, intent or an exercise-policy violation. Reviewing cases retain
open questions and an Inconclusive verdict; New cases retain Pending review.
These notes are exercise premises, not collected evidence or independent ground
truth. No screenshots, ownership checks, contacts or authenticity tests are supplied.

Every record also receives an explicit **fictional** `observed_at` fixture value:
100 fixed 12-hour slots from **2025-01-06 08:00 UTC** to **2025-02-24 20:00 UTC**,
in the existing JSON order. The values are stored in JSON and are never regenerated
at import time. This changes timestamp metadata on all 100 fixture records; nine
of those also have the note corrections above. It does not create historical
review events. `created_at`, `updated_at` and `validated_at` reflect actual local
database operations during import/review.

| Distribution | Unchanged counts |
|---|---|
| Preliminary categories | Phishing 25; brand impersonation 25; counterfeit 20; trademark 15; other 15 |
| Priorities | High 16; Medium 69; Low 15 |
| Review statuses | New 41; Reviewing 25; Validated 12; False Positive 13; Escalated 9 |
| Manual verdicts | Pending review 41; Inconclusive 25; Confirmed violation 21; No violation found 13 |

Assessment inputs and per-key category/priority outputs were compared with the
baseline before updating the fixture checksum. Notes do not enter the rules.
No regex, threshold, category precedence or priority condition was changed.

## Domain and persistence decisions

- `Database.create_case(..., observed_at=...)` accepts a timezone-aware ISO 8601
  value, rejects invalid/future values and stores UTC. Omission retains the current
  UTC default. JSON `observed_at` is optional for old datasets; existing SQLite
  columns suffice, so no migration or backfill is performed.
- The existing taxonomy is retained. `Other suspicious content` is the fallback
  category, including observations without configured risk signals. Low does not
  mean legitimate; High does not mean a confirmed violation. False Positive may
  close a cleared report even when no machine detection occurred.
- New requires Pending review. Reviewing can carry Pending review, Inconclusive,
  or a provisional No violation found with notes. Confirmed violation still requires
  Validated/Escalated plus notes; escalation requires prior validation. Reopening
  clears validation. Older stored rows remain readable and are not rewritten.
- Sample loading validates every input before acquiring a write transaction. All
  missing inserts and public review updates then share one transaction, including
  validation before escalation. A runtime exception rolls back that import's new
  rows/reviews. The writer lock is acquired before checking stable keys, so a retry
  or another importer cannot overwrite a review through a stale key snapshot.
- Existing keys are skipped wholesale. Original observation/creation/update times,
  case IDs, reviews and evidence references are preserved, including on the
  original 12-case upgrade. Existing sample rows deliberately keep their previous
  notes and timestamps; the corrected fixture is not a data migration.

## Deferred scope

Phase 2: manual observation-time controls, sample/manual filtering, search/sort,
readable timestamps/IDs, review presentation and screenshot refreshes.

Phase 3: real external benchmarking, evaluation methodology review, development
tooling, licensing and broader repository presentation. No Evaluation source or
documentation was changed as part of Phase 1.
