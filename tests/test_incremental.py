"""Real SQLite/Prolog; reviewed extractions and counting mock decisions."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from kb import admin, incremental
from kb.store import Store
from kb.semantic import Budget
from examples.admin_fixture import REQUEST, TEXTS, extraction, backend


@unittest.skipUnless(shutil.which('swipl'), 'SWI-Prolog required')
class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'kb.sqlite3'
        self.store = Store(self.path)
        admin.install(self.store)
        admin.template_register(self.store, json.loads(Path('config/appointment.json').read_text()))
        admin.configure_semantics(self.store, backend())
        self.ingest('original', '2026-10-12', new=True, template='student_appointment')
        self.ingest('ack', '2026-10-13')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def ingest(self, label, day, **kw):
        return admin.ingest(self.store, TEXTS[label], day, request=REQUEST,
                            extraction=extraction(label), **kw)

    def refresh(self, day='2026-10-20', **kw):
        return incremental.refresh(self.store, day, **kw)

    def test_duplicate_skips_extraction_and_preserves_identity(self):
        before = self.store.db.execute('SELECT count(*) FROM admin_messages').fetchone()[0]
        translator = Mock()
        result = admin.ingest(self.store, TEXTS['ack'], '2026-10-13', request=REQUEST, translator=translator)
        self.assertTrue(result['duplicate'])
        translator.request.assert_not_called()
        self.assertEqual(before, self.store.db.execute('SELECT count(*) FROM admin_messages').fetchone()[0])
        self.assertFalse(self.ingest('ack', '2026-10-14')['duplicate'])

    def test_clock_completion_restart_and_history(self):
        initial = self.refresh()
        self.assertEqual(initial['metrics']['new_judgments'], 8)
        due = self.refresh('2026-10-25', clock_only=True)
        self.assertEqual(due['metrics']['backend_calls'], 0)
        self.assertEqual(due['metrics']['reused_conclusions'], 1)
        self.assertIn('intervention_reached', [f['reason'] for f in due['requests'][0]['flags']])
        self.ingest('correct', '2026-10-26', kind='confirmation')
        done = self.refresh('2026-10-26')
        self.assertEqual(done['requests'][0]['verification'], 'verified_documentary')
        self.assertTrue(done['all_clear'])
        self.assertIn('collection', done['invalidations'][0]['changed_dependencies'])
        self.assertEqual(done['metrics']['new_judgments'], 5)
        self.assertEqual(done['metrics']['cache_hits'], 8)
        self.store.close(); self.store = Store(self.path)
        repeat = self.refresh('2026-10-26', clock_only=True)
        self.assertEqual(repeat['requests'], done['requests'])
        self.assertEqual(repeat['metrics']['backend_calls'], 0)
        transitions = [r[0] for r in self.store.db.execute('SELECT transition FROM alert_history ORDER BY id')]
        self.assertEqual(transitions, ['raised', 'changed', 'withdrawn'])

    def test_unrelated_evidence_preserves_conclusion(self):
        self.refresh()
        other = extraction('original'); other['request_id'] = 'request:other'
        admin.ingest(self.store, TEXTS['original'], '2026-10-12', request='request:other',
                     new=True, template='student_appointment', extraction=other)
        result = self.refresh(request_ids=[REQUEST])
        self.assertEqual(result['metrics']['reused_conclusions'], 1)
        self.assertEqual(result['metrics']['backend_calls'], 0)
        self.assertEqual(result['invalidations'], [])

    def test_budget_does_not_cache_false_completion(self):
        self.ingest('correct', '2026-10-26', kind='confirmation')
        limited = self.refresh('2026-10-26', clock_only=True)
        self.assertFalse(limited['all_clear'])
        self.assertFalse(limited['complete'])
        self.assertTrue(limited['unresolved_checks'])
        self.assertEqual(limited['metrics']['backend_calls'], 0)
        self.assertNotEqual(limited['requests'][0]['verification'], 'verified_documentary')
        resolved = self.refresh('2026-10-26')
        self.assertEqual(resolved['metrics']['reused_conclusions'], 0)
        self.assertTrue(resolved['all_clear'])

    def test_full_reprocessing_calls_backend_and_matches_incremental(self):
        first = self.refresh()
        full = self.refresh(mode='full')
        self.assertEqual(full['metrics']['new_judgments'], 8)
        for key in ('progress', 'verification', 'discrepancies', 'missing_evidence'):
            self.assertEqual(first['requests'][0][key], full['requests'][0][key])
        self.assertEqual(self.refresh()['metrics']['backend_calls'], 0)

    def test_override_invalidates_cached_conclusion(self):
        self.refresh()
        admin.manual_event(self.store, REQUEST, 'intervention', '2026-10-30',
                           'User extends intervention date', '2026-10-21',
                           supersedes=next(e['id'] for e in admin.active_events(self.store, REQUEST, admin.utc('2026-10-20'))
                                           if e['type']=='date' and e['payload']['role']=='intervention'))
        result = self.refresh('2026-10-25', clock_only=True)
        self.assertEqual(result['metrics']['invalidations'], 1)
        self.assertEqual(result['metrics']['backend_calls'], 0)
        self.assertNotIn('intervention_reached', [f['reason'] for f in result['requests'][0]['flags']])

    def test_cli_refresh_and_history(self):
        import subprocess
        command = ['python3','-m','kb','--db',str(self.path),'admin']
        first = json.loads(subprocess.check_output(command+['refresh','--as-of','2026-10-20'],text=True))
        second = json.loads(subprocess.check_output(command+['refresh','--as-of','2026-10-25','--clock-only',
                                                               '--timezone','America/Los_Angeles'],text=True))
        self.assertEqual(second['timezone'],'America/Los_Angeles')
        self.assertTrue(second['as_of'].endswith('-07:00'))
        self.assertEqual(second['metrics']['backend_requests'],0)
        history = json.loads(subprocess.check_output(command+['history',REQUEST],text=True))
        self.assertEqual(len(history['alert_history']),2)

    def test_conflicting_and_superseded_evidence(self):
        wrong = self.ingest('wrong','2026-10-22',kind='confirmation')
        self.refresh('2026-10-25')
        self.ingest('correct','2026-10-26',kind='confirmation')
        conflict = self.refresh('2026-10-26')
        self.assertEqual(conflict['requests'][0]['verification'],'discrepant')
        self.assertFalse(conflict['all_clear'])
        self.ingest('correct','2026-10-27',kind='confirmation',supersedes=wrong['source_id'])
        resolved = self.refresh('2026-10-27')
        self.assertEqual(resolved['requests'][0]['verification'],'verified_documentary')
        self.assertTrue(resolved['all_clear'])

    def test_candidate_limit_and_definition_changes(self):
        self.refresh()
        config = backend();config['version']='changed-fixture-version'
        admin.configure_semantics(self.store,config)
        changed = self.refresh()
        self.assertEqual(changed['metrics']['reused_conclusions'],0)
        self.assertIn('definitions',changed['invalidations'][0]['changed_dependencies'])
        self.assertEqual(changed['metrics']['new_judgments'],8)
        other = extraction('original');other['request_id']='request:other'
        admin.ingest(self.store,TEXTS['original'],'2026-10-12',request='request:other',
                     new=True,template='student_appointment',extraction=other)
        capped = self.refresh(max_requests=1)
        self.assertFalse(capped['complete'])
        self.assertFalse(capped['all_clear'])
        self.assertIn('candidate_request_limit',capped['stopping_reasons'])
        self.assertTrue(any(c.get('reason')=='candidate_request_limit' for c in capped['unresolved_checks']))

    def test_live_runner_detects_hidden_backend_work(self):
        from examples.admin_live_test import validate_no_model_work, TestFailure
        metrics = dict(new_judgments=0, backend_calls=0, backend_requests=0, reused_conclusions=1)
        validate_no_model_work({'metrics': metrics})
        for key in ('new_judgments', 'backend_calls', 'backend_requests'):
            with self.assertRaises(TestFailure):
                validate_no_model_work({'metrics':dict(metrics, **{key:1})})
        with self.assertRaises(TestFailure):
            validate_no_model_work({'metrics':dict(metrics,reused_conclusions=0)})
