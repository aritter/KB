# Administrative tracking: primary practical demo

This local CLI tracks what was requested, what a message claims, and whether documentary evidence matches the requested outcome. It sends no email, contacts no administrators, and changes no external records. All examples are fictional, including the office, account names, template, and dates.

## Fast deterministic demonstration

From this repository:

```bash
python3 -m unittest discover -s tests -v
python3 -m examples.admin_demo --backend counting_mock --db admin-demo.sqlite3
```

Choose a new database filename for each demo. This uses reviewed extraction fixtures and explicitly labeled mock decision outputs. It exercises real SQLite persistence and SWI-Prolog rules, not real language-model accuracy. The existing `knowledge.sqlite3` is untouched.

The demo records this complete sequence in `evaluation/admin-demo.json`:

1. The original request asks for Alex Example's appointment from **2026-11-01 through 2026-12-31**, using **FUND-A**. Submission is October 12; October 20 follow-up and October 25 intervention are explicit **user preferences**. No final deadline is invented from the appointment start date.
2. “Received, we’ll take care of it.” establishes independent acknowledgment and promise assessments. It does not verify completion.
3. The October 20 check flags follow-up due.
4. “All set.” establishes a completion claim; verification remains outstanding.
5. Documentary confirmation of the correct dates but **FUND-B** produces an exact funding-account mismatch.
6. The October 25 check flags intervention reached and explains the discrepancy.
7. A corrected FUND-A confirmation explicitly supersedes the wrong document. All required fields match and the evidence-addresses judgment is supported, so the template permits documentary verification.
8. Reopening the SQLite database preserves events, judgments, and status.
9. Repeated unchanged checks make **zero new model calls**. Status and provenance stay stable; operational cache counters differ from the first run.
10. An unmatched message and ambiguous `11/12` date remain preserved for review.

Supplying a correct document **without superseding** a conflicting one does not silently resolve the conflict. Both remain visible and verification stays discrepant.

## Current development policy

Administrative definitions now use score threshold **0.60**, margin **0.20**, policy `development-admin-v2`. Research skill thresholds are unchanged. Existing databases retain their registered policy until `admin configure` is rerun. The earlier 0.85 results below describe historical experiments. Reinterpreting the cached live v3 demo at 0.60 produced the intended sequence including documentary verification, with zero new model calls; see `evaluation/admin-kev-threshold-060.json`.

## Real models

Start Ollama as in the original README and Kev as in [KEV_SETUP.md](KEV_SETUP.md). From the KB repository:

```bash
python3 -m kb --db workflow.sqlite3 admin template config/appointment.json
python3 -m kb --db workflow.sqlite3 admin template config/generic_request.json
python3 -m kb --db workflow.sqlite3 admin configure config/has_skill.json
```

`configure` registers the administrative semantic definitions using the supplied backend settings; it does not duplicate the skill predicate or gateway. Use `config/has_skill_08b.json` when serving Kev-0.8B. For deterministic CLI-only experimentation, register `config/admin_counting_mock.json` instead; it only knows the exact fictional fixture messages.

Ingest the original local text file with live LLM extraction:

```bash
python3 -m kb --db workflow.sqlite3 admin ingest \
  --new --request request:alex_appointment --template student_appointment \
  --at 2026-10-12 --file examples/admin_messages/original.txt
```

Every ingest prints its source ID and extraction. Review the proposed values: successful JSON validation is not semantic verification. `incorporated: false` means the source is saved but no executable events were accepted. The ingestion timestamp is stored separately from the message's `--at` timestamp. The local LLM sees at most twelve request candidates and bounded source text, not the whole history.

For a fully deterministic extraction test, append the corresponding reviewed JSON:

```bash
# Use this on a fresh database after template/backend configuration.
python3 -m kb --db workflow.sqlite3 admin ingest \
  --new --request request:alex_appointment --template student_appointment \
  --at 2026-10-12 --file examples/admin_messages/original.txt \
  --extraction examples/admin_messages/original.json
```

Continue the fictional sequence (append the matching `--extraction` file to bypass the LLM):

```bash
python3 -m kb --db workflow.sqlite3 admin ingest --request request:alex_appointment \
  --at 2026-10-13 --text 'Received, we’ll take care of it.'
python3 -m kb --db workflow.sqlite3 admin check --as-of 2026-10-20

python3 -m kb --db workflow.sqlite3 admin ingest --request request:alex_appointment \
  --at 2026-10-21 --text 'All set.'
python3 -m kb --db workflow.sqlite3 admin check --as-of 2026-10-21

python3 -m kb --db workflow.sqlite3 admin ingest --request request:alex_appointment \
  --at 2026-10-22 --kind confirmation --file examples/admin_messages/wrong.txt
python3 -m kb --db workflow.sqlite3 admin check --as-of 2026-10-25

# Replace m_WRONG_SOURCE_ID with the source_id printed for the wrong confirmation.
python3 -m kb --db workflow.sqlite3 admin ingest --request request:alex_appointment \
  --at 2026-10-26 --kind confirmation --file examples/admin_messages/correct.txt \
  --supersedes m_WRONG_SOURCE_ID
python3 -m kb --db workflow.sqlite3 admin check --as-of 2026-10-26
python3 -m kb --db workflow.sqlite3 admin check --as-of 2026-10-26
python3 -m kb --db workflow.sqlite3 admin inspect request:alex_appointment
```

The earlier wrong document is preserved. Each CLI invocation is a new process. The scripted live-Kev smoke test uses reviewed extraction fixtures, isolating Kev behavior from extraction quality:

```bash
python3 -m examples.admin_demo --backend kev --db admin-live.sqlite3 \
  --report evaluation/admin-live.json
```

This records observations, not assumed accuracy. It explicitly reports a failed/unavailable backend. Live ingestion/extraction and real Kev decisions remain unverified in the development session.

### Message-format comparison with live Kev

The first successful live run (`evaluation/admin-kev-test2.json`) confirmed real
responses and persistent cache reuse, but failed to recognize acknowledgment and
completion claims. The corrected document received a supported score of 0.6968,
below the provisional 0.85 threshold.

Administrative registrations use the `admin-message-v2` input format: Kev receives a `message`
text field and a `request_context` list of original context texts. Questions refer
to those fields instead of opaque IDs. Full source IDs, hashes, and timestamps
remain in the gateway's audit records. The acceptance policy and choice descriptions
are unchanged, so this experiment tests presentation rather than relaxed acceptance.
The versioned input format participates in the cache key; old records are retained.
Research predicates and existing v1 registrations retain their original format.

With Kev running, compare the same fictional sequence on a fresh database:

```bash
python3 -m examples.admin_demo --backend kev --db admin-kev-format-v2.sqlite3 \
  --report evaluation/admin-kev-format-v2.json
```

To opt an existing database into the new definitions, rerun
`python3 -m kb --db YOUR.sqlite3 admin configure config/has_skill.json`.
Its next check will request new judgments; subsequent checks reuse them. Live
accuracy of v2 is not yet established. Backend failure or abstention is not a pass.

### Question-specific choices (v3)

The live v2 run improved the acknowledgment support score from 0.0508 to 0.4705,
but the workflow still abstained. New registrations now use definition version
`admin-message-v3`, with question-specific choices from `kb/domains/admin.py`.
The labeled v2 input format, questions, threshold (0.85), and margin (0.20) remain
unchanged. Contradiction now means an explicit denial for message-status questions;
silence about a status is insufficient evidence. Documentary relevance is separate
from exact field correctness.

Run a paired comparison of generic and specific choices through the same gateway:

```bash
python3 -m evaluation.admin_choices --backend kev \
  --db admin-choice-test.sqlite3 --report evaluation/admin-choice-test.json
```

Use a fresh database. This evaluates 15 reviewed fictional development cases
(positive, explicitly negative, and ambiguous for each of five predicates), with
both variants: 30 judgments total. Evidence, questions, and policy are held fixed;
the choices and definition versions differ. Each case retains raw scores, evidence,
latency, and policy decisions. Summaries distinguish raw-choice correctness,
accepted support, false support, policy abstention, and backend/budget failures.
`insufficient_evidence` is not automatically counted as a correct raw choice merely
because the policy abstained. This is not held-out validation or Ollama testing.
`--seconds 180` sets the shared wall-clock budget. For plumbing-only validation,
use `--backend counting_mock`; those results are not model accuracy.

To run the complete workflow with the new choices:

```bash
python3 -m examples.admin_demo --backend kev --db admin-kev-choices-v3.sqlite3 \
  --report evaluation/admin-kev-choices-v3.json
```

No live v3 success is claimed yet. Re-registering via `admin configure` opts an
existing database into v3 and prevents reuse of earlier definitions' raw judgments.

## Reports and authority

`admin check` emits JSON with attention items sorted by **overdue, intervention reached, discrepancies/dependencies, missing information, follow-up due, then stale/verification reminders**. Each item includes the desired outcome, responsible party, dates and their bases, evidence age, progress, verification, missing/absent evidence, exact mismatches, rule/source IDs, and a suggested action. All requests remain in `requests`, even when no reminder is due. Unmatched or ambiguous sources appear separately in `unassigned_messages`.

Progress assessments are independent: a message can acknowledge, promise, request information, and claim completion simultaneously. `progress` is a convenient headline; `progress_assessments` preserves all supported meanings. Verification is separate: `unverified`, `discrepant`, `verified_documentary`, or `user_confirmed`. A successful semantic completion-claim judgment alone never verifies an external outcome.

Documentary verification requires the template's documents/steps, every required expected field, matching observations, a supported evidence-addresses assessment, and no active discrepancy or explicit absence. Comparisons are deterministic: ISO dates, case-sensitive identifiers, exact decimals, and explicit percentages. Omission means **not observed in the available record**, not definitely absent. The system never assumes it has the full correspondence thread. A supported documentary proof can establish completion even if a different nonconflicting assessment is unresolved; conflicting values remain flagged.

The appointment template is illustrative, not university policy. Edit/register a versioned JSON template for your actual requirements. A request pins its template snapshot. New registrations affect new requests, not existing history. Template steps form a validated acyclic prerequisite graph. Additional steps require explicit human `step:NAME true` updates; satisfying prerequisites alone does not complete a step.

Dates retain `documented`, `user_preference`, or `tentative` bases. Tentative estimates are shown but do not create authoritative deadlines. Conflicting active date values are flagged; the system does not choose the newest. Final deadlines are overdue **after** the specified calendar day; follow-up/intervention dates are reached at local midnight on that day. A source's date-only timestamp also means local midnight. Offset-free timestamps containing a time are rejected to avoid DST ambiguity. The default zone is `America/New_York`; use `--timezone` to change it.

As-of checks filter effective evidence and supersession dates. They are retrospective views of the records now available, not a reconstruction of what the software had already ingested on that date. The report includes both the latest effective evidence timestamp and the latest ingestion timestamp. Evidence age uses elapsed UTC seconds. Lead times are **calendar days**; no business-day calendar is implemented.

## Human corrections and reminders

Use IDs from `admin inspect`. Sources and timestamps are mandatory for manual changes:

```bash
python3 -m kb --db workflow.sqlite3 admin set request:alex_appointment \
  follow_up 2026-10-23 --supersedes w_OLD_FOLLOWUP_EVENT \
  --source 'My revised follow-up preference' --at 2026-10-19

python3 -m kb --db workflow.sqlite3 admin set request:alex_appointment \
  observed:funding_account FUND-A --supersedes w_MISPARSED_FIELD \
  --source 'I checked the document; extraction misread the account' --at 2026-10-24

python3 -m kb --db workflow.sqlite3 admin set request:alex_appointment \
  snooze 2026-10-30 --source 'Pause routine reminders' --at 2026-10-24

python3 -m kb --db workflow.sqlite3 admin set request:alex_appointment \
  confirm true --source 'I personally verified the appointment in the system' --at 2026-10-26

python3 -m kb --db workflow.sqlite3 admin retract w_EVENT_ID \
  --source 'Withdraw my prior assertion' --at 2026-10-27
```

Snoozing suppresses routine follow-up/stale/claim reminders until the named date; it changes no deadline and hides neither discrepancies nor reached intervention/overdue flags. User confirmation is labeled separately and cannot hide a known discrepancy. Use `--supersedes` when changing a field; without it, opposing values coexist and require review. Historical source text is never rewritten.

Associate an unmatched or incorrectly matched message with the intended request:

```bash
python3 -m kb --db workflow.sqlite3 admin associate m_MESSAGE_ID request:alex_appointment \
  --source 'This message concerns Alex appointment' --at 2026-10-24
```

Ambiguous dates still require field correction; association does not guess their meaning. Human semantic overrides use the same gateway and are retractable:

```bash
python3 -m kb --db workflow.sqlite3 admin override message_claims_completion \
  message:m_MESSAGE_ID request:alex_appointment supported \
  --source 'My review of this message' --at 2026-10-24
```

Use `--replace o_OVERRIDE_ID` to supersede an earlier judgment or `admin retract o_OVERRIDE_ID` to withdraw it. Opposing active support and contradiction produce a visible conflict. This changes interpretation of the message, not documentary verification of an external system.

Requests may depend on other requests through extracted/reviewed `dependencies`. To connect an unresolved request to existing research tasks:

```bash
python3 -m kb --db workflow.sqlite3 admin set request:alex_appointment \
  affects_resource resource:funding_allocation \
  --source 'This request gates the research allocation' --at 2026-10-12
```

Tasks with explicit `requires_resource(Task,resource:funding_allocation)` assertions appear in `affected_research_tasks`. This does not silently grant resource access when a request completes: resource status still requires an explicit accepted update.

## Budgets, scheduling, and limits

```bash
python3 -m kb --db workflow.sqlite3 admin check --as-of 2026-10-25 \
  --judgments 32 --requests 32 --seconds 60
```

A check counts individual uncached judgment attempts, backend calls, HTTP requests, cache hits, and model/wall latency. Budget/error/abstention outcomes remain unresolved and cannot manufacture completion. A small part of the same wall-clock budget is reserved for symbolic attention checks. Unchanged successful judgments persist across restarts. Transient backend errors can be retried on a later check.

There is **no background monitoring**. A future `launchd`, cron, or other scheduler can invoke the same command with an explicit date and save stdout to a local report. Nothing has been scheduled or started, and no message-sending capability exists.

Current limitations: only pasted/local UTF-8 text, conservative request matching, no OCR/PDF parsing, no email threads/connectors, no institutional policy lookup, no business-day calendars, no external record verification, no template migration for existing requests, no distributed worker/single-flight coordination. Exact fields still depend on correct extraction or human review. Real-model thresholds need domain calibration before practical reliance.

### Initial-request extraction retry

A request can be ingested before any completion evidence exists. If Ollama returns `incorporated: false`, the source is retained but no request events are created. After the extraction-prompt fix, retry the same `admin ingest --new` command; the prior source remains for audit. The revised prompt distinguishes template verification requirements from message-ingestion requirements and explicitly forbids treating unmentioned documents as known absent. Live-model validation of this revision is pending.

When an explicit request/template is selected, Ollama now receives a template-specific extraction schema: `expected` and `observed` can use only that template’s field names, while workflow dates belong in `dates`. The same schema validates the response. This prevents date-role names such as `submission` from being accepted as appointment fields; it does not guarantee correct extraction of meaning.

Confirmation ingestion constrains `expected` to an empty array. A confirmation reports observed outcomes, not a revision to the request. To revise expectations intentionally, use an explicit `admin set expected:FIELD ... --supersedes ...` correction. Reviewed confirmation JSON is subject to the same no-expectations rule.

Confirmation ingestion also requires `desired_outcome` to be empty: document summaries must not become new requested outcomes. This restriction is enforced in decoding, reviewed ingestion, and reassociation. Explicit request corrections remain available through `admin set`.
