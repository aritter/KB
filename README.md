# Editable symbolic KB research prototype

A frozen local LLM translates natural language into a small validated logical language. SQLite persists accepted assertions and their sources. SWI-Prolog derives answers and supporting assertion IDs. The model neither executes code nor supplies the final answer or proof.

**Implementation status:** All 18 deterministic tests pass on Python 3.14.4 and SWI-Prolog 10.0.2 for arm64-darwin, including real inference, corrections, retractions, and fresh-process restart checks. All 10 gold-inference evaluation cases pass. This session has Ollama client 0.35.1, but sandbox restrictions prevent connecting to localhost (`Operation not permitted`). Local-model translations, memory usage, and the full model-driven demo remain **unverified**. Unavailable runtimes are reported explicitly, not counted as successful tests.

## Apple Silicon setup

Use a native Apple Silicon terminal and Python 3.11+. From this repository:

```bash
brew install python swi-prolog
# If Ollama is not already installed:
brew install ollama
# If it is installed but cannot load Qwen3.5, update it:
# brew upgrade ollama

python3 -m venv .venv
source .venv/bin/activate
# No Python runtime packages are required; python -m kb works directly.
```

Start Ollama in a separate terminal if its desktop app/server is not already running:

```bash
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

Then:

```bash
ollama pull qwen3.5:9b-q4_K_M
ollama show qwen3.5:9b-q4_K_M
swipl --version
python3 -m kb doctor
python3 -m unittest discover -s tests -v
python3 examples/demo.py --db demo.sqlite3
```

The demo requires a **new** database path, runs each CLI command in a new process, checks Alice, corrects to Bob, checks Bob twice across process restarts, retracts the renewal requirement, and checks that no notification is derivable. A failed translation or wrong answer stops the demo with an error. The notification rule goes through `teach` and Ollama; no notification rule is preloaded into Prolog.

Optional installation adds the `research-kb` command:

```bash
python3 -m pip install -e .
research-kb --help
```

## Model and runtime configuration

Default: **`qwen3.5:9b-q4_K_M`**, temperature 0, seed 0, `think: false`, 8192 context tokens, 2048 output tokens, nonstreaming `/api/chat`, schema supplied through `format`, 120-second HTTP timeout, five-minute keep-alive. No weights are updated. Seed/temperature settings do not guarantee reproducibility across runtime releases.

The [official Ollama tags](https://ollama.com/library/qwen3.5/tags), checked October 12, 2026, list the 9B Q4_K_M artifact at 6.6 GB (`56671c2ab938`) and 4B Q4_K_M at 3.3 GB (`d8b0f5e9760c`). These are download sizes, not measured RAM requirements. Explicit tags avoid the moving `latest` default, but tags themselves can change; retain `doctor` output with each run to record installed digests and model details. An 8K context and one loaded model are conservative starting settings for a 32 GB Mac; memory fit is not measured here.

To compare the smaller model:

```bash
ollama pull qwen3.5:4b-q4_K_M
python3 -m kb --model qwen3.5:4b-q4_K_M ask 'Who needs to be notified, and about what?'
```

Global CLI options must precede the command: `--db`, `--model`, `--url`, `--swipl`. Environment defaults: `KB_DB`, `KB_MODEL`, `OLLAMA_HOST` (include `http://` for this CLI), `SWIPL`. Only local HTTP endpoints are accepted; no remote model fallback exists.

Runtime support is documented by [Ollama's Qwen3.5 library](https://ollama.com/library/qwen3.5), [chat API](https://docs.ollama.com/api/chat), and [structured-output interface](https://docs.ollama.com/capabilities/structured-outputs). `doctor` checks `/api/version`, `/api/show`, and `/api/tags`; its success establishes endpoint/model availability, not generation correctness. The demo verifies actual generation. A current Ollama release is recommended; no untested minimum version is claimed.

## CLI and required demo

These commands use `knowledge.sqlite3` in the working directory:

```bash
python3 -m kb teach 'Alice manages project P.'
python3 -m kb teach 'Project P uses dataset D.'
python3 -m kb teach 'Dataset D requires renewed authorization.'
python3 -m kb teach 'Anyone who manages a project using a dataset that requires renewed authorization needs to be notified about that dataset.'
python3 -m kb ask 'Who needs to be notified, and about what?'
# Expected binding values: person:alice, dataset:d

python3 -m kb correct 'Bob now manages project P instead of Alice.'
python3 -m kb ask 'Who needs to be notified, and about what?'
# Expected: person:bob, dataset:d; no Alice notification.

# This is another process, with the same durable DB:
python3 -m kb ask 'Who needs to be notified, and about what?'
# Expected: person:bob, dataset:d

python3 -m kb retract 'Retract the requirement that dataset D needs renewed authorization.'
python3 -m kb ask 'Who needs to be notified, and about what?'
# Expected: rows: []; no notification currently derivable.

python3 -m kb inspect --all --events
```

Every response is JSON. Queries return `rows` containing raw `bindings` and `support` assertion IDs, an `answer` generated deterministically from the bindings, a `truncated` flag, the snapshot revision, and separate translation/inference timings. Variable names come from the structured query and may differ across model runs. An empty answer means **not established**, not false.

`inspect` shows assertion IDs, logical representation, original utterance, creation/retraction timestamps, active/retracted status, event ID, and `supersedes` links. `--all` includes retracted records; `--events` includes original correction/retraction utterances and proposals.

For ambiguous updates, inspect and identify the assertion explicitly:

```bash
python3 -m kb correct --id a_REPLACE_WITH_REAL_ID 'Bob now manages project P instead of Alice.'
python3 -m kb retract --id a_REPLACE_WITH_REAL_ID 'Retract this assertion.'
```

Use `--preview` with teach/ask/correct/retract to translate without applying a mutation or executing a query. Re-running without preview performs a new translation; it is not an approval of a saved proposal. Default mutations immediately accept structurally valid model proposals and print them for inspection. **Schema validity is not semantic verification.** Mistakes remain possible; use inspect/correct/retract to revise them. The prompt asks for clarification on ambiguous references and unsupported status for out-of-vocabulary meaning. These are model behaviors measured by the evaluation, not guaranteed by JSON validation.

## Logical subset and schema

Run `python3 -m kb schema` to print the exact JSON Schema. All responses require `status`, `explanation`, `assertions`, `query`, and `targets`, with no extra fields. Status is `ok`, `clarify`, or `unsupported`; non-ok proposals must contain an explanation and no actions.

| Predicate | Ordered argument types | Meaning |
| --- | --- | --- |
| `manages/2` | person, project | Person manages project |
| `uses/2` | project, dataset | Project uses dataset |
| `requires_renewal/1` | dataset | Dataset requires renewed authorization |
| `needs_notification/2` | person, dataset | Person needs notification about dataset |

Constants have canonical lowercase identifiers (`person:alice`, `project:p`, `dataset:d`); variables are explicit `{"var":"Person"}` objects. A rule has a `head` atom and a conjunctive `body` array. An empty body is a ground fact. Example representation (just the assertion part):

```json
{
  "head": {"predicate":"needs_notification", "args":[{"var":"Person"},{"var":"Data"}]},
  "body": [
    {"predicate":"manages", "args":[{"var":"Person"},{"var":"Project"}]},
    {"predicate":"uses", "args":[{"var":"Project"},{"var":"Data"}]},
    {"predicate":"requires_renewal", "args":[{"var":"Data"}]}
  ]
}
```

Only positive, function-free rules are supported. All head variables must appear in the body; repeated variables must have compatible argument types. Queries are positive conjunctions with all named variables returned. No negation, disjunction, arbitrary predicates, built-ins, arithmetic, functions, or executable model text are accepted. `schema.py` implements and validates the small closed schema using the standard library; it is not a general-purpose JSON Schema library.

Bounds: eight assertions per input, six body/query atoms, twelve variables, 1000 active assertions, 5000 derived ground atoms, 100 returned bindings, three seconds for closure plus query, six seconds subprocess wall time, and a 256 MB Prolog stack limit. Reaching a closure/time limit returns an error, never a misleading empty or partial answer. Result overflow is explicitly marked with `truncated: true`.

## Implementation and update behavior

- `kb/schema.py`: vocabulary, schemas, typing, range restriction, and operation validation.
- `kb/llm.py`: stateless local HTTP adapter, predicate definitions and examples, bounded candidate context.
- `kb/store.py`: SQLite assertions and events; atomic updates with optimistic revision checks.
- `kb/prolog.py` / `kb/engine.pl`: deterministic term compilation and positive forward chaining in SWI-Prolog.
- `kb/service.py` / `kb/cli.py`: orchestration and CLI.

Candidates are selected by exact entity-name tokens or explicit assertion ID, limited to twelve records and a 6000-character user/context envelope. Full conversation history and full KB are never inserted into the model prompt. A broad question can translate from the predicate definitions without any assertion candidates. Candidate retrieval currently scans the active SQLite records in Python; the cap is on model context, not lookup cost. Ambiguous updates exceeding the candidate cap require an explicit ID.

Every mutation uses one `BEGIN IMMEDIATE` SQLite transaction: retract the single target, insert replacements, store the event, increment the revision, commit. Failure rolls back the entire change. A concurrent mutation during translation causes a retry error. Queries read an atomic committed snapshot; an in-flight query may finish on the snapshot preceding another process's correction and reports its revision.

Teaching two managers preserves both. `correct` explicitly supersedes one identified assertion; it does not guess global uniqueness constraints or prefer the newest fact. Corrections to rules use the same mechanism. Retracted records and source events remain available for audit. Duplicate statements are retained as independent assertions; retracting one does not remove another source of the same fact.

Each ask rebuilds a fresh Prolog process from the durable active snapshot. The engine treats generated terms as data, performs finite positive closure, and records the first supporting proof for each ground atom. No tabling or cached conclusions survive a query, update, or restart. Cyclic positive rules terminate at a fixed point (or an explicit resource error). Proof output is a set of supporting fact/rule IDs, not a full proof tree or all alternative proofs. SWI interfaces used: [call_with_time_limit/2](https://www.swi-prolog.org/pldoc/man?predicate=call_with_time_limit%2F2) and [findnsols/4](https://www.swi-prolog.org/pldoc/man?predicate=findnsols%2F4), wrapped with `once/1` for a single bounded result batch.

## Validation and local-model evaluation

```bash
python3 -m unittest discover -s tests -v
python3 -m evaluation.run --model qwen3.5:9b-q4_K_M --output evaluation/9b.json
python3 -m evaluation.run --model qwen3.5:4b-q4_K_M --output evaluation/4b.json
python3 examples/demo.py --model qwen3.5:9b-q4_K_M --db fresh-demo.sqlite3
```

The deterministic suite covers schema rejection, unsafe/non-ground rules, type mismatches, source persistence, learned rule storage, explicit corrections, retractions, transaction rollback, stale revision rejection, and restarts. Four additional SWI integration tests cover the complete update sequence with a fresh Python subprocess, provenance, multi-step inference, cycles, closure/result limits, and unknown/boolean queries. These skip explicitly when SWI is missing. Ollama adapter tests use mocked HTTP responses and do not establish model quality.

The twelve-case live evaluation separates **translation** failures (invalid JSON/schema or wrong extracted meaning) from **inference** failures (wrong answer for a gold logical query/update). It covers fact/rule/question paraphrases, multi-step inference, unknown answers, corrections, retractions, ambiguity, and unsupported negation. Each case starts from isolated gold fixtures; semantics are compared modulo variable renaming and conjunction order. Gold inference runs independently of the model, so a translation failure cannot masquerade as an inference failure. Predicted ask queries are additionally executed when semantically correct. The separate demo measures the entire model-driven sequence without substituting gold fixtures.

Results include wall-clock translation and inference attempt latency, token counts when available, proposals, model details, and distinct status counters. Unavailable runtimes are not included as successes or meaning failures. `evaluation/local.json` contains the actual attempted run here: **12 translations unavailable, 10 gold-inference cases passed, 2 inference cases not applicable**. Gold inference takes approximately 17 ms median on these tiny fixtures (see the report for the exact latest measurement), including SWI process startup. Translation accuracy and model latency remain unknown; failed preflight duration is not model latency.

## Limitations and next experiment

This is deliberately a small research prototype. Lexical entity matching misses aliases and pronouns; canonicalization can merge same-named entities. Semantic errors and prompt-induced mistranslations may pass structural validation. There is no explicit negation, temporal state, confidence, contradiction solver, authentication, encryption, autonomous ontology expansion, UI, or ontology import. Inference recomputes the complete active closure; large joins can reach limits. Historical assertions/events are not size-capped, and SQLite candidate scanning is linear. Changes are structurally validated before commit; inference capacity is checked at query time, so an expensive but valid rule can be stored and later retracted after a query limit error.

Next experiment: run both quantizations on the same labeled paraphrase/update set, then expand it with ambiguous names, competing sources, omitted rule conditions, and adversarial instructions. Compare semantic translation accuracy and clarification rate separately from symbolic accuracy, and record warm/cold latency plus peak Mac memory. The likely next improvement is an explicit entity/alias registry and reviewable saved proposals, before expanding the predicate vocabulary. New predicates should be added deliberately to the typed registry, descriptions, schemas, tests, and storage migration policy; the Prolog term interpreter is vocabulary-independent.

Python runtime dependencies are standard-library only. This code is MIT licensed. [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) declares Apache-2.0; [Ollama](https://github.com/ollama/ollama/blob/main/LICENSE) uses MIT; [SWI-Prolog](https://www.swi-prolog.org/license.html) describes its BSD licensing and component details. No paid service is required.
