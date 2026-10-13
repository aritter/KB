# Session handoff — October 13, 2026

User is stepping away. Stop after saving this handoff; no background work is scheduled. Resume by reading this file and DEVELOPMENT_PLAN.md. The user wants to continue testing the current system before adding new capabilities. Avoid requiring repeated manual command/output copying.

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

## Current state

- Original KB, research coordination, and administrative workflows share SQLite, SWI-Prolog, and one semantic gateway. Administrative workflow is the primary demo.
- 64 deterministic tests passed at the last implementation change. Model responses are mocked in these tests; Prolog/SQLite are real.
- Live models: Ollama `qwen3.5:9b-q4_K_M`; Kev `jaredpalmer/kev-4b@v1.0`, MLX bfloat16, temperature **2.406050072164233**, server port 8009. Earlier rounded 2.41 config caused preflight failures; fixed.
- Administrative definitions: `admin-message-v3`, labeled input format `admin-message-v2`, question-specific choices. Policy `development-admin-v2`: threshold **0.60**, margin **0.20**, explicitly approved by user for development tuning. Do not re-argue overfitting; larger examples can come later. Research has_skill threshold remains 0.85.
- Real Kev comparison: generic choices 11/15 raw choices correct; specific choices 14/15. Historical comparison used 0.85. All live reports remain in evaluation/.
- This session can edit/read repository and run deterministic tests, but cannot reach local model servers. Latest probes of 127.0.0.1:8009 and :11434 both returned curl connection failures. Prior sessions sometimes returned Operation not permitted. Do not claim a specific root cause is proven by curl alone; sandbox/network configuration is restricted and escalation is unavailable in this session.
- User's terminal can reach both models. User-run saved reports are directly readable here: no need to have user paste entire JSON reports.
- Many changes remain uncommitted; do not reset or discard them. No commits/pushes made by assistant. No emails or external records modified. No background monitoring.

## Live workflow database and evidence

Database: `admin-ollama-test.sqlite3`; request: `request:alex_appointment`.

1. Initial request successfully extracted by live Qwen: Alex Example, November 1–December 31, 2026, FUND-A, fictional Appointments Office. Submission Oct12/documented, followup Oct20/user_preference, intervention Oct25/user_preference. No invented final deadline.
   Source `m_2904e092ead34abcaaa95c81b72a3f37`.
2. Acknowledgment accepted after extraction fixes: source `m_b2d953bb4ccb4e559b3f04b055203f29`.
   Oct20 report: promised, unverified, follow_up_due. `evaluation/admin-ollama-oct20.json`.
3. All set accepted: Oct21 report claimed_complete, unverified, follow_up_due and verification_outstanding. `evaluation/admin-ollama-oct21.json`.
4. Wrong-account confirmation Oct22: source `m_fdb7daf16075428999a68ef15d2dc03e`. Observed correct period and FUND-B. Qwen incorrectly also wrote four expected fields. Assistant explicitly retracted those four erroneous expected events with repair provenance effective Oct22; observations/document/source remain intact.
   Oct25 report correctly shows expected FUND-A vs observed FUND-B and intervention_reached. `evaluation/admin-ollama-oct25.json`.
5. Correct confirmation Oct26: source `m_94f6c3a08199480f8774fa7eb92b07f9` explicitly superseded the wrong source. Observed fields correct; expected empty. But Qwen wrote a document summary into desired_outcome, creating false `conflicting_desired_outcome`.
   Assistant retracted erroneous event `w_2bbe9357530c49d89e0a4ab9f84372ac` with repair provenance effective Oct26. Original request desired outcome, observations, and history preserved.

## Previous stopping point (completed; see latest result above)

The repaired Oct26 state has **no discrepancies**, but **five judgments for the corrected confirmation need rescoring under the restored request context**. A cache-only run reused 12 older judgments and left those five unresolved; it is NOT evidence that the latest corrected document failed Kev.

- `evaluation/admin-ollama-oct26.json` and `...-repeat.json`: BEFORE latest repair, showed false desired-outcome conflict; repeat used 17 hits and zero calls.
- `evaluation/admin-ollama-oct26-repaired.json`: AFTER repair, cache-only with judgment/request budget zero; no discrepancy but unverified because five judgments were not evaluated.
- `evaluation/admin-ollama-oct26-fixed.json`: NOT present when this handoff was written. Live post-repair check still pending.

Do not re-ingest the corrected confirmation or reset the DB. Run the dated check and repeat in fresh processes, inspect scores if verification remains unresolved. Expected if model acceptance succeeds: verified_documentary, no request flags/discrepancies; repeat zero new judgments/backend calls. Historical rejected attempts remain in unassigned_messages, so don't confuse that with current request completion or erase them.

Single command prepared for next time, with Kev running, from repo root:

```bash
python3 -m examples.admin_resume_check
```

This uses the existing DB, as-of Oct26, launches the CLI twice in separate processes, prints concise summaries, and saves full stdout/stderr under a unique `evaluation/resume-TIMESTAMP/` directory. It does not ingest new records or alter assertions; queries may populate judgment caches. Supports --db, --as-of, --seconds, --output-dir. A zero exit code means checks ran, not that the expected verification outcome passed. The helper was smoke-tested on a temporary mock-backed database, not live models.

Agent should read these saved files directly. Once model endpoints are reachable from the agent execution environment, run this helper directly rather than asking user to execute snippets. Until then user need only run this one command and say it finished. Do not bypass managed network controls or expose model servers publicly.

## Extraction bugs fixed during live testing

- Initial request mistaken for missing completion evidence: prompt separates ingestion from verification and includes explicit initial-request examples.
- Workflow dates duplicated into observed appointment fields: template-specific JSON schema constrains expected/observed field names and document names.
- Acknowledgment acquired invented submission date from source metadata plus empty followup: source timestamps withheld from extraction prompt (still stored), complete empty-extraction example, strict decoded date formats; missing date means empty dates array, not clarification.
- Confirmation duplicated observed account into expected: confirmation schema requires expected []; ingestion checks reviewed JSON too.
- Confirmation summary became desired_outcome: confirmation schema requires desired_outcome ""; ingestion and reassociation enforce this rule. Intentional corrections remain explicit admin set operations.
- All original source texts and rejected attempts remain preserved. Repairs were explicit retractions, never silent rewriting of original evidence.

## After pending check succeeds

Record actual result in evaluation/README.md and DEVELOPMENT_PLAN.md. Do not claim a clean unattended end-to-end run yet: this test involved prompt/schema fixes and manual audited repairs. Next useful test is a fresh automated full-live run using the final extraction prompts, followed by new fictional cases. Retain research and original KB regression tests. Predicate invention/Qwen-assisted semantic registration remains deferred; see staged development plan.
