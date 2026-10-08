from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request

def main() -> int:
    if len(sys.argv)==2 and sys.argv[1]=="--health": print("courtlistener runner ok"); return 0
    if len(sys.argv)!=2 or not sys.argv[1].strip(): return 2
    q=urllib.parse.quote(sys.argv[1].strip(), safe="")
    url=f"https://www.courtlistener.com/api/rest/v3/search/?q={q}&type=r&order_by=score%20desc"
    headers={"Accept":"application/json","User-Agent":"Aletheia/0.6.0"}
    token=os.environ.get("COURTLISTENER_API_TOKEN")
    if token: headers["Authorization"]=f"Token {token}"
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=30) as r: payload=json.loads(r.read().decode("utf-8"))
    rows=payload.get("results",[]) if isinstance(payload,dict) else []
    out=[]
    for r in rows[:10]:
        if not isinstance(r,dict): continue
        out.append({k:r.get(k) for k in ("caseName","case_name","absolute_url","court_citation","dateFiled","date_filed","docketNumber","docket_number","type","snippet","score")})
    print(json.dumps({"results":out},separators=(",",":")))
    return 0
if __name__=="__main__": raise SystemExit(main())
