"""Grounding, revision-bound checks and reproducible shot duration estimates."""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
import re

from .domain import digest, normalize, number, validate_script

def estimate(script, request, rules):
    rate=Decimal(str(rules["styles"].get(request["style"],3)))
    rows=[];elapsed=Decimal(0);transition=Decimal(str(rules["transition_seconds"]))
    for index,scene in enumerate(script["scenes"],1):
        units=len(normalize(scene["voiceover"]))
        speech=(Decimal(units)/rate+Decimal("0.5")).quantize(Decimal("0.1"),rounding=ROUND_CEILING)
        seconds=max(number(scene["seconds"]),speech)
        start=elapsed;elapsed+=seconds
        rows.append({"scene":index,"source_id":scene["source_id"],"fact_id":scene["fact_id"],
                     "speech_units":units,"voice_seconds":float(speech),"hold_seconds":float(number(scene["seconds"])),
                     "estimated_seconds":float(seconds),"start":float(start),"end":float(elapsed)})
        if index<len(script["scenes"]):elapsed+=transition
    target=number(request["target_seconds"],1,600)
    return {"passed":elapsed<=target,"total_seconds":float(elapsed),"target_seconds":float(target),
            "over_seconds":float(max(Decimal(0),elapsed-target)),"scenes":rows,
            "formula":"max(hold_seconds, ceil_0.1(normalized_character_count / style_rate + 0.5)) + transitions",
            "characters_per_second":float(rate),"transition_seconds":float(transition),"kind":"heuristic_not_audio_measurement"}

def check(script, request, catalog, retrieved):
    rules=catalog["rules"];risks=[];rows=[]
    def risk(code,field,detail):risks.append({"code":code,"field":field,"detail":detail})
    if script["title"] not in rules["titles"]:risk("unapproved_title","title","Use a brand-approved neutral title.")
    if request["platform"] not in rules["platforms"]:risk("unsupported_platform","platform",request["platform"])
    if request["style"] not in rules["styles"]:risk("unsupported_style","style",request["style"])
    if len(script["scenes"])>rules["max_scenes"]:risk("too_many_scenes","scenes",str(rules["max_scenes"]))
    for i,scene in enumerate(script["scenes"],1):
        source=retrieved.get(scene["source_id"])
        fact=next((f for f in source["facts"] if f["id"]==scene["fact_id"]),None) if source else None
        supported=bool(fact and normalize(scene["voiceover"])==normalize(fact["text"]))
        if not source:risk("source_not_retrieved",f"scenes.{i}.source_id",scene["source_id"])
        elif not fact:risk("unknown_fact",f"scenes.{i}.fact_id",scene["fact_id"])
        elif not supported:risk("unsupported_claim",f"scenes.{i}.voiceover","Must match the cited fact. No inferred benefits or numbers.")
        if scene["visual"] not in rules["visuals"]:risk("unapproved_visual",f"scenes.{i}.visual","Use permitted camera directions; no extra factual claim.")
        rows.append({"scene":i,"source_id":scene["source_id"],"fact_id":scene["fact_id"],
                     "source_text":fact["text"] if fact else None,"voiceover":scene["voiceover"],"supported":supported})
    fields=[("title",script["title"])]+[(f"scenes.{i}.{key}",s[key]) for i,s in enumerate(script["scenes"],1) for key in ("voiceover","visual")]
    for field,text in fields:
        for term in rules["forbidden"]:
            if normalize(term).casefold() in normalize(text).casefold():risk("brand_forbidden",field,term)
    return {"passed":not risks,"risks":risks,"scenes":rows,"policy":"extractive_grounding_v1"}

class Engine:
    def __init__(self,store,request_id,owner):self.store,self.request_id,self.owner=store,request_id,owner

    @staticmethod
    def check_key(state):return digest([state["script"],state["revision"],state["catalog"],state["request"],state["retrieved"]])

    @classmethod
    def ready(cls,state):
        return bool(state["script"] and all(state[k] and state[k]["key"]==cls.check_key(state) and state[k]["passed"] for k in ("duration_check","rules_check")))

    def view(self):
        s=self.store.get(self.request_id)
        return {"request":{k:v for k,v in s["request"].items() if k!="initial_script"},"retrieved":s["retrieved"],
                "searches":s["searches"][-3:],"script":s["script"],"revision":s["revision"],
                "duration_check":s["duration_check"],"rules_check":s["rules_check"],
                "brand_rules":s["catalog"]["rules"],"ready":self.ready(s),
                "recent_events":s["events"][-2:]}

    def execute(self,action):
        if not isinstance(action,dict) or set(action)!={"tool","arguments","reason"} or not isinstance(action["arguments"],dict) or not isinstance(action["reason"],str):
            return {"status":"rejected","error":"invalid_action","expected":"tool, arguments object, reason string"}
        return self.store.mutate(self.request_id,self.owner,lambda s,db:self.apply(s,action["tool"],action["arguments"]))

    def apply(self,s,tool,args):
        schemas={"search_materials":{"query"},"submit_script":{"title","scenes"},"estimate_duration":set(),"check_rules":set()}
        if not isinstance(tool,str) or tool not in schemas or set(args)!=schemas[tool]:
            return {"status":"rejected","error":"invalid_tool_or_arguments","expected_keys":sorted(schemas.get(tool,set())) if isinstance(tool,str) else []}
        if tool=="search_materials" and (not isinstance(args["query"],str) or not 1<=len(args["query"].strip())<=200):
            return {"status":"rejected","error":"query_must_be_nonempty_1_to_200_chars"}
        if tool=="submit_script":
            try:validate_script(args)
            except ValueError as exc:return {"status":"rejected","error":"invalid_script","detail":str(exc)}
            if not s["retrieved"]:return {"status":"rejected","error":"retrieve_evidence_before_drafting"}
            if s["script"]:s["revisions"].append({"revision":s["revision"],"script":deepcopy(s["script"]),"duration_check":s["duration_check"],"rules_check":s["rules_check"]})
            s["script"]=deepcopy(args);s["revision"]+=1;s["duration_check"]=s["rules_check"]=None
            s["events"].append({"tool":tool,"status":"drafted","revision":s["revision"]})
            return {"status":"drafted","revision":s["revision"],"must_check":["estimate_duration","check_rules"]}
        if tool in ("estimate_duration","check_rules") and not s["script"]:
            return {"status":"rejected","error":"draft_required"}
        s["attempts"][tool]=s["attempts"].get(tool,0)+1
        if s["attempts"][tool]<=s["catalog"]["failures"].get(tool,0):
            if tool=="estimate_duration":s["duration_check"]=None
            if tool=="check_rules":s["rules_check"]=None
            event={"tool":tool,"status":"failed","error":"injected_tool_failure","attempt":s["attempts"][tool]}
            s["events"].append(event);return event
        if tool=="search_materials":
            query=normalize(args["query"]).casefold()
            found=[m for m in s["catalog"]["materials"] if any(normalize(k).casefold() in query or query in normalize(k).casefold() for k in m["keywords"])]
            for material in found:s["retrieved"][material["id"]]=deepcopy(material)
            s["rules_check"]=s["duration_check"]=None
            s["searches"].append({"query":args["query"],"count":len(found)})
            result={"status":"found" if found else "empty","count":len(found),"materials":found,
                    "available_source_count":len(s["catalog"]["materials"]),
                    "hint":("The entire source library is empty. Rewriting cannot find any facts. Request additional materials: finish with outcome needs_information."
                            if not s["catalog"]["materials"] else "Try a different shorter product feature query or finish needs_information; never invent sources.") if not found else None}
        elif tool=="estimate_duration":
            result={"status":"checked",**estimate(s["script"],s["request"],s["catalog"]["rules"]),"revision":s["revision"],"key":self.check_key(s)}
            s["duration_check"]=result
        else:
            result={"status":"checked",**check(s["script"],s["request"],s["catalog"],s["retrieved"]),"revision":s["revision"],"key":self.check_key(s)}
            s["rules_check"]=result
        s["events"].append({"tool":tool,"status":result["status"],"revision":s["revision"],"passed":result.get("passed"),"attempt":s["attempts"][tool]})
        return result

    def result(self,status,reason=None):
        s=self.store.get(self.request_id);ready=self.ready(s)
        risks=deepcopy(s["rules_check"]["risks"]) if s["rules_check"] else [{"code":"rules_unchecked","detail":"Current script has not passed a current rule check."}]
        if s["duration_check"] and not s["duration_check"]["passed"]:risks.append({"code":"over_duration","over_seconds":s["duration_check"]["over_seconds"]})
        return {"request_id":self.request_id,"status":status,"reason":reason,"script_status":"ready" if ready else "unverified",
                "script":s["script"],"revision":s["revision"],"estimated_total_seconds":s["duration_check"]["total_seconds"] if s["duration_check"] else None,
                "duration_check":s["duration_check"],"rules_check":s["rules_check"],"risks":risks,
                "source_ids":sorted({scene["source_id"] for scene in s["script"]["scenes"]}) if s["script"] else [],
                "retrieved_sources":list(s["retrieved"].values()),"revision_history":s["revisions"],"tool_events":s["events"],
                "missing":[k for k in ("topic","audience","platform","target_seconds","style") if not str(s["request"].get(k) or "").strip()],
                "published":False}
