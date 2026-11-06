"""Execute fixtures and persist actual drafts, checks and traces."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import time
from src.agent import Agent
from src.models import HTTPModel,MockModel
from src.scenarios import scenario,LABELS
from src.store import Store

def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--mode",choices=("mock","real"),default="mock")
    parser.add_argument("--output",default="examples/mock");parser.add_argument("--cases",nargs="+",default=list(LABELS))
    args=parser.parse_args();report={"mode":args.mode,"started_at":datetime.now(timezone.utc).isoformat(),"cases":[],"passed":True}
    for name in args.cases:
        with tempfile.TemporaryDirectory() as temp:
            p=scenario(name);p["mode"]=args.mode;folder=Path(args.output)/name;dump(folder/"input.json",p)
            results=[];traces=[]
            for index in range(2 if name in ("normal","tool_failure") else 1):
                store=Store(Path(temp)/"state.db");agent=Agent(HTTPModel() if args.mode=="real" else MockModel(),store,p["catalog"],p["max_steps"])
                started=time.monotonic();r=agent.run(p["request"]);results.append(r);traces.append(agent.trace)
                dump(folder/f"run-{index+1}-output.json",r);dump(folder/f"run-{index+1}-meta.json",{"timestamp":datetime.now(timezone.utc).isoformat(),"seconds":round(time.monotonic()-started,2),"mode":agent.model.mode,"model":agent.model.name})
                (folder/f"run-{index+1}-trace.jsonl").write_text("".join(json.dumps(s,ensure_ascii=False)+"\n" for s in agent.trace),encoding="utf-8")
                print(f"{args.mode}/{name}/{index+1}: {r['status']} duration={r['estimated_total_seconds']} steps={r['steps_used']}",flush=True)
            first,last=results[0],results[-1];checks={"no_fake_ready":all(r["script_status"]!="ready" or (r["duration_check"]["passed"] and r["rules_check"]["passed"]) for r in results)}
            if name in ("normal","over_duration","claim_risk","rewrite","tool_failure"):
                checks.update(completed=last["status"]=="completed",within_duration=last["estimated_total_seconds"] is not None and last["estimated_total_seconds"]<=p["request"]["target_seconds"],fact_supported=bool(last["rules_check"] and all(s["supported"] for s in last["rules_check"]["scenes"])))
            if name=="normal":checks["repeat_zero_steps"]=last["steps_used"]==0
            if name=="over_duration":
                times=[s["observation"].get("total_seconds") for s in traces[0] if s["action"]["tool"]=="estimate_duration" and s["observation"].get("status")=="checked"]
                checks["observed_38_then_revised"]=len(times)>=2 and times[0]==38 and times[-1]<=30 and last["revision"]>1
            if name=="claim_risk":checks["actual_rule_failure_observed"]=any(s["action"]["tool"]=="check_rules" and s["observation"].get("passed") is False for s in traces[0])
            if name=="missing":checks["zero_calls_and_missing"]=first["status"]=="needs_information" and first["steps_used"]==0
            if name=="no_materials":checks["no_fabrication"]=first["status"]=="needs_information" and first["script"] is None
            if name=="tool_failure":checks["actual_failure"]=any(e["status"]=="failed" for e in last["tool_events"])
            if name=="too_short":checks["explicit_failure"]=first["status"] in ("cannot_satisfy","budget_exhausted") and first["script_status"]=="unverified"
            case={"name":name,"checks":checks,"passed":all(checks.values())};report["cases"].append(case);report["passed"] &= case["passed"]
            dump(Path(args.output)/"acceptance.json",report)
    report["finished_at"]=datetime.now(timezone.utc).isoformat();dump(Path(args.output)/"acceptance.json",report)
    return 0 if report["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
