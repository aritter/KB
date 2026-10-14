"""Administrative commands in the existing CLI; no network except local model APIs."""
import json
from pathlib import Path
from . import admin
from .schema import Invalid
from .semantic import encoded,now


def add_parser(sub):
    parser=sub.add_parser('admin');commands=parser.add_subparsers(dest='admin_command',required=True)
    template=commands.add_parser('template');template.add_argument('file')
    setup=commands.add_parser('configure');setup.add_argument('backend_file',help='JSON backend config or has_skill definition containing backend')
    ingest=commands.add_parser('ingest')
    text=ingest.add_mutually_exclusive_group(required=True);text.add_argument('--text');text.add_argument('--file')
    ingest.add_argument('--request');ingest.add_argument('--new',action='store_true');ingest.add_argument('--template')
    ingest.add_argument('--at',required=True);ingest.add_argument('--timezone',default='America/New_York')
    ingest.add_argument('--kind',choices=['message','confirmation'],default='message')
    ingest.add_argument('--extraction',help='Reviewed extraction JSON; explicitly bypasses the LLM')
    ingest.add_argument('--supersedes',help='Prior source message ID being explicitly replaced')
    check=commands.add_parser('check');check.add_argument('--as-of',required=True);check.add_argument('--timezone',default='America/New_York')
    check.add_argument('--judgments',type=int,default=32);check.add_argument('--requests',type=int,default=32);check.add_argument('--seconds',type=float,default=60)
    refresh=commands.add_parser('refresh',help='Incremental workflow check with persisted conclusion and alert history')
    refresh.add_argument('--as-of',required=True);refresh.add_argument('--timezone',default='America/New_York')
    refresh.add_argument('--clock-only',action='store_true',help='No model calls; unresolved assessments remain explicit')
    refresh.add_argument('--mode',choices=['incremental','full'],default='incremental')
    refresh.add_argument('--request',action='append',dest='request_ids')
    refresh.add_argument('--max-requests',type=int,default=100)
    refresh.add_argument('--judgments',type=int,default=32);refresh.add_argument('--requests',type=int,default=40)
    refresh.add_argument('--seconds',type=float,default=60)
    history=commands.add_parser('history');history.add_argument('request')
    inspect=commands.add_parser('inspect');inspect.add_argument('request',nargs='?')
    change=commands.add_parser('set');change.add_argument('request');change.add_argument('field');change.add_argument('value')
    change.add_argument('--basis',choices=['documented','user_preference','tentative'],default='user_preference');change.add_argument('--supersedes')
    retract=commands.add_parser('retract');retract.add_argument('event')
    associate=commands.add_parser('associate');associate.add_argument('message');associate.add_argument('request')
    override=commands.add_parser('override');override.add_argument('predicate',choices=list(admin.SEMANTICS));override.add_argument('message');override.add_argument('subject');override.add_argument('status',choices=['supported','contradicted']);override.add_argument('--replace')
    for p in (change,retract,associate,override):
        p.add_argument('--source',required=True);p.add_argument('--at',required=True);p.add_argument('--timezone',default='America/New_York')


def dispatch(store,args,translator):
    admin.install(store);cmd=args.admin_command
    if cmd=='template':return {'template_id':admin.template_register(store,json.loads(Path(args.file).read_text()))}
    if cmd=='configure':
        config=json.loads(Path(args.backend_file).read_text());return {'definitions':admin.configure_semantics(store,config.get('backend',config))}
    if cmd=='ingest':
        text=args.text if args.text is not None else Path(args.file).read_text()
        extraction=json.loads(Path(args.extraction).read_text()) if args.extraction else None
        return admin.ingest(store,text,args.at,args.kind,args.request,args.new,args.template,extraction,translator,args.supersedes,args.timezone)
    if cmd=='check':
        from .semantic import Budget
        return admin.report(store,args.as_of,args.timezone,Budget(judgments=args.judgments,requests=args.requests,seconds=args.seconds),executable=args.swipl)
    if cmd=='refresh':
        from .incremental import refresh
        from .semantic import Budget
        return refresh(store,args.as_of,zone=args.timezone,clock_only=args.clock_only,
                       request_ids=args.request_ids,max_requests=args.max_requests,mode=args.mode,
                       budget=Budget(judgments=args.judgments,requests=args.requests,seconds=args.seconds),
                       executable=args.swipl)
    if cmd=='history':
        return {table:[dict(r) for r in store.db.execute(
            'SELECT * FROM '+table+' WHERE request_id=? ORDER BY rowid',(args.request,))]
                for table in ('conclusion_history','alert_history')}
    if cmd=='set':return admin.manual_event(store,args.request,args.field,args.value,args.source,args.at,args.supersedes,args.timezone,args.basis)
    if cmd=='associate':return admin.associate(store,args.message,args.request,args.source,args.at,args.timezone)
    if cmd=='override':
        from .schema import atom,check_schema,ATOM
        check_schema(atom(args.predicate,args.message,args.subject),ATOM)
        at=admin.utc(args.at,args.timezone);key=admin.ident('o_')
        with store.db:
            if args.replace:
                old=store.db.execute('SELECT * FROM semantic_overrides WHERE id=?',(args.replace,)).fetchone()
                if not old or old['retracted_at'] or old['predicate']!=args.predicate or old['arguments']!=encoded([args.message,args.subject]):raise Invalid('Override replacement must match predicate and arguments')
                store.db.execute('UPDATE semantic_overrides SET retracted_at=? WHERE id=?',(at,args.replace))
            store.db.execute('INSERT INTO semantic_overrides VALUES(?,?,?,?,?,?,?)',(key,args.predicate,encoded([args.message,args.subject]),args.status,args.source,at,None))
        return {'override_id':key}
    if cmd=='retract':
        if args.event.startswith('o_'):
            at=admin.utc(args.at,args.timezone)
            with store.db:
                count=store.db.execute('UPDATE semantic_overrides SET retracted_at=? WHERE id=? AND retracted_at IS NULL',(at,args.event)).rowcount
                if count!=1:raise Invalid('Active override not found')
                store.note(args.source,'Retraction of semantic override '+args.event)
            return {'retracted':args.event}
        return admin.retract_event(store,args.event,args.source,args.at,args.timezone)
    if cmd=='inspect':
        events=[dict(r) for r in store.db.execute('SELECT * FROM admin_events'+(' WHERE request_id=?' if args.request else ''),(args.request,) if args.request else ())]
        mids={r['source_id'] for r in events}
        return {'events':events,'messages':[dict(r) for r in store.db.execute('SELECT * FROM admin_messages') if not args.request or r['id'] in mids],
                'templates':[dict(r) for r in store.db.execute('SELECT * FROM workflow_templates')],
                'semantic_overrides':[dict(r) for r in store.db.execute('SELECT * FROM semantic_overrides')]}
    raise Invalid('Unknown admin command')
