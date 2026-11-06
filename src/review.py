"""User-invoked deterministic validation, explicitly not a model decision path."""
class ReviewModel:
    mode="review";name="manual-edit-checks-no-model"
    def __init__(self,queries):self.queries=list(queries)
    def decide(self,context):
        s=context["snapshot"];last=context.get("last_observation") or {}
        def action(tool,args=None):return {"tool":tool,"arguments":args or {},"reason":"User explicitly requested checks of edited script; no model generation."}
        if last.get("status")=="failed":return action("finish",{"outcome":"failed"})
        if self.queries:return action("search_materials",{"query":self.queries.pop(0)})
        if not s["duration_check"]:return action("estimate_duration")
        if not s["rules_check"]:return action("check_rules")
        return action("finish",{"outcome":"completed" if s["ready"] else "cannot_satisfy"})
