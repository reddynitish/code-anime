from pathlib import Path
from PIL import Image,ImageDraw
from luminal_images import ROOT,submit
from draw_sequence import mask_for
# Code-drawn 2D pose block-ins: no 3D geometry and no finished-frame substitution.
poses={
 'guide_curl':{'head':(533,208),'neck':(525,231),'hips':(483,287),'shoulders':[(509,233),(537,229)],'elbows':[(477,260),(557,250)],'hands':[(456,280),(536,281)],'knees':[(435,294),(477,337)],'ankles':[(420,356),(450,392)]},
 'guide_walk':{'head':(637,159),'neck':(638,180),'hips':(635,269),'shoulders':[(623,181),(653,181)],'elbows':[(611,222),(665,213)],'hands':[(621,253),(678,230)],'knees':[(626,304),(650,304)],'ankles':[(613,365),(655,348)]},
}
for name,p in poses.items():
 im=Image.open(ROOT/'output/2d/keys/clean_plate.png').convert('RGB');d=ImageDraw.Draw(im)
 hips=p['hips'];neck=p['neck'];should=p['shoulders']
 d.polygon([should[0],should[1],(hips[0]+14,hips[1]),(hips[0]-14,hips[1])],fill=(100,106,121),outline=(35,39,54))
 for side in range(2):
  a=(hips[0]+(-10 if side==0 else 10),hips[1]);k=p['knees'][side];f=p['ankles'][side]
  d.line([a,k,f],fill=(64,72,87),width=17)
  d.line([should[side],p['elbows'][side]],fill=(100,106,121),width=14)
  d.line([p['elbows'][side],p['hands'][side]],fill=(185,164,152),width=10)
  x,y=f;d.ellipse((x-7,y-3,x+7,y+5),fill=(185,164,152))
 x,y=p['head'];d.line([neck,p['head']],fill=(185,164,152),width=10);d.ellipse((x-12,y-17,x+12,y+15),fill=(185,164,152));d.ellipse((x-14,y-21,x+14,y-2),fill=(27,30,40))
 path=ROOT/'assets/2d'/f'{name}.png';im.save(path)
 t=1.6 if name=='guide_curl' else 5.5
 submit(name,path,'Replace ONLY the rough flat-color human pose block-in with a finished detailed 2D anime drawing of the SAME young man from the reference image. The source block-in is an exact POSE AND POSITION GUIDE: keep head center, torso angle, hip center, elbow positions, knee positions and ankle positions exactly where drawn. Do not move him to a different place, do not return the reclining reference pose. Refine natural anatomy around those exact joints; short messy BLACK hair, gray loose tee, charcoal-gray pants, bare feet. Draw rich anime ink linework, clothing folds and soft night shadows matching the reference. Completely replace flat crude sketch shapes with the polished anime man; no guide lines left. Keep the entire bedroom, window, chair, desk, lamp and closed door pixel-identical. One man only.',mask_for(name,t),refs=[ROOT/'assets/2d/reference.png'],quality='high')
