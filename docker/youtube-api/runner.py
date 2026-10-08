import json, os, ssl, sys, urllib.parse, urllib.request

def get(path,params):
    url='https://www.googleapis.com/youtube/v3/'+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'Aletheia/0.5.0'})
    with urllib.request.urlopen(req,timeout=45,context=ssl.create_default_context()) as r: return json.load(r)

def main():
    if len(sys.argv)==2 and sys.argv[1]=='--health': print('ok'); return 0
    if len(sys.argv)!=2: print('usage: runner.py <username-or-handle>',file=sys.stderr); return 2
    key=os.getenv('YOUTUBE_API_KEY')
    if not key: print('YOUTUBE_API_KEY is required',file=sys.stderr); return 5
    q=sys.argv[1].strip()
    handle=q if q.startswith('@') else '@'+q
    data=get('channels',{'part':'snippet,statistics','forHandle':handle,'key':key})
    if not data.get('items'):
        data=get('search',{'part':'snippet','type':'channel','q':q,'maxResults':5,'key':key})
        ids=[i.get('snippet',{}).get('channelId') for i in data.get('items',[]) if isinstance(i,dict)]
        ids=[i for i in ids if i]
        if ids:
            details=get('channels',{'part':'snippet,statistics','id':','.join(ids[:5]),'key':key})
            data=details
    print(json.dumps(data,ensure_ascii=False,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
