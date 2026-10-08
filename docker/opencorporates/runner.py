from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request

def main() -> int:
    if len(sys.argv)==2 and sys.argv[1]=="--health": print("opencorporates runner ok"); return 0
    if len(sys.argv)!=3 or sys.argv[1] != "name": return 2
    token=os.environ.get("OPENCORPORATES_API_TOKEN")
    if not token:
        print("OPENCORPORATES_API_TOKEN is required",file=sys.stderr); return 3
    q=urllib.parse.quote(sys.argv[2].strip(), safe="")
    url=f"https://api.opencorporates.com/v0.4/companies/search?q={q}&per_page=10"
    req=urllib.request.Request(url,headers={"X-API-TOKEN":token,"Accept":"application/json","User-Agent":"Aletheia/0.6.0"})
    with urllib.request.urlopen(req,timeout=30) as r: payload=json.loads(r.read().decode("utf-8"))
    rows=((payload.get("results") or {}).get("companies") or []) if isinstance(payload,dict) else []
    companies=[]
    for row in rows:
        c=(row or {}).get("company") if isinstance(row,dict) else None
        if isinstance(c,dict):
            companies.append({k:c.get(k) for k in ("name","company_number","jurisdiction_code","incorporation_date","current_status","registered_address_in_full","opencorporates_url")})
    print(json.dumps({"companies":companies},separators=(",",":")))
    return 0
if __name__=="__main__": raise SystemExit(main())
