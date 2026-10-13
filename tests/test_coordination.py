import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kb.schema import atom as a, assertion as r, proposal as p, Invalid
from kb.store import Store
from kb.semantic import Gateway, Budget, register, validate_raw
from kb.kev import CountingMock, KevBackend
from kb.coordination import Coordination
from examples.research_fixture import records, mock_definition


@unittest.skipUnless(shutil.which('swipl'),'SWI-Prolog required')
class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'kb.sqlite3'
        self.store=Store(self.path);self.store.import_records(records(),'fixture')
        self.definition=mock_definition();register(self.store,self.definition)
        self.mock=CountingMock(self.definition['backend'])
    def tearDown(self): self.store.close();self.tmp.cleanup()
    def ask(self,*query,**kwargs):
        return Coordination(self.store,backend=self.mock,**kwargs).ask(self.store.snapshot()[1],list(query))
    def add(self,*items):
        return self.store.apply('teach','explicit test update',p(items),self.store.snapshot()[0],[])['created']
    def retract(self,ident):
        self.store.apply('retract','test retraction',p(targets=[ident]),self.store.snapshot()[0],[ident])
    def find(self,predicate,*args):
        return next(x for x in self.store.snapshot()[1] if x['assertion']==r(a(predicate,*args)))['id']
    def correct(self,ident,item,source='explicit correction'):
        self.store.apply('correct',source,p([item],targets=[ident]),self.store.snapshot()[0],[ident])
    def candidate(self,task='preprocess',who='?Who',**kw):
        return self.ask(a('candidate',who,'task:'+task,'period:october'),**kw)

    def test_symbolic_filtering_and_unknown(self):
        out=self.candidate()
        self.assertEqual([x['bindings']['Who'] for x in out['rows']],['person:alice'])
        self.assertEqual(out['unresolved_candidates'][0][0]['bindings']['Who'],'person:carol')
        self.assertFalse(out['complete']);self.assertEqual(self.mock.judgments,2)
        self.assertTrue(all(x['arguments'][0]!='person:bob' for x in self.mock.seen))

    def test_cross_task_restart_and_unrelated_update_cache(self):
        self.candidate();self.assertEqual(self.mock.judgments,2)
        self.add(r(a('assigned_to','task:baseline','person:alice')))
        out=self.candidate('baseline');self.assertEqual(out['metrics']['cache_hits'],2)
        self.store.close();self.store=Store(self.path)
        out=self.candidate('document_protocol')
        self.assertEqual(out['metrics']['cache_hits'],2);self.assertEqual(self.mock.judgments,2)

    def test_profile_revision_invalidates_only_one_person(self):
        self.candidate()
        self.correct(self.find('person_profile','person:alice','profile:alice'),r(a('person_profile','person:alice','profile:alice_v2')),source='Alice now has a more detailed Python profile.')
        out=self.candidate();self.assertEqual(out['metrics']['new_judgments'],1);self.assertEqual(out['metrics']['cache_hits'],1)

    def test_definition_model_and_policy_revisions(self):
        self.candidate()
        new=copy.deepcopy(self.definition);new['policy']['version']='strict-v2';new['policy']['threshold']=0.99
        register(self.store,new)
        out=self.candidate();self.assertEqual(out['metrics']['new_judgments'],0)
        new['version']='meaning-v2';register(self.store,new)
        self.assertEqual(self.candidate()['metrics']['new_judgments'],2)
        new['backend']['version']='mock-v2';register(self.store,new);self.mock=CountingMock(new['backend'])
        self.assertEqual(self.candidate()['metrics']['new_judgments'],2)

    def test_override_conflict_retraction_and_cached_model_not_overwrite(self):
        self.candidate()
        yes,no=self.add(r(a('has_skill','person:alice','skill:python')),r(a('lacks_skill','person:alice','skill:python')))
        out=self.candidate(who='person:alice');self.assertEqual(out['rows'],[])
        self.assertEqual(out['unresolved_candidates'][0][0]['judgments'][0]['status'],'conflict')
        self.assertEqual(out['metrics']['new_judgments'],0)
        self.retract(yes);out=self.candidate(who='person:alice');self.assertEqual(out['rejected_candidates'][0][0]['status'],'contradicted')
        self.retract(no);self.assertEqual(len(self.candidate(who='person:alice')['rows']),1)

    def test_all_skills_short_circuit_known_failure_and_batch_counts(self):
        self.add(r(a('requires_skill','task:preprocess','skill:statistics')),
                 r(a('lacks_skill','person:alice','skill:statistics')))
        out=self.candidate(who='person:alice')
        self.assertFalse(out['rows']);self.assertEqual(self.mock.judgments,0)
        self.retract(self.find('lacks_skill','person:alice','skill:statistics'))
        out=self.candidate(who='person:alice')
        self.assertFalse(out['rows']);self.assertEqual(self.mock.judgments,2);self.assertEqual(self.mock.calls,1)
        self.assertFalse(out['complete'])

    def test_first_answer_stops_model_work(self):
        out=self.candidate(first=True)
        self.assertEqual(len(out['rows']),1);self.assertEqual(self.mock.judgments,1)
        self.assertIn('first_answer',out['stopping_reasons']);self.assertFalse(out['complete'])

    def test_budget_and_errors_are_unresolved(self):
        out=self.candidate(budget=Budget(judgments=0))
        self.assertEqual(self.mock.judgments,0);self.assertFalse(out['complete'])
        self.assertEqual(out['unresolved_candidates'][0][0]['judgments'][0]['status'],'not_evaluated_budget')
        self.assertIn('judgment_budget',out['stopping_reasons'])
        config=copy.deepcopy(self.definition);config['backend']['answers']['person:alice|skill:python']='backend_error'
        register(self.store,config);self.mock=CountingMock(config['backend'])
        out=self.candidate(who='person:alice')
        self.assertEqual(out['unresolved_candidates'][0][0]['judgments'][0]['status'],'backend_error')
        self.assertFalse(out['complete'])

    def test_readiness_known_unmet_unknown_and_declared_empty(self):
        out=self.ask(a('ready','?Task'))
        self.assertEqual([x['bindings']['Task'] for x in out['rows']],['task:document_protocol'])
        self.retract(self.find('task_spec_complete','task:document_protocol'))
        out=self.ask(a('ready','task:document_protocol'));self.assertFalse(out['rows']);self.assertFalse(out['complete'])
        self.retract(self.find('resource_status','dataset:d','status:unavailable'))
        out=self.ask(a('ready','task:preprocess'));self.assertFalse(out['complete'])
        self.assertIn('reason:unknown_status',out['unresolved_candidates'][0][0]['reasons'])
        self.add(r(a('resource_status','dataset:d','status:available')))
        self.assertEqual(len(self.ask(a('ready','task:preprocess'))['rows']),1)
        self.assertEqual(self.mock.judgments,0)

    def test_completion_updates_and_dependency_consequences(self):
        self.correct(self.find('task_status','task:preprocess','status:pending'),r(a('task_status','task:preprocess','status:completed')))
        self.assertEqual(len(self.ask(a('ready','task:baseline'))['rows']),1)
        out=self.ask(a('affected_milestone','?M','dataset:d'))
        self.assertEqual(out['rows'][0]['bindings']['M'],'milestone:evaluation_complete')
        self.retract(self.find('task_spec_complete','task:baseline'))
        out=self.ask(a('affected_milestone','?M','dataset:d'));self.assertFalse(out['complete']);self.assertTrue(out['coverage_warnings'])

    def test_cycles_and_symbolic_budgets(self):
        self.add(r(a('depends_on','task:preprocess','task:validate')))
        out=self.ask(a('blocked_by','task:preprocess','?D','?R'))
        self.assertIn('reason:cycle',[x['bindings']['R'] for x in out['rows']])
        out=self.ask(a('ready','?T'),budget=Budget(steps=1));self.assertFalse(out['complete']);self.assertTrue(out['symbolic_error'])
        out=self.ask(a('affected_milestone','?M','dataset:d'),budget=Budget(depth=1));self.assertFalse(out['complete'])

    def test_supported_alternative_beats_unresolved_and_semantic_rules(self):
        self.add(r(a('manages','person:alice','project:p')),
            r(a('needs_notification','?P','dataset:d'),a('manages','?P','project:p'),a('has_skill','?P','skill:unknown')),
            r(a('needs_notification','person:alice','dataset:d')))
        out=self.ask(a('needs_notification','?P','dataset:d'))
        self.assertEqual(len(out['rows']),1);self.assertFalse(out['unresolved_candidates'])
        self.assertEqual(self.mock.judgments,0)

    def test_dependent_rule_cannot_bypass_conflict_gateway(self):
        self.add(r(a('has_skill','person:alice','skill:python')),r(a('lacks_skill','person:alice','skill:python')),
          r(a('needs_notification','?P','dataset:d'),a('has_skill','?P','skill:python')))
        out=self.ask(a('needs_notification','person:alice','dataset:d'))
        self.assertFalse(out['rows']);self.assertFalse(out['complete']);self.assertEqual(self.mock.judgments,0)

    def test_evidence_limit_and_no_evidence(self):
        self.correct(self.find('person_profile','person:alice','profile:alice'),r(a('person_profile','person:alice','profile:long')),source='x'*8000)
        out=self.candidate(who='person:alice');self.assertFalse(out['rows']);self.assertEqual(self.mock.judgments,0)
        self.assertEqual(out['unresolved_candidates'][0][0]['judgments'][0]['origin'],'evidence_limit')
        self.retract(self.find('person_profile','person:alice','profile:long'))
        out=self.candidate(who='person:alice');self.assertEqual(out['unresolved_candidates'][0][0]['judgments'][0]['origin'],'deterministic')


class KevContractTests(unittest.TestCase):
    def test_admin_payload_labels_original_text_without_provenance_ids(self):
        from kb import admin
        from kb.semantic import definition
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'kb.sqlite3')
            config=json.loads(Path('config/has_skill.json').read_text())['backend']
            admin.configure_semantics(store,config)
            _,spec=definition(store,'message_acknowledges')
            evidence=[{'id':'m_private_id','source':'Received, we’ll take care of it.','hash':'opaque'},
                      {'id':'w_context','source':'Requested outcome: an appointment.'}]
            request={'arguments':['message:m_private_id','request:appointment'],
                     'evidence':evidence,'definition':spec}
            backend=KevBackend(config);backend.verified=True;backend.model_metadata={}
            with patch.object(backend,'request',return_value={'answers':{'q0':{}}}) as call:
                backend.evaluate([request],10)
            payload=call.call_args.args[1]
            self.assertEqual(payload['state'],{'message':evidence[0]['source'],
                                               'request_context':[evidence[1]['source']]})
            self.assertNotIn('m_private_id',json.dumps(payload))
            self.assertNotIn('opaque',json.dumps(payload))
            self.assertIn('message field',payload['questions']['q0']['instructions'])
            self.assertEqual(evidence[0]['id'],'m_private_id')
            self.assertEqual(spec['policy']['threshold'],0.60)
            store.close()

    def test_temperature_mismatch_is_rejected_before_scoring(self):
        config=json.loads(Path('config/has_skill.json').read_text())['backend']
        backend=KevBackend(config)
        models={'models':[{'name':'kev-latest','run':config['checkpoint'],'truncate_states':False,
                          'backend':'mlx','dtype':'bfloat16','temperature':2.41}]}
        with patch.object(backend,'request',return_value=models) as request:
            with self.assertRaisesRegex(Invalid,'temperature differs'):
                backend.evaluate([],10)
        self.assertEqual(request.call_count,1)

    def test_demo_surfaces_unique_backend_errors(self):
        from examples.admin_demo import backend_errors
        error={'status':'backend_error','error':'temperature mismatch'}
        self.assertEqual(backend_errors({'rows':[error,error], 'other':{'status':'supported'}}),
                         ['temperature mismatch'])

    def test_real_protocol_batches_only_same_evidence(self):
        from kb.semantic import validate_raw
        config=json.loads(Path('config/has_skill.json').read_text())
        backend=KevBackend(config['backend'])
        models={'models':[{'name':'kev-latest','run':config['backend']['checkpoint'],'truncate_states':False,
                          'backend':'mlx','dtype':'bfloat16','temperature':2.406050072164233}]}
        answer={'type':'choice','choice':'supported','confidence':0.8,
                'probabilities':{'supported':0.95,'contradicted':0.01,'insufficient_evidence':0.04}}
        response={'answers':{'q0':answer,'q1':answer},'latency_ms':12,'model':'kev-latest'}
        requests=[{'arguments':['person:alice',skill],'evidence':[{'source':'Original profile'}],'definition':config}
                  for skill in ['skill:python','skill:statistics']]
        with patch.object(backend,'request',side_effect=[models,response]) as mock:
            results=backend.evaluate(requests,10)
        for result in results: validate_raw(result)
        self.assertEqual(mock.call_args.args[0],'/v1/systemone')
        payload=mock.call_args.args[1];self.assertEqual(len(payload['questions']),2)
        self.assertEqual(payload['state'],requests[0]['evidence'])
        self.assertEqual(payload['questions']['q0']['type'],'choice')
        requests[1]['evidence']=[{'source':'Bob profile'}]
        with self.assertRaises(Invalid):backend.evaluate(requests,10)

    def test_bad_scores_and_truncation_rejected(self):
        for raw in [{'answer':{}},{'truncated':True,'answer':{'probabilities':{},'choice':'supported'}}]:
            with self.assertRaises(Invalid):validate_raw(raw)
