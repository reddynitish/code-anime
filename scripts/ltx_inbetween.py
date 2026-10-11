"""In-between two keyframes with LTX-Video 2B in local ComfyUI (MPS).

Keyframe A is pinned at frame 0 and keyframe B at the last frame via LTXVAddGuide;
LTX invents only the motion between. Frames are saved as PNGs so assembly and
continuity inspection stay local.

  python3 scripts/ltx_inbetween.py A.png B.png --prompt "..." --frames 49 --out output/ltx/seg01
"""
import argparse, json, time, urllib.parse, urllib.request, uuid
from pathlib import Path

COMFY = 'http://127.0.0.1:8188'
CKPT = 'ltx-video-2b-v0.9.5.safetensors'
T5 = 't5xxl_fp8_e4m3fn.safetensors'
NEG = ('low quality, worst quality, deformed, distorted, extra limbs, two people, duplicate person, '
       'morphing, flicker, blurry, watermark, text, camera movement, zoom')


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(COMFY + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def upload(path):
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
            f'Content-Type: image/png\r\n\r\n').encode() + path.read_bytes() + \
           f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(COMFY + '/upload/image', data=body,
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())['name']


def graph(a, b, prompt, w, h, frames, steps, seed, guide_strength, prefix, fps):
    return {
        'ckpt': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': CKPT}},
        'clip': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': T5, 'type': 'ltxv', 'device': 'cpu'}},
        'pos': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['clip', 0]}},
        'neg': {'class_type': 'CLIPTextEncode', 'inputs': {'text': NEG, 'clip': ['clip', 0]}},
        'imgA': {'class_type': 'LoadImage', 'inputs': {'image': a}},
        'imgB': {'class_type': 'LoadImage', 'inputs': {'image': b}},
        'lat': {'class_type': 'EmptyLTXVLatentVideo', 'inputs': {'width': w, 'height': h, 'length': frames, 'batch_size': 1}},
        'gA': {'class_type': 'LTXVAddGuide', 'inputs': {'positive': ['pos', 0], 'negative': ['neg', 0], 'vae': ['ckpt', 2],
                                                         'latent': ['lat', 0], 'image': ['imgA', 0], 'frame_idx': 0, 'strength': 1.0}},
        'gB': {'class_type': 'LTXVAddGuide', 'inputs': {'positive': ['gA', 0], 'negative': ['gA', 1], 'vae': ['ckpt', 2],
                                                         'latent': ['gA', 2], 'image': ['imgB', 0], 'frame_idx': -1, 'strength': guide_strength}},
        'cond': {'class_type': 'LTXVConditioning', 'inputs': {'positive': ['gB', 0], 'negative': ['gB', 1], 'frame_rate': fps}},
        'sched': {'class_type': 'LTXVScheduler', 'inputs': {'latent': ['gB', 2], 'steps': steps, 'max_shift': 2.05,
                                                            'base_shift': 0.95, 'stretch': True, 'terminal': 0.1}},
        'sampler': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        'sample': {'class_type': 'SamplerCustom', 'inputs': {'model': ['ckpt', 0], 'positive': ['cond', 0], 'negative': ['cond', 1],
                                                             'sampler': ['sampler', 0], 'sigmas': ['sched', 0], 'latent_image': ['gB', 2],
                                                             'add_noise': True, 'noise_seed': seed, 'cfg': 3.0}},
        'crop': {'class_type': 'LTXVCropGuides', 'inputs': {'positive': ['cond', 0], 'negative': ['cond', 1], 'latent': ['sample', 0]}},
        'dec': {'class_type': 'VAEDecode', 'inputs': {'samples': ['crop', 2], 'vae': ['ckpt', 2]}},
        'save': {'class_type': 'SaveImage', 'inputs': {'images': ['dec', 0], 'filename_prefix': prefix}},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('a', type=Path)
    p.add_argument('b', type=Path)
    p.add_argument('--prompt', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--w', type=int, default=768)
    p.add_argument('--h', type=int, default=448)
    p.add_argument('--frames', type=int, default=49, help='8n+1')
    p.add_argument('--steps', type=int, default=30)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--guide-strength', type=float, default=1.0)
    p.add_argument('--fps', type=int, default=24)
    a = p.parse_args()
    assert (a.frames - 1) % 8 == 0 and a.w % 32 == 0 and a.h % 32 == 0

    a.out.mkdir(parents=True, exist_ok=True)
    prefix = f'inbetween/{a.out.name}_{int(time.time())}'
    g = graph(upload(a.a), upload(a.b), a.prompt, a.w, a.h, a.frames, a.steps, a.seed, a.guide_strength, prefix, a.fps)
    pid = call('/prompt', {'prompt': g})['prompt_id']
    t0 = time.time()
    print('queued', pid, flush=True)
    while True:
        time.sleep(5)
        hist = call(f'/history/{pid}').get(pid)
        if hist and hist.get('status', {}).get('completed') is not None:
            break
    if hist['status'].get('status_str') != 'success':
        raise SystemExit('failed: ' + json.dumps(hist['status'])[:1500])
    imgs = hist['outputs']['save']['images']
    for i, im in enumerate(imgs):
        q = urllib.parse.urlencode({'filename': im['filename'], 'subfolder': im['subfolder'], 'type': im['type']})
        with urllib.request.urlopen(f'{COMFY}/view?{q}', timeout=60) as r:
            (a.out / f'f{i:04d}.png').write_bytes(r.read())
    meta = {'a': str(a.a), 'b': str(a.b), 'prompt': a.prompt, 'w': a.w, 'h': a.h, 'frames': a.frames, 'steps': a.steps,
            'seed': a.seed, 'guide_strength': a.guide_strength, 'seconds': round(time.time() - t0, 1), 'saved': len(imgs)}
    (a.out / 'meta.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
