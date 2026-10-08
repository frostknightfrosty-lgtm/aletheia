import json,os,sys
from pathlib import Path
if len(sys.argv)==2 and sys.argv[1]=='--health':
    import insightface; print('ok'); raise SystemExit(0)
if len(sys.argv)!=2: print('usage: runner.py <image>',file=sys.stderr); raise SystemExit(2)
from insightface.app import FaceAnalysis
app=FaceAnalysis(name='buffalo_l',providers=['CPUExecutionProvider'],root='/models')
app.prepare(ctx_id=0,det_size=(640,640))
faces=app.get(sys.argv[1])
out=[]
for f in faces:
    out.append({'bbox':[float(x) for x in f.bbox.tolist()],'det_score':float(f.det_score)})
print(json.dumps({'faces':out,'image':Path(sys.argv[1]).name}));
