"""Animate between two keyframes with Wan 2.2 first/last-frame on a free Hugging Face ZeroGPU Space.

Runs in runtime/hfclient (gradio_client). Optional HF_TOKEN env raises the free
ZeroGPU quota; it is never written anywhere by this script.

Strict policy:
- Explicit error catching on quota / rate limits.
- No retry loops or circumvention.
- No automatic paid fallback.
- Never spend HF quota unnecessarily.

Usage:
  runtime/hfclient/bin/python scripts/hf_wan_flf.py A.png B.png --prompt "..." --seconds 2 --out output/wan/seg00.mp4
"""
import argparse, json, os, shutil, sys, time
from pathlib import Path

try:
    from gradio_client import Client, handle_file
except ImportError:
    Client = None
    handle_file = None

SPACES = {
    'flf': ('multimodalart/wan-2-2-first-last-frame', '/generate_video'),
}
NEG = ('static, still, blurry, low quality, worst quality, deformed, extra limbs, extra fingers, bad hands, bad face, '
       'two people, duplicate person, ghost, morphing, flicker, camera shake, zoom, subtitles, watermark, 3d render, photo')

QUOTA_KEYWORDS = (
    'quota', 'rate limit', 'zerogpu', 'exceeded', '429', 'too many requests',
    'gpu task aborted', 'no gpu available', 'queue is full'
)


def is_quota_error(err_str: str) -> bool:
    err_lower = err_str.lower()
    return any(k in err_lower for k in QUOTA_KEYWORDS)


def main():
    ap = argparse.ArgumentParser(description="Wan 2.2 First-Last Frame via HF ZeroGPU Space")
    ap.add_argument('a', help="Path to start image")
    ap.add_argument('b', help="Path to end image")
    ap.add_argument('--prompt', required=True)
    ap.add_argument('--seconds', type=float, default=2.1)
    ap.add_argument('--steps', type=int, default=8)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()

    if not Path(a.a).is_file():
        sys.exit(f"Start image not found: {a.a}")
    if not Path(a.b).is_file():
        sys.exit(f"End image not found: {a.b}")

    if Client is None or handle_file is None:
        sys.exit("gradio_client is not installed in the current environment.")

    space, api = SPACES['flf']
    t0 = time.time()
    try:
        client = Client(space, token=os.environ.get('HF_TOKEN'), verbose=False)
        video, seed = client.predict(
            handle_file(a.a),
            handle_file(a.b),
            a.prompt,
            NEG,
            a.seconds,
            a.steps,
            1.0,
            1.0,
            a.seed,
            False,
            api_name=api,
        )
    except Exception as e:
        err_msg = str(e)
        if is_quota_error(err_msg):
            sys.stderr.write(
                f"[HF_QUOTA_EXHAUSTED] Hugging Face ZeroGPU quota or rate limit exceeded: {err_msg}\n"
                "Halting immediately. Strict policy: No retry loops, no circumvention, no paid fallback.\n"
            )
            sys.exit(2)
        else:
            sys.stderr.write(f"[HF_ERROR] Inference failed: {err_msg}\n")
            sys.exit(1)

    path = video['video'] if isinstance(video, dict) else video
    a.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(path, a.out)
    meta = {
        'space': space,
        'a': a.a,
        'b': a.b,
        'prompt': a.prompt,
        'seconds': a.seconds,
        'steps': a.steps,
        'seed': seed,
        'wall_s': round(time.time() - t0, 1),
    }
    a.out.with_suffix('.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
