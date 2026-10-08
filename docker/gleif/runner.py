from __future__ import annotations
import json, sys, urllib.parse, urllib.request

def get(url: str) -> object:
    req=urllib.request.Request(url, headers={"User-Agent":"Aletheia/0.6.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def main() -> int:
    if len(sys.argv)==2 and sys.argv[1]=="--health": print("gleif runner ok"); return 0
    if len(sys.argv)!=2 or not sys.argv[1].strip(): return 2
    name=sys.argv[1].strip()
    params=urllib.parse.urlencode({"filter[entity.legalName]":name,"page[size]":10})
    payload=get("https://api.gleif.org/api/v1/lei-records?"+params)
    out=[]
    if isinstance(payload,dict):
        for item in payload.get("data",[]) or []:
            if not isinstance(item,dict): continue
            attrs=item.get("attributes") or {}
            ent=attrs.get("entity") or {}
            rel=item.get("relationships") or {}
            parent=(rel.get("directParent") or {}).get("data") if isinstance(rel,dict) else None
            out.append({
                "lei": attrs.get("lei") or item.get("id"),
                "status": attrs.get("registration",{}).get("status") if isinstance(attrs.get("registration"),dict) else None,
                "entity": {"legalName": (ent.get("legalName") or {}).get("name") if isinstance(ent.get("legalName"),dict) else ent.get("legalName"),
                           "jurisdiction": ent.get("jurisdiction"), "legalForm": (ent.get("legalForm") or {}).get("id") if isinstance(ent.get("legalForm"),dict) else ent.get("legalForm")},
                "parent": {"lei": parent.get("id")} if isinstance(parent,dict) and parent.get("id") else None,
                "source_url": "https://api.gleif.org/api/v1/lei-records/"+str(attrs.get("lei") or item.get("id")),
            })
    print(json.dumps({"records":out},separators=(",",":")))
    return 0
if __name__=="__main__": raise SystemExit(main())
