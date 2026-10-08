import json,sys
from pathlib import Path
if len(sys.argv)==2 and sys.argv[1]=='--health': print('ok'); raise SystemExit(0)
if len(sys.argv)!=2: print('usage: runner.py <image>',file=sys.stderr); raise SystemExit(2)
from deepface import DeepFace
path=sys.argv[1]
faces=DeepFace.extract_faces(img_path=path,detector_backend='opencv',enforce_detection=False,align=False,anti_spoofing=False)
out=[]
for item in faces or []:
    if not isinstance(item,dict): continue
    area=item.get('facial_area',{}) or {}
    conf=item.get('confidence',item.get('face_confidence',0))
    if area or float(conf or 0)>0: out.append({'facial_area':area,'confidence':conf})
print(json.dumps({'faces':out,'image':str(Path(path).name)}));
