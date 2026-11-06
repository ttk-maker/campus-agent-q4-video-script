"""Strict input shapes and canonical hashes, independent of model assertions."""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata

REQUIRED = ("topic", "audience", "platform", "target_seconds", "style")

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(",",":")).encode()).hexdigest()

def number(value, minimum=0.1, maximum=600):
    if isinstance(value,bool) or len(str(value))>80: raise ValueError("invalid duration representation")
    try:
        n=Decimal(str(value))
        if not n.is_finite() or not Decimal(str(minimum))<=n<=Decimal(str(maximum)) or n != n.quantize(Decimal('0.1')):
            raise ValueError("duration must be finite with at most one decimal")
        return n
    except InvalidOperation: raise ValueError("invalid number") from None

def require_text(value, limit=1000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError("nonempty bounded text required")

def normalize(text):
    # Only ignore sentence punctuation away from digits. Dropping all punctuation
    # would conflate 1.0 with 10 or -5 with 5 and silently change factual quantities.
    value="".join(c for c in unicodedata.normalize("NFKC",text) if not c.isspace())
    result=[]
    for i,c in enumerate(value):
        adjacent_digit=(i>0 and value[i-1].isdigit()) or (i+1<len(value) and value[i+1].isdigit())
        if c in "。！？!?,，；;：:、." and not adjacent_digit:continue
        result.append(c)
    return "".join(result)

def fact_normalize(text):
    """Preserve clause boundaries, questions, Latin word boundaries and unit exponents.

    NFC deliberately avoids compatibility folding of m² into m2. Only spacing
    between Han characters and final declarative/exclamatory punctuation is ignored.
    Search and duration normalization have separate, looser semantics.
    """
    value=unicodedata.normalize('NFC',text).strip()
    value=re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])','',value)
    value=re.sub(r'\s+',' ',value)
    if value.endswith(('。','！','!')):value=value[:-1]
    elif value.endswith('.') and (len(value)<2 or not value[-2].isdigit()):value=value[:-1]
    return value


def validate_script(script):
    if not isinstance(script,dict) or set(script)!={"title","scenes"}: raise ValueError("script requires title and scenes")
    require_text(script["title"],120)
    if not isinstance(script["scenes"],list) or not 1<=len(script["scenes"])<=12: raise ValueError("1..12 scenes required")
    for scene in script["scenes"]:
        if not isinstance(scene,dict) or set(scene)!={"source_id","fact_id","voiceover","visual","seconds"}: raise ValueError("invalid scene fields")
        for key in ("source_id","fact_id"): require_text(scene[key],80)
        for key in ("voiceover","visual"): require_text(scene[key],1000)
        number(scene["seconds"],.1,600)
    return script

def validate_request(request):
    if not isinstance(request,dict) or set(request)-{"request_id",*REQUIRED,"initial_script"}: raise ValueError("unknown request fields")
    require_text(request.get("request_id"),128)
    missing=[k for k in REQUIRED if request.get(k) is None or (isinstance(request.get(k),str) and not request[k].strip())]
    for key in REQUIRED:
        if key not in missing:
            if key=="target_seconds": number(request[key],1,600)
            else: require_text(request[key],500)
    if request.get("initial_script") is not None: validate_script(request["initial_script"])
    return missing

def validate_catalog(catalog):
    try:
        if not isinstance(catalog,dict) or set(catalog)!={"version","materials","rules","failures"}: raise ValueError("invalid catalog")
        require_text(catalog["version"],80)
        if not isinstance(catalog["materials"],list) or len(catalog["materials"])>30: raise ValueError("too many materials")
        ids=set()
        for material in catalog["materials"]:
            if set(material)!={"id","name","keywords","facts"}: raise ValueError("invalid material")
            require_text(material["id"],80);require_text(material["name"],200)
            if material["id"] in ids: raise ValueError("duplicate source ID")
            ids.add(material["id"])
            if not isinstance(material["keywords"],list) or not 1<=len(material["keywords"])<=20: raise ValueError("invalid keywords")
            for term in material["keywords"]:
                require_text(term,100)
                if not normalize(term):raise ValueError("keyword must contain searchable characters")
            if not isinstance(material["facts"],list) or not 1<=len(material["facts"])<=20: raise ValueError("invalid facts")
            seen=set()
            for fact in material["facts"]:
                if set(fact)!={"id","text"}:raise ValueError("invalid fact")
                require_text(fact["id"],80);require_text(fact["text"],1000)
                if fact["id"] in seen:raise ValueError("duplicate fact ID")
                seen.add(fact["id"])
        rules=catalog["rules"]
        if set(rules)!={"titles","visuals","forbidden","platforms","styles","transition_seconds","max_scenes"}:raise ValueError("invalid rules")
        for key in ("titles","visuals","forbidden","platforms"):
            if not isinstance(rules[key],list) or len(rules[key])>30 or (key!="forbidden" and not rules[key]):raise ValueError("invalid rule list")
            for value in rules[key]:require_text(value,120)
        if not isinstance(rules["styles"],dict) or not 1<=len(rules["styles"])<=10:raise ValueError("invalid styles")
        for name,rate in rules["styles"].items():require_text(name,80);number(rate,1,10)
        number(rules["transition_seconds"],0,5)
        if type(rules["max_scenes"]) is not int or not 1<=rules["max_scenes"]<=12:raise ValueError("invalid scene cap")
        if not isinstance(catalog["failures"],dict) or set(catalog["failures"])-{"search_materials","estimate_duration","check_rules"}:raise ValueError("invalid failure tool")
        if any(type(v) is not int or not 0<=v<=10 for v in catalog["failures"].values()):raise ValueError("invalid failures")
    except (TypeError,KeyError):raise ValueError("malformed catalog") from None
    return catalog

def fingerprint(request,catalog):
    normalized=dict(request)
    if request.get("target_seconds") is not None and str(request["target_seconds"]).strip():normalized["target_seconds"]=str(number(request["target_seconds"]).normalize())
    return digest([normalized,catalog])
