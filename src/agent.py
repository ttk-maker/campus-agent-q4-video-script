from .domain import validate_request,validate_catalog
from .engine import Engine
from .models import ModelError


class Agent:
    def __init__(self,model,store,catalog,max_steps=16):
        validate_catalog(catalog)
        if type(max_steps) is not int or not 1<=max_steps<=100:raise ValueError("max_steps must be 1..100")
        self.model,self.store,self.catalog,self.max_steps=model,store,catalog,max_steps
        self.trace=[]

    def run(self,request):
        missing=validate_request(request);self.trace=[]
        owner=self.store.acquire(request,self.catalog)
        engine=Engine(self.store,request["request_id"],owner)
        status,reason="budget_exhausted","model_step_limit"
        try:
            engine.invalidate_stale_checks()
            if missing:status,reason="needs_information","missing_required_inputs"
            elif engine.ready(self.store.get(request["request_id"])):status,reason="completed","existing_checked_script_reused"
            else:
                for step in range(1,self.max_steps+1):
                    self.store.renew(request["request_id"],owner)
                    try:action=self.model.decide({"snapshot":engine.view(),"last_observation":self.trace[-1]["observation"] if self.trace else None})
                    except ModelError as exc:
                        status,reason="failed","model_unavailable"
                        if self.trace:self.trace[-1]["next_action"]="model"
                        self.trace.append({"step":step,"action":{"tool":"model","arguments":{},"reason":"Model request failed"},"observation":{"status":"failed","error":str(exc)},"next_action":"stop:failed"})
                        break
                    valid=isinstance(action,dict) and set(action)=={"tool","arguments","reason"} and isinstance(action["arguments"],dict) and isinstance(action["reason"],str)
                    terminal=False
                    if valid and action["tool"]=="finish" and set(action["arguments"])=={"outcome"}:
                        outcome=action["arguments"]["outcome"];state=self.store.get(request["request_id"])
                        allowed=[]
                        if engine.ready(state):allowed=["completed"]
                        else:
                            if state["searches"] and not state["retrieved"]:allowed.append("needs_information")
                            if any(e["status"]=="failed" for e in state["events"]):allowed.append("failed")
                            if any(state[k] and not state[k]["passed"] for k in ("duration_check","rules_check")):allowed.append("cannot_satisfy")
                        if outcome in allowed:
                            status=outcome;reason={"completed":None,"needs_information":"no_matching_materials","failed":"tool_failure","cannot_satisfy":"checks_not_satisfied"}[outcome]
                            observation={"status":"finished","outcome":outcome};terminal=True
                        else:observation={"status":"rejected","error":"unsupported_finish","allowed_outcomes":allowed}
                    else:observation=engine.execute(action)
                    safe={"tool":str(action.get("tool","invalid")) if isinstance(action,dict) else "invalid",
                          "arguments":action.get("arguments",{}) if isinstance(action,dict) else {},
                          "reason":str(action.get("reason",""))[:240] if isinstance(action,dict) else ""}
                    if self.trace:self.trace[-1]["next_action"]=safe["tool"]
                    self.trace.append({"step":step,"action":safe,"observation":observation,"next_action":None})
                    self.store.mutate(request["request_id"],owner,lambda s,db:s.update(trace=self.trace))
                    if terminal:break
                if self.trace and self.trace[-1]["next_action"] is None:self.trace[-1]["next_action"]="stop:"+status
            def finish_state(state,db):
                if self.trace:state['trace']=self.trace
                state.update(status=status,reason=reason)
            self.store.mutate(request["request_id"],owner,finish_state)
            result=engine.result(status,reason)
            result.update(mode=self.model.mode,model=self.model.name,steps_used=len(self.trace),max_steps=self.max_steps)
            return result
        finally:self.store.release(request["request_id"],owner)
