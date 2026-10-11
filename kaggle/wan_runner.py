"""Kaggle GPU kernel: Wan 2.2 I2V A14B (GGUF Q4) + lightx2v 4-step LoRA in headless ComfyUI.

Hardware note:
  Wan2.2-I2V-A14B Q4_K_M UNET (~9.65 GB) + UMT5 XXL FP8 text encoder (~4.9 GB) + VAE (~0.3 GB).
  Total weights exceed 14 GB. ComfyUI dynamically offloads models between CPU and GPU.
  NOTE: T4 (16 GB VRAM) fit is UNTESTED and UNVERIFIED until empirical validation.
  If T4 OOMs during latent generation or VAE decode, use Kaggle P100 (16 GB) or Kaggle dual T4.

Reads jobs.json from the attached dataset (code-anime-jobs). Each job:
  {"id": "shot01_t1", "image": "img/x.png", "end_image": optional, "prompt": "...",
   "negative": optional, "seconds": 5, "width": 832, "height": 480, "seed": 1}
Writes /kaggle/working/out/<id>.mp4 and results.json. Pushed and polled by scripts/kaggle_wan.py.
"""
import glob, json, os, re, shutil, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

# Kaggle preinstalls these with a matching CUDA build; never let requirements.txt
# clobber them. Match the exact normalized distribution name, not a prefix, so
# related-but-distinct packages (e.g. torchsde) are not accidentally skipped.
PROTECTED_TORCH_PACKAGES = {'torch', 'torchvision', 'torchaudio'}


def normalize_dist_name(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def requirement_package_name(line):
    line = line.split('#', 1)[0].strip()
    if not line:
        return None
    m = re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)', line)
    return normalize_dist_name(m.group(1)) if m else None

T0 = time.time()
WORK = Path('/kaggle/working')
OUT = WORK / 'out'
OUT.mkdir(parents=True, exist_ok=True)
COMFY = Path('/kaggle/tmp/ComfyUI')
LOG = open(WORK / 'runner.log', 'a')


def log(*a):
    msg = f'[{time.time() - T0:7.1f}s] ' + ' '.join(str(x) for x in a)
    print(msg, flush=True)
    LOG.write(msg + '\n')
    LOG.flush()


def sh(cmd, **kw):
    log('$', cmd)
    subprocess.run(cmd, shell=True, check=True, **kw)


# ── setup ────────────────────────────────────────────────────────────────────
jobs_file = next(iter(glob.glob('/kaggle/input/**/jobs.json', recursive=True)), None)
if not jobs_file:
    sys.exit('jobs.json not found in /kaggle/input')
JOBDIR = Path(jobs_file).parent
JOBS = json.loads(Path(jobs_file).read_text())
log('jobs', len(JOBS), 'from', JOBDIR)
# Check GPU availability
try:
    sh('nvidia-smi --query-gpu=name,memory.total --format=csv')
except Exception as e:
    sys.exit(f'GPU not available or nvidia-smi failed: {e}')


if not COMFY.exists():
    sh(f'git clone --depth 1 https://github.com/comfyanonymous/ComfyUI {COMFY}')
    sh(f'git clone --depth 1 https://github.com/city96/ComfyUI-GGUF {COMFY}/custom_nodes/ComfyUI-GGUF')
    # keep Kaggle's CUDA torch/torchvision/torchaudio: install everything else,
    # including torchsde (required by comfy.k_diffusion.sampling) which a naive
    # prefix check would otherwise also strip.
    reqs = [l for l in (COMFY / 'requirements.txt').read_text().splitlines()
            if requirement_package_name(l) not in PROTECTED_TORCH_PACKAGES and requirement_package_name(l) is not None]
    Path('/kaggle/tmp/reqs.txt').write_text('\n'.join(reqs + ['gguf', 'hf_transfer', 'huggingface_hub']))
    sh('pip install -q -r /kaggle/tmp/reqs.txt')

os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
from huggingface_hub import hf_hub_download  # noqa: E402

FILES = [
    ('QuantStack/Wan2.2-I2V-A14B-GGUF', 'HighNoise/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf', 'unet'),
    ('QuantStack/Wan2.2-I2V-A14B-GGUF', 'LowNoise/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf', 'unet'),
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'text_encoders'),
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/vae/wan_2.1_vae.safetensors', 'vae'),
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors', 'loras'),
    ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors', 'loras'),
]
for repo, path, kind in FILES:
    dest = COMFY / 'models' / kind / Path(path).name
    if not dest.exists():
        src = hf_hub_download(repo, path, local_dir='/kaggle/tmp/hf')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
        log('got', dest.name, f'{dest.stat().st_size / 1e9:.2f} GB')

server = subprocess.Popen([sys.executable, 'main.py', '--listen', '127.0.0.1', '--port', '8188', '--disable-auto-launch'],
                          cwd=COMFY, stdout=open(WORK / 'comfy.log', 'w'), stderr=subprocess.STDOUT)
API = 'http://127.0.0.1:8188'


def call(path, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


for _ in range(180):
    try:
        call('/system_stats')
        break
    except Exception:
        time.sleep(2)
else:
    sys.exit('ComfyUI did not start; see comfy.log')
log('ComfyUI up')

NEG = ('static, still image, blurry, low quality, worst quality, jpeg artifacts, deformed, bad anatomy, extra limbs, '
       'extra fingers, fused fingers, bad hands, bad face, two people, duplicate person, ghost, morphing, flicker, '
       'camera shake, subtitles, watermark, 3d render, photo, realistic')


def graph(job, start_name, end_name):
    fps = 16
    length = int(round(job.get('seconds', 5) * fps / 4)) * 4 + 1  # Wan wants 4n+1
    g = {
        'hi': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf'}},
        'lo': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf'}},
        'hiL': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['hi', 0], 'lora_name': 'wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors', 'strength_model': 1.0}},
        'loL': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['lo', 0], 'lora_name': 'wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors', 'strength_model': 1.0}},
        'hiS': {'class_type': 'ModelSamplingSD3', 'inputs': {'model': ['hiL', 0], 'shift': 5.0}},
        'loS': {'class_type': 'ModelSamplingSD3', 'inputs': {'model': ['loL', 0], 'shift': 5.0}},
        'clip': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'type': 'wan', 'device': 'default'}},
        'pos': {'class_type': 'CLIPTextEncode', 'inputs': {'text': job['prompt'], 'clip': ['clip', 0]}},
        'neg': {'class_type': 'CLIPTextEncode', 'inputs': {'text': job.get('negative', NEG), 'clip': ['clip', 0]}},
        'vae': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'wan_2.1_vae.safetensors'}},
        'img': {'class_type': 'LoadImage', 'inputs': {'image': start_name}},
    }
    common = {'positive': ['pos', 0], 'negative': ['neg', 0], 'vae': ['vae', 0], 'width': job.get('width', 832),
              'height': job.get('height', 480), 'length': length, 'batch_size': 1, 'start_image': ['img', 0]}
    if end_name:
        g['end'] = {'class_type': 'LoadImage', 'inputs': {'image': end_name}}
        g['i2v'] = {'class_type': 'WanFirstLastFrameToVideo', 'inputs': {**common, 'end_image': ['end', 0]}}
    else:
        g['i2v'] = {'class_type': 'WanImageToVideo', 'inputs': common}
    steps, split = 4, 2
    g['k1'] = {'class_type': 'KSamplerAdvanced', 'inputs': {
        'model': ['hiS', 0], 'add_noise': 'enable', 'noise_seed': job.get('seed', 1), 'steps': steps, 'cfg': 1.0,
        'sampler_name': 'euler', 'scheduler': 'simple', 'positive': ['i2v', 0], 'negative': ['i2v', 1],
        'latent_image': ['i2v', 2], 'start_at_step': 0, 'end_at_step': split, 'return_with_leftover_noise': 'enable'}}
    g['k2'] = {'class_type': 'KSamplerAdvanced', 'inputs': {
        'model': ['loS', 0], 'add_noise': 'disable', 'noise_seed': job.get('seed', 1), 'steps': steps, 'cfg': 1.0,
        'sampler_name': 'euler', 'scheduler': 'simple', 'positive': ['i2v', 0], 'negative': ['i2v', 1],
        'latent_image': ['k1', 0], 'start_at_step': split, 'end_at_step': 10000, 'return_with_leftover_noise': 'disable'}}
    g['dec'] = {'class_type': 'VAEDecode', 'inputs': {'samples': ['k2', 0], 'vae': ['vae', 0]}}
    g['vid'] = {'class_type': 'CreateVideo', 'inputs': {'images': ['dec', 0], 'fps': fps}}
    g['save'] = {'class_type': 'SaveVideo', 'inputs': {'video': ['vid', 0], 'filename_prefix': f"video/{job['id']}",
                                                        'format': 'mp4', 'codec': 'h264'}}
    return g


def stage(rel):
    src = JOBDIR / rel
    name = f'{uuid.uuid4().hex[:8]}_{src.name}'
    shutil.copy(src, COMFY / 'input' / name)
    return name


results = []
for job in JOBS:
    if (OUT / f"{job['id']}.mp4").exists():
        continue
    t = time.time()
    try:
        pid = call('/prompt', {'prompt': graph(job, stage(job['image']), stage(job['end_image']) if job.get('end_image') else None)})['prompt_id']
        poll_start = time.time()
        max_poll_sec = 1200  # 20 min max per job
        while True:
            time.sleep(5)
            h = call(f'/history/{pid}').get(pid)
            if h and h.get('status', {}).get('completed') is not None:
                break
            if time.time() - poll_start > max_poll_sec:
                raise TimeoutError(f'Prompt {pid} timed out after {max_poll_sec}s')
        if h['status'].get('status_str') != 'success':
            raise RuntimeError(json.dumps(h['status'])[:1500])
        files = [f for o in h['outputs'].values() for k in ('images', 'videos', 'gifs') for f in o.get(k, [])]
        src = COMFY / 'output' / files[0].get('subfolder', '') / files[0]['filename']
        shutil.copy(src, OUT / f"{job['id']}.mp4")
        results.append({'id': job['id'], 'ok': True, 'seconds': round(time.time() - t, 1)})
        log('done', job['id'], f'{time.time() - t:.0f}s')
    except Exception as e:  # keep going; one bad job must not sink the batch
        results.append({'id': job['id'], 'ok': False, 'error': str(e)[:1500]})
        log('FAILED', job['id'], str(e)[:300])
    (WORK / 'results.json').write_text(json.dumps(results, indent=2))

server.terminate()
log('all done', sum(r['ok'] for r in results), '/', len(results))
