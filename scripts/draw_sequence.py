"""Produce a 2D drawing sequence with Luminal image edits only.
Use --keys first; inspect anchor images before --frames. Resume by job records.
"""
import argparse,json,time,math
from pathlib import Path
from PIL import Image,ImageDraw
from luminal_images import ROOT,submit,poll,JOBS
REF=ROOT/'assets/2d/reference.png';PLATE=ROOT/'output/2d/keys/clean_plate.png'
COMMON='Create ONE successive 2D anime animation drawing of the supplied room. The source is an anime drawing with the fixed room background. The room must remain pixel-identical except for the character and, when requested, the opening door. Reference image1 defines the EXACT same young man: slim adult, messy short BLACK hair, gray loose short-sleeved tee, dark gray pants, bare feet. Preserve his face, body proportions, costume, detailed hand-drawn ink contours and soft blue night cel colors. Keep camera absolutely fixed looking through the window, same bed, warm bedside lamp, chair, desk, window and posters. No camera changes, no 3D look, no simple cartoon shapes, no text, no duplicate person. Draw ONE man at natural scale in the requested precise animation pose. Foreground chair must occlude his legs when he is behind it; never draw on top of the chair. '
ANCHORS=[
(.0,'original','Original resting pose'),
(1.2,'key_12','The man is STILL lying on his back on the bed in the original exact position, head near pixel(535,196), feet near(460,398). He has lowered his right arm from above his head to his chest and turned his head toward the rear-right closed door. Torso remains on mattress, knees gently bend. Match the original man and blanket contact; this is the anticipation pose just before sitting up.'),
(1.8,'key_18','He is HALFWAY through sitting up from his original reclined position. Hips still on mattress around(490,295), torso lifted about45degrees, head around(553,214); left palm braces mattress near hip. Knees bend and draw closer to hips, feet still on bed near(475,350). A natural curling sit-up, not a fully seated pose. Closed door unchanged.'),
(2.5,'key_25','He sits upright on the mattress, beginning to turn toward the RIGHT long edge nearest the aisle. Head around(553,191), hips around(531,281). Both knees bent together; his lower legs are in mid-swing over the mattress right edge, one bare foot near(569,330), the other near(578,337), not yet touching floor. Both palms lightly brace bed. Closed door unchanged.'),
(3.0,'test_sit','Fully seated bed edge pose'),
(3.5,'key_35','He is leaning forward from sitting on the right bed edge, preparing to stand. Hips remain near(553,291), head around(586,217), both bare feet firmly on floor near(591,380), knees sharply bent, upper body pitched forward30degrees, hands press the mattress beside hips. Weight shifts over feet. Door stays closed.'),
(4.0,'key_40_revised','He is HALFWAY standing up off the right edge of the bed. Hips have lifted just above mattress, knees still bent about35degrees, bare feet firmly planted in floor aisle near(604,378), torso leaning slightly forward, head around(614,191). Hands have just released mattress; both arms hang low. Empty bed behind him. Door closed.'),
(4.5,'key_45','He now stands fully upright in the narrow aisle beside the bed, just in front of the foreground chair and ready to walk toward the rear-right door. Bare feet around(607,370), head around(618,165). Back/left three-quarter side toward camera, torso faces door. Left foot begins first small step toward door, right foot supports weight; arms begin gentle opposing swing. Bed empty, door closed.'),
(5.4,'key_54','He is walking away from the camera up the narrow aisle toward the rear-right closed bedroom door, BEHIND the foreground chair. Head around(641,146), hips around(640,266). LEFT foot planted forward toward door near(648,347), RIGHT heel lifted behind near(629,370), knees naturally bent. Right arm swings gently forward, left back; back/three-quarter side visible. No exaggerated running pose. Empty bed.'),
(6.3,'test_stand','Near door standing pose'),
(7.0,'key_70','He has arrived immediately in front of the CLOSED rear-right bedroom door and has stopped walking. Bare feet side by side near(660,331), head around(672,127), back/three-quarter side faces camera. Right elbow begins bending to lift hand toward the lever handle around(695,173), hand still15cm short of handle. Left arm hangs relaxed. Bed empty.'),
(8.0,'key_80','He stands before the CLOSED bedroom door, feet planted near(660,331), head around(671,124), torso facing door. His right hand now grips the metal lever handle at(695,174), elbow bent naturally and wrist aligned, starting to push the lever down. Left arm relaxed. Door has NOT swung open yet. Empty bed.'),
(8.8,'key_88','He is opening the bedroom door, now swung about35degrees around the ORIGINAL right-side hinges. Keep same single right-hinged door, beginning the same opening direction as the supplied later open-door reference. A narrow dark hallway gap with warm light appears. Man head near(684,124), feet near(657,328). His right hand remains on lever, arm follows moving handle, weight shifts forward with one small step. Bed empty. Do not change door to a second door or rehang it.'),
(9.5,'test_open','Open door final pose'),
(10.0,'test_open','Hold open door final pose')]

def mask_for(name,t):
 mask=Image.new('L',Image.open(REF).size,255);d=ImageDraw.Draw(mask)
 if t<2.1:d.polygon([(400,158),(603,156),(616,245),(568,333),(491,429),(417,426),(390,353)],fill=0)
 elif t<4.4:d.polygon([(517,153),(605,149),(639,243),(633,379),(580,420),(510,347)],fill=0)
 else:d.polygon([(515,95),(745,95),(760,345),(688,431),(575,432),(515,290)],fill=0)
 if t>8.0:d.polygon([(645,49),(813,60),(818,327),(680,352),(633,327)],fill=0)
 # exact foreground / lamp exclusion, copied unchanged by final compositing too
 d.polygon([(612,321),(648,318),(664,342),(674,376),(661,425),(634,435),(606,396)],fill=255)
 # Lamp stays in the source plate; allow the character to occlude it naturally.
 path=ROOT/'assets/2d'/f'mask_{name}.png';mask.save(path);return path

def run(tasks):
 waiting=list(tasks);active=[];completed=0
 while waiting or active:
  while waiting and len(active)<6:
   x=waiting.pop(0);name=x['name'];path=JOBS/(name+'.json')
   if path.exists():
    job=json.loads(path.read_text())
    if job['state']=='completed':completed+=1;continue
   else:job=submit(name,x['source'],x['prompt'],x['mask'],refs=x['refs'],quality=x.get('quality','medium'),seed=8311)
   active.append(name)
  for name in list(active):
   try:j=poll(name)
   except Exception as e:print('Poll retrieval error',name,type(e).__name__,str(e)[:250],flush=True);continue
   if j['state']=='completed':active.remove(name);completed+=1
   elif j['state']=='failed':
    attempts=len(list(JOBS.glob(name+'_failed_attempt_*.json')))
    if attempts>=2:raise RuntimeError('Repeated confirmed generation failure: '+name)
    (JOBS/(name+'.json')).rename(JOBS/(name+f'_failed_attempt_{attempts+1}.json'))
    active.remove(name);waiting.insert(0,next(x for x in tasks if x['name']==name));print('Retrying confirmed failed image',name,flush=True)
  print('PROGRESS',completed,'complete;',len(active),'inflight;',len(waiting),'remaining',flush=True)
  if active:time.sleep(8)

def key_tasks():
 tasks=[]
 for t,n,p in ANCHORS:
  if n in ('original','test_sit','test_stand','test_open'):continue
  # Late opening uses the successfully staged open door drawing as an extra reference.
  refs=[REF]+([ROOT/'output/2d/keys/test_open.png'] if t>8 else [])
  tasks.append({'name':n,'source':PLATE,'mask':mask_for(n,t),'prompt':COMMON+p,'refs':refs,'quality':'high'})
 return tasks

def sample_pose(t):
 if t<1.8:return f'Sitting-up phase, {100*(t-1.0)/.8:.0f}% of the curl from reclining to a45degree raised torso. Gradually lower raised arm, bend knees and curl torso upward; hips stay on bed. Do NOT jump straight to upright. '
 if t<3:return f'Leg swing phase, {100*(t-1.8)/1.2:.0f}% from partially raised torso to sitting on right edge with feet on floor. Torso becomes upright, hips rotate toward aisle, bent knees swing over edge, feet descend gradually. '
 if t<4.5:return f'Stand-up phase, {100*(t-3)/1.5:.0f}% from seated to fully standing. Feet remain planted, lean chest forward first, lift hips and gradually straighten knees. '
 if t<7:
  u=(t-4.5)/2.5;cx=610+55*u;heady=162-36*u;fy=371-39*u;phase=(t-4.5)*2.1;cycle=phase%1
  foot='LEFT foot forward planted toward door, RIGHT foot behind lifting heel' if cycle<.5 else 'RIGHT foot forward planted toward door, LEFT foot behind lifting heel'
  lift='Passing pose: rear knee comes through under hip, lifted foot just off floor' if .18<cycle<.32 or .68<cycle<.82 else 'Small grounded walking stride, feet separated naturally fore-aft'
  return f'Walking frame at image head center({cx:.0f},{heady:.0f}) and foot base({cx:.0f},{fy:.0f}). He faces the door and walks AWAY from camera behind chair. {foot}. {lift}. Arms swing opposite legs. This exact position matters; neither seated nor already at handle. Door CLOSED. '
 if t<8:return f'Reach phase, {100*(t-7):.0f}%: stop at closed door, gradually raise right forearm and extend hand to lever without moving the feet. Door CLOSED. '
 return f'Door opening phase, {min(70,70*(t-8)/1.5):.0f}degrees open toward the SAME direction as the later reference drawing. Hand follows metal handle of the single original right-hinged door; one small step toward threshold, increasing warm hallway gap. '

def frame_tasks():
 tasks=[];timeline=[]
 for i in range(120):
  t=i/12
  if t<1:timeline.append({'frame':i+1,'time':t,'image':str(REF),'mask':None});continue
  if t>=9.5:timeline.append({'frame':i+1,'time':t,'image':str(ROOT/'output/2d/keys/test_open.png'),'mask':str(mask_for('final',9.5))});continue
  lower=max((x for x in ANCHORS if x[0]<=t),key=lambda x:x[0]);upper=min((x for x in ANCHORS if x[0]>=t),key=lambda x:x[0])
  name=f'drawing_{i+1:03d}';mask=mask_for(name,t)
  def refpath(x):return REF if x[1]=='original' else ROOT/'output/2d/keys'/f'{x[1]}.png'
  a,b=refpath(lower),refpath(upper)
  fraction=0 if upper[0]==lower[0] else (t-lower[0])/(upper[0]-lower[0])
  prompt=COMMON+f'The source already shows the SAME man in the earlier pose. Reposition and redraw him a SMALL amount farther along the motion, {fraction*100:.0f}% toward this next key pose: '+upper[2]+'. Do not leave him in the unchanged source pose and do not duplicate his old body. Restore the bed/floor where his body previously was. '+sample_pose(t)+'Match the neighboring key drawings closely, with small natural changes in joint pose. Keep the detailed background fixed and bed empty wherever not occupied by him.'
  tasks.append({'name':name,'source':a,'mask':mask,'prompt':prompt,'refs':[REF]})
  timeline.append({'frame':i+1,'time':t,'image':str(ROOT/'output/2d/keys'/f'{name}.png'),'mask':str(mask)})
 (ROOT/'output/2d/timeline.json').write_text(json.dumps(timeline,indent=2));return tasks
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--keys',action='store_true');p.add_argument('--frames',action='store_true');args=p.parse_args()
 if args.keys:run(key_tasks())
 elif args.frames:run(frame_tasks())
