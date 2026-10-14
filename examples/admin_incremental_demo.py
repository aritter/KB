"""Deterministic incremental vs full-reprocessing demo; no live models required."""
import argparse
import json
import tempfile
import time
from pathlib import Path
from kb import admin, incremental
from kb.store import Store
from examples.admin_fixture import REQUEST, TEXTS, extraction, backend


def run(directory, mode):
    path = directory / (mode + '.sqlite3')
    if path.exists():
        raise ValueError('Use a fresh output directory; databases are never overwritten.')
    store = Store(path)
    admin.install(store)
    admin.template_register(store, json.loads(Path('config/appointment.json').read_text()))
    admin.configure_semantics(store, backend())
    steps = []
    def ingest(label, day, **kw):
        return admin.ingest(store, TEXTS[label], day, request=REQUEST,
                            extraction=extraction(label), **kw)
    def check(label, day, expected, clock=False):
        report = incremental.refresh(store, day, mode=mode, clock_only=clock and mode=='incremental')
        row = report['requests'][0]
        actual = {'verification': row['verification'], 'flags': [f['reason'] for f in row['flags']]}
        assert actual == expected, (label, actual, expected)
        steps.append({'step': label, 'report': report})
        print(json.dumps({'mode': mode, 'step': label, **actual,
                          'new_judgments': report['metrics']['new_judgments'],
                          'backend_calls': report['metrics']['backend_calls'],
                          'reused_conclusions': report['metrics']['reused_conclusions']}))
        return report
    ingest('original','2026-10-12',new=True,template='student_appointment')
    ingest('ack','2026-10-13')
    pending = {'verification':'unverified','flags':['follow_up_due']}
    check('initial', '2026-10-20', pending)
    duplicate = ingest('ack','2026-10-13')
    assert duplicate['duplicate'] and duplicate['new_extractions']==0
    check('duplicate import', '2026-10-20', pending)
    due = check('clock advanced', '2026-10-25',
                {'verification':'unverified','flags':['intervention_reached','follow_up_due']}, clock=True)
    if mode=='incremental': assert due['metrics']['backend_calls']==0
    ingest('correct','2026-10-26',kind='confirmation')
    done = {'verification':'verified_documentary','flags':[]}
    check('completion evidence', '2026-10-26', done)
    store.close(); store = Store(path)
    repeat = check('restart', '2026-10-26', done, clock=True)
    if mode=='incremental': assert repeat['metrics']['backend_calls']==0
    history = [dict(r) for r in store.db.execute('SELECT * FROM alert_history ORDER BY id')]
    assert [r['transition'] for r in history]==['raised','changed','withdrawn']
    store.close()
    return {'steps': steps, 'alert_history': history,
            'totals': {key: sum(s['report']['metrics'][key] for s in steps)
                       for key in ('new_judgments','backend_calls','model_latency_ms','refresh_seconds')}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',help='Fresh directory for databases and JSON; defaults to a temporary directory')
    args=parser.parse_args()
    directory=Path(args.output) if args.output else Path(tempfile.mkdtemp(prefix='kb-incremental-'))
    directory.mkdir(parents=True,exist_ok=True)
    if any((directory/(mode+'.sqlite3')).exists() for mode in ('incremental','full')):
        parser.error('Use a fresh directory; existing databases are never overwritten')
    results={'validation':'Deterministic reviewed extractions and counting mock judgments; real SQLite/SWI-Prolog.',
             'comparison':'Full-reprocessing baseline, not a reproduction of the RLM paper.'}
    for mode in ('incremental','full'):results[mode]=run(directory,mode)
    results['status']='passed'
    (directory/'report.json').write_text(json.dumps(results,indent=2)+'\n')
    print('PASS; full report: '+str(directory/'report.json'))
    print(json.dumps({m:results[m]['totals'] for m in ('incremental','full')},indent=2))


if __name__=='__main__':main()
