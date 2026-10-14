"""Small validated plans over durable evidence. No generated code or raw Prolog."""
import json
import time
from .schema import Invalid, obj, array, check_schema
from .semantic import Budget, Gateway, digest, encoded, now, definition
from . import admin
from . import incremental

TEXT={'type':'string','maxLength':120}
OPS = {
 'find_requests': {'request_id':TEXT, 'responsible':TEXT},
 'evidence_metadata': {'request_id':TEXT},
 'read_excerpt': {'evidence_id':TEXT, 'offset':{'type':'integer'}, 'length':{'type':'integer'}},
 'extract': {'evidence_id':TEXT,'request_id':TEXT},
 'semantic': {'evidence_id':TEXT,'request_id':TEXT,'predicate':{'enum':list(admin.SEMANTICS)}},
 'query': {'request_id':TEXT},
 'explain': {'conclusion_id':TEXT},
}
PLAN_SCHEMA=obj({'steps':array({'oneOf':[obj({'op':{'const':name},'args':obj(fields)}) for name,fields in OPS.items()]},1,6)})


def validate_plan(plan):
    check_schema(plan,PLAN_SCHEMA)
    for step in plan['steps']:
        a=step['args']
        if step['op']=='read_excerpt':
            if type(a['offset']) is not int or a['offset']<0 or type(a['length']) is not int or not 1<=a['length']<=3000:
                raise Invalid('Excerpt offset must be nonnegative and length 1–3000 characters')
        if step['op'] in {'extract','semantic','query'} and not a['request_id']:
            raise Invalid('Operation requires an explicit request ID')
    return plan


def compact_request(row):
    return {k:row[k] for k in ('request_id','owner','responsible','desired_outcome','progress','verification',
                               'dates','flags','missing_evidence','discrepancies','conclusion_id')}


class BoundedTranslator:
    """Count Qwen calls against the same request and wall budget as Kev calls."""
    def __init__(self, translator, budget):
        self.translator,self.budget=translator,budget
        self.model=translator.model
    def request(self, endpoint, data=None):
        if not self.budget.permit(0,1):raise Invalid('Qwen budget exhausted')
        self.budget.metrics['backend_requests']+=1
        self.budget.metrics['backend_calls']+=1
        self.budget.metrics['qwen_calls']=self.budget.metrics.get('qwen_calls',0)+1
        before=time.monotonic()
        old=getattr(self.translator,'timeout',120)
        self.translator.timeout=min(old,self.budget.remaining())
        try:
            result=self.translator.request(endpoint,data)
            if self.budget.remaining()<=0:raise Invalid('Qwen response exceeded wall budget')
            return result
        finally:
            self.translator.timeout=old
            self.budget.metrics['qwen_wall_seconds']=self.budget.metrics.get('qwen_wall_seconds',0)+(time.monotonic()-before)


def source(store, evidence_id):
    row=store.db.execute('SELECT * FROM admin_messages WHERE id=?',(evidence_id,)).fetchone()
    if not row:raise Invalid('Unknown evidence ID')
    return dict(row)


def find_requests(store, cutoff, request_id='', responsible='', limit=12):
    # Both filters use indexed events; no evidence bodies are sent to Qwen.
    sql="SELECT DISTINCT r.request_id FROM admin_events r WHERE r.type='request' AND r.valid_from<=? AND (r.retracted_at IS NULL OR r.retracted_at>?)"
    params=[cutoff,cutoff]
    if request_id:sql+=' AND r.request_id=?';params.append(request_id)
    if responsible:
        sql+=" AND EXISTS(SELECT 1 FROM admin_events p WHERE p.request_id=r.request_id AND p.type='responsible' AND json_extract(p.payload,'$.value')=? AND p.valid_from<=? AND (p.retracted_at IS NULL OR p.retracted_at>?))"
        params.extend([responsible,cutoff,cutoff])
    ids=[r[0] for r in store.db.execute(sql+' ORDER BY r.request_id LIMIT ?',(*params,limit+1))]
    return {'requests':[{'request_id':r} for r in ids[:limit]],'complete':len(ids)<=limit}


def propose(store, text, as_of, translator, budget):
    if not isinstance(text,str) or not 1<=len(text)<=3000:raise Invalid('Question must be 1–3000 characters')
    metadata=find_requests(store,admin.utc(as_of))
    prompt='''Plan a bounded local administrative query using the supplied operation schema.
Use only known IDs. You may find requests, list evidence metadata, read bounded excerpts,
request extraction drafts, request registered semantic assessments, run the approved query
(which refreshes one request through Prolog), or retrieve a recorded explanation.
No arbitrary code, raw Prolog, mutation of assertions, or new predicate creation.
Return steps with literal IDs, not invented IDs or references to future results.
If more discovery is needed, return only discovery steps; the user can refine the query.
find_requests empty filters list up to 12 request IDs. Unknown/missing evidence is not false.
'''
    response=BoundedTranslator(translator,budget).request('/api/chat',{'model':translator.model,
        'messages':[{'role':'system','content':prompt},{'role':'user','content':encoded({'question':text,'as_of':as_of,'metadata':metadata})}],
        'format':PLAN_SCHEMA,'stream':False,'think':False,'options':{'temperature':0,'num_ctx':4096,'num_predict':1200}})
    if response.get('done_reason')=='length':raise Invalid('Plan token limit exceeded')
    try:plan=json.loads(response['message']['content'])
    except (KeyError,ValueError) as exc:raise Invalid('Invalid plan JSON') from exc
    return validate_plan(plan)


def execute(store, plan, as_of, *, translator=None, budget=None, limit=12, excerpt_budget=8000):
    admin.install(store);validate_plan(plan)
    if not 1<=limit<=100:raise Invalid('Result limit must be 1–100')
    budget=budget or Budget(judgments=12,requests=16,seconds=60)
    cutoff=admin.utc(as_of);outputs=[];unresolved=[];used_chars=0
    for index,step in enumerate(plan['steps']):
        op=step['op'];a=step['args']
        if budget.remaining()<=0:
            unresolved.append({'step':index,'reason':'wall_clock_budget'});budget.stopping.add('wall_clock_budget');break
        try:
            if op=='find_requests':
                result=find_requests(store,cutoff,**a,limit=limit)
            elif op=='evidence_metadata':
                admin.current_request(store,a['request_id'],cutoff)
                rows=store.db.execute("SELECT DISTINCT m.id,m.received_at,m.kind,length(m.text) AS characters,m.superseded_at,c.content_hash,c.version FROM admin_messages m JOIN admin_events e ON e.source_id=m.id LEFT JOIN evidence_catalog c ON c.id=m.id WHERE e.request_id=? AND e.type='association' AND e.valid_from<=? AND (e.retracted_at IS NULL OR e.retracted_at>?) ORDER BY m.id LIMIT ?",(a['request_id'],cutoff,cutoff,limit+1)).fetchall()
                result={'evidence':[dict(r) for r in rows[:limit]],'complete':len(rows)<=limit}
            elif op=='read_excerpt':
                msg=source(store,a['evidence_id'])
                if msg['received_at']>cutoff:raise Invalid('Evidence is after as-of time')
                if used_chars+a['length']>excerpt_budget:raise Invalid('Total excerpt budget exceeded')
                excerpt=msg['text'][a['offset']:a['offset']+a['length']];used_chars+=len(excerpt)
                result={'evidence_id':msg['id'],'content_version':digest(msg['text']),'offset':a['offset'],
                        'excerpt':excerpt,'total_characters':len(msg['text']), 'complete':a['offset']==0 and len(excerpt)==len(msg['text'])}
            elif op=='extract':
                if translator is None:raise Invalid('Extraction requires configured Qwen')
                msg=source(store,a['evidence_id']);root,_=admin.current_request(store,a['request_id'],cutoff)
                if msg['received_at']>cutoff:raise Invalid('Evidence is after as-of time')
                if len(msg['text'])>12000:raise Invalid('Evidence exceeds extraction limit; read excerpts and provide a bounded source explicitly')
                tpl=admin.load_template(store,root['payload']['template_id'])[1]
                before=time.monotonic()
                draft=admin.extract_message(BoundedTranslator(translator,budget),msg['text'],[{'request_id':a['request_id'],'template':tpl}],a['request_id'],kind=msg['kind'])
                eid=admin.ident('extract_')
                with store.db:store.db.execute('INSERT INTO extraction_runs VALUES(?,?,?,?,?,?,?,?)',
                    (eid,msg['id'],translator.model,incremental.EXTRACTION_VERSION,'admin-schema-v3',time.monotonic()-before,encoded(draft),now()))
                result={'extraction_id':eid,'status':draft['status'],'incorporated':False,'complete':draft['status']=='ok'}
            elif op=='query':
                report=incremental.refresh(store,as_of,budget=budget,request_ids=[a['request_id']],max_requests=limit)
                result={'requests':[compact_request(r) for r in report['requests']], 'complete':report['complete'],
                        'unresolved_count':len(report['unresolved_checks']),'refresh_id':report['refresh_id']}
            elif op=='explain':
                row=store.db.execute('SELECT * FROM conclusion_history WHERE id=?',(a['conclusion_id'],)).fetchone()
                if not row:raise Invalid('Unknown conclusion ID')
                conclusion=json.loads(row['row']);deps=json.loads(row['dependencies'])
                result={'conclusion_id':row['id'],'as_of':row['as_of'],'rule_version':deps['rule_version'],
                        'flags':conclusion['flags'],'source_refs':deps['sources'][:limit],
                        'collection_dependency':deps['collection'],'verification':conclusion['verification'],
                        'judgment_refs':[{'id':j.get('id'),'status':j['status'],'origin':j.get('origin')} for j in conclusion['judgments'][:limit]],
                        'complete':len(deps['sources'])<=limit and len(conclusion['judgments'])<=limit}
            elif op=='semantic':
                msg=source(store,a['evidence_id']);root,events=admin.current_request(store,a['request_id'],cutoff)
                associations=[e['id'] for e in events if e['type']=='association' and e['payload']['message_id']==msg['id']]
                if not associations or msg['received_at']>cutoff or (msg['superseded_at'] and msg['superseded_at']<=cutoff):raise Invalid('Evidence must be active and associated with this request')
                desired={e['payload']['value'] for e in events if e['type']=='desired_outcome'}
                if len(desired)!=1:raise Invalid('Requested outcome missing or conflicting')
                desired=next(iter(desired));subject=a['request_id']
                evidence=[{'id':msg['id'],'source':msg['text'],'received_at':msg['received_at'],
                           'hash':digest({'text':msg['text'],'received_at':msg['received_at'],'association':associations})}]
                if a['predicate']=='evidence_addresses':
                    tpl=admin.load_template(store,root['payload']['template_id'])[1];subject=tpl['verification_requirement']
                    evidence.append({'id':root['payload']['template_id'],'source':tpl['description']+'; evidence required: '+', '.join(tpl['required_documents'])+'; requested outcome: '+desired,'hash':digest({'template':tpl,'desired':desired})})
                else:evidence.append({'id':root['id'],'source':'Requested outcome: '+desired,'hash':digest(desired)})
                g=Gateway(store,[],budget,predicate=a['predicate'],resolver=lambda *_:(evidence,[]),as_of=cutoff)
                j=g.resolve([('message:'+msg['id'],subject)])[('message:'+msg['id'],subject)]
                result={'judgment_id':j['id'],'status':j['status'],'origin':j['origin'],'complete':j['status'] in {'supported','contradicted'}}
            if len(encoded(result))>20000:
                result={'complete':False,'reason':'result_size_limit','operation':op}
            if not result.get('complete',True):unresolved.append({'step':index,'reason':result.get('reason','partial_or_unresolved')})
            outputs.append({'step':index,'op':op,'result':result})
        except (Invalid,TimeoutError,OSError) as exc:
            unresolved.append({'step':index,'reason':str(exc)})
            outputs.append({'step':index,'op':op,'error':str(exc)})
    return {'results':outputs,'complete':not unresolved and not budget.stopping,'unresolved':unresolved,
            'metrics':budget.metrics,'stopping_reasons':sorted(budget.stopping),'excerpt_characters':used_chars}
