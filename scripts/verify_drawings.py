import json,subprocess,hashlib
from pathlib import Path
from PIL import Image
from luminal_images import ROOT
out=ROOT/'output/2d';clip=out/'anime_door_10s.mp4';frames=sorted((out/'frames').glob('frame_*.png'))
assert len(frames)==120,len(frames)
for i,p in enumerate(frames,1):
 assert p.name==f'frame_{i:04d}.png';im=Image.open(p);im.verify()
r=subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_entries','format=duration:stream=codec_name,width,height,r_frame_rate,nb_read_frames','-of','json',str(clip)],text=True)
d=json.loads(r);v=d['streams'][0]
assert float(d['format']['duration'])==10,d
assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_read_frames']))==(1024,572,'24/1',240),v
subprocess.run(['ffmpeg','-v','error','-i',str(clip),'-f','null','-'],check=True)
unique=len({hashlib.sha256(p.read_bytes()).hexdigest() for p in frames})
report={'duration_seconds':10,'resolution':[1024,572],'video_fps':24,'video_frames':240,'drawing_exposure_frames':120,'distinct_composited_images':unique,'full_decode':'passed','production':'Luminal image edits; local Python compositing and FFmpeg encoding; no video generation'}
(out/'verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
