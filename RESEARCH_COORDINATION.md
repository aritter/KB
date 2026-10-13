# Research coordination retained alongside administrative tracking

This incremental domain uses the original assertions, rules, sources, correction/retraction, and SQLite persistence. It shares `kb/semantic.py` with administrative tracking; neither application has its own semantic cache.

```bash
python3 -m examples.coordination_demo --backend counting_mock --db research-demo.sqlite3
# For a real Kev attempt after local setup:
python3 -m examples.coordination_demo --backend kev --db research-live.sqlite3
```

The fixtures contain Alice's Python data-processing experience, unavailable Bob's Python experience, and available Carol's vague profile. Preprocessing needs Python and dataset access; baseline needs Python, completed preprocessing, and compute; validation needs statistical-validation skills and a completed baseline. The milestone requires validation. A separate documentation task has explicitly empty prerequisite/resource lists so something can proceed while waiting. These are reviewed data, not control-flow branches.

The mock demo checks initial eligibility, shared skill-cache reuse across tasks, readiness, transitive blockers, resource-loss consequences, explicit status corrections, cache persistence after restart, first-answer stopping, and zero-budget uncertainty. It uses real Prolog. Mock scores are fixture labels, not evidence of Kev accuracy.

To populate a working database for natural-language questions:

```bash
python3 -m kb --db research.sqlite3 register config/has_skill.json
python3 -m kb --db research.sqlite3 import-data examples/research_data.json
python3 -m kb --db research.sqlite3 ask 'Who could take over preprocess in October?'
python3 -m kb --db research.sqlite3 ask 'Which tasks are ready to start?'
python3 -m kb --db research.sqlite3 ask 'What is blocking the evaluation complete milestone?'
python3 -m kb --db research.sqlite3 ask 'Which tasks can proceed while dataset D access is unavailable?'
python3 -m kb --db research.sqlite3 ask 'Which milestones are affected if dataset D becomes unavailable?'
python3 -m kb --db research.sqlite3 inspect --rules --semantic
```

The general LLM still translates questions into validated atoms. Unresolved references such as “this experiment” require clarification; no conversational history is presumed. Explicitly named entities are preferable. Teaching profile experience uses `person_profile(Person,Profile)` and retains the full original utterance as evidence. Unsupported teaching is saved as a source note, explicitly excluded from executable knowledge.

The bounded research vocabulary lives in `kb/domains/research.py`; trusted coordination rules live in `kb/domains/research.pl`. `available(Person,Period)` and `unavailable(Person,Period)` deliberately include the planning period. Availability is not permanent or unlimited capacity. `candidate(Person,Task,Period)` requires **all** mandatory skills, not one existentially matching skill. Candidacy does not imply availability of resources, authorization, or assignment.

`task_spec_complete(Task)` explicitly says that all prerequisite tasks, resources, and skills are listed, including empty lists. Missing completeness never establishes readiness or eligibility by absence. `ready(Task)` requires pending status, completed prerequisites, available resources, a complete specification, and no dependency cycle. Status conflicts and missing statuses remain visible. `blocked_by`, `milestone_blocker`, and `affected_milestone` trace known dependency edges with visited-node cycle detection and depth limits. Incomplete reachable specifications make consequence coverage incomplete.

Coordination input predicates require explicit ground updates. Derived coordination predicates are read-only. The original positive rule teaching remains available; taught rules can use `has_skill` in their body. No user-generated Prolog is executed. Python compiles validated terms, Prolog discovers proof plans and grounded semantic requests, and the gateway resolves only the needed requests. There is no persistent Prolog derived-answer cache. Each query rebuilds its snapshot, so removed facts cannot leave stale conclusions.

A raw skill-cache key includes grounded arguments, original profile source hashes/IDs, semantic definition/version, and backend configuration. Changing one profile invalidates only its relevant judgments. Policy-only changes reuse scores. Explicit `has_skill`/`lacks_skill` assertions and human overrides are inspected first; conflicts do not fall through to the model. Overrides use existing assertion provenance and ordinary retraction:

```bash
python3 -m kb --db research.sqlite3 override person:alice skill:python supported \
  --source 'I reviewed Alice’s documented Python work'
# Use --replace a_OLD_SKILL_ASSERTION to supersede one existing skill assertion.
python3 -m kb --db research.sqlite3 retract --id a_ASSERTION_ID 'Retract this skill assertion.'
```

For deterministic query input, `python3 -m kb --db research.sqlite3 query FILE.json` accepts the same validated query-array representation. Both `query` and `ask` accept `--first`, `--judgments`, `--requests`, `--seconds`, `--steps`, `--depth`, `--results`, `--plans`, and `--batch`. Defaults are 12 judgments, 12 HTTP requests, 30 seconds, 200,000 symbolic inferences, depth 32, 100 answers, 500 proof plans, and batches of at most eight judgments. First-answer mode stops semantic evaluation after one supported binding; bounded symbolic discovery can precede that answer.

Supported answers, rejected proof branches, and unresolved candidates are separate. A supported alternative proof establishes an answer even if another proof is unresolved. `complete` reports answer coverage over declared entities and edges; it becomes false on unresolved candidates, incomplete dependency specifications, or limits. No answer probability is invented. Known failed skill requirements prevent spending on unknown skills for that candidate. Batching shares only one person's exact evidence; individual judgments and requests are counted separately.

Test coverage includes the original prototype, multi-skill conjunction, unavailable-person filtering, cross-task/restart cache reuse, profile/definition/model changes, policy reinterpretation, overrides/conflicts, cycles, unknown statuses, incomplete specifications, limits, and alternative proofs. Real Kev and new natural-language translations remain unverified here because local server access is restricted. See [KEV_SETUP.md](KEV_SETUP.md) for setup and acceptance-policy limitations.
