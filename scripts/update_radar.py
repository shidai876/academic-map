#!/usr/bin/env python3
# Academic Map 2.2 — balanced precision membrane-separation radar
from __future__ import annotations
import os, re, json, time, hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter
import requests

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
SITE_DATA=ROOT/"site"/"data"; SITE_DATA.mkdir(parents=True,exist_ok=True)
HISTORY_PATH=ROOT/"data"/"history.json"; HISTORY_PATH.parent.mkdir(parents=True,exist_ok=True)
TZ8=timezone(timedelta(hours=8)); NOW=datetime.now(TZ8); TODAY=NOW.date()
DAYS=int(CFG.get("window_days",7)); FROM_DATE=TODAY-timedelta(days=DAYS-1)
UA="AcademicMapResearchRadar/2.2 (personal academic radar; public metadata only)"
OPENALEX_KEY=os.getenv("OPENALEX_API_KEY","").strip()
CROSSREF_MAILTO=os.getenv("CROSSREF_MAILTO","").strip()
S=requests.Session(); S.headers.update({"User-Agent":UA,"Accept":"application/json"})

def clean(s): return re.sub(r"\s+"," ",str(s or "")).strip()
def doi_norm(s): return clean(s).lower().replace("https://doi.org/","").replace("http://doi.org/","")
def reconstruct(inv):
    if not isinstance(inv,dict): return ""
    pairs=[]
    for w,ps in inv.items():
        for p in ps or []: pairs.append((p,w))
    return clean(" ".join(w for _,w in sorted(pairs)))
def req(url,params,tries=3):
    for i in range(tries):
        try:
            r=S.get(url,params=params,timeout=35)
            if r.status_code==429: time.sleep(2*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            if i==tries-1: print("WARN",e)
            time.sleep(1.2*(i+1))
    return None

def fetch_openalex(q):
    p={"search":q,"filter":f"from_publication_date:{FROM_DATE},to_publication_date:{TODAY},type:article","sort":"publication_date:desc","per-page":40}
    if OPENALEX_KEY:p["api_key"]=OPENALEX_KEY
    js=req("https://api.openalex.org/works",p); out=[]
    for w in (js or {}).get("results",[]):
        loc=w.get("primary_location") or {}; src=loc.get("source") or {}
        au=[]; inst=[]
        for a in w.get("authorships") or []:
            n=clean((a.get("author") or {}).get("display_name"))
            if n and n not in au: au.append(n)
            for i in a.get("institutions") or []:
                n2=clean(i.get("display_name"))
                if n2 and n2 not in inst:inst.append(n2)
        out.append({"source_db":"OpenAlex","openalex_id":clean(w.get("id")).split("/")[-1],"openalex_url":clean(w.get("id")),
                    "doi":doi_norm(w.get("doi")),"title":clean(w.get("display_name") or w.get("title")),
                    "publication_date":clean(w.get("publication_date")),"journal":clean(src.get("display_name")),
                    "authors":au,"first_author":au[0] if au else "","institutions":inst,
                    "abstract":reconstruct(w.get("abstract_inverted_index")),"cited_by_count":int(w.get("cited_by_count") or 0)})
    return out

def cdate(it):
    for k in ["published-online","published-print","published","issued","created"]:
        parts=((it.get(k) or {}).get("date-parts") or [[]])[0]
        try:
            if len(parts)>=3:return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
            if len(parts)>=2:return f"{parts[0]:04d}-{parts[1]:02d}-01"
            if len(parts)>=1:return f"{parts[0]:04d}-01-01"
        except: pass
    return ""
def strip_tags(s): return clean(re.sub(r"<[^>]+>"," ",s or ""))
def fetch_crossref(q):
    p={"query.bibliographic":q,"filter":f"from-pub-date:{FROM_DATE},until-pub-date:{TODAY},type:journal-article",
       "rows":40,"select":"DOI,title,published-online,published-print,published,issued,created,container-title,author,abstract,URL,type"}
    if CROSSREF_MAILTO:p["mailto"]=CROSSREF_MAILTO
    js=req("https://api.crossref.org/works",p); out=[]
    for it in ((js or {}).get("message") or {}).get("items",[]):
        au=[]; inst=[]
        for a in it.get("author") or []:
            n=clean(" ".join([a.get("given",""),a.get("family","")]))
            if n and n not in au:au.append(n)
            for aff in a.get("affiliation") or []:
                n2=clean(aff.get("name"))
                if n2 and n2 not in inst:inst.append(n2)
        out.append({"source_db":"Crossref","openalex_id":"","openalex_url":"","doi":doi_norm(it.get("DOI")),
                    "title":clean((it.get("title") or [""])[0]),"publication_date":cdate(it),
                    "journal":clean((it.get("container-title") or [""])[0]),"authors":au,
                    "first_author":au[0] if au else "","institutions":inst,"abstract":strip_tags(it.get("abstract")),
                    "cited_by_count":0})
    return out

def key(w):
    if w.get("doi"):return "doi:"+w["doi"]
    t=re.sub(r"[^a-z0-9]+","",w.get("title","").lower())
    return "title:"+hashlib.sha1(t.encode()).hexdigest()[:20]
def merge(a,b):
    x=dict(a)
    for k in ["title","publication_date","journal","abstract","first_author"]:
        if len(str(b.get(k,"")))>len(str(x.get(k,""))):x[k]=b[k]
    for k in ["authors","institutions"]:
        vals=[]
        for z in (x.get(k) or [])+(b.get(k) or []):
            if z and z not in vals:vals.append(z)
        x[k]=vals
    if b.get("openalex_url"):x["openalex_url"]=b["openalex_url"]
    if b.get("openalex_id"):x["openalex_id"]=b["openalex_id"]
    if a.get("source_db")!=b.get("source_db"):x["source_db"]="OpenAlex + Crossref"
    return x

def classify(w):
    text=" ".join([w.get("title",""),w.get("abstract",""),w.get("journal","")]).lower()
    topics=[]
    for topic,phrases in CFG["topic_rules"].items():
        if any(p.lower() in text for p in phrases):topics.append(topic)

    membrane=any(p.lower() in text for p in CFG["membrane_words"])
    separation=any(p.lower() in text for p in CFG["separation_words"])
    pair=any(a.lower() in text and b.lower() in text for a,b in CFG["high_value_pairs"])
    core=(membrane and separation) or pair
    adjacent=bool(topics)

    score=0;hits=[]
    for wt,phrases in CFG["weighted_keywords"].items():
        m=[p for p in phrases if p.lower() in text]
        if m:score+=int(wt);hits+=m[:3]
    if core:score+=18
    if pair:score+=8

    for wt,phrases in CFG.get("penalty_keywords",{}).items():
        if any(p.lower() in text for p in phrases):score+=int(wt)
    jl=w.get("journal","").lower()
    for name,boost in CFG.get("journal_boost",{}).items():
        if name.lower() in jl:score+=int(boost);break
    if w.get("abstract"):score+=3
    if w.get("institutions"):score+=2

    off=any(p.lower() in text for p in CFG.get("off_topic_cap_keywords",[]))
    if off and not core:score=min(score,int(CFG["score_caps"]["off_topic_without_membrane_separation"]))
    elif adjacent and not core:score=min(score,int(CFG["score_caps"]["adjacent_only"]))

    score=max(0,min(100,score))
    seen=set();hits=[h for h in hits if not(h in seen or seen.add(h))]
    rel="核心膜分离" if core and score>=50 else ("膜领域相关" if core else ("领域扩展" if adjacent else "低相关"))
    return topics,hits,score,rel

UNITS=r"(?:%|nm|μm|um|Å|bar|MPa|kPa|h\b|hours?|days?|L\s*m[\-−–]?[²2]\s*h[\-−–]?1(?:\s*bar[\-−–]?1)?|LMH)"
NUM_RE=re.compile(rf"\b\d+(?:\.\d+)?(?:\s*[±\-–~]\s*\d+(?:\.\d+)?)?\s*{UNITS}",re.I)
def numbers(t):
    out=[]
    for m in NUM_RE.finditer(t or ""):
        v=clean(m.group(0))
        if v not in out:out.append(v)
    return out[:8]
def brief(w):
    p=[f"定位：{w.get('relevance_class','')}"]
    if w.get("topics"):p.append("主题："+" / ".join(w["topics"][:3]))
    if w.get("institutions"):p.append("团队："+"、".join(w["institutions"][:2]))
    if w.get("abstract"):
        s=clean(re.split(r"(?<=[.!?])\s+",w["abstract"])[0])
        if len(s)>230:s=s[:227]+"…"
        p.append("摘要首句："+s)
    else:p.append("题名线索："+w.get("title",""))
    return "；".join(p)+"。"

def update_history(works):
    try:h=json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except:h={"days":[]}
    d={"date":TODAY.isoformat(),"works":[{"id":w["id"],"title":w["title"],"journal":w.get("journal",""),
        "topics":w.get("topics",[]),"authors":w.get("authors",[])[:8],"institutions":w.get("institutions",[])[:6],
        "score":w["score"],"relevance_class":w["relevance_class"]} for w in works]}
    days=[x for x in h.get("days",[]) if x.get("date")!=d["date"]]+[d]
    h={"days":sorted(days,key=lambda x:x.get("date",""))[-60:]}
    HISTORY_PATH.write_text(json.dumps(h,ensure_ascii=False,indent=2),encoding="utf-8");return h
def period(days,a,b):
    lo=TODAY-timedelta(days=b);hi=TODAY-timedelta(days=a)
    return [d for d in days if lo<=datetime.fromisoformat(d["date"]).date()<=hi]
def cnt(ds):
    tc=Counter();jc=Counter();ac=Counter();ic=Counter()
    for d in ds:
        for w in d.get("works",[]):
            tc.update(w.get("topics",[]))
            if w.get("journal"):jc[w["journal"]]+=1
            ac.update(w.get("authors",[]));ic.update(w.get("institutions",[]))
    return tc,jc,ac,ic
def rows(c,p=None,n=12):
    p=p or Counter();return [{"name":k,"count":v,"delta":v-p.get(k,0)} for k,v in c.most_common(n)]
def trends(h):
    ds=h.get("days",[]);a=cnt(period(ds,0,6));b=cnt(period(ds,7,13));c=cnt(period(ds,0,29))
    return {"topics":rows(a[0],b[0]),"journals":rows(c[1],None),"authors":rows(c[2],None,15),"institutions":rows(c[3],None,15)}

def main():
    raw=[]
    for q in CFG["queries"]:
        print("OpenAlex:",q);raw+=fetch_openalex(q);time.sleep(.12)
    for q in CFG["queries"]:
        print("Crossref:",q);raw+=fetch_crossref(q);time.sleep(.12)
    fetched=len(raw); merged={}
    for w in raw:
        if not w.get("title"):continue
        k=key(w);merged[k]=merge(merged[k],w) if k in merged else w

    works=[]
    for w in merged.values():
        topics,hits,score,rel=classify(w)
        if score<18 or not topics:continue
        w.update({"topics":topics,"keyword_hits":hits,"score":score,"relevance_class":rel})
        w["key_numbers"]=numbers((w.get("abstract") or "")+" "+w.get("title",""))
        w["brief"]=brief(w);w["id"]=key(w);works.append(w)
    works=sorted(works,key=lambda x:(x["score"],x.get("publication_date","")),reverse=True)[:int(CFG["max_display"])]
    h=update_history(works)
    out={"status":"ok","version":"2.2","updated_at":datetime.now(timezone.utc).isoformat(),
         "updated_at_local":NOW.strftime("%Y-%m-%d %H:%M (UTC+8)"),
         "stats":{"fetched":fetched,"related":len(works),
                  "recommended":sum(1 for w in works if w["score"]>=int(CFG["recommend_score"]) and w["relevance_class"]=="核心膜分离"),
                  "window_days":DAYS,"sources":["OpenAlex","Crossref"]},
         "works":works,"trends":trends(h),
         "notes":{"precision_mode":"2.2 balanced precision","ai":"No paid AI API is used."}}
    (SITE_DATA/"radar.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    (SITE_DATA/"last_run.txt").write_text(NOW.isoformat(),encoding="utf-8")
    print("DONE",out["stats"])

if __name__=="__main__":main()
