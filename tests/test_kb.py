import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kb.schema import Invalid, atom as a, assertion as rule, proposal as p, validate
from kb.store import Store
from kb.prolog import Prolog, program, InferenceError
from kb.llm import Ollama
from kb.service import execute

ALICE = rule(a("manages", "person:alice", "project:p"))
BOB = rule(a("manages", "person:bob", "project:p"))
USES = rule(a("uses", "project:p", "dataset:d"))
RENEW = rule(a("requires_renewal", "dataset:d"))
NOTIFY = rule(a("needs_notification", "?Who", "?Data"), a("manages", "?Who", "?Project"),
              a("uses", "?Project", "?Data"), a("requires_renewal", "?Data"))
QUERY = [a("needs_notification", "?Who", "?Data")]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "kb.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def teach(self, *items):
        revision, _ = self.store.snapshot()
        return self.store.apply("teach", "original utterance", p(items), revision, [])['created']

    def test_correction_retraction_and_restart(self):
        alice, = self.teach(ALICE)
        rev, _ = self.store.snapshot()
        bob, = self.store.apply("correct", "Bob instead of Alice", p([BOB], targets=[alice]), rev, [alice])["created"]
        self.store.close()
        self.store = Store(self.path)
        rev, active = self.store.snapshot()
        self.assertEqual([r['id'] for r in active], [bob])
        self.assertEqual(active[0]["supersedes"], alice)
        self.store.apply("retract", "Remove Bob", p(targets=[bob]), rev, [bob])
        self.assertEqual(self.store.snapshot()[1], [])
        self.assertEqual(len(self.store.snapshot(False)[1]), 2)
        self.assertEqual(len(self.store.events()), 3)

    def test_rule_ingestion_and_sources(self):
        ids = self.teach(NOTIFY)
        record = self.store.snapshot()[1][0]
        self.assertEqual(record['assertion'], NOTIFY)
        self.assertEqual(record['source'], "original utterance")
        self.assertEqual(record['id'], ids[0])

    def test_no_implicit_exclusivity(self):
        self.teach(ALICE, BOB)
        self.assertEqual(len(self.store.snapshot()[1]), 2)

    def test_stale_update_is_atomic(self):
        ident, = self.teach(ALICE)
        rev, _ = self.store.snapshot()
        self.teach(USES)
        with self.assertRaises(Invalid):
            self.store.apply('correct', 'Bob', p([BOB], targets=[ident]), rev, [ident])
        self.assertEqual(self.store.snapshot()[1][0]['status'], 'active')
        self.assertEqual(len(self.store.events()), 2)

    def test_invalid_rule_leaves_target_active(self):
        ident, = self.teach(ALICE)
        rev, _ = self.store.snapshot()
        with self.assertRaises(Invalid):
            self.store.apply('correct', 'bad', p([rule(a('manages', '?X', 'project:p'))], targets=[ident]), rev, [ident])
        self.assertEqual(self.store.snapshot()[1][0]['id'], ident)

    def test_transaction_rollback_after_retraction(self):
        ident, = self.teach(ALICE)
        self.store.db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        self.store.db.commit()
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.apply('correct', 'Bob', p([BOB], targets=[ident]), 1, [ident])
        self.assertEqual(self.store.snapshot()[0], 1)
        self.assertEqual(self.store.snapshot()[1][0]['id'], ident)

    def test_candidate_bounds_and_target(self):
        ids = self.teach(ALICE, USES, RENEW)
        _, candidates, overflow = self.store.candidates('dataset D')
        self.assertEqual({r['id'] for r in candidates}, set(ids[1:]))
        self.assertFalse(overflow)
        self.assertEqual(self.store.candidates('it')[1], [])
        self.assertEqual(self.store.candidates('it', ids[0])[1][0]['id'], ids[0])

    def test_preview_and_clarification_do_not_write(self):
        class Fake:
            def translate(self, *args): return p([ALICE]), {}
        execute(self.store, Fake(), None, 'teach', 'Alice manages P', preview=True)
        self.assertEqual(self.store.snapshot()[0], 0)
        class Clarify:
            def translate(self, *args): return p(status='clarify', explanation='Which person?'), {}
        execute(self.store, Clarify(), None, 'teach', 'She manages it')
        self.assertEqual(self.store.snapshot()[0], 0)


class SchemaTests(unittest.TestCase):
    def test_accept_rule_and_query(self):
        validate(p([NOTIFY]), 'teach')
        validate(p(query=QUERY), 'ask')

    def test_reject_unsafe_and_wrong_types(self):
        bad = [rule(a('shell', 'person:alice')), rule(a('manages','?X','project:p')),
               rule(a('manages','dataset:d','project:p')),
               rule(a('manages',"person:alice');halt.",'project:p')),
               rule(a('manages','?X','?Y'), a('uses','?X','?Y'))]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(Invalid):
                validate(p([item]), 'teach')

    def test_extra_fields_and_operation_mismatch(self):
        bad = p([ALICE]); bad['prolog'] = 'halt.'
        with self.assertRaises(Invalid): validate(bad, 'teach')
        with self.assertRaises(Invalid): validate(p([ALICE]), 'ask')
        with self.assertRaises(Invalid): validate(p(targets=['a_'+'1'*32]), 'retract')

    def test_compilation_is_data_only(self):
        code = program([{'id':'a_'+'1'*32, 'assertion':NOTIFY}], QUERY)
        self.assertIn('rule(needs_notification(V_Who,V_Data)', code)
        self.assertNotIn('needs_notification(V_Who,V_Data) :-', code)


class AdapterTests(unittest.TestCase):
    def test_ollama_contract_and_bounded_context(self):
        llm = Ollama()
        response = {'message': {'content': json.dumps(p([ALICE]))}, 'done_reason': 'stop'}
        with patch.object(llm, 'request', return_value=response) as request:
            result, metrics = llm.translate('teach', 'Alice manages project P', [])
        self.assertEqual(result, p([ALICE]))
        endpoint, payload = request.call_args.args
        self.assertEqual(endpoint, '/api/chat')
        self.assertEqual(len(payload['messages']), 2)
        self.assertFalse(payload['think'])
        self.assertIsInstance(payload['format'], dict)
        self.assertGreaterEqual(metrics['translation_seconds'], 0)

    def test_bad_output_rejected(self):
        llm = Ollama()
        with patch.object(llm, 'request', return_value={'message': {'content':'not json'}}):
            with self.assertRaises(Invalid): llm.translate('teach', 'hi', [])


@unittest.skipUnless(shutil.which('swipl'), 'SWI-Prolog unavailable; actual inference not tested')
class PrologTests(unittest.TestCase):
    setUp = StoreTests.setUp
    tearDown = StoreTests.tearDown
    teach = StoreTests.teach
    def test_full_demo_with_process_restart(self):
        alice, uses, renew, notification = self.teach(ALICE, USES, RENEW, NOTIFY)
        engine = Prolog()
        def ask(): return engine.ask(self.store.snapshot()[1], QUERY)
        result = ask()
        self.assertEqual(result['rows'][0]['bindings'], {'Who':'person:alice', 'Data':'dataset:d'})
        self.assertEqual(set(result['rows'][0]['support']), {alice, uses, renew, notification})
        self.store.apply('correct', 'Bob now instead', p([BOB], targets=[alice]), 1, [alice])
        self.assertEqual(ask()['rows'][0]['bindings']['Who'], 'person:bob')
        script = 'from kb.store import Store; from kb.prolog import Prolog; import json,sys; s=Store(sys.argv[1]); print(json.dumps(Prolog().ask(s.snapshot()[1],json.loads(sys.argv[2]))))'
        completed = subprocess.run([sys.executable, '-c', script, str(self.path), json.dumps(QUERY)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(completed.stdout)['rows'][0]['bindings']['Who'], 'person:bob')
        self.store.apply('retract', 'No renewal', p(targets=[renew]), 2, [renew])
        self.assertEqual(ask()['rows'], [])

    def test_multistep_cycles_and_result_limits(self):
        self.teach(ALICE, USES, NOTIFY,
            rule(a('requires_renewal','?D'), a('uses','?P','?D')),
            rule(a('requires_renewal','?D'), a('needs_notification','?Who','?D')))
        result = Prolog().ask(self.store.snapshot()[1], QUERY)
        self.assertEqual(len(result['rows']), 1)
        self.teach(BOB)
        result = Prolog(limit=1).ask(self.store.snapshot()[1], QUERY)
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['rows']), 1)

    def test_closure_cap_returns_error_not_empty_answer(self):
        self.teach(ALICE, USES)
        from kb import prolog
        original = prolog.program
        def capped(*args, **kwargs):
            return original(*args, **kwargs, max_facts=1)
        with patch.object(prolog, 'program', side_effect=capped):
            with self.assertRaises(InferenceError):
                Prolog().ask(self.store.snapshot()[1], QUERY)

    def test_unknown_and_boolean(self):
        self.teach(ALICE)
        self.assertEqual(Prolog().ask(self.store.snapshot()[1], QUERY)['rows'], [])
        self.assertEqual(Prolog().ask(self.store.snapshot()[1], [ALICE['head']])['rows'][0]['bindings'], {})


if __name__ == '__main__': unittest.main()
