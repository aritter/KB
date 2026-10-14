"""Incremental administrative refresh: dependency signatures, immutable history, bounded reads."""
import copy
import json
import time
from pathlib import Path
from .schema import Invalid
from .semantic import Budget, digest, encoded, now

RULE_VERSION = 'incremental-admin-v1'
EXTRACTION_VERSION = 'admin-extract-v5'


def install(store):
    store.db.executescript('''
    CREATE TABLE IF NOT EXISTS evidence_catalog (
      id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, version TEXT NOT NULL,
      previous_id TEXT, bytes INTEGER NOT NULL, extraction_version TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS evidence_content ON evidence_catalog(content_hash);
    CREATE TABLE IF NOT EXISTS import_keys (key TEXT PRIMARY KEY, source_id TEXT NOT NULL, result TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS extraction_runs (
      id TEXT PRIMARY KEY, source_id TEXT NOT NULL, model TEXT NOT NULL,
      prompt_version TEXT NOT NULL, schema_version TEXT NOT NULL, seconds REAL NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS conclusion_cache (
      request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, row TEXT NOT NULL, dependencies TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS conclusion_history (
      id TEXT PRIMARY KEY, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      as_of TEXT NOT NULL, dependencies TEXT NOT NULL, row TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS alert_history (
      id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, as_of TEXT NOT NULL,
      transition TEXT NOT NULL, flags TEXT NOT NULL, conclusion_id TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS refresh_runs (
      id TEXT PRIMARY KEY, as_of TEXT NOT NULL, metrics TEXT NOT NULL, unresolved TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS admin_event_request ON admin_events(request_id,type,valid_from);
    CREATE INDEX IF NOT EXISTS admin_event_source ON admin_events(source_id,type);
    CREATE INDEX IF NOT EXISTS admin_event_time ON admin_events(valid_from,retracted_at);
    CREATE INDEX IF NOT EXISTS admin_message_time ON admin_messages(received_at);
    ''')


def import_key(text, at, request, kind, supersedes):
    return digest({'text': text, 'at': at, 'request': request, 'kind': kind, 'supersedes': supersedes})


def duplicate(store, key):
    row = store.db.execute('SELECT result FROM import_keys WHERE key=?', (key,)).fetchone()
    if row:
        return {**json.loads(row['result']), 'duplicate': True, 'new_extractions': 0}


def record_source(store, source, text, previous=None, version=EXTRACTION_VERSION):
    hashed = digest(text)
    store.db.execute('INSERT OR IGNORE INTO evidence_catalog VALUES(?,?,?,?,?,?)',
                     (source, hashed, hashed, previous, len(text.encode()), version))


def archive(store, text, at, kind='message'):
    """Store unprocessed local evidence, including long text. No extraction is implied."""
    from . import admin
    admin.install(store)
    at = admin.utc(at)
    if not isinstance(text,str) or not text.strip() or len(text.encode()) > 1_000_000:
        raise Invalid('Archive requires 1–1000000 UTF-8 bytes')
    key = import_key(text, at, None, kind, None)
    known = duplicate(store, key)
    if known: return known
    sid = admin.ident('m_')
    result = {'source_id': sid, 'incorporated': False, 'archived': True, 'duplicate': False}
    with store.db:
        store.db.execute('INSERT INTO admin_messages VALUES(?,?,?,?,?,?,?,?)',
                         (sid,text,at,now(),kind,encoded({'status':'unsupported','explanation':'Archived; extraction not requested.'}),None,None))
        record_source(store,sid,text,version='unprocessed')
        store.db.execute('INSERT INTO import_keys VALUES(?,?,?)',(key,sid,encoded(result)))
    return result


def dependencies(store, request, cutoff, events, messages, definitions, rule_hash):
    """Includes membership, not just documents read: new evidence invalidates absence."""
    own = [e for e in events if e['request_id'] == request]
    ids = sorted({e['payload']['message_id'] for e in own if e['type']=='association'})
    docs = [dict(messages[mid]) for mid in ids if mid in messages]
    # Only fields used in derivation participate. Ingestion time is not semantic evidence.
    docs = [{k:m[k] for k in ('id','text','kind','received_at','superseded_at')} for m in docs]
    overrides = [dict(r) for r in store.db.execute('SELECT * FROM semantic_overrides WHERE created_at<=? AND (retracted_at IS NULL OR retracted_at>?)',(cutoff,cutoff))
                 if any('message:'+mid in json.loads(r['arguments']) for mid in ids)]
    resources = {e['payload']['value'] for e in own if e['type']=='affects_resource'}
    research = []
    if resources:
        for row in store.snapshot()[1]:
            if any(t.get('const') in resources for t in row['assertion']['head']['args']): research.append(row)
    return {'rule_version':RULE_VERSION, 'rule_hash':rule_hash, 'request_events':own,
            'collection':{'query':'active associations for request', 'request_id':request, 'members':ids,
                          'fingerprint':digest(docs)},
            'sources':[{'id':m['id'],'hash':digest(m)} for m in docs],
            'definitions':definitions,'overrides':overrides,'research':research}


def snapshot(store, cutoff):
    with store.db:
        store.db.execute('BEGIN')
        events = [dict(r,payload=json.loads(r['payload'])) for r in store.db.execute(
            'SELECT * FROM admin_events WHERE valid_from<=? AND (retracted_at IS NULL OR retracted_at>?) ORDER BY rowid',(cutoff,cutoff))]
        messages = {r['id']:dict(r) for r in store.db.execute('SELECT * FROM admin_messages WHERE received_at<=?',(cutoff,))}
    return events,messages


def refresh(store, as_of, *, budget=None, max_requests=100, clock_only=False, request_ids=None,
            mode='incremental', backend_factory=None, executable='swipl', zone='America/New_York'):
    from . import admin
    admin.install(store)
    if not 1 <= max_requests <= 1000: raise Invalid('max_requests must be 1–1000')
    if mode not in {'incremental','full'}: raise Invalid('Unknown refresh mode')
    budget = budget or Budget(judgments=32,requests=40,seconds=60)
    if clock_only: budget.judgments=budget.requests=0
    cutoff = admin.utc(as_of, zone)
    events,messages = snapshot(store,cutoff)
    roots = sorted({e['request_id'] for e in events if e['type']=='request'})
    if request_ids is not None:
        if not isinstance(request_ids,list) or not all(isinstance(r,str) for r in request_ids): raise Invalid('Request IDs must be a list')
        unknown=set(request_ids)-set(roots)
        if unknown: raise Invalid('Unknown request IDs: '+', '.join(sorted(unknown)))
        # Include prerequisites under the same candidate/depth caps.
        selected=set(request_ids); frontier=list(selected)
        for _ in range(budget.depth):
            following={e['payload']['request_id'] for e in events if e['type']=='dependency' and e['request_id'] in frontier} - selected
            if not following: break
            selected |= following; frontier=list(following)
        else: budget.stopping.add('dependency_depth_limit')
        roots=[r for r in roots if r in selected]
    skipped=roots[max_requests:];roots=roots[:max_requests]
    if skipped: budget.stopping.add('candidate_request_limit')
    definitions=[dict(r) for r in store.db.execute('SELECT id,name,document FROM semantic_definitions WHERE active=1 ORDER BY name')
                 if r['name'] in admin.SEMANTICS]
    rule_hash=digest((Path(__file__).parent/'domains/admin.pl').read_text()+ (Path(__file__).parent/'admin.py').read_text())
    prepared={};cached={};invalidations=[]
    for rid in roots:
        dep=dependencies(store,rid,cutoff,events,messages,definitions,rule_hash)
        root=next(e for e in events if e['request_id']==rid and e['type']=='request')
        dep['template_id']=root['payload']['template_id']
        fingerprint=digest(dep);prepared[rid]=(fingerprint,dep)
        old=store.db.execute('SELECT * FROM conclusion_cache WHERE request_id=?',(rid,)).fetchone()
        if mode=='incremental' and old and old['fingerprint']==fingerprint:
            row=json.loads(old['row'])
            if not any(j['status'] in {'backend_error','not_evaluated_budget'} for j in row['judgments']):
                cached[rid]=row
        if old and old['fingerprint']!=fingerprint:
            olddep=json.loads(old['dependencies'])
            invalidations.append({'request_id':rid,'changed_dependencies':[k for k in dep if dep[k]!=olddep.get(k)]})
    started=time.monotonic()
    result=admin.report(store,as_of,zone=zone,budget=budget,backend_factory=backend_factory,executable=executable,
                        request_ids=roots,cached_rows=cached,force_models=mode=='full',snapshot_data=(events,messages))
    unresolved=[{'request_id':rid,'reason':'candidate_request_limit'} for rid in skipped]
    unresolved += [{'request_id':r['request_id'],**j} for r in result['requests'] for j in r['unresolved_assessments']]
    metrics={**result['metrics'],'candidate_requests':len(roots)+len(skipped),'reused_conclusions':len(cached),
             'recomputed_requests':len(roots)-len(cached),'invalidations':len(invalidations),
             'processed_evidence':sum(len(prepared[r][1]['collection']['members']) for r in roots if r not in cached),
             'refresh_seconds':time.monotonic()-started}
    result.update(metrics=metrics,invalidations=invalidations,unresolved_checks=unresolved,mode=mode)
    result['complete']=result['complete'] and not unresolved
    result['all_clear']=result['complete'] and not result['attention']
    ridrun=admin.ident('refresh_')
    with store.db:
        for row in result['requests']:
            fingerprint,dep=prepared[row['request_id']]
            # Parent conclusions depend on prerequisite conclusions as well as own evidence.
            dep=copy.deepcopy(dep)
            dep['dependent_requests']={r:prepared[r][0] if r in prepared else 'not_observed_or_skipped' for r in row['dependencies']}
            record={'fingerprint':fingerprint,'as_of':result['as_of'],'row':row,'dependencies':dep}
            cid='conclusion_'+digest(record)
            latest=store.db.execute('SELECT row FROM conclusion_history WHERE request_id=? ORDER BY rowid DESC LIMIT 1',(row['request_id'],)).fetchone()
            old_flags=json.loads(latest['row'])['flags'] if latest else []
            # New judgment IDs alone are not a change in the alert condition.
            flag_state=lambda flags: [{k:v for k,v in f.items() if k!='support'} for f in flags]
            if flag_state(old_flags)!=flag_state(row['flags']):
                transition='withdrawn' if not row['flags'] else ('raised' if not old_flags else 'changed')
                store.db.execute('INSERT INTO alert_history(request_id,as_of,transition,flags,conclusion_id,created_at) VALUES(?,?,?,?,?,?)',
                                 (row['request_id'],result['as_of'],transition,encoded(row['flags']),cid,now()))
            store.db.execute('INSERT OR IGNORE INTO conclusion_history VALUES(?,?,?,?,?,?,?)',
                             (cid,row['request_id'],fingerprint,result['as_of'],encoded(dep),encoded(row),now()))
            store.db.execute('INSERT OR REPLACE INTO conclusion_cache VALUES(?,?,?,?,?)',
                             (row['request_id'],fingerprint,encoded(row),encoded(prepared[row['request_id']][1]),now()))
            row['conclusion_id']=cid
        store.db.execute('INSERT INTO refresh_runs VALUES(?,?,?,?,?)',(ridrun,result['as_of'],encoded(metrics),encoded(unresolved),now()))
    result['refresh_id']=ridrun
    return result
