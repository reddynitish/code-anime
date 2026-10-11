"""Select an ordered pose path from candidate drawings; no invented inbetween pixels.
Uses low-resolution blurred silhouettes to rank progression between anchor drawings.
Every selected output is an actual drawing. Holds may reuse it for several frames.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageFilter
from draw_sequence import ANCHORS,mask_for,REF,PLATE
from luminal_images import ROOT
rows=json.loads((ROOT/'output/2d/timeline.json').read_text())
plate=Image.open(PLATE).convert('RGB')
def pic(path,t):
 image=Image.open(path).convert('RGB');mask=ImageOps.invert(Image.open(mask_for('curation',t)).convert('L'))
 return Image.composite(image,plate,mask)
def feat(image):
 return np.asarray(image.crop((375,95,775,430)).resize((160,134)).filter(ImageFilter.GaussianBlur(2)),dtype=np.float32)/255

def anchorpath(n):return REF if n=='original' else ROOT/'output/2d/keys'/f'{n}.png'
selection=rows.copy();report=[]
for a,b in zip(ANCHORS[:-1],ANCHORS[1:]):
 ta,na,_=a;tb,nb,_=b
 indices=[j for j,r in enumerate(rows) if ta<=r['time']<tb and 1<=r['time']<9.5]
 if not indices:continue
 A=feat(pic(anchorpath(na),ta));B=feat(pic(anchorpath(nb),tb));D=B-A;den=float(np.sum(D*D))
 candidates=[]
 for j in indices:
  C=feat(pic(rows[j]['image'],rows[j]['time']));q=float(np.sum((C-A)*D)/max(den,1e-8));q=max(0,min(1,q))
  residual=float(np.mean((C-(A+q*D))**2))
  candidates.append((q,residual,j,rows[j]['image']))
 # Reject the most divergent quarter of each interval, keeping at least three options.
 threshold=float(np.quantile([x[1] for x in candidates],.75))
 candidates=[x for x in candidates if x[1]<=threshold] or candidates
 candidates.sort(key=lambda x:x[0])
 choices=[(0,0,-1,str(anchorpath(na)))]+candidates+[(1,0,-1,str(anchorpath(nb)))]
 for j in indices:
  target=(rows[j]['time']-ta)/(tb-ta)
  chosen=min(choices,key=lambda x:abs(x[0]-target)+.05*x[1])
  selection[j]={**rows[j],'image':chosen[3]}
 report.append({'interval':[ta,tb],'candidate_drawings':len(indices),'retained':len(candidates),'selected_images':len({selection[j]['image'] for j in indices})})
(ROOT/'output/2d/timeline_uncurated.json').write_text(json.dumps(rows,indent=2))
(ROOT/'output/2d/timeline_curated.json').write_text(json.dumps(selection,indent=2))
(ROOT/'output/2d/curation_report.json').write_text(json.dumps(report,indent=2))
print('Curated drawings selected:',len({r['image'] for r in selection}))
