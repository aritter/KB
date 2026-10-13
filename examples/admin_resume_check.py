"""Run the pending dated check twice in fresh processes and save full reports."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='admin-ollama-test.sqlite3')
    parser.add_argument('--as-of', default='2026-10-26')
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--output-dir', default='evaluation')
    args = parser.parse_args()
    if not Path(args.db).is_file():
        parser.error('Existing test database required; no database will be created.')
    target = Path(args.output_dir) / ('resume-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    target.mkdir(parents=True, exist_ok=False)
    failures = False
    for label in ('first', 'repeat'):
        command = [sys.executable, '-m', 'kb', '--db', args.db, 'admin', 'check',
                   '--as-of', args.as_of, '--seconds', str(args.seconds)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=args.seconds + 15)
        except subprocess.TimeoutExpired:
            print('Check exceeded timeout; reports directory: ' + str(target), file=sys.stderr)
            return 2
        (target / (label + '.json')).write_text(result.stdout)
        (target / (label + '.stderr.txt')).write_text(result.stderr)
        if result.returncode:
            print(result.stderr or result.stdout, file=sys.stderr)
            print('Reports: ' + str(target))
            return result.returncode
        report = json.loads(result.stdout)
        summary = {'run': label, 'requests': [{
            'request': q['request_id'], 'progress': q['progress'],
            'verification': q['verification'], 'discrepancies': q['discrepancies'],
            'flags': [f['reason'] for f in q['flags']],
        } for q in report['requests']], 'metrics': report['metrics'],
            'stopping_reasons': report['stopping_reasons']}
        print(json.dumps(summary, indent=2))
        failures |= bool(report['stopping_reasons'])
    print('Full reports saved in ' + str(target))
    print('These are observations; a successful command does not assert documentary verification.')
    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
