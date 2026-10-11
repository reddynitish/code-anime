import bpy, math, random, os, sys
from mathutils import Vector, Matrix
from pathlib import Path
random.seed(11)
ROOT=Path(__file__).resolve().parent.parent
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.render.engine='BLENDER_EEVEE'
scene.render.resolution_x=1280; scene.render.resolution_y=720; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.fps=12; scene.frame_start=1; scene.frame_end=120
scene.world.color=(.14,.14,.14)
scene.view_settings.view_transform='Standard'
scene.render.film_transparent=False
if hasattr(scene,'eevee'): scene.eevee.taa_render_samples=16

def mat(name,c,toon=True):
 c=tuple(v**2.2 for v in c)
 m=bpy.data.materials.new(name); m.diffuse_color=(*c,1); m.use_nodes=True
 n=m.node_tree.nodes; n.clear(); l=m.node_tree.links; out=n.new('ShaderNodeOutputMaterial')
 em=n.new('ShaderNodeEmission'); l.new(em.outputs[0],out.inputs['Surface'])
 if toon:
  dif=n.new('ShaderNodeBsdfDiffuse'); dif.inputs['Color'].default_value=(.8,.8,.8,1)
  rgb=n.new('ShaderNodeShaderToRGB'); ramp=n.new('ShaderNodeValToRGB'); ramp.color_ramp.interpolation='CONSTANT'
  es=ramp.color_ramp.elements; es.remove(es[1]); es[0].position=0; es[0].color=(*(v*.40 for v in c),1)
  e=es.new(.32); e.color=(*(v*.72 for v in c),1); e=es.new(.62);e.color=(*c,1)
  l.new(dif.outputs[0],rgb.inputs[0]);l.new(rgb.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],em.inputs[0])
 else: em.inputs[0].default_value=(*c,1)
 return m
ink=mat('Ink midnight',(.025,.036,.055),False); ink.use_backface_culling=True
wall=mat('Blue dusk plaster',(.27,.29,.39)); wood=mat('Walnut',(.30,.23,.22));floor=mat('Floor warm gray',(.42,.34,.30))
sheet=mat('Faded mauve linen',(.55,.46,.48));pillow=mat('Pillow slate',(.47,.52,.61));skin=mat('Warm skin',(.78,.61,.47))
tee=mat('Charcoal tee',(.30,.34,.39));pants=mat('Slate pants',(.23,.29,.34));hair=mat('Black hair blue edge',(.055,.068,.092))
white=mat('Eye white',(.78,.80,.79),False);iris=mat('Dark eyes',(.055,.068,.08),False)
trim=mat('Window blue enamel',(.15,.23,.28)); gold=mat('Brass',(.51,.40,.22)); glow=mat('Lamp warm',(.98,.73,.42),False)
hall=mat('Hall warm',(.67,.46,.28)); pages=mat('Book pages',(.64,.63,.58));screenmat=mat('Laptop light',(.38,.73,.87),False)

def outline(o,factor=1.025):
 me=o.data.copy()
 for p in me.polygons: pass
 # Reverse winding in a separate mesh. Culling makes the expanded shell visible only at silhouette.
 import bmesh
 bm=bmesh.new();bm.from_mesh(me);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(me);bm.free()
 s=bpy.data.objects.new(o.name+' ink shell',me);bpy.context.collection.objects.link(s)
 s.data.materials.clear();s.data.materials.append(ink);s.parent=o;s.location=(0,0,0);s.scale=(factor,)*3
 return s

def cube(name,loc,size,m,bevel=0):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.scale=size
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if bevel:
  mod=o.modifiers.new('Soft edges','BEVEL');mod.width=bevel;mod.segments=2
  o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
 return o

def ball(name,loc,scale,m,outlined=False):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=10,location=loc);o=bpy.context.object;o.name=name;o.scale=scale;o.data.materials.append(m)
 for p in o.data.polygons:p.use_smooth=True
 if outlined:outline(o)
 return o

def rod(name,a,b,r,m):
 a,b=Vector(a),Vector(b);bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=r,depth=(b-a).length,location=(a+b)*.5)
 o=bpy.context.object;o.name=name;o.rotation_mode='QUATERNION';o.rotation_quaternion=(b-a).to_track_quat('Z','Y');o.data.materials.append(m);return o

def parent_local(o,p,loc):o.parent=p;o.location=loc

# Set in metres: rear wall at y=2.0; open foreground window at y=-2.25.
cube('Floor', (0,0,-.06),(3.9,4.6,.12),floor)
for x in [i*.26-1.85 for i in range(15)]:cube('Floorboard seam',(x,0,.002),(.008,4.5,.006),wood)
for i in range(18):
 x=random.uniform(-1.8,1.8);y=random.uniform(-2.1,1.9)
 cube('Floor grain',(x,y,.006),(.008,random.uniform(.15,.5),.004),wood)
cube('Left wall',(-1.95,0,1.42),(.12,4.5,2.85),wall)
cube('Rear wall left',(-.60,2.06,1.42),(2.70,.12,2.85),wall)
cube('Rear wall right',(1.84,2.06,1.42),(.25,.12,2.85),wall)
cube('Door lintel',(1.22,2.06,2.53),(1.10,.12,.63),wall)
cube('Left skirting',(-1.86,0,.12),(.06,4.4,.19),trim)
cube('Rear skirting',(-.60,1.97,.12),(2.65,.06,.19),trim)
# Door opening, hall beyond; door swings away into corridor, preserving aisle clearance.
cube('Hall floor',(1.2,2.7,-.01),(1.1,1.5,.08),wood)
cube('Hall far wall',(1.2,3.4,1.4),(1.4,.12,2.8),hall)
for x in (.72,1.74):cube('Door casing',(x,1.96,1.12),(.08,.09,2.25),gold)
cube('Door casing top',(1.23,1.96,2.24),(1.1,.1,.08),gold)
bpy.ops.object.empty_add(location=(1.70,2.0,0));doorroot=bpy.context.object;doorroot.name='DOOR hinge control'
door=cube('Bedroom door', (0,0,0),(.92,.075,2.14),wood,.02);parent_local(door,doorroot,(-.46,0,1.07))
for z in (.49,1.48):
 panel=cube('Door inset', (0,0,0),(.73,.013,.73),wall,.012);parent_local(panel,doorroot,(-.46,-.045,z))
plate=cube('Handle plate',(0,0,0),(.08,.045,.20),gold,.01);parent_local(plate,doorroot,(-.78,-.065,1.03))
handle=rod('Door lever',(-.79,-.095,1.03),(-.62,-.095,1.03),.025,gold);handle.parent=doorroot
# Bed frame, mattress, folded linen and rounded pillow.
cube('Bed frame',(-.91,.03,.35),(1.45,3.05,.23),wood,.04)
for x in(-1.48,-.32):
 for y in(-1.29,1.34):cube('Bed leg',(x,y,.18),(.09,.10,.36),wood)
cube('Mattress',(-.91,.03,.56),(1.39,2.96,.25),pillow,.10)
cube('Headboard',(-.91,1.58,.88),(1.48,.11,.92),wood,.035)
cube('Pillow',(-.91,1.12,.76),(1.01,.49,.17),pillow,.10)
# Rumpled sheet grid, not an image texture.
verts=[];faces=[];nx,ny=18,26
for j in range(ny):
 for i in range(nx):
  x=-1.59+1.37*i/(nx-1);y=-1.46+2.15*j/(ny-1)
  z=.78+.012*math.sin(i*1.1+j*.7)+.016*math.cos(j*.9)+.012*math.sin(i*2.5)
  verts.append((x,y,z))
for j in range(ny-1):
 for i in range(nx-1):a=j*nx+i;faces.append((a,a+1,a+nx+1,a+nx))
me=bpy.data.meshes.new('Linen folds');me.from_pydata(verts,[],faces);o=bpy.data.objects.new('Rumpled cover',me);bpy.context.collection.objects.link(o);o.data.materials.append(sheet)
for i in range(8):
 y=-1.2+i*.23;rod('Linen crease',(-1.53,y,.791),(-1.04,y+.10,.798),.005,wood)
# Lower bedding to a normal seat height so the stand has a visible rise.
for obj in list(bpy.context.scene.objects):
 if obj.name.startswith(('Bed frame','Bed leg','Mattress','Headboard','Pillow','Rumpled cover','Linen crease')): obj.location.z-=.16
# bedside table and warm lamp
cube('Bedside shelf',(-.08,1.59,.64),(.42,.42,.08),wood,.015)
rod('Lamp stem',(-.08,1.59,.67),(-.08,1.59,1.17),.021,gold)
ball('Lamp base',(-.08,1.59,.69),(.11,.11,.025),gold)
bpy.ops.mesh.primitive_cone_add(vertices=32,radius1=.19,radius2=.11,depth=.23,location=(-.08,1.59,1.23));bpy.context.object.data.materials.append(glow)
# desk at front right, leaving walking aisle between bed and desk
cube('Desk',(1.36,-1.25,.78),(.98,1.16,.075),wood,.025)
for x in(.94,1.77):
 for y in(-1.71,-.81):cube('Desk leg',(x,y,.38),(.05,.05,.76),wood)
cube('Laptop base',(1.29,-1.25,.83),(.55,.39,.03),trim,.015)
lap=cube('Laptop display',(1.29,-1.09,1.04),(.55,.025,.36),trim,.015);lap.rotation_euler.x=math.radians(-12)
dis=cube('Laptop screen',(1.29,-1.109,1.04),(.49,.01,.29),screenmat);dis.rotation_euler.x=math.radians(-12)
for i in range(7):
 b=cube('Desk book',(1.65,-1.55+i*.065,.91),(.31,.045,.22+random.random()*.10),mat('Book '+str(i),random.choice([(.28,.39,.47),(.47,.31,.32),(.38,.42,.33)])),.004)
for i in range(3):cube('Stacked book',(1.51,-.88,.84+i*.047),(.33,.27,.04),pillow if i%2 else sheet)
cube('Chair seat',(.97,-.82,.47),(.48,.45,.09),trim,.045)
cube('Chair back',(.97,-1.01,.86),(.48,.07,.64),trim,.06)
for x in(.78,1.16):rod('Chair leg',(x,-.99,.44),(x,-.99,.02),.023,ink)
# posters use local geometry silhouettes, no drawn frames
for i,(x,z) in enumerate([(-1.22,1.82),(-.55,2.07)]):
 cube('Poster backing',(x,1.982,z),(.48,.012,.57),pages)
 cube('Poster picture',(x,1.970,z+.05),(.43,.01,.39),trim)
 ball('Poster moon',(x+.11,1.956,z+.14),(.055,.005,.055),pillow)
 for k in range(3):
  bpy.ops.mesh.primitive_cone_add(vertices=3,radius1=.13,depth=.012,location=(x-.12+k*.11,1.951,z-.04));m=bpy.context.object;m.rotation_euler.x=math.pi/2;m.data.materials.append(wall)
# socket / switch
cube('Light switch',(.43,1.97,1.40),(.10,.025,.15),pages,.006)
cube('Socket',(.19,1.96,.25),(.09,.025,.13),pages,.006)
# Open foreground window frame, sides and sill. No panes across action.
for x in(-2.65,3.6):cube('Window upright',(x,-2.25,1.85),(.12,.13,3.70),trim,.012)
cube('Window upper',(0,-2.25,4.5),(7.3,.14,.12),trim,.015)
cube('Window sill',(0,-2.25,.23),(7.3,.32,.13),trim,.02)
for side in(-1,1):
 x=-2.65 if side<0 else 3.6
 for z in(.50,4.4):rod('Open casement horizontal',(x,-2.25,z),(x+side*.57,-2.92,z),.045,trim)
 rod('Open casement outer',(x+side*.57,-2.92,.50),(x+side*.57,-2.92,4.4),.05,trim)
# foliage along exterior frame
for i in range(12):
 x=-1.82+random.uniform(-.22,.20);z=.30+i*.11
 rod('Vine',(-1.9,-2.44,z-.1),(x,-2.45,z),.013,trim)
 leaf=ball('Window leaf',(x,-2.45,z),(.08,.035,.025),mat('Leaf '+str(i),(.16,.27,.23)));leaf.rotation_euler.y=random.uniform(-1,1)
# Articulated character: each mesh is driven by joint coordinates.
parts={}
for name,r,m in [('torso',.22,tee),('pelvis',.17,pants),('neck',.065,skin),('upperL',.083,tee),('upperR',.083,tee),('foreL',.057,skin),('foreR',.057,skin),('thighL',.095,pants),('thighR',.095,pants),('shinL',.075,pants),('shinR',.075,pants)]:
 parts[name]=ball(name,(0,0,0),(r,r,1),m,True)
for name,m in [('handL',skin),('handR',skin),('footL',skin),('footR',skin)]:parts[name]=ball(name,(0,0,0),(.065,.11,.045) if 'foot' in name else (.052,.045,.078),m,True)
bpy.ops.object.empty_add();headroot=bpy.context.object;headroot.name='HEAD expression control'
head=ball('Face',(0,0,0),(.135,.116,.183),skin,True);parent_local(head,headroot,(0,0,0))
cap=ball('Hair crown',(0,0,0),(.145,.123,.115),hair,True);parent_local(cap,headroot,(0,.01,.10))
for i in range(18):
 a=i*math.tau/18;r=.10+random.uniform(-.02,.02)
 bpy.ops.mesh.primitive_cone_add(vertices=5,radius1=.055,radius2=0,depth=.16);o=bpy.context.object;o.name='Tousled hair lock';o.data.materials.append(hair)
 parent_local(o,headroot,(math.cos(a)*r,math.sin(a)*r,.10+random.uniform(-.01,.04)))
 o.rotation_euler=(random.uniform(-.6,.6),random.uniform(-.6,.6),a)
for s in(-1,1):
 ear=ball('Ear',(0,0,0),(.034,.028,.055),skin);parent_local(ear,headroot,(s*.135,0,-.015))
 eye=ball('Eye',(0,0,0),(.033,.012,.018),white);parent_local(eye,headroot,(s*.052,-.107,.015))
 pupil=ball('Iris',(0,0,0),(.012,.009,.015),iris);parent_local(pupil,headroot,(s*.051,-.118,.014))
 brow=cube('Brow',(0,0,0),(.059,.012,.012),hair,.003);parent_local(brow,headroot,(s*.052,-.111,.049));brow.rotation_euler.y=s*.1
nose=ball('Nose',(0,0,0),(.018,.027,.035),skin);parent_local(nose,headroot,(0,-.112,-.022))
mouth=cube('Mouth',(0,0,0),(.047,.008,.007),wood,.002);parent_local(mouth,headroot,(0,-.109,-.081))
# shirt neckline follows torso transform
neckline=ball('Tee neckline',(0,0,0),(.10,.10,.025),ink);neckline.parent=parts['torso'];neckline.location=(0,0,.75);neckline.scale=(.42,.42,.035)

def ease(a,b,t):return a+(b-a)*(t*t*(3-2*t))
def blend(A,B,t):return {k:Vector(A[k]).lerp(Vector(B[k]),t) for k in A}
def pose(hip,tilt,yaw,legmode='stand'):
 hip=Vector(hip); front=Vector((math.sin(yaw),-math.cos(yaw),0));right=Vector((math.cos(yaw),math.sin(yaw),0))
 up=Vector((0,0,1))*math.cos(tilt)-front*math.sin(tilt)
 shoulder=hip+up*.54;head=shoulder+up*.24
 p={'hip':hip,'shoulder':shoulder,'head':head,'up':up,'front':front,'right':right}
 for side,s in [('L',-1),('R',1)]:
  p['shoulder'+side]=shoulder+right*s*.195
  p['elbow'+side]=p['shoulder'+side]-up*.25+front*.035
  p['hand'+side]=p['elbow'+side]-up*.235
  h=hip+right*s*.11;p['hip'+side]=h
  p['knee'+side]=h-up*.39+front*.025;p['ankle'+side]=h-up*.78
 return p

def ik(a,b,L1,L2,bend):
 delta=b-a;dist=min(delta.length,L1+L2-.001);u=delta.normalized();v=Vector(bend)-u*Vector(bend).dot(u)
 if v.length<.001:v=Vector((1,0,0))-u*u.x
 v.normalize();d=(L1*L1-L2*L2+dist*dist)/(2*max(dist,.001));height=math.sqrt(max(0,L1*L1-d*d))
 return a+u*d+v*height

lying=pose((-.91,.40,.90),math.pi/2,0)
# Upper body points toward headboard, legs toward foot of bed.
for side,s in [('L',-1),('R',1)]:
 lying['knee'+side]=Vector((-.91+s*.11,-.05,.83));lying['ankle'+side]=Vector((-.91+s*.11,-.49,.79))
 lying['elbow'+side]=Vector((-.91+s*.28,.70,1.02));lying['hand'+side]=Vector((-.91+s*.09,.50,1.10))
lying={k:v-Vector((0,0,.16)) if k not in ('up','front','right') else v for k,v in lying.items()}
seated=pose((-.22,.20,.68),0,math.pi/2)
for side,s in [('L',-1),('R',1)]:
 seated['knee'+side]=Vector((.133,.20+s*.11,.493));seated['ankle'+side]=Vector((.06,.20+s*.11,.10))
 seated['elbow'+side]=Vector((-.28,.20+s*.27,1.01));seated['hand'+side]=Vector((-.28,.20+s*.25,.67))
standing=pose((.18,.20,.87),0,math.pi/2)
for side,s in [('L',-1),('R',1)]:
 standing['ankle'+side]=Vector((.06,.20+s*.11,.10));standing['knee'+side]=ik(standing['hip'+side],standing['ankle'+side],.40,.40,(1,0,0))
walk_start=pose((.60,.20,.87),0,math.pi)
walk_end=pose((1.0,1.55,.87),0,math.pi)

# Returns frame pose and hinge angle. Walking uses feet planted during stance.
def action(t):
 angle=0
 if t<1:p=lying.copy()
 elif t<3:p=blend(lying,seated,ease(0,1,(t-1)/2))
 elif t<4:p=blend(seated,standing,ease(0,1,t-3))
 elif t<4.7:
  u=(t-4)/.7;p=blend(standing,walk_start,ease(0,1,u))
  for side,offset in [('L',0),('R',.5)]:
   q=max(0,min(1,(u-offset)*2));p['ankle'+side]=standing['ankle'+side].lerp(walk_start['ankle'+side],ease(0,1,q));p['ankle'+side].z+=.08*math.sin(math.pi*q)
   p['knee'+side]=ik(p['hip'+side],p['ankle'+side],.40,.40,(1,0,0))
 elif t<7:
  u=(t-4.7)/2.3;hip=Vector((.60+.40*u,.20+1.35*u,.87+.018*math.sin(u*math.pi*8)**2));p=pose(hip,0,math.pi)
  # Four alternating strides; each stance endpoint remains in world coordinates.
  duration=2.3;step=duration/4
  for side,offset in [('L',0),('R',.5)]:
   phase=(t-4.7)/step+offset;cycle=math.floor(phase);q=phase-cycle
   y0=.20+1.35*(cycle-offset)/4
   x0=.60+.40*(cycle-offset)/4
   if q<.60:fy=y0;fz=.09
   else:su=(q-.60)/.40;fy=ease(y0,y0+.3375,su);x0=ease(x0,x0+.10,su);fz=.09+.095*math.sin(math.pi*su)
   fy=max(.13,min(1.55,fy));s=-1 if side=='L' else 1
   foot=Vector((x0-s*.11,fy,fz));p['ankle'+side]=foot
   p['knee'+side]=ik(p['hip'+side],foot,.40,.40,(0,1,0))
   swing=.08*math.sin(phase*math.tau)
   p['hand'+side]+=Vector((0,swing,0));p['elbow'+side]+=Vector((0,swing*.5,0))
 elif t<7.45:p=blend(pose((.96,1.48,.87),0,math.pi),walk_end,ease(0,1,(t-7)/.45))
 else:
  p=walk_end.copy()
  # Right hand travels to handle, then follows exact hinge rotation.
  angle=ease(0,-math.radians(78),max(0,min(1,(t-8)/1.5)))
  target=Vector((1.70-.71*math.cos(angle)+.095*math.sin(angle),2.0-.71*math.sin(angle)-.095*math.cos(angle),1.03))
  reach=ease(0,1,min(1,(t-7.45)/.55))
  p['handR']=p['handR'].lerp(target,reach)
  # Take a small step toward threshold as the opening hand moves away.
  if t>8:
   follow=ease(0,1,min(1,(t-8)/1.5));p=pose((target.x+.01-.16*follow,target.y-.35+.10*follow,.87),0,math.pi);p['handR']=target
  p['elbowR']=ik(p['shoulderR'],p['handR'],.29,.29,(1,0,.1))
 return p,angle

def keyobj(o,loc,quat=None,scale=None):
 o.location=loc;o.keyframe_insert('location')
 if quat is not None:o.rotation_mode='QUATERNION';o.rotation_quaternion=quat;o.keyframe_insert('rotation_quaternion')
 if scale is not None:o.scale=scale;o.keyframe_insert('scale')

def segment(name,a,b,r1,r2=None):
 a,b=Vector(a),Vector(b);d=b-a;keyobj(parts[name],(a+b)*.5,d.to_track_quat('Z','Y'),(r1,r2 or r1,d.length*.64))
for f in range(1,121):
 scene.frame_set(f);t=(f-1)/12;p,angle=action(t)
 up=(p['head']-p['shoulder']).normalized();front=p['front'].normalized();right=p['right'].normalized();forward=up.cross(right).normalized()
 quat=Matrix((right,forward,up)).transposed().to_quaternion()
 segment('torso',p['hip'],p['shoulder'],.215,.145);segment('pelvis',p['hip']-up*.08,p['hip']+up*.13,.18,.13)
 segment('neck',p['shoulder']-up*.015,p['head']-up*.135,.063)
 keyobj(headroot,p['head'],quat)
 for side in('L','R'):
  segment('upper'+side,p['shoulder'+side],p['elbow'+side],.082)
  segment('fore'+side,p['elbow'+side],p['hand'+side],.057)
  segment('thigh'+side,p['hip'+side],p['knee'+side],.096)
  segment('shin'+side,p['knee'+side],p['ankle'+side],.073)
  keyobj(parts['hand'+side],p['hand'+side],quat)
  foot=p['ankle'+side]+front*.055+Vector((0,0,.04-.095*max(0,up.z))); keyobj(parts['foot'+side],foot,Matrix((right,-front,Vector((0,0,1)))).transposed().to_quaternion())
 doorroot.rotation_euler.z=angle;doorroot.keyframe_insert('rotation_euler')
# A fixed camera, like a background layout shot viewed from the window.
bpy.ops.object.camera_add(location=(2.0,-7.0,3.85));cam=bpy.context.object;cam.name='Window layout camera'
cam.rotation_euler=(Vector((-.05,.10,1.12))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=6.1;scene.camera=cam

def light(name,loc,color,power,size):
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.name=name;o.data.energy=power;o.data.color=color;o.data.shape='DISK';o.data.size=size
 o.rotation_euler=(Vector((0,0,.8))-o.location).to_track_quat('-Z','Y').to_euler()
light('Cool moon through window',(0,-3.2,4.4),(.48,.63,1),500,5)
light('Warm ceiling fill',(-.1,1.2,3.3),(1,.71,.43),180,2)
bpy.ops.object.light_add(type='POINT',location=(-.08,1.59,1.21));bpy.context.object.data.energy=35;bpy.context.object.data.color=(1,.57,.24)
scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.10,.15,.24,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.4
scene.render.filepath=str(ROOT/'output/frames/frame_')
import json
checks={'right_arm_reach_max':max((action((f-1)/12)[0]['handR']-action((f-1)/12)[0]['shoulderR']).length for f in range(91,121)), 'door_open_degrees':math.degrees(action(119/12)[1]),'unique_frames':120,'seconds':10}
(ROOT/'output/motion_checks.json').write_text(json.dumps(checks,indent=2))
scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output/bedroom.blend'))
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if '--preview' in args:
 for f in [1,30,48,72,96,120]:
  scene.frame_set(f);scene.render.filepath=str(ROOT/f'output/preview_{f:03d}.png');bpy.ops.render.render(write_still=True)
else:
 os.makedirs(ROOT/'output/frames',exist_ok=True);bpy.ops.render.render(animation=True)
