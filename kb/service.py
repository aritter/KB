import time
from .schema import Invalid


def execute(store, translator, engine, operation, text, target_id=None, preview=False):
    revision, candidates, overflow = store.candidates(text, target_id)
    if operation in {"correct", "retract"} and overflow:
        raise Invalid("Too many matching assertions. Inspect and supply --id to identify one.")
    result, metrics = translator.translate(operation, text, candidates, target_id)
    response = {"proposal": result, "metrics": metrics, "candidate_count": len(candidates),
                "semantic_verification": "Model extraction; inspect source and proposal for meaning errors."}
    if result["status"] != "ok" or preview:
        return response
    if operation == "ask":
        revision, records = store.snapshot()
        started = time.perf_counter()
        response.update(engine.ask(records, result["query"]))
        metrics["inference_seconds"] = time.perf_counter() - started
        response["revision"] = revision
    else:
        response.update(store.apply(operation, text, result, revision, [r["id"] for r in candidates]))
    return response
