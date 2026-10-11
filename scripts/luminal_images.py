"""Luminal image-only client. Credentials stay outside the repository.
Never submits video generation. Async IDs and costs are persisted for safe resume.
"""
import json, os, time, uuid, urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
CONFIG=Path.home()/'.config/code-anime/luminal.json'
JOBS=ROOT/'output/2d/jobs';JOBS.mkdir(parents=True,exist_ok=True)
PRICE={'very_low':.008,'low':.03,'medium':.06,'high':.20}
CAP=15.0

def request(path, body=None, content_type=None):
 cfg=json.loads(CONFIG.read_text()); headers={'Api-Key':cfg['api_key']}
 if content_type:headers['Content-Type']=content_type
 req=urllib.request.Request(cfg['image_base_url']+path,data=body,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=90) as r:return r.status,{k.lower():v for k,v in r.headers.items()},json.loads(r.read())
 except urllib.error.HTTPError as e:
  detail=e.read().decode()[:2000]
  raise RuntimeError(f'HTTP {e.code}: {detail}') from None

def multipart(fields,files):
 boundary='----anime'+uuid.uuid4().hex;data=[]
 for k,v in fields.items():data.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()])
 for k,path in files:
  p=Path(path);data.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{p.name}"\r\nContent-Type: image/png\r\n\r\n'.encode(),p.read_bytes(),b'\r\n'])
 data.append(f'--{boundary}--\r\n'.encode());return b''.join(data),'multipart/form-data; boundary='+boundary

def submit(name,image,prompt,mask=None,refs=(),quality='medium',seed=8311):
 path=JOBS/(name+'.json')
 if path.exists():return json.loads(path.read_text())
 spent=sum(j.get('reserved_usd',0) for p in JOBS.glob('*.json') for j in [json.loads(p.read_text())])
 if spent+PRICE[quality]>CAP:raise RuntimeError('Local $15 image request ceiling reached')
 files=[('image',image)]+([('mask',mask)] if mask else [])+[('reference_images',r) for r in refs]
 body,ctype=multipart({'prompt':prompt,'quality':quality,'num_images':'1','async':'true','seed':str(seed)},files)
 # Write a submitting record BEFORE POST. An uncertain network outcome is never blindly retried.
 job={'name':name,'state':'submitting','prompt':prompt,'quality':quality,'source':str(image),'mask':str(mask),'reserved_usd':PRICE[quality],'submitted_ms':int(time.time()*1000)}
 path.write_text(json.dumps(job,indent=2))
 try:status,headers,result=request('/v2/image/precise-edit/ideogram-4-5',body,ctype)
 except Exception as e:
  job['state']='submission_uncertain';job['error']=str(e);path.write_text(json.dumps(job,indent=2));raise
 job.update({'state':'pending','generation_id':result.get('generation_id') or headers.get('x-luminal-generation-id'),'response':result,'submit_headers':{k:v for k,v in headers.items() if k.lower().startswith('x-luminal')}})
 if not job['generation_id']:raise RuntimeError('Missing generation ID; reconcile record before retry')
 path.write_text(json.dumps(job,indent=2));print('Submitted',name,job['generation_id'],flush=True);return job

def poll(name):
 path=JOBS/(name+'.json');job=json.loads(path.read_text())
 if job['state']=='completed':return job
 if not job.get('generation_id'):raise RuntimeError('Submission must be reconciled, not retried')
 status,headers,result=request('/v1/generations/'+job['generation_id'])
 if result.get('status')=='pending':return job
 if result.get('status')=='failed':job['state']='failed';job['response']=result
 elif result.get('data'):
  item=result['data'][0]
  if not item.get('is_image_safe',True) or not item.get('url'):raise RuntimeError('No delivered image')
  output=ROOT/'output/2d/keys'/f'{name}.png'
  with urllib.request.urlopen(urllib.request.Request(item['url'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://ideogram.ai/'}),timeout=90) as r:output.write_bytes(r.read())
  job.update({'state':'completed','output':str(output),'response':result,'charged_usd':headers.get('x-luminal-cost-usd')})
 else:raise RuntimeError('Unrecognized poll response: '+json.dumps(result)[:700])
 path.write_text(json.dumps(job,indent=2));print(job['state'],name,flush=True);return job

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('action',choices=['balance','poll','list']);p.add_argument('names',nargs='*');a=p.parse_args()
 if a.action=='balance':
  _,_,d=request('/v1/balance');print(json.dumps({'available_usd':int(d['available_units'])/int(d['units_per_usd']),'postpaid':d['postpaid']}))
 elif a.action=='poll':
  for n in a.names:poll(n)
 else:
  for f in JOBS.glob('*.json'):
   j=json.loads(f.read_text());print(j['name'],j['state'])
