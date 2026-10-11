from pathlib import Path
from PIL import Image,ImageDraw
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from luminal_images import submit,ROOT
source=ROOT/'assets/2d/reference.png'
im=Image.open(source);w,h=im.size
mask=Image.new('L',(w,h),255);d=ImageDraw.Draw(mask)
d.polygon([(385,160),(604,148),(639,122),(696,115),(740,164),(736,331),(661,404),(585,434),(414,430),(377,323)],fill=0)
# Protect the foreground chair; moving character must pass behind it.
d.polygon([(614,321),(648,318),(664,342),(674,376),(661,425),(634,435),(606,396)],fill=255)
mask.save(ROOT/'assets/2d/action_mask.png')
openmask=mask.copy();d=ImageDraw.Draw(openmask)
d.polygon([(658,59),(801,68),(781,298),(657,310)],fill=0)
openmask.save(ROOT/'assets/2d/door_mask.png')
COMMON='Edit this single anime animation drawing. Keep the exact same fixed exterior window camera, 2D hand-drawn anime linework, detailed painted background, cool blue night colors, warm bedside light and perspective. Keep the young man exactly the same person: short messy black hair, gray loose short-sleeved T-shirt, charcoal-gray pants, bare feet, slim natural human anatomy. There is ONLY ONE man. Move him out of his old pose, restoring the empty bed and pillow where he previously lay. No duplicate or ghost person. Do not change window, walls, posters, desk, chair, lamp or other furniture. No 3D rendering, no simplified shapes, no text. '
TESTS={
 'test_sit': 'He is now sitting upright on the RIGHT long edge of the bed nearest the narrow aisle, around the middle of the mattress. His hips are on the mattress edge around image pixel (548,292), head around(550,198), torso upright, knees bent and bare feet lowered to the floor around(584,365). He faces the rear-right bedroom door. Both hands lightly brace the mattress beside hips. The bedding is rumpled underneath him. Draw this exact single seated pose naturally in the source anime style. Keep the bedroom door CLOSED.',
 'test_stand':'He has got out of bed and now stands in the narrow floor aisle on the right of the bed, BEHIND the foreground chair, near the headboard end. Bare feet planted around pixel(630,347), head around(635,150). His back and left three-quarter side face the camera; he faces the CLOSED bedroom door. Arms hang naturally, body weight on both feet. The bed is now completely empty. Keep the man naturally scaled to the room and preserve his exact design.',
 'test_open':'He is standing in the aisle directly before the rear-right bedroom doorway. Bare feet around pixel(652,320), head around(663,126). He faces into the doorway, back/three-quarter side toward the camera. His right hand holds the metal lever handle. The bedroom door is swung visibly OPEN about70degrees INTO the hallway, revealing a dark warmly edged hallway opening. The hinges remain on the right jamb of the original door and the leaf pivots around them. No second door or impossible geometry. He has just opened the door and pauses at the threshold. The bed is empty. Preserve source anime details and all foreground furniture.'}
if __name__=='__main__':
 for name,pose in TESTS.items():submit(name,source,COMMON+pose,ROOT/'assets/2d/door_mask.png' if name=='test_open' else ROOT/'assets/2d/action_mask.png',refs=[source],quality='high')
