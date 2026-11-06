from copy import deepcopy
import json
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]
LABELS={"normal":"正常生成 · 30 秒","over_duration":"38 秒草稿 · 压缩并复查","missing":"缺关键信息",
        "no_materials":"检索无结果","tool_failure":"检索失败一次","claim_risk":"无依据的 80% 结论","too_short":"仅 1 秒 · 无法满足",
        "rewrite":"第一次检索为空 · 改写查询"}

def draft(seconds=(14,12,12)):
    return {"title":"字幕功能介绍","scenes":[{"source_id":"P01","fact_id":"F01","voiceover":"支持字幕。","visual":v,"seconds":sec} for v,sec in zip(["产品界面特写","字幕文字卡","创作者出镜"],seconds)]}

def scenario(name):
    if name not in LABELS:raise ValueError("unknown scenario")
    catalog=json.loads((ROOT/"data/catalog.json").read_text(encoding="utf-8"))
    request={"request_id":name+"-"+uuid.uuid4().hex[:12],"topic":"视频助手字幕功能","audience":"短视频创作者","platform":"抖音","target_seconds":30,"style":"简洁"}
    if name=="over_duration":request["initial_script"]=draft()
    if name=="missing":request.update(audience=None,target_seconds=None)
    if name=="no_materials":catalog["materials"]=[]
    if name=="tool_failure":catalog["failures"]={"search_materials":1}
    if name=="claim_risk":
        request["initial_script"]=draft((10,9,9));request["initial_script"]["scenes"][0]["voiceover"]="支持字幕，效率提升80%。"
    if name=="too_short":request["target_seconds"]=1
    if name=="rewrite":request["topic"]="创作灵感分享"
    return {"request":request,"catalog":catalog,"mode":"mock","max_steps":16}
