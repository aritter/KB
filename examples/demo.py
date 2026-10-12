"""Real model end-to-end demo. Each command starts a fresh application process."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='demo.sqlite3')
    parser.add_argument('--model', default='qwen3.5:9b-q4_K_M')
    args = parser.parse_args()
    if Path(args.db).exists():
        raise SystemExit('Choose a new --db path for the isolated demo.')
    def run(command, text):
        result = subprocess.run([sys.executable, '-m', 'kb', '--db', args.db, '--model', args.model, command, text], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(result.stderr)
        response = json.loads(result.stdout)
        print(json.dumps(response, indent=2))
        if response.get('proposal', {}).get('status') != 'ok':
            raise SystemExit('Model requested clarification or reported unsupported input; demo stopped.')
        return response
    for text in [
        'Alice manages project P.',
        'Project P uses dataset D.',
        'Dataset D requires renewed authorization.',
        'Anyone who manages a project using a dataset that requires renewed authorization needs to be notified about that dataset.',
    ]:
        run('teach', text)
    question = 'Who needs to be notified, and about what?'
    def verify(expected):
        rows = run('ask', question)['rows']
        actual = sorted(tuple(sorted(row['bindings'].values())) for row in rows)
        if actual != expected:
            raise SystemExit(f'Demo answer mismatch: {actual!r}, expected {expected!r}')
    verify([('dataset:d', 'person:alice')])
    run('correct', 'Bob now manages project P instead of Alice.')
    verify([('dataset:d', 'person:bob')])
    verify([('dataset:d', 'person:bob')])  # Another entirely fresh process.
    run('retract', 'Retract the requirement that dataset D needs renewed authorization.')
    verify([])
    print('PASS: taught rule, correction, restart, and retraction verified with the local model.')


if __name__ == '__main__': main()
