import json,ssl,sys,urllib.parse,urllib.request
ENDPOINT='https://overpass-api.de/api/interpreter'
def main():
    if len(sys.argv)==2 and sys.argv[1]=='--health': print('ok'); return 0
    if len(sys.argv)!=2: print('usage: runner.py <lat,lon>',file=sys.stderr); return 2
    parts=[p.strip() for p in sys.argv[1].split(',')]
    try: lat=float(parts[0]); lon=float(parts[1])
    except Exception: print('invalid geolocation',file=sys.stderr); return 2
    if not (-90<=lat<=90 and -180<=lon<=180): print('invalid geolocation',file=sys.stderr); return 2
    q=f'[out:json][timeout:25];nwr(around:500,{lat},{lon})[name];out center tags;'
    body=urllib.parse.urlencode({'data':q}).encode()
    req=urllib.request.Request(ENDPOINT,data=body,headers={'User-Agent':'Aletheia/0.5.0','Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=60,context=ssl.create_default_context()) as r: payload=json.load(r)
    print(json.dumps(payload,ensure_ascii=False,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
