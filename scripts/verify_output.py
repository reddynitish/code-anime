"""Verify the actual encoded deliverable, rendered sequence, and reach envelope."""
import json, subprocess
from pathlib import Path
root=Path(__file__).resolve().parent.parent
clip=root/'output/bedroom_10s.mp4'
raw=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_name,width,height,r_frame_rate,nb_frames','-of','json',str(clip)],text=True)
info=json.loads(raw);v=next(s for s in info['streams'] if s['codec_name']=='h264')
assert abs(float(info['format']['duration'])-10)<.01,info
assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_frames']))==(1280,720,'24/1',240),v
frames=sorted((root/'output/frames').glob('frame_*.png'))
assert len(frames)==120,len(frames)
assert [p.name for p in frames]==[f'frame_{i:04d}.png' for i in range(1,121)]
motion=json.loads((root/'output/motion_checks.json').read_text())
assert motion['right_arm_reach_max']<=.58,motion
assert abs(motion['door_open_degrees']+78)<.01,motion
subprocess.run(['ffmpeg','-v','error','-i',str(clip),'-f','null','-'],check=True)
report={'duration_seconds':10,'resolution':[1280,720],'fps':24,'encoded_frames':240,'unique_rendered_frames':120,'full_decode':'passed','right_arm_reach_m':motion['right_arm_reach_max'],'arm_reach_limit_m':.58,'door_open_degrees':78}
(root/'output/verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
