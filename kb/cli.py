import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
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
    # Coordination query options share the existing ask/translation path.
    ask = sub.choices['ask']
    ask.add_argument('--coordination', action='store_true')
    ask.add_argument('--first', action='store_true')
    for name, default, kind in [('judgments',12,int),('requests',12,int),('seconds',30,float),
                               ('steps',200000,int),('depth',32,int),('results',100,int),('plans',500,int),('batch',8,int)]:
        ask.add_argument('--'+name, type=kind, default=default)
    reg = sub.add_parser('register')
    reg.add_argument('file')
    ov = sub.add_parser('override')
    ov.add_argument('person')
    ov.add_argument('skill')
    ov.add_argument('status', choices=['supported','contradicted'])
    ov.add_argument('--source', required=True)
    ov.add_argument('--replace', help='Explicit prior assertion ID to supersede')
    imp = sub.add_parser('import-data')
    imp.add_argument('file', help='Reviewed JSON list of {source, assertion} records')
    imp.add_argument('--source', default='Reviewed domain data import')
    direct = sub.add_parser('query')
    direct.add_argument('file', help='Validated query JSON array; bypasses NL translation only')
    direct.add_argument('--first',action='store_true')
    for name, default, kind in [('judgments',12,int),('requests',12,int),('seconds',30,float),
                               ('steps',200000,int),('depth',32,int),('results',100,int),('plans',500,int),('batch',8,int)]:
        direct.add_argument('--'+name,type=kind,default=default)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--all", action="store_true", help="Include retracted assertions")
    inspect.add_argument("--events", action="store_true")
    inspect.add_argument("--semantic", action="store_true")
    inspect.add_argument("--rules", action="store_true")
    sub.add_parser("doctor")
    sub.add_parser("schema")
    from .admin_cli import add_parser
    add_parser(sub)
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
            if args.command == 'admin':
                from .admin_cli import dispatch
                result=dispatch(store,args,Ollama(args.model,args.url))
            elif args.command == 'register':
                from .semantic import register
                result = {'definition_id':register(store,json.loads(Path(args.file).read_text()))}
            elif args.command == 'override':
                from .schema import atom, assertion, proposal
                item = assertion(atom('has_skill' if args.status=='supported' else 'lacks_skill',args.person,args.skill))
                revision, rows = store.snapshot()
                targets = [args.replace] if args.replace else []
                if targets:
                    target=next((r for r in rows if r['id']==args.replace),None)
                    if not target or target['assertion']['head']['predicate'] not in {'has_skill','lacks_skill'} or target['assertion']['head']['args'] != item['head']['args']:
                        raise Invalid('--replace must identify an active skill assertion for this person and skill')
                result = store.apply('correct' if targets else 'teach', args.source,
                                     proposal([item],targets=targets), revision, targets)
            elif args.command == 'import-data':
                result = store.import_records(json.loads(Path(args.file).read_text()),args.source)
            elif args.command == 'query':
                from .coordination import Coordination
                from .semantic import Budget
                revision, records = store.snapshot()
                budget=Budget(**{k:getattr(args,k) for k in ('judgments','requests','seconds','steps','depth','results','plans','batch')})
                result=Coordination(store,budget,args.first,executable=args.swipl).ask(records,json.loads(Path(args.file).read_text()))
                result['revision']=revision
            elif args.command == "inspect":
                revision, records = store.snapshot(not args.all)
                result = {"revision": revision, "assertions": records}
                if args.events:
                    result["events"] = store.events()
                result['source_notes'] = [dict(r) for r in store.db.execute('SELECT * FROM source_notes')]
                if args.rules:
                    result['coordination_rules'] = (Path(__file__).parent/'domains/research.pl').read_text()
                if args.semantic:
                    for table in ('semantic_definitions','raw_judgments','judgment_decisions'):
                        result[table]=[dict(r) for r in store.db.execute('SELECT * FROM '+table)]
            else:
                engine=Prolog(args.swipl)
                if args.command=='ask':
                    from .coordination import AutoEngine
                    from .semantic import Budget
                    budget=Budget(**{k:getattr(args,k) for k in ('judgments','requests','seconds','steps','depth','results','plans','batch')})
                    engine=AutoEngine(store,engine,budget,args.first,args.coordination)
                result = execute(store, Ollama(args.model, args.url), engine,
                    args.command, args.text, getattr(args, "target_id", None), args.preview)
        print(json.dumps(result, indent=2))
        return 0
    except (Invalid, InferenceError, RuntimeUnavailable, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        error = {"error": str(exc), "type": type(exc).__name__}
        if hasattr(exc, "rejected_proposal"):
            error["rejected_proposal"] = exc.rejected_proposal
        print(json.dumps(error), file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()
