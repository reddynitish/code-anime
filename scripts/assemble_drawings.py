"""Composite frozen background/foreground and assemble drawings locally."""
import json,subprocess
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parent.parent
plate=Image.open(ROOT/'output/2d/keys/clean_plate.png').convert('RGB')
out=ROOT/'output/2d/frames';out.mkdir(exist_ok=True)
rows=json.loads((ROOT/'output/2d/timeline.json').read_text())
for row in rows:
 image=Image.open(row['image']).convert('RGB')
 assert image.size==plate.size,(row['image'],image.size)
 if row['mask']:
  allowed=ImageOps.invert(Image.open(row['mask']).convert('L'))
  image=Image.composite(image,plate,allowed)
 # Once he is walking, restore the now-empty mattress. Some image edits
 # preserve a second copy of the resting character inside their editable area.
 if row['time']>=4.5:
  bed_mask=Image.new('L',plate.size,0)
  ImageDraw.Draw(bed_mask).polygon([(397,157),(585,157),(590,256),(553,370),(498,434),(399,413),(376,332)],fill=255)
  image=Image.composite(plate,image,bed_mask)
 image.save(out/f"frame_{row['frame']:04d}.png")
cmd=['ffmpeg','-y','-framerate','12','-i',str(out/'frame_%04d.png'),'-vf','fps=24','-c:v','libx264','-crf','16','-pix_fmt','yuv420p','-t','10','-movflags','+faststart',str(ROOT/'output/2d/anime_door_10s.mp4')]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
# Indexed overview for visual review, including early and final action.
contact=Image.new('RGB',(512*4,286*3),'#11151b');d=ImageDraw.Draw(contact)
for j,i in enumerate([1,15,22,30,37,43,49,60,73,85,103,115]):
 im=Image.open(out/f'frame_{i:04d}.png').resize((512,286));contact.paste(im,((j%4)*512,(j//4)*286));d.text(((j%4)*512+8,(j//4)*286+8),f'{(i-1)/12:.2f}s',fill='white',stroke_width=2,stroke_fill='black')
contact.save(ROOT/'output/2d/contact_sheet.jpg',quality=95)
print(ROOT/'output/2d/anime_door_10s.mp4')
