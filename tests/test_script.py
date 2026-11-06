from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from src.agent import Agent
from src.domain import validate_request,validate_catalog,fingerprint
from src.engine import Engine,check,estimate
from src.models import MockModel,ModelError
from src.scenarios import scenario,draft
from src.store import Store,StateError

def action(tool,**args):return {"tool":tool,"arguments":args,"reason":"Adversarial test action"}
class Scripted:
    mode="test";name="scripted-boundary-test"
    def __init__(self,actions):self.actions=iter(actions)
    def decide(self,context):return next(self.actions,action("invalid"))

class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/"state.db");self.payload=scenario("normal")
    def run_agent(self,model=None,steps=16):
        self.agent=Agent(model or MockModel(),self.store,self.payload["catalog"],steps)
        return self.agent.run(self.payload["request"])
    def engine(self):
        owner=self.store.acquire(self.payload["request"],self.payload["catalog"])
        self.addCleanup(lambda:self.store.release(self.payload["request"]["request_id"],owner))
        return Engine(self.store,self.payload["request"]["request_id"],owner)
    def test_normal_grounded_generation(self):
        r=self.run_agent();self.assertEqual(r["status"],"completed");self.assertEqual(r["source_ids"],["P01"])
        self.assertTrue(r["rules_check"]["passed"]);self.assertEqual(r["estimated_total_seconds"],28)
    def test_actual_38_to_28_revision_and_recheck(self):
        self.payload=scenario("over_duration");r=self.run_agent()
        times=[s["observation"]["total_seconds"] for s in self.agent.trace if s["action"]["tool"]=="estimate_duration"]
        self.assertEqual(times,[38,28]);self.assertEqual(r["revision"],2);self.assertEqual(r["status"],"completed")
        self.assertEqual(r["revision_history"][0]["duration_check"]["total_seconds"],38)
    def test_all_required_fields_missing_individually(self):
        original=deepcopy(self.payload)
        for key in ("topic","audience","platform","target_seconds","style"):
            self.payload=deepcopy(original);self.payload["request"]["request_id"]+=key;self.payload["request"][key]=None
            r=self.run_agent();self.assertEqual(r["missing"],[key]);self.assertEqual(r["steps_used"],0);self.assertEqual(r["status"],"needs_information")
    def test_blank_required_fields(self):
        self.payload["request"]["target_seconds"]="  "
        self.assertEqual(self.run_agent()["status"],"needs_information")
    def test_empty_search_rewrite_then_request_info(self):
        self.payload=scenario("no_materials");r=self.run_agent()
        self.assertEqual(r["status"],"needs_information");self.assertIsNone(r["script"])
        self.assertEqual([s["observation"]["status"] for s in self.agent.trace],["empty","empty","finished"])
    def test_query_rewrite_changes_result(self):
        self.payload=scenario("rewrite");r=self.run_agent()
        self.assertEqual(r["status"],"completed")
        self.assertEqual(self.agent.trace[0]["observation"]["status"],"empty")
        self.assertEqual(self.agent.trace[1]["observation"]["status"],"found")
    def test_tool_failure_and_resume(self):
        self.payload=scenario("tool_failure");r=self.run_agent();self.assertEqual(r["status"],"failed")
        self.store=Store(self.store.path);r=self.run_agent();self.assertEqual(r["status"],"completed")
    def test_estimate_failure_not_passed(self):
        self.payload["catalog"]["failures"]={"estimate_duration":1};r=self.run_agent()
        self.assertEqual(r["status"],"failed");self.assertIsNone(r["estimated_total_seconds"]);self.assertEqual(r["script_status"],"unverified")
    def test_rules_failure_not_passed(self):
        self.payload["catalog"]["failures"]={"check_rules":1};r=self.run_agent()
        self.assertEqual(r["status"],"failed");self.assertIsNone(r["rules_check"])
        self.assertEqual(self.run_agent()["status"],"completed")
    def test_unsupported_80_percent_repaired(self):
        self.payload=scenario("claim_risk");r=self.run_agent()
        self.assertEqual(r["status"],"completed");self.assertNotIn("80",json.dumps(r["script"],ensure_ascii=False))
        risks=r["revision_history"][0]["rules_check"]["risks"]
        self.assertIn("unsupported_claim",[x["code"] for x in risks])
    def test_one_second_cannot_satisfy(self):
        self.payload=scenario("too_short");r=self.run_agent()
        self.assertEqual(r["status"],"cannot_satisfy");self.assertGreater(r["estimated_total_seconds"],1)
    def test_repeat_reuses_checked_script(self):
        first=self.run_agent();second=self.run_agent();self.assertEqual(second["steps_used"],0)
        self.assertEqual(first["script"],second["script"]);self.assertEqual(len(self.store.saved()),1)
    def test_changed_request_same_id_rejected(self):
        self.run_agent();self.payload["request"]["target_seconds"]=20
        with self.assertRaisesRegex(StateError,"idempotency_conflict"):self.run_agent()
    def test_changed_catalog_same_id_rejected(self):
        self.run_agent();self.payload["catalog"]["materials"][0]["facts"][0]["text"]="新的事实"
        with self.assertRaises(StateError):self.run_agent()
    def test_fake_completion_blocked(self):
        r=self.run_agent(Scripted([action("finish",outcome="completed")]),1)
        self.assertEqual(r["status"],"budget_exhausted");self.assertEqual(r["script_status"],"unverified")
    def test_no_sources_cannot_draft(self):
        r=self.run_agent(Scripted([action("submit_script",**draft())]),1)
        self.assertIsNone(r["script"]);self.assertEqual(self.agent.trace[0]["observation"]["error"],"retrieve_evidence_before_drafting")
    def test_rules_check_must_cover_current_version(self):
        e=self.engine();e.execute(action("search_materials",query="字幕"));e.execute(action("submit_script",**draft((10,9,9))))
        e.execute(action("estimate_duration"));e.execute(action("check_rules"));self.assertTrue(e.view()["ready"])
        bad=draft((10,9,9));bad["scenes"][0]["voiceover"]="效率提升80%"
        e.execute(action("submit_script",**bad));v=e.view();self.assertFalse(v["ready"])
        self.assertIsNone(v["duration_check"]);self.assertIsNone(v["rules_check"])
    def test_search_invalidates_checks(self):
        e=self.engine();e.execute(action("search_materials",query="字幕"));e.execute(action("submit_script",**draft((10,9,9))))
        e.execute(action("estimate_duration"));e.execute(action("check_rules"));e.execute(action("search_materials",query="字幕"))
        self.assertFalse(e.view()["ready"])
    def test_fake_source_or_fact_not_supported(self):
        for key,value in (("source_id","P99"),("fact_id","F99")):
            d=draft();d["scenes"][0][key]=value
            result=check(d,self.payload["request"],self.payload["catalog"],{"P01":self.payload["catalog"]["materials"][0]})
            self.assertFalse(result["passed"]);self.assertFalse(result["scenes"][0]["supported"])
    def test_catalog_fact_not_retrieved_is_rejected(self):
        result=check(draft(),self.payload["request"],self.payload["catalog"],{})
        self.assertEqual(result["risks"][0]["code"],"source_not_retrieved")
    def test_correct_citation_does_not_allow_added_claim(self):
        d=draft();d["scenes"][0]["voiceover"]="支持字幕，还支持智能配音。"
        result=check(d,self.payload["request"],self.payload["catalog"],{"P01":self.payload["catalog"]["materials"][0]})
        self.assertFalse(result["passed"])
    def test_title_and_visual_also_checked(self):
        d=draft();d["title"]="效率提升80%";d["scenes"][0]["visual"]="永久免费"
        r=check(d,self.payload["request"],self.payload["catalog"],{"P01":self.payload["catalog"]["materials"][0]})
        self.assertFalse(r["passed"]);self.assertTrue(any(x["field"]=="title" for x in r["risks"]))
    def test_forbidden_source_fact_still_fails_brand(self):
        c=self.payload["catalog"];c["materials"][0]["facts"][0]["text"]="效率提升80%"
        d=draft();d["scenes"][0]["voiceover"]="效率提升80%"
        r=check(d,self.payload["request"],c,{"P01":c["materials"][0]})
        self.assertTrue(r["scenes"][0]["supported"]);self.assertFalse(r["passed"])
    def test_voiceover_lower_bound_overrides_fake_short_hold(self):
        d=draft((.1,.1,.1));r=estimate(d,self.payload["request"],self.payload["catalog"]["rules"])
        self.assertEqual(r["total_seconds"],4.5)
    def test_transition_included_exactly_between_scenes(self):
        self.payload["catalog"]["rules"]["transition_seconds"]=.5
        r=estimate(draft((10,9,9)),self.payload["request"],self.payload["catalog"]["rules"])
        self.assertEqual(r["total_seconds"],29);self.assertEqual(r["scenes"][1]["start"],10.5)
    def test_equal_target_passes_one_tenth_over_fails(self):
        req=self.payload["request"];req["target_seconds"]=28
        self.assertTrue(estimate(draft((10,9,9)),req,self.payload["catalog"]["rules"])["passed"])
        req["target_seconds"]=27.9
        self.assertFalse(estimate(draft((10,9,9)),req,self.payload["catalog"]["rules"])["passed"])
    def test_invalid_durations_rejected(self):
        for value in (True,-1,0,"NaN","Infinity",1000,1.01):
            self.payload["request"]["target_seconds"]=value
            with self.assertRaises(ValueError):validate_request(self.payload["request"])
    def test_unsupported_platform_cannot_complete(self):
        self.payload["request"]["platform"]="未知平台";r=self.run_agent()
        self.assertEqual(r["status"],"cannot_satisfy");self.assertEqual(r["script_status"],"unverified")
    def test_step_limit_preserves_draft(self):
        r=self.run_agent(steps=2);self.assertEqual(r["status"],"budget_exhausted");self.assertIsNotNone(r["script"])
        self.assertEqual(self.run_agent()["status"],"completed")
    def test_model_failure_preserves_draft(self):
        class Fail(MockModel):
            def decide(self,context):
                if context["snapshot"]["script"]:raise ModelError("test")
                return super().decide(context)
        r=self.run_agent(Fail());self.assertEqual(r["status"],"failed");self.assertIsNotNone(r["script"])
    def test_same_key_lease_excludes_concurrent_run(self):
        self.engine()
        with self.assertRaisesRegex(StateError,"request_busy"):self.run_agent()
    def test_punctuation_normalization_not_claim_normalization(self):
        d=draft();d["scenes"][0]["voiceover"]="支持 字幕！"
        self.assertTrue(check(d,self.payload["request"],self.payload["catalog"],{"P01":self.payload["catalog"]["materials"][0]})["passed"])
    def test_malformed_action_bounded(self):
        r=self.run_agent(Scripted([None,{},action("publish"),action("estimate_duration",seconds=0)]),4)
        self.assertEqual(r["status"],"budget_exhausted");self.assertIsNone(r["script"])
    def test_numeric_equivalence_idempotency(self):
        first=fingerprint(self.payload["request"],self.payload["catalog"]);self.payload["request"]["target_seconds"]="30.0"
        self.assertEqual(first,fingerprint(self.payload["request"],self.payload["catalog"]))
    def test_duplicate_material_and_bad_schema(self):
        self.payload["catalog"]["materials"]*=2
        with self.assertRaises(ValueError):validate_catalog(self.payload["catalog"])
