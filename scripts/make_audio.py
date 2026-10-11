"""Procedural room tone, footfalls and door sounds. No external audio assets."""
import math, random, wave, struct
from pathlib import Path
random.seed(11)
rate=48000;duration=10;audio=[0.0]*(rate*duration)
for i in range(len(audio)):
 t=i/rate;audio[i]=.003*random.uniform(-1,1)+.002*math.sin(2*math.pi*70*t)
def sound(start,duration,kind):
 previous=0
 for j in range(int(duration*rate)):
  i=int(start*rate)+j
  if i>=len(audio):break
  t=j/rate;noise=random.uniform(-1,1);previous=.8*previous+.2*noise
  if kind=='step':v=(.045*previous+.032*math.sin(2*math.pi*115*t))*math.exp(-t*28)
  elif kind=='cloth':v=.014*previous*math.sin(math.pi*t/duration)**2
  elif kind=='latch':v=.055*noise*math.exp(-t*90)
  else:v=.009*(math.sin(2*math.pi*(230+25*math.sin(t*8))*t)+previous)*math.sin(math.pi*t/duration)
  audio[i]+=v
sound(1.15,1.5,'cloth');sound(3.4,.25,'step')
for t in(4.5,5.14,5.78,6.42,7.05,8.42,8.9):sound(t,.25,'step')
sound(8.0,.12,'latch');sound(8.08,1.35,'creak')
out=Path(__file__).resolve().parent.parent/'output/room_audio.wav'
with wave.open(str(out),'w') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
 w.writeframes(b''.join(struct.pack('<h',int(max(-1,min(1,s))*32767)) for s in audio))
print(out)
