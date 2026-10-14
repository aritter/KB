"""Fresh full-live administrative test: Ollama extraction, Kev, Prolog, restart/cache.

Run from the repository root. Never substitutes reviewed extractions or model mocks.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from .admin_fixture import REQUEST, extraction


class TestFailure(Exception):
    pass


def validate_extraction(label, result):
    if not result.get('incorporated'):
        raise TestFailure('Extraction not incorporated: ' + result.get('extraction', {}).get('explanation', 'unknown'))
    actual = result['extraction']
    gold = extraction(label)
    # Reviewed fixtures are comparison targets only; never supplied to either model.
    for key in ('expected', 'observed', 'dates', 'documents', 'absent_documents', 'dependencies'):
        canonical = lambda values: sorted(json.dumps(v, sort_keys=True) for v in values)
        if canonical(actual[key]) != canonical(gold[key]):
            raise TestFailure(f'Extraction mismatch for {label}.{key}: '
                              f'expected {json.dumps(gold[key])}; got {json.dumps(actual[key])}')
    if label == 'original' and (not actual['desired_outcome'] or 'Appointments Office' not in actual['responsible']):
        raise TestFailure('Initial extraction omitted desired outcome or responsible office')
    if label != 'original' and actual['desired_outcome']:
        raise TestFailure('Reply incorrectly changed the desired outcome')


def validate_no_model_work(report, *, reused=True):
    metrics = report['metrics']
    for key in ('new_judgments', 'backend_calls', 'backend_requests'):
        if metrics[key] != 0:
            raise TestFailure('Unexpected model work: ' + key)
    if reused and metrics['reused_conclusions'] != 1:
        raise TestFailure('Expected reuse of the request conclusion')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--incremental', action='store_true', help='Test incremental refresh, duplicate import, clock-only updates and alert history')
    parser.add_argument('--model', default='qwen3.5:9b-q4_K_M')
    parser.add_argument('--definition', default='config/has_skill.json')
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--output-dir', default='evaluation')
    args = parser.parse_args()
    config = json.loads(Path(args.definition).read_text())
    if config['backend']['kind'] != 'kev':
        parser.error('This test requires real Kev configuration')
    target = Path(args.output_dir) / ('live-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    target.mkdir(parents=True, exist_ok=False)
    database = target / 'knowledge.sqlite3'
    results = {'incremental': args.incremental, 'model': args.model, 'backend': config['backend'], 'steps': [], 'status': 'running'}
    stage = 'setup'
    def save():
        (target / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    def call(label, *command):
        started = time.monotonic()
        proc = subprocess.run([sys.executable, '-m', 'kb', '--db', str(database), '--model', args.model, *command],
                              capture_output=True, text=True, timeout=max(150, args.seconds + 30))
        (target / (label + '.json')).write_text(proc.stdout)
        (target / (label + '.stderr.txt')).write_text(proc.stderr)
        results['steps'].append({'step': label, 'seconds': time.monotonic()-started, 'exit_code': proc.returncode})
        save()
        if proc.returncode:
            raise TestFailure(label + ': ' + (proc.stderr or proc.stdout).strip())
        return json.loads(proc.stdout)
    def ingest(label, date, *extra):
        value = call('ingest-' + label, 'admin', 'ingest', '--request', REQUEST, '--at', date,
                     '--file', 'examples/admin_messages/' + label + '.txt', *extra)
        validate_extraction(label, value)
        print('PASS extraction: ' + label, flush=True)
        return value
    def check(label, date, verification, clock_only=False):
        extra = ['--clock-only'] if clock_only else []
        report = call(label, 'admin', 'refresh' if args.incremental else 'check',
                      '--as-of', date, '--seconds', str(args.seconds), *extra)
        row = report['requests'][0]
        print(json.dumps({'step': label, 'progress': row['progress'], 'verification': row['verification'],
                          'flags': [f['reason'] for f in row['flags']], 'metrics': report['metrics']}), flush=True)
        if report['stopping_reasons']:
            raise TestFailure('Backend/budget failure: ' + str(report['stopping_reasons']))
        if row['verification'] != verification:
            raise TestFailure(f'{label}: expected {verification}, got {row["verification"]}')
        return report, row
    try:
        call('doctor', 'doctor')
        call('template', 'admin', 'template', 'config/appointment.json')
        call('configure', 'admin', 'configure', args.definition)
        stage = 'extraction'
        ingest('original', '2026-10-12', '--new', '--template', 'student_appointment')
        ack = ingest('ack', '2026-10-13')
        stage = 'judgment_or_workflow'
        _, row = check('ack', '2026-10-20', 'unverified')
        if not row['progress_assessments']['acknowledged'] or 'follow_up_due' not in [f['reason'] for f in row['flags']]:
            raise TestFailure('Acknowledgment or follow-up due not established')
        if args.incremental:
            stage = 'duplicate_import'
            before = call('before-duplicate', 'admin', 'inspect', REQUEST)
            duplicate = call('duplicate-ingest', 'admin', 'ingest', '--request', REQUEST,
                             '--at', '2026-10-13', '--file', 'examples/admin_messages/ack.txt')
            after = call('after-duplicate', 'admin', 'inspect', REQUEST)
            if (not duplicate.get('duplicate') or duplicate.get('new_extractions') != 0
                    or duplicate['source_id'] != ack['source_id'] or before != after):
                raise TestFailure('Duplicate import changed records or did not reuse extraction')
            repeated, _ = check('duplicate-refresh', '2026-10-20', 'unverified')
            validate_no_model_work(repeated)
            stage = 'clock_refresh'
            advanced, due = check('clock-advanced', '2026-10-25', 'unverified', clock_only=True)
            validate_no_model_work(advanced)
            if 'intervention_reached' not in [f['reason'] for f in due['flags']]:
                raise TestFailure('Clock-only refresh did not raise intervention')
        stage = 'extraction'
        ingest('claim', '2026-10-21')
        stage = 'judgment_or_workflow'
        _, row = check('claim', '2026-10-25' if args.incremental else '2026-10-21', 'unverified')
        if row['progress'] != 'claimed_complete':
            raise TestFailure('Completion claim not established')
        stage = 'extraction'
        wrong = ingest('wrong', '2026-10-22', '--kind', 'confirmation')
        stage = 'judgment_or_workflow'
        _, row = check('wrong', '2026-10-25', 'discrepant')
        if not any(d.get('expected') == 'FUND-A' and d.get('observed') == 'FUND-B' for d in row['discrepancies']):
            raise TestFailure('Exact funding mismatch missing')
        if 'intervention_reached' not in [f['reason'] for f in row['flags']]:
            raise TestFailure('Intervention reminder missing')
        stage = 'extraction'
        ingest('correct', '2026-10-26', '--kind', 'confirmation', '--supersedes', wrong['source_id'])
        stage = 'judgment_or_workflow'
        completed, row = check('correct', '2026-10-26', 'verified_documentary')
        if args.incremental and not any('collection' in i['changed_dependencies'] for i in completed['invalidations']):
            raise TestFailure('Completion evidence did not invalidate the evidence collection')
        if row['flags'] or row['discrepancies']:
            raise TestFailure('Corrected request still flagged')
        stage = 'restart_cache'
        repeated, again = check('repeat', '2026-10-26', 'verified_documentary', clock_only=args.incremental)
        if again != row or repeated['metrics']['new_judgments'] or repeated['metrics']['backend_calls']:
            raise TestFailure('Restart changed request results or made new model calls')
        if args.incremental:
            validate_no_model_work(repeated)
            history = call('history', 'admin', 'history', REQUEST)
            transitions = [h['transition'] for h in history['alert_history']]
            if not transitions or transitions[0] != 'raised' or transitions[-1] != 'withdrawn':
                raise TestFailure('Alert history did not retain raising and withdrawal')
        results['status'] = 'passed'
    except (TestFailure, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, OSError) as exc:
        results.update(status='failed', failure_stage=stage, error=str(exc))
        print('FAIL: ' + str(exc), flush=True)
    finally:
        save()
        print('Full reports: ' + str(target), flush=True)
    print('LIVE TEST ' + results['status'].upper())
    return 0 if results['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
