from __future__ import annotations

from html import escape


def page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aletheia</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}header{padding:14px 18px;border-bottom:1px solid #333;display:flex;gap:12px;align-items:center}main{padding:16px;display:grid;gap:16px}.panel{border:1px solid #333;border-radius:10px;padding:14px;background:#181818}input,button{font:inherit;padding:8px;border-radius:6px;border:1px solid #555;background:#222;color:#eee}button{cursor:pointer}#graph{width:100%;height:560px;border:1px solid #333;background:#101010}.node{cursor:pointer}.edge{stroke:#555;stroke-width:1.3}.node circle{fill:#222;stroke:#9aa;stroke-width:1.5}.node text{fill:#ddd;font-size:11px}.muted{color:#999;font-size:.9em}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #333;padding:8px;text-align:left;font-size:.9em}pre{white-space:pre-wrap;overflow:auto}
</style></head>
<body><header><strong>Aletheia</strong><span class="muted">provenance-first OSINT control plane</span></header>
<main>
<div class="panel"><label>Run ID <input id="run" size="38" placeholder="UUID"></label> <button onclick="loadRun()">Load graph</button> <span id="status" class="muted"></span></div>
<div class="panel"><div id="meta" class="muted">No run loaded.</div><svg id="graph" viewBox="0 0 1200 560"></svg></div>
<div class="panel"><h3>Benchmark leaderboard</h3><div id="bench">Loading…</div></div>
<div class="panel"><h3>Node details</h3><pre id="details">Click a node.</pre></div>
</main>
<script>
const NS='http://www.w3.org/2000/svg';
function esc(x){return String(x??'').replace(/[&<>\"]/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[s]));}
async function loadBench(){const r=await fetch('/v1/benchmarks/leaderboard');const d=await r.json();const rows=d.rows||[];document.querySelector('#bench').innerHTML=rows.length?'<table><tr><th>#</th><th>Adapter</th><th>Cases</th><th>Precision</th><th>Recall</th><th>Coverage</th><th>Avg ms</th></tr>'+rows.map(x=>`<tr><td>${x.rank}</td><td>${esc(x.adapter)}</td><td>${x.cases}</td><td>${fmt(x.precision)}</td><td>${fmt(x.recall)}</td><td>${fmt(x.coverage)}</td><td>${x.avg_duration_ms?x.avg_duration_ms.toFixed(1):'—'}</td></tr>`).join('')+'</table>':'No labeled benchmark cases yet.'}
function fmt(v){return v==null?'—':(v*100).toFixed(1)+'%'}
async function loadRun(){const id=document.querySelector('#run').value.trim(); if(!id)return;const status=document.querySelector('#status');status.textContent='Loading…';try{const [m,g]=await Promise.all([fetch('/v1/investigations/'+id),fetch('/v1/investigations/'+id+'/graph')]);if(!m.ok||!g.ok)throw Error('Run not found');const manifest=await m.json(),graph=await g.json();document.querySelector('#meta').textContent=`${manifest.goal} · ${manifest.status} · completed ${manifest.completed?.length||0} / pending ${manifest.pending?.length||0}`;renderGraph(graph);status.textContent='Loaded';}catch(e){status.textContent=e.message}}
function renderGraph(g){const svg=document.querySelector('#graph');svg.innerHTML='';const nodes=g.entities||[],edges=g.edges||[];const map=new Map(nodes.map((n,i)=>[n.entity_id,i]));const cx=600,cy=280,rad=Math.max(90,Math.min(240,nodes.length*13));const pos=nodes.map((n,i)=>({x:cx+Math.cos(i/nodes.length*Math.PI*2)*rad,y:cy+Math.sin(i/nodes.length*Math.PI*2)*rad}));edges.forEach(e=>{const a=pos[map.get(e.source_entity_id)],b=pos[map.get(e.target_entity_id)];if(!a||!b)return;const l=document.createElementNS(NS,'line');l.setAttribute('x1',a.x);l.setAttribute('y1',a.y);l.setAttribute('x2',b.x);l.setAttribute('y2',b.y);l.setAttribute('class','edge');svg.appendChild(l)});nodes.forEach((n,i)=>{const gEl=document.createElementNS(NS,'g');gEl.setAttribute('class','node');gEl.setAttribute('transform',`translate(${pos[i].x},${pos[i].y})`);const c=document.createElementNS(NS,'circle');c.setAttribute('r','22');const t=document.createElementNS(NS,'text');t.setAttribute('text-anchor','middle');t.setAttribute('y','4');t.textContent=(n.canonical_value||'').slice(0,16);gEl.append(c,t);gEl.onclick=()=>document.querySelector('#details').textContent=JSON.stringify(n,null,2);svg.appendChild(gEl)})}
loadBench();
</script></body></html>"""
