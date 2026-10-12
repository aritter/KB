"""Live translation benchmark with gold semantics and an independent inference check.
Run from the repository: python3 -m evaluation.run --output evaluation/local.json
"""
import argparse
import itertools
import json
import platform
from datetime import datetime, timezone
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from kb.llm import Ollama, DEFAULT_MODEL
from kb.prolog import Prolog, RuntimeUnavailable
from kb.schema import atom as a, assertion as r, proposal as p, variables
from kb.store import Store

ALICE = r(a('manages','person:alice','project:p'))
BOB = r(a('manages','person:bob','project:p'))
USES = r(a('uses','project:p','dataset:d'))
RENEW = r(a('requires_renewal','dataset:d'))
RULE = r(a('needs_notification','?Who','?Data'), a('manages','?Who','?Project'), a('uses','?Project','?Data'), a('requires_renewal','?Data'))
QUERY = [a('needs_notification','?Who','?Data')]
BASE = [ALICE, USES, RENEW, RULE]
EXPECTED = [('dataset:d','person:alice')]


def canonical_atoms(atoms, head=None):
    names = sorted(variables(atoms + ([head] if head else [])))
    if len(names) > 6:
        return 'too-many-variables-for-this-benchmark'
    variants = []
    for permutation in itertools.permutations(range(len(names))):
        mapping = dict(zip(names, permutation))
        def encode(atom):
            return (atom['predicate'], tuple(('v', mapping[t['var']]) if 'var' in t else ('c', t['const']) for t in atom['args']))
        variants.append((encode(head) if head else (), tuple(sorted(map(encode, atoms)))))
    return min(variants)


def equivalent(left, right):
    return (left['status'] == right['status'] and left['targets'] == right['targets']
        and canonical_atoms(left['query']) == canonical_atoms(right['query'])
        and sorted(canonical_atoms(x['body'], x['head']) for x in left['assertions']) ==
            sorted(canonical_atoms(x['body'], x['head']) for x in right['assertions']))


def values(result):
    return sorted(tuple(sorted(row['bindings'].values())) for row in result['rows'])


def cases():
    return [
        ('fact_paraphrase', 'teach', 'Project P is managed by Alice.', [], p([ALICE]), [ALICE['head']], [()]),
        ('dataset_paraphrase', 'teach', 'Authorization for dataset D must be renewed.', [], p([RENEW]), [RENEW['head']], [()]),
        ('rule_acquisition', 'teach', 'Anyone who manages a project using a dataset that requires renewed authorization needs to be notified about that dataset.', BASE[:3], p([RULE]), QUERY, EXPECTED),
        ('rule_paraphrase', 'teach', 'If a person manages a project, that project uses a dataset, and that dataset requires renewed authorization, notify that person about that dataset.', BASE[:3], p([RULE]), QUERY, EXPECTED),
        ('query_paraphrase', 'ask', 'Who needs to be notified, and about what?', BASE, p(query=QUERY), QUERY, EXPECTED),
        ('query_paraphrase_2', 'ask', 'Which people need notification about which datasets?', BASE, p(query=QUERY), QUERY, EXPECTED),
        ('multistep', 'ask', 'Who needs to be notified, and about what?', [ALICE, USES, RULE, r(a('requires_renewal','?D'), a('uses','?P','?D'))], p(query=QUERY), QUERY, EXPECTED),
        ('unknown', 'ask', 'Does Carol manage project P?', BASE, p(query=[a('manages','person:carol','project:p')]), [a('manages','person:carol','project:p')], []),
        ('correction', 'correct', 'Bob now manages project P instead of Alice.', BASE, p([BOB]), QUERY, [('dataset:d','person:bob')]),
        ('retraction', 'retract', 'Retract the requirement that dataset D needs renewed authorization.', BASE, p(), QUERY, []),
        ('ambiguous', 'teach', 'She manages it.', [], p(status='clarify', explanation='Name the entities.'), None, None),
        ('unsupported', 'teach', 'Alice does not manage project P.', [], p(status='unsupported', explanation='No negation.'), None, None),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--output', default='evaluation/local.json')
    args = parser.parse_args()
    llm, engine = Ollama(args.model), Prolog()
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(), 'platform': platform.platform(), 'model': args.model, 'swipl': shutil.which('swipl'), 'cases': [],
              'method': 'Each case starts with isolated gold fixtures. Translation is scored modulo variable renaming and conjunction order. Gold inference is checked independently. Predicted inference is checked only after a semantically correct translation. No fixture is described as model-acquired.'}
    if report['swipl']:
        report['swipl_version'] = subprocess.run([report['swipl'], '--version'], capture_output=True, text=True, check=True).stdout.strip()
    started = time.perf_counter()
    try:
        report['runtime'] = llm.doctor()
    except Exception as exc:
        report['runtime_error'] = str(exc)
    report['preflight_seconds'] = time.perf_counter() - started
    for name, operation, text, fixtures, gold, query, expected in cases():
        entry = {'name': name, 'operation': operation, 'input': text}
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'kb.sqlite3')
            ids = store.apply('teach', 'Gold evaluation fixture', p(fixtures), 0, [])['created'] if fixtures else []
            if operation == 'correct': gold['targets'] = [ids[0]]
            if operation == 'retract': gold['targets'] = [ids[2]]
            revision, candidates, _ = store.candidates(text)
            predicted = None
            start = time.perf_counter()
            if 'runtime_error' in report:
                entry['translation_status'] = 'runtime_unavailable'
            else:
                try:
                    predicted, metrics = llm.translate(operation, text, candidates)
                    entry.update(metrics)
                    entry['proposal'] = predicted
                    entry['translation_status'] = 'passed' if equivalent(predicted, gold) else 'meaning_failure'
                except Exception as exc:
                    entry.update(translation_status='translation_failure', translation_error=str(exc))
                entry['translation_attempt_seconds'] = time.perf_counter() - start
            # For mutation cases, evaluate the gold update even if translation fails.
            if query is not None:
                if operation != 'ask':
                    store.apply(operation, text, gold, revision, [x['id'] for x in candidates])
                start = time.perf_counter()
                try:
                    result = engine.ask(store.snapshot()[1], query)
                    entry['gold_inference_status'] = 'passed' if values(result) == expected else 'inference_failure'
                    entry['gold_result'] = result
                except RuntimeUnavailable as exc:
                    entry.update(gold_inference_status='runtime_unavailable', inference_error=str(exc))
                except Exception as exc:
                    entry.update(gold_inference_status='inference_failure', inference_error=str(exc))
                entry['inference_attempt_seconds'] = time.perf_counter() - start
                if predicted and entry['translation_status'] == 'passed' and operation == 'ask':
                    try:
                        result = engine.ask(store.snapshot()[1], predicted['query'])
                        entry['predicted_query_status'] = 'passed' if values(result) == expected else 'inference_failure'
                    except Exception as exc:
                        entry['predicted_query_status'] = 'runtime_unavailable' if isinstance(exc, RuntimeUnavailable) else 'inference_failure'
            store.close()
        report['cases'].append(entry)
    report['translation_summary'] = dict(Counter(x['translation_status'] for x in report['cases']))
    report['inference_summary'] = dict(Counter(x.get('gold_inference_status', 'not_applicable') for x in report['cases']))
    report['latency_seconds'] = {}
    for label, status_key, metric in [('translation', 'translation_status', 'translation_seconds'), ('gold_inference', 'gold_inference_status', 'inference_attempt_seconds')]:
        samples = [x[metric] for x in report['cases'] if x.get(status_key) == 'passed' and metric in x]
        report['latency_seconds'][label] = {'count': len(samples), 'median': statistics.median(samples) if samples else None}
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['translation_summary', 'inference_summary', 'preflight_seconds']}, indent=2))


if __name__ == '__main__': main()
