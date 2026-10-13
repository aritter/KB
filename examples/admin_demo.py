"""python3 -m examples.admin_demo --backend counting_mock|kev --db NEW.sqlite3"""
import argparse
import json
from pathlib import Path
from kb import admin
from kb.store import Store
from kb.semantic import Budget
from .admin_fixture import REQUEST,TEXTS,extraction,backend


def backend_errors(value):
    """Surface unique gateway failures without dumping the entire evidence trace."""
    errors = set()
    if isinstance(value, dict):
        if value.get('status') == 'backend_error' and value.get('error'):
            errors.add(value['error'])
        for child in value.values():
            errors.update(backend_errors(child))
    elif isinstance(value, list):
        for child in value:
            errors.update(backend_errors(child))
    return sorted(errors)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',default='admin-demo.sqlite3');parser.add_argument('--backend',choices=['counting_mock','kev'],required=True)
    parser.add_argument('--report',default='evaluation/admin-demo.json');parser.add_argument('--definition',default='config/has_skill.json')
    args=parser.parse_args()
    if Path(args.db).exists():raise SystemExit('Use a fresh database filename; existing data is never overwritten.')
    store=Store(args.db);admin.install(store)
    admin.template_register(store,json.loads(Path('config/appointment.json').read_text()))
    config=backend() if args.backend=='counting_mock' else json.loads(Path(args.definition).read_text())['backend']
    admin.configure_semantics(store,config)
    output={'backend':args.backend,'extraction':'reviewed fixtures (not LLM-tested)','steps':[]}
    def ingest(label,at,**kw):return admin.ingest(store,TEXTS[label],at,request=REQUEST,extraction=extraction(label),**kw)
    def check(label,day):
        report=admin.report(store,day,budget=Budget(judgments=64,requests=64,seconds=60))
        output['steps'].append({'label':label,'report':report})
        row=report['requests'][0]
        print(json.dumps({'step':label,'progress':row['progress'],'verification':row['verification'],
                          'flags':[x['reason'] for x in row['flags']],'new_judgments':report['metrics']['new_judgments'],'cache_hits':report['metrics']['cache_hits'],
                          'backend_errors':backend_errors(report)}))
        return report,row
    ingest('original','2026-10-12',new=True,template='student_appointment')
    ingest('ack','2026-10-13')
    _,row=check('Acknowledged, not complete; follow-up due','2026-10-20')
    if args.backend=='counting_mock':assert row['verification']=='unverified' and row['progress_assessments']['acknowledged']
    ingest('claim','2026-10-21')
    _,row=check('Completion claim without verification','2026-10-21')
    if args.backend=='counting_mock':assert row['progress']=='claimed_complete' and row['verification']=='unverified'
    wrong=ingest('wrong','2026-10-22',kind='confirmation')
    _,row=check('Wrong account and intervention reached','2026-10-25')
    assert row['discrepancies'][0]['observed']=='FUND-B'
    assert 'intervention_reached' in [x['reason'] for x in row['flags']]
    ingest('correct','2026-10-26',kind='confirmation',supersedes=wrong['source_id'])
    _,row=check('Explicitly superseding corrected evidence','2026-10-26')
    if args.backend=='counting_mock':assert row['verification']=='verified_documentary' and not row['flags']
    store.close();store=Store(args.db)
    restarted,row=check('After restart','2026-10-26')
    repeated,again=check('Unchanged repeated check','2026-10-26')
    if args.backend=='counting_mock':
        assert repeated['metrics']['new_judgments']==restarted['metrics']['new_judgments']==0
        assert row['verification']==again['verification']=='verified_documentary'
    admin.ingest(store,TEXTS['ambiguous'],'2026-10-26',extraction=extraction('ambiguous'))
    ingest('date','2026-10-26')
    review,_=check('Unmatched message and ambiguous date retained for review','2026-10-26')
    assert len(review['unassigned_messages'])==2
    store.close()
    output['status']='mock_checks_passed' if args.backend=='counting_mock' else 'real_backend_observations_only'
    if args.backend=='kev' and any('backend_error' in x['report']['stopping_reasons'] for x in output['steps']):output['status']='real_backend_unavailable_or_failed'
    Path(args.report).write_text(json.dumps(output,indent=2)+'\n')
    print(output['status']+'; '+args.report)
    return 2 if output['status']=='real_backend_unavailable_or_failed' else 0


if __name__=='__main__':raise SystemExit(main())
