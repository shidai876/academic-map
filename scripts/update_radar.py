#!/usr/bin/env python3
# Academic Map 2.0 research radar updater
# Free data sources: OpenAlex basic search + Crossref REST API.
from __future__ import annotations
import os, re, json, math, time, hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SITE_DATA = ROOT / "site" / "data"
HISTORY_PATH = ROOT / "data" / "history.json"
SITE_DATA.mkdir(parents=True, exist_ok=True)
HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

TZ8 = timezone(timedelta(hours=8))
NOW = datetime.now(TZ8)
TODAY = NOW.date()
DAYS = int(CFG.get("window_days", 3))
FROM_DATE = TODAY - timedelta(days=DAYS-1)
UA = "AcademicMapResearchRadar/2.0 (personal academic radar; public metadata only)"
OPENALEX_KEY = os.getenv("OPENALEX_API_KEY","").strip()
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO","").strip()
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "application/json"})

def clean(s):
    if s is None: return ""
    return re.sub(r"\s+"," ",str(s)).strip()

def doi_norm(s):
    s=clean(s).lower().replace("https://doi.org/","").replace("http://doi.org/","")
    return s

def reconstruct_abstract(inv):
    if not isinstance(inv, dict) or not inv: return ""
    pairs=[]
    for word, positions in inv.items():
        for p in positions or []: pairs.append((p,word))
    return clean(" ".join(w for _,w in sorted(pairs)))

def request_json(url, params, tries=3):
    for i in range(tries):
        try:
            r=session.get(url,params=params,timeout=35)
            if r.status_code==429:
                time.sleep(3*(i+1)); continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i==tries-1:
                print("WARN request failed:",url,params,"=>",e)
            time.sleep(1.5*(i+1))
    return None

def fetch_openalex(query):
    params={
        "search":query,
        "filter":f"from_publication_date:{FROM_DATE.isoformat()},to_publication_date:{TODAY.isoformat()},type:article",
        "sort":"publication_date:desc",
        "per-page":40
    }
    if OPENALEX_KEY: params["api_key"]=OPENALEX_KEY
    js=request_json("https://api.openalex.org/works",params)
    out=[]
    for w in (js or {}).get("results",[]):
        primary=w.get("primary_location") or {}
        src=primary.get("source") or {}
        authorships=w.get("authorships") or []
        authors=[]; institutions=[]
        for a in authorships:
            nm=clean((a.get("author") or {}).get("display_name"))
            if nm and nm not in authors: authors.append(nm)
            for inst in a.get("institutions") or []:
                nm2=clean(inst.get("display_name"))
                if nm2 and nm2 not in institutions: institutions.append(nm2)
        out.append({
            "source_db":"OpenAlex",
            "openalex_id":clean(w.get("id")).split("/")[-1],
            "openalex_url":clean(w.get("id")),
            "doi":doi_norm(w.get("doi")),
            "title":clean(w.get("display_name") or w.get("title")),
            "publication_date":clean(w.get("publication_date")),
            "journal":clean(src.get("display_name")),
            "authors":authors,
            "first_author":authors[0] if authors else "",
            "institutions":institutions,
            "abstract":reconstruct_abstract(w.get("abstract_inverted_index")),
            "cited_by_count":int(w.get("cited_by_count") or 0),
            "type":clean(w.get("type"))
        })
    return out

def crossref_date(item):
    for k in ["published-online","published-print","published","issued","created"]:
        p=item.get(k) or {}
        parts=(p.get("date-parts") or [[]])[0]
        if len(parts)>=3:
            try:return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
            except: pass
        if len(parts)>=2:
            try:return f"{parts[0]:04d}-{parts[1]:02d}-01"
            except: pass
        if len(parts)>=1:
            try:return f"{parts[0]:04d}-01-01"
            except: pass
    return ""

def strip_tags(s):
    return clean(re.sub(r"<[^>]+>"," ",s or ""))

def fetch_crossref(query):
    params={
        "query.bibliographic":query,
        "filter":f"from-pub-date:{FROM_DATE.isoformat()},until-pub-date:{TODAY.isoformat()},type:journal-article",
        "rows":40,
        "select":"DOI,title,published-online,published-print,published,issued,created,container-title,author,abstract,URL,type"
    }
    if CROSSREF_MAILTO: params["mailto"]=CROSSREF_MAILTO
    js=request_json("https://api.crossref.org/works",params)
    out=[]
    for it in ((js or {}).get("message") or {}).get("items",[]):
        au=[]; inst=[]
        for a in it.get("author") or []:
            nm=clean(" ".join([a.get("given",""),a.get("family","")]))
            if nm and nm not in au: au.append(nm)
            for aff in a.get("affiliation") or []:
                nm2=clean(aff.get("name"))
                if nm2 and nm2 not in inst:inst.append(nm2)
        title=(it.get("title") or [""])[0]
        journal=(it.get("container-title") or [""])[0]
        out.append({
            "source_db":"Crossref",
            "openalex_id":"",
            "openalex_url":"",
            "doi":doi_norm(it.get("DOI")),
            "title":clean(title),
            "publication_date":crossref_date(it),
            "journal":clean(journal),
            "authors":au,
            "first_author":au[0] if au else "",
            "institutions":inst,
            "abstract":strip_tags(it.get("abstract")),
            "cited_by_count":0,
            "type":clean(it.get("type"))
        })
    return out

def key_for(w):
    if w.get("doi"): return "doi:"+w["doi"]
    t=re.sub(r"[^a-z0-9]+","",w.get("title","").lower())
    return "title:"+hashlib.sha1(t.encode()).hexdigest()[:20]

def merge_records(a,b):
    # Prefer richer fields, while preserving OpenAlex links.
    x=dict(a)
    for k in ["title","publication_date","journal","abstract","first_author"]:
        if len(str(b.get(k,""))) > len(str(x.get(k,""))): x[k]=b[k]
    for k in ["authors","institutions"]:
        vals=[]
        for z in (x.get(k) or [])+(b.get(k) or []):
            if z and z not in vals:vals.append(z)
        x[k]=vals
    if b.get("openalex_url"): x["openalex_url"]=b["openalex_url"]
    if b.get("openalex_id"): x["openalex_id"]=b["openalex_id"]
    x["source_db"]="OpenAlex + Crossref" if a.get("source_db")!=b.get("source_db") else a.get("source_db")
    return x

def contains_phrase(text,p):
    p=p.lower()
    return p in text

def classify_score(w):
    text=(" ".join([w.get("title",""),w.get("abstract",""),w.get("journal","")])).lower()
    topics=[]; hits=[]
    for topic,phrases in CFG["topic_rules"].items():
        if any(contains_phrase(text,p) for p in phrases): topics.append(topic)
    score=0
    for weight,phrases in CFG["weighted_keywords"].items():
        matched=[p for p in phrases if contains_phrase(text,p)]
        if matched:
            score += int(weight)
            hits.extend(matched[:3])
    for weight,phrases in CFG.get("penalty_keywords",{}).items():
        if any(contains_phrase(text,p) for p in phrases): score += int(weight)
    j=w.get("journal","").lower()
    for name,boost in CFG.get("journal_boost",{}).items():
        if name.lower() in j:
            score+=int(boost);break
    if any(k in text for k in ["membrane","nanofiltration","nanochannel"]): score+=5
    if w.get("abstract"):score+=3
    if w.get("institutions"):score+=2
    score=max(0,min(100,score))
    # dedupe hits preserving order
    seen=set();hits=[x for x in hits if not (x in seen or seen.add(x))]
    return topics,hits,score

UNITS=r"(?:%|nm|μm|um|Å|A\b|bar|MPa|kPa|h\b|hours?|days?|L\s*m[\-−–]?[²2]\s*h[\-−–]?1(?:\s*bar[\-−–]?1)?|LMH|mol\s*m[\-−–]?2\s*h[\-−–]?1)"
NUM_RE=re.compile(rf"\b\d+(?:\.\d+)?(?:\s*[±\-–~]\s*\d+(?:\.\d+)?)?\s*{UNITS}",re.I)
def numbers(text):
    vals=[]
    for m in NUM_RE.finditer(text or ""):
        v=clean(m.group(0))
        if v not in vals:vals.append(v)
    return vals[:8]

def brief_for(w):
    topics=w.get("topics") or []
    title=w.get("title","")
    inst=(w.get("institutions") or [])[:2]
    parts=[]
    if topics:parts.append("主题："+" / ".join(topics[:3]))
    if inst:parts.append("团队："+"、".join(inst))
    if w.get("abstract"):
        sent=re.split(r"(?<=[.!?])\s+",w["abstract"])
        if sent:
            s=clean(sent[0])
            if len(s)>230:s=s[:227]+"…"
            parts.append("摘要首句："+s)
    else:
        parts.append("题名线索："+title)
    return "；".join(parts)+"。"

def update_history(works):
    try:h=json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except:h={"days":[]}
    daily={
        "date":TODAY.isoformat(),
        "works":[{
            "id":w["id"],"title":w["title"],"journal":w.get("journal",""),
            "topics":w.get("topics",[]),"authors":w.get("authors",[])[:8],
            "institutions":w.get("institutions",[])[:6],"score":w.get("score",0)
        } for w in works]
    }
    days=[d for d in h.get("days",[]) if d.get("date")!=daily["date"]]
    days.append(daily);days=sorted(days,key=lambda d:d.get("date",""))[-60:]
    h={"days":days}
    HISTORY_PATH.write_text(json.dumps(h,ensure_ascii=False,indent=2),encoding="utf-8")
    return h

def count_period(days, start_days_ago, end_days_ago):
    # Inclusive lower/upper offsets from TODAY: e.g. 0..6 = last 7 days
    a=TODAY-timedelta(days=end_days_ago); b=TODAY-timedelta(days=start_days_ago)
    subset=[d for d in days if a<=datetime.fromisoformat(d["date"]).date()<=b]
    return subset

def counters(ds):
    tc=Counter();jc=Counter();ac=Counter();ic=Counter()
    for d in ds:
        for w in d.get("works",[]):
            tc.update(w.get("topics",[]))
            if w.get("journal"):jc[w["journal"]]+=1
            ac.update(w.get("authors",[]))
            ic.update(w.get("institutions",[]))
    return tc,jc,ac,ic

def trend_rows(cur,prev=None,n=12):
    prev=prev or Counter()
    rows=[]
    for name,count in cur.most_common(n):
        rows.append({"name":name,"count":count,"delta":count-prev.get(name,0)})
    return rows

def make_trends(history):
    days=history.get("days",[])
    last7=count_period(days,0,6); prev7=count_period(days,7,13); last30=count_period(days,0,29)
    c7=counters(last7);p7=counters(prev7);c30=counters(last30)
    return {
        "topics":trend_rows(c7[0],p7[0],12),
        "journals":trend_rows(c30[1],None,12),
        "authors":trend_rows(c30[2],None,15),
        "institutions":trend_rows(c30[3],None,15)
    }

def main():
    raw=[]
    queries=CFG["queries"]
    for q in queries:
        print("OpenAlex:",q)
        raw.extend(fetch_openalex(q))
        time.sleep(.15)
    for q in queries:
        print("Crossref:",q)
        raw.extend(fetch_crossref(q))
        time.sleep(.15)
    fetched=len(raw)
    merged={}
    for w in raw:
        if not w.get("title"):continue
        k=key_for(w)
        merged[k]=merge_records(merged[k],w) if k in merged else w
    works=[]
    for w in merged.values():
        topics,hits,score=classify_score(w)
        if score<25 or not topics:continue
        w["topics"]=topics;w["keyword_hits"]=hits;w["score"]=score
        w["key_numbers"]=numbers((w.get("abstract") or "")+" "+w.get("title",""))
        w["brief"]=brief_for(w)
        w["id"]=key_for(w)
        works.append(w)
    works=sorted(works,key=lambda x:(x.get("score",0),x.get("publication_date","")),reverse=True)[:int(CFG.get("max_display",60))]
    hist=update_history(works)
    trends=make_trends(hist)
    out={
        "status":"ok",
        "updated_at":datetime.now(timezone.utc).isoformat(),
        "updated_at_local":NOW.strftime("%Y-%m-%d %H:%M (UTC+8)"),
        "stats":{
            "fetched":fetched,
            "related":len(works),
            "recommended":sum(1 for w in works if w["score"]>=int(CFG.get("recommend_score",55))),
            "window_days":DAYS,
            "sources":["OpenAlex","Crossref"]
        },
        "works":works,
        "trends":trends,
        "notes":{
            "corresponding_author":"Not inferred unless source metadata explicitly provides it.",
            "ai":"No paid AI API is used; brief summaries are deterministic metadata/abstract extraction."
        }
    }
    (SITE_DATA/"radar.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    (SITE_DATA/"last_run.txt").write_text(NOW.isoformat(),encoding="utf-8")
    print("DONE fetched",fetched,"related",len(works),"recommended",out["stats"]["recommended"])

if __name__=="__main__":
    main()
