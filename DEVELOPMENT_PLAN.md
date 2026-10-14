# Development plan

## Real incremental live test passed — October 14

`evaluation/live-20261014T173415769133Z/summary.json` records a passing
`python3 -m examples.admin_live_test --incremental` run. Real Qwen extraction,
Kev judgments and Prolog checks passed. Duplicate refresh, clock-only intervention
and restart reused the conclusion with zero model requests (about 18 ms per refresh).
New claim, wrong confirmation and corrected confirmation each invalidated the
request conclusion while retaining applicable judgment cache entries. The corrected
confirmation established documentary verification and withdrew the alerts.
This validates one fictional development sequence, not broad extraction accuracy.
Next: bounded adaptive long-document reading with explicit coverage and a
cross-section correction/exception. `kb/operations.py` remains an unexposed draft.


## Next live test — incremental runner

Run `python3 -m examples.admin_live_test --incremental` with Ollama and Kev started.
It retains real extraction/judgments and checks duplicate import, clock-only
intervention, correction, collection invalidation, fresh-process reuse and alert
history. Outputs are saved in evaluation/live-TIMESTAMP. All 76 deterministic tests
pass; the incremental real-model run remains unverified. This session's connection
probes to both local model ports failed; no cause is inferred from that alone.


## Incremental slice implemented — October 14

`python3 -m examples.admin_incremental_demo` now validates duplicate import,
clock-only intervention, completion, retained alert transitions and restart.
`admin refresh` and `admin history` are available. The saved deterministic comparison
is `evaluation/incremental-development/report.json`: 13 vs 50 mock judgments,
with expected status and alert transitions in both modes. No live-model speedup
is claimed. Nine focused incremental tests cover the new path, including CLI,
timezone, conflicts, supersession, definition changes and budget/candidate limits.

Next: extend chronological fixtures (promise deadlines and dependent requests),
then optional live refresh validation. Adaptive reading and coverage tracking are
still pending. The operation-plan draft is not exposed as a completed interface.


Updated October 14, 2026. This is a development roadmap, not a commitment to automatic background work or a delivery schedule.

## Objective and current decision

Test whether a frozen local language model can acquire and revise external knowledge, combine symbolic inference with bounded semantic assessments, and answer from persistent knowledge without reloading full history. Administrative request tracking is the primary practical application; research coordination remains a second application of the same architecture.

**Current priority: preserve the passing administrative baseline, then develop two
separate experiments: incremental workflow maintenance and bounded long-document
processing.** This architecture was agreed with the user on October 14. Keep the
current registered semantic predicates and administrative policy (threshold 0.60,
margin 0.20, version `development-admin-v2`) stable while testing this extension.
Qwen-authored predicate activation remains a separate later experiment.

## Agreed architecture and implementation order

This section supersedes the older stage ordering below. Earlier live failures and
prompt experiments are historical context, not the current baseline status.

| Component | Responsibility |
| --- | --- |
| Durable evidence store | Original text, immutable versions, thread/document structure, source locations and content hashes |
| Qwen with a bounded Python executor | Adaptive evidence discovery, reading subtasks and structured extraction proposals |
| Existing Kev gateway | Registered, grounded semantic assessments with evidence, cache, policy, overrides and uncertainty |
| SWI-Prolog | Inspectable workflow rules over accepted facts and recorded assessments; pending semantic requests rather than model calls during backtracking |
| Dependency tracking | Evidence and collection dependencies, invalidation, conclusion and alert history |

Prolog is not the primary document-navigation language. Qwen may select reading
operations and revise its plan after inspecting results; Python enforces budgets.
Keep full documents and large intermediate outputs outside the parent context.
Return references, counts, bounded excerpts and explicit unresolved work. Subtask
results retain their source spans and remain interpretations until validated.

This is inspired by [Recursive Language Models, Section 2](https://arxiv.org/html/2512.24601v3#S2),
which uses an external programming environment and model subcalls. Our restricted
executor is an adaptation, not a reproduction. Caching or a fixed retrieval plan
alone does not demonstrate recursive/adaptive document processing. No arbitrary
generated Python, raw Prolog, or automatic predicate installation is permitted.

### Experiment A — Incremental workflow maintenance

Finish a narrow end-to-end slice before adding a reading planner:

1. Ingest and retain evidence with stable identity and explicit versions. Identical
   reimports in the same source context must reuse extraction and judgments;
   identical text from distinct messages must not be conflated accidentally.
2. Track dependencies of request conclusions on facts, interpretations, overrides,
   rules, model/prompt versions and evidence collections. New evidence can invalidate
   an absence-based conclusion without changing any previously read document.
3. Refresh affected requests and retain alert transitions. A clock-only refresh
   recomputes due dates without model calls; unresolved judgments remain unresolved.
4. Expose the slice through the existing CLI with shared call/time/search budgets,
   partial-result reporting and serialized Qwen/Kev inference.

Acceptance tests: duplicate import causes no new extraction or judgment calls;
clock advancement triggers an explained intervention alert; completion evidence
withdraws the obsolete alert while retaining history; unrelated evidence preserves
cached judgments; conflicting evidence remains visible; budget exhaustion never
produces an unsupported all-clear. Verify persistence after restart.

Compare full reprocessing with incremental refresh on the same chronological
fixture. Record status/alert correctness, model calls, cache hits and latency.
Label this a full-reprocessing baseline, not a replication of the RLM paper.

### Experiment B — Bounded long-document processing

Use one fictional request, a long message thread and a structured attachment with
an important correction or exception in a different section. Preserve originals;
start with local text and section/source offsets. PDF layout/OCR is separate work.

Implement discovery, metadata, bounded reads, extraction, registered semantic
assessment, approved workflow queries and explanations. Add a bounded adaptive
loop so a result can inform the next read without requiring the user to supply IDs
manually. Subtasks can process selected sections and store outputs externally;
the parent receives compact references. Begin with one level of reading subtasks.
All subcalls share a single enforced budget across retries and replanning.

Track examined sections, remaining candidates, truncation and unresolved checks.
Support in one passage does not prove that no exception exists elsewhere. Conclusions
requiring complete review must depend on documented coverage and collection versions.
Kev assesses specific evidence questions; Qwen performs navigation/extraction;
exact dates, accounts and amounts remain deterministic comparisons.

Compare ordinary bounded retrieval against adaptive reading with the same model
configuration and resource ceilings. Measure missed evidence, false verification,
status correctness, evidence coverage, calls, input size and latency. Include a
cross-section exception, a correction, distracting documents and insufficient-budget
cases. Add deterministic executor tests before an optional live-model run.

### Integration gates and current work in progress

The short-message full-live demonstration remains the regression baseline. Preserve
original teaching/correction/persistence and research coordination tests throughout.
Do not treat the existing 66-test suite as validation of the new features.

Draft `kb/incremental.py`, `kb/operations.py` and `kb/runtime.py`, plus integration
edits, exist in the working tree. They need focused tests, CLI integration and review.
In particular the current operation draft uses literal IDs and a single plan; it
does not yet implement adaptive reading or recursive subtasks. Review it against
Experiment B rather than exposing it as a completed RLM interface.

Next implementation step: validate Experiment A's dependency and duplicate-import
semantics with deterministic tests, then integrate its CLI demonstration. Only then
extend the operation draft for Experiment B. No background monitoring is installed;
refresh remains an explicit command. No email or external-account integration.

## Current milestone — fresh full-live pass, October 14

`evaluation/live-20261014T170701352931Z/summary.json` records **LIVE TEST PASSED**.
A fresh database completed all five live Ollama extractions, real Kev assessments,
Prolog workflow checks, explicit wrong-document supersession, documentary verification,
and fresh-process repeat/cache checks without manual repairs or fixture substitution.
The repeat reused 17 judgments and made zero model calls. Total command wall time
was about 87 seconds; the cached repeat took about 0.11 seconds.

This completes the clean administrative baseline. Next test additional fictional
messages/requests and the retained original KB/research applications; no need to
repeat the repaired October 13 run. Keep the current 0.60 administrative threshold
and 0.20 margin unless a subsequent experiment intentionally changes them. This
is one passing development scenario, not a broad accuracy estimate.

## Where we are

| Area | Evidence | Remaining uncertainty |
| --- | --- | --- |
| Original editable KB | Deterministic teaching/rules, querying, correction, retraction, provenance, and persistence tests pass | Live Qwen correction reliability after fixes needs retesting |
| Shared semantic gateway | Budget, override, conflict, raw-score/policy separation, relevant cache invalidation, and restart tests pass | Broader real-model behavior and memory use |
| Research coordination | Mock-backed eligibility, readiness, blockers, dependencies, and update tests pass | Real Kev skill judgments and Qwen translations |
| Administrative workflows | Deterministic mismatch, date, evidence, correction, snooze, and persistence tests pass | Additional scenarios and broader extraction reliability |
| Real Kev integration | User-run reports show successful responses and 17 cached judgments after restart | Correct semantics are not guaranteed by a successful API response |
| Prompt experiment | 15 development examples: generic choices 11/15 correct raw choices; specific choices 14/15, 3 accepted positive judgments, 0 accepted false positives | Tiny development set; not held-out accuracy or calibrated scores |

The current deterministic suite passes **66 tests**. Model outputs in those tests are mocked; Prolog and SQLite are real. Live evidence is recorded in `evaluation/admin-kev-test2.json`, `evaluation/admin-kev-format-v2.json`, and `evaluation/admin-choice-test.json`. Earlier unavailable-runtime reports remain historical evidence. This agent session still cannot connect to port 8009; successful live runs were executed in the user's terminal.

## Earlier roadmap and test history (retained for reference)

The agreed experiments above now take priority. Historical pending statements below
are superseded by the October 14 full-live pass where applicable.

## Stage 1 — Finish testing the current version

### 1A. Full administrative sequence with real Kev

Run from the KB repository, with Kev running, using fresh filenames:

```bash
python3 -m examples.admin_demo --backend kev \
  --db admin-kev-choices-v3.sqlite3 \
  --report evaluation/admin-kev-choices-v3.json
```

This uses reviewed extraction fixtures, isolating Kev from Qwen. Check acknowledgment, promises, claims, wrong-account detection, explicit corrected-document supersession, restart persistence, and zero new calls on repeated successful checks. Report semantic failures and policy abstentions separately. An exit code of zero means observations were collected, not that all expected semantics passed.

Known risks from the small comparison: “All set” support was 0.7720 and documentary-evidence support was 0.5745, both below 0.85. The complete workflow has different context and may produce different scores. Do not assume it will verify completion.

The user-run v3 baseline is now saved in `evaluation/admin-kev-choices-v3.json`. Acknowledgment passed (0.8533); promise, completion claim, and corrected documentary evidence chose supported but abstained (0.7931, 0.6670, 0.6338). Exact mismatch and intervention checks worked, and restart/repeated checks reused 17 judgments with zero new calls. Documentary verification remains unresolved. Keep this as the baseline; next test live extraction without changing thresholds.

### 1B. Test Qwen extraction separately, then combine the models

Use a new database and the live ingestion sequence in [ADMIN_WORKFLOWS.md](ADMIN_WORKFLOWS.md). Omit `--extraction` to call Ollama. Review each returned extraction against the original text before interpreting downstream failures.

Check person, dates, account case, date provenance, request association, and completion claims. Include ambiguous dates and unmatched messages. Count wrong accepted fields separately from rejected/clarification outputs. Then run the dated reports through real Kev on the same accepted events.

Retest the original correction sequence independently:

```bash
python3 examples/demo.py --model qwen3.5:9b-q4_K_M --db original-live-retest.sqlite3
python3 -m evaluation.run --model qwen3.5:9b-q4_K_M --output evaluation/qwen-live-retest.json
```

### 1C. Preserve the research application

Run the retained research demonstration and live commands in [RESEARCH_COORDINATION.md](RESEARCH_COORDINATION.md). Verify that Bob's unavailability filters him out before skill assessment, multiple skills are mandatory, Carol can remain unresolved, and missing completeness metadata does not produce readiness. Removal of a prerequisite or supporting fact must affect subsequent answers.

### 1D. Record a baseline and review failures

For each run record model/checkpoint configuration, predicate/policy versions, extraction errors, raw semantic choices, acceptance/abstention, false support, workflow outcomes, backend errors, latency, judgment/request counts, and cache reuse. Measure Mac memory with both runtimes loaded. Keep unavailable and budget-limited cases out of accuracy denominators and report their counts.

**Exit criteria:** all three applications have an actual live attempt with saved results; failures are classified as extraction, semantic choice, acceptance policy, symbolic inference, or runtime/resource problems. Deterministic invariants must pass. Model misses can remain, but must be explicit and reproducible. Do not describe the prototype as reliably verifying requests while the positive documentary cases remain unresolved.

## Stage 2 — Improve semantic reliability with controlled experiments

1. Establish the intended meaning of each predicate. In particular, decide whether completion contradiction requires an explicit denial or may follow from a future-action implication. Current intended semantics require an explicit denial; “we will process it tomorrow” is labeled insufficient evidence.
2. Expand reviewed examples across all five administrative predicates: paraphrases, mixed messages, explicit denials, unrelated replies, partial evidence, contradictory documents, and quoted text. Reserve an untouched evaluation split before prompt tuning.
3. Compare one change at a time: clearer explicitness instructions, example inclusion, and evidence formatting. Keep exact account/date/amount comparisons deterministic.
4. Evaluate acceptance policies on development data, including different costs for falsely accepting completion versus missing a reminder. Do not treat the model's score or confidence field as calibrated accuracy. Keep raw judgments so policy-only experiments need no rescoring.
5. Compare Kev-4B and Kev-0.8B after verifying each server's exact configuration. Compare Qwen-9B and Qwen-4B extraction separately.

**Exit criteria:** report raw choices, accepted precision/coverage, abstention, and false completion on the untouched split. Agree on acceptable error/coverage targets before examining that split. Every known deterministic regression remains fixed; do not repeatedly tune against the test split.

## Stage 3 — Practical local use, without external actions

Improve report readability, make unresolved judgments easy to inspect, and streamline field corrections and evidence supersession. Add user-selected local text collections only after fictional tests establish a useful baseline. Preserve distinctions between documentary verification and user confirmation. If scheduling checks becomes useful, add an explicit opt-in local scheduler with visible run/freshness logs; do not imply one exists now.

**Exit criteria:** a user can explain every alert and completion decision from the source trail, correct errors, and see whether a report is stale. No email sending, administrator contact, or external-record modifications.

## Stage 4 — Qwen-assisted semantic predicate authoring

Keep this separate from ordinary query execution. Qwen may draft a proposed predicate definition containing typed arguments, grounded-input constraints, bounded evidence retrieval, question/choices, acceptance policy, and positive/negative/ambiguous tests. Definitions must remain data, never arbitrary executable Python or Prolog.

Validate and test proposals in isolation; initially require explicit user activation. A query may return that a capability is missing and suggest a proposal, but must not silently install it to complete a proof. Retain the proposal, tests, activation source, and definition version. Changed definitions invalidate only dependent judgments; human overrides keep their authority.

**Exit criteria:** proposals are inspectable, unsafe/unsupported retrieval is rejected, inactive proposals cannot influence answers, and version changes have tested cache/provenance behavior. The current fixed vocabulary cannot yet accept arbitrary new predicates; extending schema and dispatch is part of this stage.

## Stage 5 — Optional research experiments

Only after Stage 4: evaluate autonomous predicate proposal/activation under a separately agreed policy, new domain vocabularies, and query-planning improvements. Compare these against the fixed-predicate baseline to measure whether flexibility improves knowledge acquisition without damaging consistency or auditability.

Deferred: autonomous predicate creation during ordinary inference, optimal scheduling, predictions of research success, broad ontology imports, probabilistic proof scores, learned approximations, web UI, email integration, and institutional-policy assumptions.

## Latest development updates

The existing live v3 judgments were reinterpreted at threshold 0.60 with backend calls prohibited. `evaluation/admin-kev-threshold-060.json` records the intended promise, claim/unverified, discrepancy, and corrected/verified sequence with zero new judgments or backend calls. Original raw judgments and prior policy decisions remain preserved.

Live Qwen ingestion rejected the initial request because it confused verification requirements with ingestion prerequisites. The extraction prompt now explicitly separates these, passes new-request/source-date context, and explains missing versus known-absent documents and request dependencies. A mocked transport regression passes; real extraction after this change still needs retesting.

## Latest result — pending check completed

User ran `python3 -m examples.admin_resume_check`; reports are in
`evaluation/resume-20261013T144304427007Z/`.
Both first and repeat checks show **verified_documentary**, no discrepancies,
and no request flags. The first check reused 12 judgments and computed five;
Kev supported the corrected document with score 0.6958 (threshold 0.60).
Backend wall time was about 3.21 seconds. The repeat reused all 17 judgments
with zero new judgments or backend calls. No stopping reasons or stderr errors.
The pending post-repair check is therefore complete; do not rerun it by default.
Next: a fresh automated full-live sequence with the final prompts/schema, then
additional fictional cases. This successful repaired run is not yet a clean
unattended end-to-end run: it included earlier extraction fixes and audited repairs.

