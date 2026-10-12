import argparse
import json
import os
import shutil
import sqlite3
import sys
from .llm import Ollama, DEFAULT_MODEL
from .prolog import Prolog, InferenceError, RuntimeUnavailable
from .schema import Invalid, SCHEMA
from .service import execute
from .store import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local editable symbolic research KB")
    parser.add_argument("--db", default=os.getenv("KB_DB", "knowledge.sqlite3"))
    parser.add_argument("--model", default=os.getenv("KB_MODEL", DEFAULT_MODEL))
    parser.add_argument("--url", default=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--swipl", default=os.getenv("SWIPL", "swipl"))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("teach", "ask", "correct", "retract"):
        cmd = sub.add_parser(name)
        cmd.add_argument("text")
        cmd.add_argument("--preview", action="store_true", help="Translate and validate without applying or querying")
        if name in {"correct", "retract"}:
            cmd.add_argument("--id", dest="target_id")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--all", action="store_true", help="Include retracted assertions")
    inspect.add_argument("--events", action="store_true")
    sub.add_parser("doctor")
    sub.add_parser("schema")
    args = parser.parse_args(argv)
    store = None
    try:
        if args.command == "schema":
            result = SCHEMA
        elif args.command == "doctor":
            result = {"swipl": shutil.which(args.swipl), "configured_model": args.model}
            try:
                result["ollama"] = Ollama(args.model, args.url).doctor()
            except RuntimeUnavailable as exc:
                result["ollama_error"] = str(exc)
            print(json.dumps(result, indent=2))
            return 0 if result["swipl"] and "ollama_error" not in result else 2
        else:
            store = Store(args.db)
            if args.command == "inspect":
                revision, records = store.snapshot(not args.all)
                result = {"revision": revision, "assertions": records}
                if args.events:
                    result["events"] = store.events()
            else:
                result = execute(store, Ollama(args.model, args.url), Prolog(args.swipl),
                    args.command, args.text, getattr(args, "target_id", None), args.preview)
        print(json.dumps(result, indent=2))
        return 0
    except (Invalid, InferenceError, RuntimeUnavailable, OSError, sqlite3.Error) as exc:
        error = {"error": str(exc), "type": type(exc).__name__}
        if hasattr(exc, "rejected_proposal"):
            error["rejected_proposal"] = exc.rejected_proposal
        print(json.dumps(error), file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()
