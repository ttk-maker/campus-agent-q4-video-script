"""Recalculate acceptance from frozen outputs; historical failed suites stay unchanged."""
from datetime import datetime,timezone
import json
from pathlib import Path
from src.engine import estimate,check
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text(encoding="utf-8"))
def trace(path):return [json.loads(line) for line in (ROOT/path).read_text(encoding="utf-8").splitlines()]
def valid(r,payload):
    if r["status"]!="completed" or r["script_status"]!="ready":return False
    d=r["duration_check"];c=r["rules_check"]
    recomputed_time=estimate(r["script"],payload["request"],payload["catalog"]["rules"])
    recomputed_rules=check(r["script"],payload["request"],payload["catalog"],{s["id"]:s for s in r["retrieved_sources"]})
    return recomputed_rules["passed"] and recomputed_time["passed"] and recomputed_time["total_seconds"]==d["total_seconds"] and d["passed"] and c["passed"] and d["key"]==c["key"] and d["revision"]==c["revision"]==r["revision"] and all(s["supported"] for s in c["scenes"]) and [(s["scene"],s["source_id"],s["fact_id"]) for s in d["scenes"]]==[(s["scene"],s["source_id"],s["fact_id"]) for s in c["scenes"]]
def main():
    checks={}
    normal=read("examples/real/normal/run-1-output.json");checks["real_generated_normal"]=valid(normal,read("examples/real/normal/input.json"))
    over=read("examples/real/over_duration/run-1-output.json");overtrace=trace("examples/real/over_duration/run-1-trace.jsonl")
    times=[r["observation"].get("total_seconds") for r in overtrace if r["action"]["tool"]=="estimate_duration" and r["observation"]["status"]=="checked"]
    checks["real_duration_revision"]=valid(over,read("examples/real/over_duration/input.json")) and len(times)>=2 and times[0]==38 and times[-1]<=30 and over["revision"]>1
    failure=read("examples/real/tool_failure/run-1-output.json")
    checks["real_tool_failure_recovery"]=valid(failure,read("examples/real/tool_failure/input.json")) and any(e["status"]=="failed" for e in failure["tool_events"])
    claim=read("examples/real/claim_risk/run-1-output.json");claimtrace=trace("examples/real/claim_risk/run-1-trace.jsonl")
    checks["real_unsupported_claim_repaired"]=valid(claim,read("examples/real/claim_risk/input.json")) and any(s["action"]["tool"]=="check_rules" and s["observation"].get("passed") is False for s in claimtrace)
    empty=read("examples/real-empty-retest/no_materials/run-1-output.json")
    checks["real_empty_library_requests_materials"]=empty["status"]=="needs_information" and empty["script"] is None
    repeat=read("examples/real/normal/run-2-output.json");checks["real_repeat"]=repeat["steps_used"]==0 and repeat["script"]==normal["script"]
    browser=read("examples/browser-real/job.json");checks["real_browser"]=valid(browser["result"],browser["payload"]) and read("examples/browser-real/report.json")["passed"]
    for name,file in (("mock","acceptance.json"),("tests","report.json"),("browser","report.json")):
        checks[name]=read("examples/"+name+"/"+file)["passed"]
    for name in ('review','browser','real-duration-final'):
        checks['hardening_'+name]=read('examples/hardening/'+name+'/report.json')['passed']
    fixed=read('examples/hardening/real/english_boundary/run.json')
    checks['hardening_word_boundary_repair']=valid(fixed['output'],read('examples/hardening/real/english_boundary/input.json')) and any(t['action']['tool']=='check_rules' and t['observation'].get('passed') is False for t in fixed['trace'])
    impossible=read('examples/hardening/real-duration-final/impossible_duration/run.json')['output']
    checks['hardening_impossible_not_ready']=impossible['status']=='cannot_satisfy' and impossible['script_status']=='unverified' and impossible['duration_check']['catalog_bound']['proven_impossible']
    report={"verified_at":datetime.now(timezone.utc).isoformat(),"passed":all(checks.values()),"checks":checks,
            "historical_hardening_failures":["examples/hardening/before.txt","examples/hardening/before-voice-feedback.txt","examples/hardening/real/impossible_duration","examples/hardening/real-duration-retest"],"duration_observations":times,"note":"Initial invalid-action run, interrupted schema diagnostic and initial empty-search failure remain unchanged; empty search uses explicit retest evidence."}
    (ROOT/"examples/acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
