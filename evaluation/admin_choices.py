"""Paired generic-vs-specific choice experiment through the shared gateway.

Reviewed fictional labels are evaluation targets, never sent to real Kev.
The counting mock checks experiment plumbing only, not semantic accuracy.
"""
import argparse
import copy
import json
from pathlib import Path

from kb import admin
from kb.domains.admin import SEMANTICS
from kb.kev import make_backend
from kb.semantic import Budget, Gateway, definition, digest, register
from kb.store import Store

CONTEXT = 'This message is a reply about the request to appoint Alex Example from November 1 through December 31, 2026 using FUND-A.'
GENERIC = {'supported': 'The message clearly expresses this meaning.',
           'contradicted': 'The message clearly does not express this meaning.',
           'insufficient_evidence': 'Ambiguous, insufficient context, or uncertainty.'}
CASES = [
    ('ack_positive', 'message_acknowledges', 'Received, we’ll take care of it.', 'supported'),
    ('ack_negative', 'message_acknowledges', 'We have not received your appointment request.', 'contradicted'),
    ('ack_unknown', 'message_acknowledges', 'The office closes at five.', 'insufficient_evidence'),
    ('promise_positive', 'message_promises', 'Received, we’ll take care of it.', 'supported'),
    ('promise_negative', 'message_promises', 'We will not take action on this request.', 'contradicted'),
    ('promise_unknown', 'message_promises', 'Perhaps someone can help with that.', 'insufficient_evidence'),
    ('claim_positive', 'message_claims_completion', 'All set.', 'supported'),
    ('claim_negative', 'message_claims_completion', 'The appointment has not been processed yet.', 'contradicted'),
    ('claim_unknown', 'message_claims_completion', 'We will process the appointment tomorrow.', 'insufficient_evidence'),
    ('info_positive', 'message_requests_info', 'Please provide the signed appointment form.', 'supported'),
    ('info_negative', 'message_requests_info', 'We need no additional information or documents from you.', 'contradicted'),
    ('info_unknown', 'message_requests_info', 'Thank you for your patience.', 'insufficient_evidence'),
    ('evidence_positive', 'evidence_addresses', 'Corrected appointment confirmation: Alex Example, 2026-11-01 through 2026-12-31, funding account FUND-A.', 'supported'),
    ('evidence_negative', 'evidence_addresses', 'This is only an acknowledgment, not confirmation of an appointment or funding outcome.', 'contradicted'),
    ('evidence_unknown', 'evidence_addresses', 'All set.', 'insufficient_evidence'),
]


def run(store, config, budget):
    admin.configure_semantics(store, config)
    specs = {name: definition(store, name)[1] for name in SEMANTICS}
    backend = make_backend(config)
    rows = []
    for variant in ('generic', 'specific'):
        for name, spec in specs.items():
            current = copy.deepcopy(spec)
            if variant == 'generic':
                current['version'] = 'admin-message-v2'
                current['choices'] = GENERIC
            register(store, current)
        for case_id, predicate, message, expected in CASES:
            context = CONTEXT
            if predicate == 'evidence_addresses':
                context += ' Evidence required: appointment_confirmation.'
            evidence = [{'id': case_id, 'source': message, 'hash': digest(message)},
                        {'id': 'request_context', 'source': context, 'hash': digest(context)}]
            pair = ('message:' + case_id, 'requirement:appointment_confirmation' if predicate == 'evidence_addresses' else 'request:alex_appointment')
            gateway = Gateway(store, [], budget, backend=backend, predicate=predicate,
                              resolver=lambda *_: (copy.deepcopy(evidence), []))
            result = gateway.resolve([pair])[pair]
            winner = result.get('raw', {}).get('answer', {}).get('choice')
            rows.append({'variant': variant, 'case': case_id, 'expected': expected,
                         'raw_choice_correct': winner == expected if winner else None,
                         'accepted_correct': result['status'] == expected,
                         'decision': result})
    summaries = {}
    for variant in ('generic', 'specific'):
        group = [r for r in rows if r['variant'] == variant]
        summaries[variant] = {
            'cases': len(group), 'raw_responses': sum(r['raw_choice_correct'] is not None for r in group),
            'raw_choices_correct': sum(r['raw_choice_correct'] is True for r in group),
            'accepted_supported': sum(r['decision']['status'] == 'supported' for r in group),
            'false_support': sum(r['decision']['status'] == 'supported' and r['expected'] != 'supported' for r in group),
            'policy_abstentions': sum(r['decision'].get('acceptance') == 'policy_abstention' for r in group),
            'errors_or_budget': sum(r['decision']['status'] in {'backend_error', 'not_evaluated_budget'} for r in group)}
    return {'backend': config['kind'], 'labels': 'Reviewed fictional development examples; not held-out validation.',
            'scope': 'Semantic choice comparison only; no Ollama extraction or workflow inference accuracy measured.',
            'summaries': summaries, 'metrics': budget.metrics, 'stopping_reasons': sorted(budget.stopping), 'cases': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['kev', 'counting_mock'], required=True)
    parser.add_argument('--db', required=True)
    parser.add_argument('--report', default='evaluation/admin-choice-comparison.json')
    parser.add_argument('--definition', default='config/has_skill.json')
    parser.add_argument('--seconds', type=float, default=180)
    args = parser.parse_args()
    if Path(args.db).exists():
        raise SystemExit('Use a fresh database filename.')
    config = json.loads(Path(args.definition).read_text())['backend']
    if args.backend == 'counting_mock':
        config = {'kind': 'counting_mock', 'version': 'choice-eval-plumbing-v1',
                  'fixtures': {predicate + '|' + message: expected for _, predicate, message, expected in CASES}}
    store = Store(args.db)
    try:
        report = run(store, config, Budget(judgments=30, requests=40, seconds=args.seconds))
    finally:
        store.close()
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('backend', 'labels', 'summaries', 'metrics', 'stopping_reasons')}, indent=2))
    print('Full report: ' + args.report)
    return 2 if any(s['errors_or_budget'] for s in report['summaries'].values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
