"""Bounded symbolic discovery followed by demand-driven semantic resolution."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from .schema import ATOM, array, check_schema, typed, variables, validate_assertion
from .prolog import compile_atom, compile_list, quote, RuntimeUnavailable
from .semantic import Gateway, Budget


def discover(records, query, budget, executable='swipl'):
    check_schema(query,array(ATOM,1,6));typed(query)
    executable=shutil.which(executable)
    if not executable: raise RuntimeUnavailable('SWI-Prolog unavailable')
    root=Path(__file__).parent
    source=[(root/'engine.pl').read_text(),(root/'domains/research.pl').read_text(),(root/'planner.pl').read_text(),
            f'depth_bound({budget.depth}).', ':- dynamic deferred_rule/3.']
    # Forward closure must never bypass the gateway via an explicit semantic fact.
    dependent={'has_skill','candidate','ready','blocked_by','milestone_blocker','affected_milestone'}
    while True:
        expanded=dependent | {r['assertion']['head']['predicate'] for r in records
            if any(a['predicate'] in dependent for a in r['assertion']['body'])}
        if expanded==dependent: break
        dependent=expanded
    for rec in records:
        item=rec['assertion'];validate_assertion(item)
        check_schema(rec['id'],{'type':'string','pattern':r'^a_[a-f0-9]{32}$'})
        predicate='deferred_rule' if item['body'] and item['head']['predicate'] in dependent else 'rule'
        source.append(f"{predicate}({compile_atom(item['head'])},{compile_list(item['body'])},{quote(rec['id'])}).")
    bindings='bindings{'+','.join(quote(v)+':V_'+v for v in sorted(variables(query)))+'}'
    goal=f'plan_query({compile_list(query)},{bindings},{budget.plans+1},{max(0.001,budget.remaining())},{budget.steps},{budget.depth})'
    source.append(f':- initialization((catch(({goal}),E,(print_message(error,E),halt(2))),halt),main).')
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'plan.pl';path.write_text('\n'.join(source))
        try:
            proc=subprocess.run([executable,'--stack-limit=256m','-q','-f','none','-s',str(path)],capture_output=True,text=True,timeout=max(0.001,budget.remaining()))
        except subprocess.TimeoutExpired:
            return {'plans':[], 'stopping':['wall_clock_budget']}
        if proc.returncode:
            return {'plans':[], 'stopping':['symbolic_limit_or_error'], 'error':proc.stderr[-2000:]}
        result=json.loads(proc.stdout)
    result['stopping']=[]
    if len(result['plans'])>budget.plans:
        result['plans']=result['plans'][:budget.plans];result['stopping'].append('symbolic_plan_limit')
    return result


class Coordination:
    def __init__(self, store, budget=None, first=False, backend=None, executable='swipl'):
        self.store,self.budget,self.first,self.backend,self.executable=store,budget or Budget(),first,backend,executable

    def ask(self, records, query):
        budget=self.budget
        found=discover(records,query,budget,self.executable)
        budget.stopping.update(found['stopping'])
        gateway=None
        supported={};unresolved={};rejected={}
        evaluated=[]
        for plan in found['plans']:
            key=json.dumps(plan['bindings'],sort_keys=True)
            if key in supported: continue  # A supported alternative proof is sufficient.
            if budget.remaining()<=0:
                budget.stopping.add('wall_clock_budget');break
            judgments=[]
            status=plan['status']
            if plan['needs'] and status=='supported':
                gateway=gateway or Gateway(self.store,records,budget,self.backend)
                known={tuple(pair):gateway.lookup(pair) for pair in plan['needs']}
                # Check ALL cached/explicit requirements before spending on any missing one.
                if not any(j and j['status']=='contradicted' for j in known.values()):
                    missing=[pair for pair,j in known.items() if j is None]
                    known.update(gateway.resolve(missing))
                judgments=[j for j in known.values() if j is not None]
                states={j['status'] for j in judgments}
                if 'contradicted' in states: status='contradicted'
                elif any(s!='supported' for s in states) or len(judgments)!=len(known): status='insufficient_evidence'
            row={**plan,'status':status,'judgments':judgments}
            evaluated.append(row)
            if status=='supported':
                supported[key]=row;unresolved.pop(key,None);rejected.pop(key,None)
                if self.first:
                    budget.stopping.add('first_answer');break
                if len(supported)>=budget.results:
                    budget.stopping.add('result_limit');break
            elif status=='contradicted':
                rejected.setdefault(key,[]).append(row)
            else:
                unresolved.setdefault(key,[]).append(row)
        # Contradicted proof branches do not disprove a different unresolved branch.
        rejected={k:v for k,v in rejected.items() if k not in supported and k not in unresolved}
        complete=not unresolved and not budget.stopping and not found.get('coverage_warnings')
        return {'rows':list(supported.values()),'unresolved_candidates':list(unresolved.values()),
                'rejected_candidates':list(rejected.values()),'complete':complete,
                'pending_requests':[j for row in evaluated for j in row['judgments'] if j['status']=='not_evaluated_budget'],
                'metrics':{**budget.metrics,'symbolic_steps':found.get('symbolic_steps',0)},
                'stopping_reasons':sorted(budget.stopping),'symbolic_error':found.get('error'),
                'coverage_warnings':found.get('coverage_warnings',[]),
                'answer': f'{len(supported)} supported answer(s); {len(unresolved)} unresolved candidate(s).',
                'coverage_scope':'Declared entities and dependency edges in the active snapshot; eligibility is not authorization or capacity.'}


class AutoEngine:
    """Keep the original engine for old positive-only queries; dispatch new domain queries."""
    def __init__(self,store,original,budget,first=False,force=False):
        self.store,self.original,self.budget,self.first,self.force=store,original,budget,first,force
    def ask(self,records,query):
        from .domains.research import PREDICATES
        if self.force or any(a['predicate'] in PREDICATES for a in query) or any(
            a['predicate'] in PREDICATES for r in records for a in r['assertion']['body']):
            return Coordination(self.store,self.budget,self.first,executable=self.original.executable).ask(records,query)
        return self.original.ask(records,query)
