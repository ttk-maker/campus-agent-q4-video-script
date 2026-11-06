import argparse
import json
from pathlib import Path
from .agent import Agent
from .models import HTTPModel,MockModel,ModelError
from .store import Store,StateError

def main():
    parser=argparse.ArgumentParser(description="Grounded short video script Agent")
    parser.add_argument("--request",required=True);parser.add_argument("--catalog",default="data/catalog.json")
    parser.add_argument("--mode",choices=("mock","real"),default="mock");parser.add_argument("--db",default="runtime/scripts.db")
    parser.add_argument("--max-steps",type=int,default=16);parser.add_argument("--output",default="runtime/output.json")
    parser.add_argument("--trace",default="runtime/trace.jsonl")
    args=parser.parse_args()
    try:
        request=json.loads(Path(args.request).read_text(encoding="utf-8"));catalog=json.loads(Path(args.catalog).read_text(encoding="utf-8"))
        agent=Agent(HTTPModel() if args.mode=="real" else MockModel(),Store(args.db),catalog,args.max_steps)
        result=agent.run(request)
        for path,content in [(args.output,json.dumps(result,ensure_ascii=False,indent=2)),(args.trace,"".join(json.dumps(s,ensure_ascii=False)+"\n" for s in agent.trace))]:
            p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding="utf-8")
        print(json.dumps({k:result[k] for k in ("status","reason","script_status","estimated_total_seconds","revision","steps_used")},ensure_ascii=False))
        return 0 if result["status"]=="completed" else 2
    except (ValueError,ModelError,StateError,OSError) as exc:
        print(json.dumps({"status":"failed","error":str(exc) if isinstance(exc,StateError) else type(exc).__name__}));return 2

if __name__=="__main__":raise SystemExit(main())
