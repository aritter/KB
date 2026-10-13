# Local Kev setup and judgment policy

The KB uses Ollama for natural-language extraction and **Kev's separate decision server** for semantic assessments. It never attempts to serve Kev's pointer head through Ollama.

Interfaces and licenses were inspected on October 12, 2026. Kev's code is Apache-2.0. The [4B model card](https://huggingface.co/jaredpalmer/kev-4b) and [0.8B model card](https://huggingface.co/jaredpalmer/kev-0.8b) identify Apache-2.0 adapters/heads and Qwen3.5 base models. The configured checkpoints are `jaredpalmer/kev-4b@v1.0` and `jaredpalmer/kev-0.8b@v1.0`. Upstream documents 4B on a 32 GB Apple Silicon Mac; that does not establish memory fit alongside your loaded Ollama model. Start with short evidence; unload Ollama when necessary or use 0.8B. See the [model family and release](https://github.com/jaredpalmer/kev/releases/tag/kev-1.0).

Kev requires a **separate Python 3.12/3.13 environment**; this KB can continue using Python 3.14. Install the source repository, not the unrelated PyPI package named `kev`. The [upstream dependency file](https://github.com/jaredpalmer/kev/blob/kev-1.0/pyproject.toml) provides the serving and Apple Silicon extras.

In a directory outside this repository:

```bash
git clone --branch kev-1.0 https://github.com/jaredpalmer/kev.git
cd kev
uv sync --python 3.13 --extra serve
KEV_BACKEND=mlx KEV_DTYPE=bf16 KEV_TRUNCATE_STATES=0 \
  uv run --extra serve python -m kev.serve \
  --run jaredpalmer/kev-4b@v1.0 --host 127.0.0.1 --port 8009
```

For the lightweight alternative, use `--run jaredpalmer/kev-0.8b@v1.0` and select `config/has_skill_08b.json` in this application. The first server start downloads weights. Subsequent inference is local. No weights or new runtime dependencies were installed by this implementation.

Inspect the running server:

```bash
curl http://127.0.0.1:8009/v1/models
```

The adapter checks the reported checkpoint, backend, dtype, temperature, and disabled truncation before scoring. The 4B config pins the full temperature reported by the live server (`2.406050072164233`), not the rounded model-card value `2.41`. The 0.8B config still uses the documented rounded value `2.35`; verify its full value against `/v1/models` before use. A mismatch is a visible backend error; inspect the server and register a configuration matching the intended runtime. `runtime_version` is an operator declaration of the installed code revision; the upstream API does not attest its Git commit. Update that declaration when changing runtime code or serving options. Checkpoint tags are reproducible only while their upstream contents remain unchanged; immutable Hub revisions can also be configured.

The [verified serving interface](https://github.com/jaredpalmer/kev/blob/kev-1.0/kev/serve.py) is `GET /v1/models` and `POST /v1/systemone`. Requests contain a `state`, `model: kev-latest`, and named `choice` questions with `instructions` and `criteria`. The adapter preserves `choice`, `probabilities`, `confidence`, `usage`, and `latency_ms`. In the [answer implementation](https://github.com/jaredpalmer/kev/blob/kev-1.0/kev/api.py), choice confidence is normalized concentration above the uniform baseline; it is **not a probability that our domain assessment is correct**. Acceptance uses the winning probability and runner-up margin, not that confidence field. Scores are never multiplied into a proof probability.

All semantic assessments use `kb/semantic.py`, including administrative messages. The gateway order is explicit assertions/overrides → exact persistent cache → optional registered deterministic evaluator → bounded backend call → audited decision. Raw scores and policy decisions are separate tables. The research skill threshold remains 0.85. Administrative registrations now use the development threshold 0.60; both use margin 0.20. These are **provisional, uncalibrated for these applications**. A policy-only change reinterprets stored raw scores without rescoring; a changed semantic definition/version, relevant evidence, association, or backend configuration changes the raw cache key. Unrelated updates do not.

Backend requests and individual judgment attempts are counted separately. A two-skill batch is two judgments and one scoring request. The initial model-metadata request counts against the request budget too. `model_latency_ms` is Kev-reported shared model time, counted once per batch; `backend_wall_seconds` includes HTTP waiting. Errors are audited and memoized within a query, but may be retried on a later check. No automatic retry loop exists. Exact cache hits remain usable without contacting a stopped server.

Original evidence is retained and passed locally. Oversized evidence produces an explicit unresolved result; nothing is silently truncated. Backend truncation is rejected. An explicit support/contradiction conflict is exposed rather than settled by timestamp. Explicit overrides remain authoritative over cached assessments until retracted; opposing active overrides produce conflict.

**Validation limits:** HTTP contract tests mock the server response. Real requests here fail with the session's localhost `Operation not permitted` restriction. Model quality, full live extraction, simultaneous Mac memory usage, and actual Kev latency remain unverified. The real-attempt reports are not accuracy results. A counting mock is fixture lookup, never a fallback masquerading as Kev.
