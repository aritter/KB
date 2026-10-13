# Validation status

The current deterministic suite passes **64 tests**, including protocol-format, cache-invalidation, and paired-evaluation checks added after the initial 54-test milestone. Tests use labeled mock decisions or mocked HTTP responses for models. SQLite and Prolog are real, including fresh-process CLI restart checks.

- `admin-mock.json`: the full fictional administrative sequence passed; final unchanged reports used zero new judgments/backend calls and 17 cached judgments.
- `coordination-mock.json`: research eligibility, readiness, dependency consequences, updates, first-answer stopping, and restart/cache behavior passed with a counting mock.
- `admin-kev-attempt.json` and `coordination-kev-attempt.json`: real local Kev attempts were blocked by localhost `Operation not permitted`. These are unavailable-runtime observations, not model accuracy measurements.
- `admin-extraction-attempt.json`: actual Ollama extraction attempt was blocked by the same local access restriction. The original source was preserved for review and no extraction was incorporated.
- `local.json`: historical evaluation of the original positive-KB milestone.

Administrative deterministic checks cover acknowledgment/claim/verification separation, exact mismatches, partial records versus explicit absence, timezone/day boundaries, explicit supersession versus conflicting documents, field corrections, user confirmation, snoozes, semantic override conflicts, ambiguous request matching and dates, template prerequisites, dependency reporting, cache persistence, and budget exhaustion without false completion.

Run `python3 -m unittest discover -s tests -v` from the repository. See the main README for both demos and live setup. The next experiment is to hand-label a small collection of fictional administrative messages (especially vague acknowledgments and conflicting confirmations), run both Kev sizes locally, and measure precision/abstention and extraction errors separately before changing the provisional thresholds.

## User-run live experiments (October 13, 2026)

- `admin-kev-test.json`: preflight failed because the configuration used rounded temperature 2.41. The 4B configuration now pins the reported 2.406050072164233.
- `admin-kev-test2.json`: real scoring succeeded; repeated checks reused 17 judgments with zero new calls. Semantic outcomes did not meet the demo expectations.
- `admin-kev-format-v2.json`: labeled message/context fields improved acknowledgment support, but workflow results still abstained.
- `admin-choice-test.json`: on 15 reviewed development cases, generic choices gave 11 correct raw choices; specific choices gave 14. Specific choices accepted 3 positive judgments, had 5 policy abstentions, and no accepted false support in this small set. Thirty judgments took 15.82 seconds backend wall time. This is not held-out validation.

The complete v3 live workflow was run in `admin-kev-choices-v3.json`: acknowledgment was accepted (support 0.8533); promise (0.7931), completion claim (0.6670), and corrected documentary evidence (0.6338) all had the expected raw choice but abstained below the unchanged 0.85 threshold. Exact FUND-B discrepancy and intervention flags worked; restart/repeated checks reused 17 judgments with zero new calls. The workflow did not achieve documentary verification. Live administrative Qwen extraction remains to be tested. See [the development plan](../DEVELOPMENT_PLAN.md). No predicate or threshold changes were made when documenting this baseline.

`admin-kev-threshold-060.json` reinterprets the existing live v3 cache with administrative threshold 0.60 and margin 0.20: all intended dated workflow states now appear, including corrected documentary verification. No model calls were allowed or made. This is policy tuning on development examples, not a new model run. The latest extraction-prompt revision has deterministic transport/integration coverage but still needs a live Ollama retry.

The next live extraction attempt correctly extracted requested fields and dates, but duplicated submission/follow-up/intervention into `observed`, causing rejection. Selected-template extraction now constrains `expected`/`observed` field names and document names in the JSON schema passed to Ollama, and validates against the same schema. Regression coverage verifies rejection/preservation even if a backend ignores decoding constraints. Live retest is pending; no silent repair of rejected outputs is performed.

The live initial request was then correctly incorporated. A later acknowledgment was rejected because Qwen invented a submission date from source timestamp metadata and an empty follow-up date. Kev consequently saw only the original request, not the acknowledgment. The extractor now withholds source timestamps from the model (retaining them in SQLite), uses a complete JSON acknowledgment example, and constrains decoded date values to ISO dates or integer lead days. All 64 deterministic tests pass, including date-free acknowledgment ingestion through mocked Ollama transport. Live retry remains required.

The live wrong-account confirmation duplicated FUND-B into both expected and observed fields. Confirmation decoding now requires an empty expected array, and ingestion rejects reviewed confirmations that violate this rule. Four erroneous expected events from source `m_fdb7daf16075428999a68ef15d2dc03e` in the local development database were explicitly retracted with repair provenance; its original source, document event, and four observed fields remain. Active expected account is FUND-A. All 63 tests pass; the next dated live report is pending.

The live corrected confirmation created an erroneous second desired-outcome description, producing `conflicting_desired_outcome`. Confirmation decoding and ingestion now forbid changing desired_outcome, including through reassociation. Event `w_2bbe9357530c49d89e0a4ab9f84372ac` was retracted with repair provenance, preserving the original source and observations. `admin-ollama-oct26-repaired.json` is a cache-only check: no discrepancies, 12 cached judgments, five unresolved judgments requiring the restored context; not yet documentary verification. All 64 tests pass.

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

