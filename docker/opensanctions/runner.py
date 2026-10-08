from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request

def main() -> int:
    if len(sys.argv)==2 and sys.argv[1]=="--health": print("opensanctions runner ok"); return 0
    if len(sys.argv)!=3: return 2
    token=os.environ.get("OPENSANCTIONS_API_KEY")
    if not token:
        print("OPENSANCTIONS_API_KEY is required",file=sys.stderr); return 3
    q=urllib.parse.quote(sys.argv[2].strip(), safe="")
    url=f"https://api.opensanctions.org/search/sanctions?q={q}&limit=10"
    req=urllib.request.Request(url,headers={"Authorization":f"ApiKey {token}","Accept":"application/json","User-Agent":"Aletheia/0.6.0"})
    with urllib.request.urlopen(req,timeout=30) as r: payload=json.loads(r.read().decode("utf-8"))
    results=payload.get("results",[]) if isinstance(payload,dict) else []
    print(json.dumps({"results":results},separators=(",",":")))
    return 0
if __name__=="__main__": raise SystemExit(main())
