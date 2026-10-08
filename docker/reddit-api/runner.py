import base64, json, os, ssl, sys, urllib.parse, urllib.request

def request(url, method='GET', data=None, headers=None):
    req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
    with urllib.request.urlopen(req,timeout=45,context=ssl.create_default_context()) as r: return json.load(r)

def main():
    if len(sys.argv)==2 and sys.argv[1]=='--health': print('ok'); return 0
    if len(sys.argv)!=2: print('usage: runner.py <username>',file=sys.stderr); return 2
    cid=os.getenv('REDDIT_CLIENT_ID'); secret=os.getenv('REDDIT_CLIENT_SECRET'); ua=os.getenv('REDDIT_USER_AGENT','Aletheia/0.5.0')
    if not cid or not secret: print('REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required',file=sys.stderr); return 5
    basic=base64.b64encode(f'{cid}:{secret}'.encode()).decode()
    body=urllib.parse.urlencode({'grant_type':'client_credentials'}).encode()
    token=request('https://www.reddit.com/api/v1/access_token',method='POST',data=body,headers={'Authorization':f'Basic {basic}','User-Agent':ua,'Content-Type':'application/x-www-form-urlencoded'})['access_token']
    name=sys.argv[1].lstrip('u/').strip()
    data=request('https://oauth.reddit.com/user/'+urllib.parse.quote(name,safe='')+'/about',headers={'Authorization':f'Bearer {token}','User-Agent':ua,'Accept':'application/json'})
    print(json.dumps(data,ensure_ascii=False,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
