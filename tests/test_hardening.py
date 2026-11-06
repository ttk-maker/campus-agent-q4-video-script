from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import unittest
from tests import test_script as base
from src.agent import Agent
from src.domain import number, digest
from src.engine import Engine, check
from src.models import MockModel, ModelError
from src.store import StateError
from src.scenarios import draft

class HardeningTests(unittest.TestCase):
    setUp=base.ScriptTests.setUp
    run_agent=base.ScriptTests.run_agent
    engine=base.ScriptTests.engine

    def check_claim(self,fact,claim):
        c=deepcopy(self.payload['catalog']);c['materials'][0]['facts'][0]['text']=fact
        d=draft((10,9,9))
        for s in d['scenes']:s['voiceover']=fact
        d['scenes'][0]['voiceover']=claim
        return check(d,self.payload['request'],c,{'P01':c['materials'][0]})

    def test_english_word_boundary_is_factual(self):
        self.assertFalse(self.check_claim('We are now here.','We are nowhere.')['passed'])

    def test_internal_punctuation_changes_clause_meaning(self):
        self.assertFalse(self.check_claim('不支持字幕，导出。','不支持，字幕导出。')['passed'])

    def test_question_cannot_become_assertion(self):
        self.assertFalse(self.check_claim('支持字幕？','支持字幕。')['passed'])

    def test_superscript_unit_cannot_be_flattened(self):
        self.assertFalse(self.check_claim('面积2m²。','面积2m2。')['passed'])

    def test_fractional_duration_not_rounded_into_valid_input(self):
        with self.assertRaises(ValueError):number('1.000000000000000000000000000001')

    def test_old_policy_ready_cache_requires_recheck(self):
        first=self.run_agent();rid=self.payload['request']['request_id']
        owner=self.store.acquire(self.payload['request'],self.payload['catalog'])
        def legacy(s,db):
            key=digest([s['script'],s['revision'],s['catalog'],s['request'],s['retrieved']])
            s['duration_check']['key']=key;s['rules_check']['key']=key
        self.store.mutate(rid,owner,legacy);self.store.release(rid,owner)
        second=self.run_agent()
        self.assertEqual(second['status'],'completed');self.assertGreater(second['steps_used'],0)
        self.assertEqual(first['script'],second['script'])

    def test_model_failure_is_in_durable_trace(self):
        class Fail(MockModel):
            def decide(self,context):
                if context['snapshot']['script']:raise ModelError('test-unavailable')
                return super().decide(context)
        r=self.run_agent(Fail());s=self.store.get(self.payload['request']['request_id'])
        self.assertEqual(r['status'],'failed')
        self.assertEqual(s['trace'][-1]['action']['tool'],'model')
        self.assertEqual(s['trace'][-1]['next_action'],'stop:failed')

    def test_budget_stop_is_persisted_in_trace(self):
        self.run_agent(steps=2)
        self.assertEqual(self.store.get(self.payload['request']['request_id'])['trace'][-1]['next_action'],'stop:budget_exhausted')

    def test_multi_source_wrong_fact_id_cannot_borrow_text(self):
        c=self.payload['catalog'];c['materials'].append({'id':'P02','name':'other','keywords':['字幕'],'facts':[{'id':'F02','text':'支持配音。'}]})
        d=draft();d['scenes'][0].update(voiceover='支持配音。')
        r=check(d,self.payload['request'],c,{m['id']:m for m in c['materials']})
        self.assertFalse(r['passed'])

    def test_two_threads_only_one_can_mutate_request(self):
        entered=Event();release=Event()
        class Slow(MockModel):
            def decide(self,context):entered.set();release.wait(5);return super().decide(context)
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(Agent(Slow(),self.store,self.payload['catalog']).run,self.payload['request'])
            try:
                self.assertTrue(entered.wait(3))
                with self.assertRaisesRegex(StateError,'request_busy'):self.run_agent()
            finally:release.set()
            self.assertEqual(future.result(timeout=10)['status'],'completed')

    def test_exact_claim_with_ending_punctuation_still_allowed(self):
        self.assertTrue(self.check_claim('支持字幕。','支持 字幕！')['passed'])

    def test_model_receives_measured_voice_floor_for_impossible_duration(self):
        from src.models import HTTPModel
        from src.transport import HTTPTransport
        self.payload['request']['target_seconds']=1
        self.run_agent()
        snapshot=self.engine().view()
        model=HTTPModel.__new__(HTTPModel)
        with patch.object(HTTPTransport,'decide',return_value=base.action('finish',outcome='cannot_satisfy')) as decide:
            model.decide({'snapshot':snapshot})
        actual=decide.call_args.args[0]['snapshot']['duration_check']
        self.assertEqual(actual['scenes'][0]['voice_seconds'],1.5)
        self.assertGreater(actual['scenes'][0]['voice_seconds'],actual['target_seconds'])
