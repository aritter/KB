# Development plan

Updated October 13, 2026. This is a development roadmap, not a commitment to automatic background work or a delivery schedule.

## Objective and current decision

Test whether a frozen local language model can acquire and revise external knowledge, combine symbolic inference with bounded semantic assessments, and answer from persistent knowledge without reloading full history. Administrative request tracking is the primary practical application; research coordination remains a second application of the same architecture.

**Current priority: test the existing version before adding capabilities.** Keep the v3 administrative predicate definitions and labeled v2 input format for the next runs. Following user review, the administrative development threshold is now 0.60 with margin 0.20 (policy development-admin-v2). Do not yet implement the proposed future-tense wording change or Qwen-authored predicates.

## Where we are

| Area | Evidence | Remaining uncertainty |
| --- | --- | --- |
| Original editable KB | Deterministic teaching/rules, querying, correction, retraction, provenance, and persistence tests pass | Live Qwen correction reliability after fixes needs retesting |
| Shared semantic gateway | Budget, override, conflict, raw-score/policy separation, relevant cache invalidation, and restart tests pass | Broader real-model behavior and memory use |
| Research coordination | Mock-backed eligibility, readiness, blockers, dependencies, and update tests pass | Real Kev skill judgments and Qwen translations |
| Administrative workflows | Deterministic mismatch, date, evidence, correction, snooze, and persistence tests pass | Full live extraction-to-verification sequence |
| Real Kev integration | User-run reports show successful responses and 17 cached judgments after restart | Correct semantics are not guaranteed by a successful API response |
| Prompt experiment | 15 development examples: generic choices 11/15 correct raw choices; specific choices 14/15, 3 accepted positive judgments, 0 accepted false positives | Tiny development set; not held-out accuracy or calibrated scores |

The current deterministic suite passes **64 tests**. Model outputs in those tests are mocked; Prolog and SQLite are real. Live evidence is recorded in `evaluation/admin-kev-test2.json`, `evaluation/admin-kev-format-v2.json`, and `evaluation/admin-choice-test.json`. Earlier unavailable-runtime reports remain historical evidence. This agent session still cannot connect to port 8009; successful live runs were executed in the user's terminal.

## Stage 1 — Finish testing the current version (now)

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

