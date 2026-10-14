import json
import shutil
import tempfile
import unittest
from pathlib import Path
from kb import admin
from kb.store import Store
from kb.semantic import Budget,encoded
from kb.schema import Invalid
from kb.admin_schema import empty
from examples.admin_fixture import REQUEST,TEXTS,extraction,backend


@unittest.skipUnless(shutil.which('swipl'),'SWI-Prolog required')
class AdminTests(unittest.TestCase):
    def test_live_runner_validates_extractions_without_repairing_them(self):
        from examples.admin_live_test import validate_extraction, TestFailure
        for label in ('original','ack','claim','wrong','correct'):
            result={'incorporated':True,'extraction':extraction(label)}
            validate_extraction(label,result)
        bad=extraction('wrong');bad['expected']=bad['observed'][:]
        with self.assertRaises(TestFailure):
            validate_extraction('wrong',{'incorporated':True,'extraction':bad})
        with self.assertRaises(TestFailure):
            validate_extraction('ack',{'incorporated':False,'extraction':{'explanation':'Needs review'}})
        wrong_basis=extraction('original')
        next(d for d in wrong_basis['dates'] if d['role']=='intervention')['basis']='documented'
        with self.assertRaisesRegex(TestFailure,'original.dates: expected .*user_preference.*got .*documented'):
            validate_extraction('original',{'incorporated':True,'extraction':wrong_basis})
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'kb.sqlite3';self.store=Store(self.path)
        admin.install(self.store);admin.template_register(self.store,json.loads(Path('config/appointment.json').read_text()))
        admin.configure_semantics(self.store,backend())
        self.ingest('original','2026-10-12',new=True,template='student_appointment')
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def ingest(self,label,at,**kw):return admin.ingest(self.store,TEXTS[label],at,request=REQUEST,extraction=extraction(label),**kw)
    def check(self,day='2026-10-25',**kw):
        report=admin.report(self.store,day,budget=kw.pop('budget',Budget(judgments=64,requests=64)),**kw)
        return report,report['requests'][0]
    def set(self,field,value,at='2026-10-19',supersedes=None):
        return admin.manual_event(self.store,REQUEST,field,value,'Explicit user instruction',at,supersedes)
    def test_ack_claim_verified_are_distinct(self):
        self.ingest('ack','2026-10-13');_,row=self.check('2026-10-20')
        self.assertTrue(row['progress_assessments']['acknowledged']);self.assertFalse(row['progress_assessments']['completion_claim'])
        self.assertEqual(row['verification'],'unverified')
        self.ingest('claim','2026-10-21');_,row=self.check('2026-10-21')
        self.assertEqual(row['progress'],'claimed_complete');self.assertEqual(row['verification'],'unverified')
        self.ingest('correct','2026-10-22',kind='confirmation');_,row=self.check()
        self.assertEqual(row['verification'],'verified_documentary');self.assertFalse(row['flags'])
    def test_live_extraction_request_context_and_unfulfilled_request_ingestion(self):
        from unittest.mock import Mock
        translator=Mock(model='test-model')
        extracted=extraction('original');extracted['request_id']='request:new_appointment'
        translator.request.return_value={'message':{'content':json.dumps(extracted)}}
        result=admin.ingest(self.store,TEXTS['original'],'2026-10-12',
                            request='request:new_appointment',new=True,template='student_appointment',translator=translator)
        self.assertTrue(result['incorporated'])
        payload=translator.request.call_args.args[1]
        context=json.loads(payload['messages'][-1]['content'])
        self.assertEqual(context['operation'],'new_request')
        self.assertNotIn('source_at',context)
        self.assertEqual(context['source'],TEXTS['original'])
        self.assertEqual(payload['format']['properties']['observed']['items']['properties']['name']['enum'],
                         ['allocation','end_date','funding_account','person','start_date'])
        events=admin.active_events(self.store,'request:new_appointment',admin.utc('2026-10-12'))
        self.assertEqual(sum(e['type']=='expected' for e in events),4)
        self.assertFalse(any(e['type'] in {'observed','document','document_absent','dependency'} for e in events))
    def test_workflow_dates_cannot_be_extracted_as_appointment_observations(self):
        from unittest.mock import Mock
        from kb.admin_schema import EXTRACTION, extraction_schema
        from kb.schema import check_schema
        tpl=json.loads(Path('config/appointment.json').read_text())
        schema=extraction_schema(tpl)
        invalid=extraction('original')
        invalid['observed']=[{'name':'submission','value':'2026-10-12'}]
        with self.assertRaises(Invalid):check_schema(invalid,schema)
        self.assertNotIn('enum',EXTRACTION['properties']['observed']['items']['properties']['name'])
        # Another domain gets its own fields, not the appointment allowlist.
        other=dict(tpl,fields={'purchase_amount':'amount'},required_documents=[])
        self.assertEqual(extraction_schema(other)['properties']['expected']['items']['properties']['name']['enum'],['purchase_amount'])
        self.assertEqual(extraction_schema(other)['properties']['documents']['maxItems'],0)
        translator=Mock(model='test-model')
        invalid['request_id']='request:bad_observation'
        translator.request.return_value={'message':{'content':json.dumps(invalid)}}
        result=admin.ingest(self.store,TEXTS['original'],'2026-10-12',request='request:bad_observation',
                            new=True,template='student_appointment',translator=translator)
        self.assertFalse(result['incorporated'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM admin_events WHERE request_id=?',
                                              ('request:bad_observation',)).fetchone()[0],0)
        self.assertIsNotNone(self.store.db.execute('SELECT id FROM admin_messages WHERE id=?',
                                                  (result['source_id'],)).fetchone())
    def test_ack_extraction_keeps_timestamp_out_of_workflow_dates(self):
        from unittest.mock import Mock
        from kb.admin_schema import extraction_schema
        from kb.schema import check_schema
        translator=Mock(model='test-model')
        translator.request.return_value={'message':{'content':json.dumps(empty(REQUEST))}}
        result=admin.ingest(self.store,TEXTS['ack'],'2026-10-13',request=REQUEST,translator=translator)
        self.assertTrue(result['incorporated'])
        payload=translator.request.call_args.args[1]
        self.assertNotIn('2026-10-13',json.dumps(payload))
        self.assertEqual(json.loads(payload['messages'][-1]['content'])['source'],TEXTS['ack'])
        events=admin.active_events(self.store,REQUEST,admin.utc('2026-10-20'))
        self.assertEqual([e['type'] for e in events if e['source_id']==result['source_id']],['association'])
        _,row=self.check('2026-10-20')
        self.assertEqual(row['latest_evidence']['id'],result['source_id'])
        self.assertTrue(row['progress_assessments']['acknowledged'])
        for role,value in [('follow_up',''),('submission','unknown')]:
            bad=empty(REQUEST);bad['dates']=[{'role':role,'value':value,'basis':'documented'}]
            with self.assertRaises(Invalid):check_schema(bad,extraction_schema())
        good=empty(REQUEST);good['dates']=[{'role':'lead_days','value':'7','basis':'user_preference'}]
        check_schema(good,extraction_schema())
        template=json.loads(Path('config/appointment.json').read_text())
        for role,value in [('lead_days','2026-10-13'),('submission','7'),('submission','2026-02-31')]:
            bad=empty(REQUEST);bad['dates']=[{'role':role,'value':value,'basis':'documented'}]
            with self.assertRaises(Invalid):admin.extracted_events(bad,template)
    def test_input_format_change_invalidates_cache_but_preserves_old_judgments(self):
        from kb.semantic import definition,register
        self.ingest('ack','2026-10-13')
        _,spec=definition(self.store,'message_acknowledges')
        old=dict(spec);old.pop('input_format');old['version']='admin-message-v1'
        register(self.store,old)
        first,_=self.check()
        repeated,_=self.check()
        self.assertEqual(first['metrics']['new_judgments'],8)
        self.assertEqual(repeated['metrics']['new_judgments'],0)
        count=self.store.db.execute('SELECT count(*) FROM raw_judgments').fetchone()[0]
        register(self.store,spec)
        changed,_=self.check()
        self.assertEqual(changed['metrics']['new_judgments'],2)
        self.assertEqual(changed['metrics']['cache_hits'],6)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM raw_judgments').fetchone()[0],count+2)
    def test_choice_comparison_uses_gateway_and_keeps_policy_fixed(self):
        from evaluation.admin_choices import CASES,run
        config={'kind':'counting_mock','version':'test-comparison',
                'fixtures':{pred+'|'+text:label for _,pred,text,label in CASES}}
        out=run(self.store,config,Budget(judgments=30,requests=40))
        self.assertEqual(out['metrics']['new_judgments'],30)
        for summary in out['summaries'].values():
            self.assertEqual(summary['raw_choices_correct'],15)
            self.assertEqual(summary['false_support'],0)
        for case in out['cases']:
            self.assertEqual(case['decision']['policy']['threshold'],0.60)
            self.assertEqual(case['decision']['policy']['margin'],0.2)
        repeat=run(self.store,config,Budget(judgments=0,requests=0))
        self.assertEqual(repeat['metrics']['cache_hits'],30)
        self.assertEqual(repeat['metrics']['backend_calls'],0)
    def test_exact_mismatch_and_explicit_supersession(self):
        wrong=self.ingest('wrong','2026-10-22',kind='confirmation');_,row=self.check()
        self.assertEqual(row['discrepancies'][0]['field'],'funding_account');self.assertEqual(row['discrepancies'][0]['observed'],'FUND-B')
        self.assertIn('intervention_reached',[x['reason'] for x in row['flags']])
        self.ingest('correct','2026-10-26',kind='confirmation',supersedes=wrong['source_id'])
        _,row=self.check('2026-10-26');self.assertEqual(row['verification'],'verified_documentary')
        _,past=self.check('2026-10-25');self.assertEqual(past['verification'],'discrepant')
    def test_confirmation_cannot_introduce_expectations(self):
        from unittest.mock import Mock
        from kb.admin_schema import extraction_schema
        from kb.schema import check_schema
        bad=extraction('wrong');bad['expected']=bad['observed'][:]
        schema=extraction_schema(json.loads(Path('config/appointment.json').read_text()),kind='confirmation')
        with self.assertRaises(Invalid):check_schema(bad,schema)
        rejected=admin.ingest(self.store,TEXTS['wrong'],'2026-10-22',kind='confirmation',request=REQUEST,extraction=bad)
        self.assertFalse(rejected['incorporated'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM admin_events WHERE source_id=?',
                                              (rejected['source_id'],)).fetchone()[0],0)
        translator=Mock(model='test-model')
        translator.request.return_value={'message':{'content':json.dumps(extraction('wrong'))}}
        accepted=admin.ingest(self.store,TEXTS['wrong'],'2026-10-22',kind='confirmation',request=REQUEST,translator=translator)
        self.assertTrue(accepted['incorporated'])
        self.assertEqual(translator.request.call_args.args[1]['format']['properties']['expected']['maxItems'],0)
        examples=[json.loads(m['content']) for m in translator.request.call_args.args[1]['messages'] if m['role']=='assistant']
        confirmation=next(e for e in examples if e['documents']==['appointment_confirmation'])
        self.assertEqual(confirmation['dates'],[])
        self.assertEqual(confirmation['expected'],[])
        self.assertEqual(confirmation['observed'][0]['value'],'Morgan Sample')
        _,row=self.check()
        mismatch=next(d for d in row['discrepancies'] if d.get('field')=='funding_account')
        self.assertEqual(mismatch['observed'],'FUND-B')
        expected=[e['payload']['value'] for e in admin.active_events(self.store,REQUEST,admin.utc('2026-10-25'))
                  if e['type']=='expected' and e['payload']['name']=='funding_account']
        self.assertEqual(expected,['FUND-A'])
    def test_confirmation_summary_cannot_redefine_desired_outcome(self):
        from kb.admin_schema import extraction_schema
        from kb.schema import check_schema
        bad=extraction('correct');bad['desired_outcome']='Corrected appointment confirmation for Alex Example.'
        schema=extraction_schema(json.loads(Path('config/appointment.json').read_text()),kind='confirmation')
        with self.assertRaises(Invalid):check_schema(bad,schema)
        rejected=admin.ingest(self.store,TEXTS['correct'],'2026-10-26',kind='confirmation',request=REQUEST,extraction=bad)
        self.assertFalse(rejected['incorporated'])
        with self.assertRaises(Invalid):
            admin.associate(self.store,rejected['source_id'],REQUEST,'Review association','2026-10-26')
        accepted=self.ingest('correct','2026-10-26',kind='confirmation')
        _,row=self.check('2026-10-26')
        self.assertEqual(row['verification'],'verified_documentary')
        self.assertEqual(row['desired_outcome'],extraction('original')['desired_outcome'])
        self.assertFalse(row['discrepancies'])
    def test_rejected_date_proposal_retained_without_superseding_evidence(self):
        from unittest.mock import Mock
        wrong=self.ingest('wrong','2026-10-22',kind='confirmation')
        bad=extraction('correct')
        bad['dates']=[{'role':'follow_up','value':'','basis':'documented'}]
        translator=Mock(model='test-model')
        translator.request.return_value={'message':{'content':json.dumps(bad)}}
        out=admin.ingest(self.store,TEXTS['correct'],'2026-10-26',kind='confirmation',request=REQUEST,
                         supersedes=wrong['source_id'],translator=translator)
        self.assertFalse(out['incorporated'])
        self.assertEqual(out['extraction']['rejected_proposal'],bad)
        saved=json.loads(self.store.db.execute('SELECT extraction FROM admin_messages WHERE id=?',
                                              (out['source_id'],)).fetchone()[0])
        self.assertEqual(saved['rejected_proposal'],bad)
        self.assertIsNone(self.store.db.execute('SELECT superseded_at FROM admin_messages WHERE id=?',
                                               (wrong['source_id'],)).fetchone()[0])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM admin_events WHERE source_id=?',
                                              (out['source_id'],)).fetchone()[0],0)
    def test_conflicting_evidence_does_not_use_newest(self):
        self.ingest('wrong','2026-10-22',kind='confirmation');self.ingest('correct','2026-10-23',kind='confirmation')
        _,row=self.check();self.assertEqual(row['verification'],'discrepant')
        self.assertTrue(row['documentary_proofs']);self.assertTrue(row['discrepancies'])
    def test_missing_vs_explicit_absence(self):
        _,row=self.check();self.assertFalse(row['known_absent']);self.assertIn('not observed',row['missing_evidence'][0])
        ext=empty(REQUEST);ext['absent_documents']=['appointment_confirmation']
        admin.ingest(self.store,'The appointment confirmation document is absent.','2026-10-19',request=REQUEST,extraction=ext)
        _,row=self.check();self.assertEqual(row['known_absent'][0]['document'],'appointment_confirmation')
    def test_date_boundaries_timezone_and_lead_days(self):
        _,row=self.check('2026-10-20T03:59:59Z');self.assertNotIn('follow_up_due',[x['reason'] for x in row['flags']])
        _,row=self.check('2026-10-20T04:00:00Z');self.assertIn('follow_up_due',[x['reason'] for x in row['flags']])
        self.set('deadline','2026-11-01');self.set('lead_days','7')
        _,row=self.check('2026-11-01');self.assertNotIn('overdue',[x['reason'] for x in row['flags']])
        _,row=self.check('2026-11-02');self.assertEqual(row['flags'][0]['reason'],'overdue')
        with self.assertRaises(Invalid):admin.moment('2026-11-01T01:30:00')
        self.assertNotEqual(admin.utc('2026-11-01T01:30:00-04:00'),admin.utc('2026-11-01T01:30:00-05:00'))
    def test_snooze_does_not_hide_discrepancy_or_intervention(self):
        self.ingest('wrong','2026-10-22',kind='confirmation');self.set('snooze','2026-10-30',at='2026-10-23')
        _,row=self.check();flags=[x['reason'] for x in row['flags']]
        self.assertIn('discrepancy',flags);self.assertIn('intervention_reached',flags);self.assertNotIn('follow_up_due',flags)
        self.assertEqual(row['dates']['intervention']['value'],'2026-10-25')
    def test_user_confirmation_separate_and_retractable(self):
        confirmation=self.set('confirm','true');_,row=self.check()
        self.assertEqual(row['verification'],'user_confirmed');self.assertFalse(row['documentary_proofs'])
        admin.retract_event(self.store,confirmation['event_id'],'Withdraw user confirmation','2026-10-24')
        _,row=self.check();self.assertEqual(row['verification'],'unverified')
    def test_field_correction_and_source_history(self):
        wrong=self.ingest('wrong','2026-10-22',kind='confirmation')
        old=next(e for e in admin.active_events(self.store,REQUEST,admin.utc('2026-10-23')) if e['type']=='observed' and e['payload']['name']=='funding_account')
        self.set('observed:funding_account','FUND-A',at='2026-10-23',supersedes=old['id'])
        _,row=self.check();self.assertEqual(row['verification'],'verified_documentary')
        self.assertEqual(self.store.db.execute('SELECT text FROM admin_messages WHERE id=?',(wrong['source_id'],)).fetchone()[0],TEXTS['wrong'])
    def test_ambiguity_retained_and_association_corrected(self):
        msg=admin.ingest(self.store,TEXTS['ambiguous'],'2026-10-18',extraction=extraction('ambiguous'))
        report,_=self.check();self.assertEqual(len(report['unassigned_messages']),1)
        admin.associate(self.store,msg['source_id'],REQUEST,'This concerns Alex appointment','2026-10-19')
        report,_=self.check();self.assertFalse(report['unassigned_messages'])
        ext=empty(REQUEST);ext['dates']=[{'role':'follow_up','value':'11/12','basis':'documented'}]
        msg=admin.ingest(self.store,TEXTS['date'],'2026-10-19',request=REQUEST,extraction=ext)
        self.assertFalse(msg['incorporated']);self.assertEqual(msg['extraction']['status'],'clarify')
    def test_cache_restart_budget_and_invalidation(self):
        self.ingest('correct','2026-10-22',kind='confirmation')
        first,row=self.check();self.assertEqual(row['verification'],'verified_documentary');self.assertGreater(first['metrics']['new_judgments'],0)
        self.store.close();self.store=Store(self.path)
        repeat,row=self.check();self.assertEqual(repeat['metrics']['new_judgments'],0)
        self.set('snooze','2026-10-30');repeat,row=self.check();self.assertEqual(repeat['metrics']['new_judgments'],0)
        ext=empty(REQUEST);ext['observed']=extraction('correct')['observed'];ext['documents']=['appointment_confirmation']
        admin.ingest(self.store,'A differently worded confirmation.','2026-10-24',kind='confirmation',request=REQUEST,extraction=ext)
        out,row=self.check(budget=Budget(judgments=0));self.assertEqual(out['metrics']['new_judgments'],0)
        # Existing valid proof still establishes completion despite an unresolved alternative.
        self.assertEqual(row['verification'],'verified_documentary');self.assertFalse(out['complete'])
    def test_budget_cannot_manufacture_verification(self):
        self.ingest('correct','2026-10-22',kind='confirmation')
        out,row=self.check(budget=Budget(judgments=0));self.assertEqual(row['verification'],'unverified');self.assertFalse(out['complete'])
    def test_tentative_dates_not_institutional_deadlines(self):
        admin.manual_event(self.store,REQUEST,'deadline','2026-10-13','A tentative estimate','2026-10-12',basis='tentative')
        _,row=self.check();self.assertIsNone(row['dates']['deadline']['value']);self.assertNotIn('overdue',[f['reason'] for f in row['flags']])

    def test_ambiguous_matching_cannot_be_guessed_by_model(self):
        msg=admin.ingest(self.store,'All set.','2026-10-18',extraction=empty(REQUEST))
        self.assertFalse(msg['incorporated']);self.assertEqual(msg['extraction']['status'],'clarify')

    def test_semantic_override_conflict_is_flagged(self):
        source=self.ingest('correct','2026-10-22',kind='confirmation')['source_id']
        args=['message:'+source,'requirement:appointment_confirmation']
        with self.store.db:
            for i,status in enumerate(('supported','contradicted')):
                self.store.db.execute('INSERT INTO semantic_overrides VALUES(?,?,?,?,?,?,?)',
                    ('o_'+str(i),'evidence_addresses',encoded(args),status,'Human evidence review',admin.utc('2026-10-23'),None))
        out,row=self.check()
        self.assertEqual(row['verification'],'discrepant')
        self.assertTrue(any(x['type']=='semantic_conflict' for x in row['discrepancies']))
        self.assertTrue(row['flags'])

    def test_template_steps_gate_documentary_verification(self):
        tpl=json.loads(Path('config/appointment.json').read_text());tpl['name']='with_approval'
        tpl['steps']=[{'name':'submission','requires':[]},{'name':'approval','requires':['submission']},{'name':'verification','requires':['approval','appointment_confirmation']}]
        admin.template_register(self.store,tpl)
        ext=extraction('original');ext['request_id']='request:second'
        admin.ingest(self.store,TEXTS['original'],'2026-10-12',request='request:second',new=True,template='with_approval',extraction=ext)
        ext=extraction('correct');ext['request_id']='request:second'
        admin.ingest(self.store,TEXTS['correct'],'2026-10-22',request='request:second',kind='confirmation',extraction=ext)
        out=admin.report(self.store,'2026-10-25',budget=Budget(judgments=64,requests=64))
        row=next(r for r in out['requests'] if r['request_id']=='request:second')
        self.assertEqual(row['verification'],'unverified')
        admin.manual_event(self.store,'request:second','step:approval','true','Approval explicitly confirmed','2026-10-24')
        out=admin.report(self.store,'2026-10-25',budget=Budget(judgments=64,requests=64))
        self.assertEqual(next(r for r in out['requests'] if r['request_id']=='request:second')['verification'],'verified_documentary')

    def test_cli_restart_and_cache_reuse(self):
        import subprocess,sys
        self.ingest('correct','2026-10-22',kind='confirmation');self.check()
        def run(*args):
            result=subprocess.run([sys.executable,'-m','kb','--db',str(self.path),'admin',*args],capture_output=True,text=True,check=True)
            return json.loads(result.stdout)
        first=run('check','--as-of','2026-10-25');second=run('check','--as-of','2026-10-25')
        self.assertEqual(first['requests'],second['requests'])
        self.assertEqual(first['metrics']['new_judgments'],0)
        self.assertEqual(second['metrics']['backend_calls'],0)
        self.assertTrue(run('inspect',REQUEST)['messages'])

    def test_calendar_lead_and_dependent_requests(self):
        intervention=next(e for e in admin.active_events(self.store,REQUEST,admin.utc('2026-10-19')) if e['type']=='date' and e['payload']['role']=='intervention')
        admin.retract_event(self.store,intervention['id'],'Replace fixed intervention with explicit calendar lead','2026-10-19')
        self.set('deadline','2026-11-01');self.set('lead_days','7')
        _,row=self.check();self.assertEqual(row['dates']['intervention']['value'],'2026-10-25')
        ext=empty(REQUEST);ext['dependencies']=['request:unknown']
        admin.ingest(self.store,'This depends on another request not yet in our record.','2026-10-19',request=REQUEST,extraction=ext)
        _,row=self.check();self.assertEqual(row['unresolved_dependencies'][0]['reason'],'not_observed')
        self.assertIn('unresolved_dependency',[f['reason'] for f in row['flags']])

    def test_informal_observation_can_flag_but_not_verify(self):
        ext=empty(REQUEST);ext['observed']=[{'name':'funding_account','value':'FUND-B'}]
        admin.ingest(self.store,'An informal update lists account FUND-B.','2026-10-19',request=REQUEST,extraction=ext)
        _,row=self.check();self.assertEqual(row['verification'],'discrepant')
        self.assertEqual(row['discrepancies'][0]['field'],'funding_account')
