import json,os,sys
from pathlib import Path
if len(sys.argv)==2 and sys.argv[1]=='--health': print('ok'); raise SystemExit(0)
if len(sys.argv)!=2: print('usage: runner.py <image>',file=sys.stderr); raise SystemExit(2)
from google.cloud import vision
from google.oauth2 import service_account
raw=os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if not raw: print('GOOGLE_APPLICATION_CREDENTIALS_JSON is required',file=sys.stderr); raise SystemExit(5)
creds=service_account.Credentials.from_service_account_info(json.loads(raw))
client=vision.ImageAnnotatorClient(credentials=creds)
content=Path(sys.argv[1]).read_bytes(); image=vision.Image(content=content)
labels=client.label_detection(image=image).label_annotations
texts=client.text_detection(image=image).text_annotations
faces=client.face_detection(image=image).face_annotations
if labels and getattr(labels[0],'description',None): pass
out={'labels':[{'description':x.description,'score':x.score} for x in labels], 'text': {'text': texts[0].description if texts else ''}, 'faces':[{} for _ in faces]}
print(json.dumps(out,ensure_ascii=False));
