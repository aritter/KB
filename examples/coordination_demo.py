"""Run with python3 -m examples.coordination_demo --backend counting_mock|kev."""
import argparse
import json
from pathlib import Path
from kb.store import Store
from kb.schema import atom as a, assertion as r, proposal as p
from kb.semantic import register, Budget
from kb.coordination import Coordination
from .research_fixture import records, mock_definition


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default='coordination-demo.sqlite3')
    parser.add_argument('--backend',choices=['counting_mock','kev'],required=True)
    parser.add_argument('--definition',default='config/has_skill.json')
    parser.add_argument('--report',default='evaluation/coordination-demo.json')
    args=parser.parse_args()
    if Path(args.db).exists():raise SystemExit('Choose a fresh --db; the demo will not overwrite existing knowledge.')
    store=Store(args.db);store.import_records(records(),'Fictional reviewed research coordination fixture')
    spec=mock_definition() if args.backend=='counting_mock' else json.loads(Path(args.definition).read_text())
    register(store,spec)
    report={'backend':args.backend,'real_model_validation':args.backend=='kev','steps':[]}
    def query(label,atom,**kw):
        result=Coordination(store,**kw).ask(store.snapshot()[1],[atom])
        report['steps'].append({'label':label,'result':result})
        print(json.dumps({'step':label,'bindings':[x['bindings'] for x in result['rows']],
                          'unresolved':len(result['unresolved_candidates']),'complete':result['complete'],
                          'metrics':result['metrics'],'stopping':result['stopping_reasons']}))
        return result
    def find(pred,*terms):
        return next(x['id'] for x in store.snapshot()[1] if x['assertion']==r(a(pred,*terms)))
    def correct(ident,item,source):
        store.apply('correct',source,p([item],targets=[ident]),store.snapshot()[0],[ident])
    try:
        first=query('eligible people: Bob filtered, Carol unresolved',a('candidate','?Who','task:preprocess','period:october'))
        reuse=query('same Python judgments reused for baseline',a('candidate','?Who','task:baseline','period:october'))
        query('work that can proceed while waiting for dataset access',a('ready','?Task'))
        query('milestone blockers, including transitive prerequisites',a('milestone_blocker','milestone:evaluation_complete','?Dependency','?Reason'))
        query('milestone affected by hypothetical dataset loss',a('affected_milestone','?Milestone','dataset:d'))
        correct(find('resource_status','dataset:d','status:unavailable'),r(a('resource_status','dataset:d','status:available')),'Dataset D access explicitly granted.')
        query('preprocessing becomes structurally ready',a('ready','task:preprocess'))
        correct(find('task_status','task:preprocess','status:pending'),r(a('task_status','task:preprocess','status:completed')),'Preprocessing is complete.')
        query('baseline becomes structurally ready',a('ready','task:baseline'))
        store.close();store=Store(args.db)
        restarted=query('semantic cache survives restart',a('candidate','?Who','task:preprocess','period:october'))
        query('first supported candidate',a('candidate','?Who','task:preprocess','period:october'),first=True)
        query('new validation skill with zero judgment budget',a('candidate','person:alice','task:validate','period:october'),budget=Budget(judgments=0))
        if args.backend=='counting_mock':
            assert [x['bindings']['Who'] for x in first['rows']]==['person:alice']
            assert first['metrics']['new_judgments']==2
            assert reuse['metrics']['new_judgments']==restarted['metrics']['new_judgments']==0
            assert reuse['metrics']['cache_hits']==restarted['metrics']['cache_hits']==2
            report['status']='counting_mock_checks_passed'
        else:
            report['status']='real_backend_observations_recorded'
            if any('backend_error' in step['result']['stopping_reasons'] for step in report['steps']):
                report['status']='real_backend_unavailable_or_failed'
    finally:
        store.close()
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print(report['status']+'; '+args.report)
    return 2 if report['status']=='real_backend_unavailable_or_failed' else 0


if __name__=='__main__':raise SystemExit(main())
