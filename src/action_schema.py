"""Structured-output grammar constrains syntax, never chooses the next action."""
def obj(properties):return {"type":"object","properties":properties,"required":list(properties),"additionalProperties":False}
SCENE=obj({"source_id":{"type":"string"},"fact_id":{"type":"string"},"voiceover":{"type":"string"},"visual":{"type":"string"},"seconds":{"type":"number"}})
SCHEMA=obj({"tool":{"type":"string","enum":["search_materials","submit_script","estimate_duration","check_rules","finish"]},
            "arguments":{"anyOf":[obj({"query":{"type":"string"}}),obj({"title":{"type":"string"},"scenes":{"type":"array","items":SCENE,"minItems":1,"maxItems":8}}),obj({"outcome":{"type":"string","enum":["completed","needs_information","failed","cannot_satisfy"]}}),obj({})]},
            "reason":{"type":"string","maxLength":160}})
