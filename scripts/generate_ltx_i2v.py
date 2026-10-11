#!/usr/bin/env python3
"""
scripts/generate_ltx_i2v.py
────────────────────────────
Local LTX-Video 2B image-to-video generation via ComfyUI on MPS.

Usage:
    python scripts/generate_ltx_i2v.py [--smoke] [--prompt "..."] [--seed N]

    --smoke   Tiny 256x160, 9 frames, 2 steps (fast validation)
    --prompt  Override positive prompt
    --seed    RNG seed (default 42)

Exits 0 on success, non-zero on any error.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
COMFY_URL = "http://127.0.0.1:8188"
COMFYUI_ROOT = Path.home() / ".local/share/code-anime/ComfyUI"
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / "runtime/workflows/ltx_i2v.json"
MODELS_JSON = REPO_ROOT / "runtime/models.json"
INPUT_DIR = COMFYUI_ROOT / "input"
OUTPUT_DIR = COMFYUI_ROOT / "output"
FINAL_DIR = REPO_ROOT / "output"

REQUIRED_MODELS = {
    "checkpoint": {
        "path": COMFYUI_ROOT / "models/checkpoints/ltx-video-2b-v0.9.5.safetensors",
        "min_bytes": 5_000_000_000,   # sanity floor; actual ~5.91 GB
        "url": "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors",
    },
    "text_encoder": {
        "path": COMFYUI_ROOT / "models/clip/t5xxl_fp8_e4m3fn.safetensors",
        "min_bytes": 4_000_000_000,   # sanity floor; actual ~4.89 GB
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
    },
}

# Nodes we must see in live object_info before queuing
REQUIRED_NODES = [
    "CheckpointLoaderSimple",
    "CLIPLoader",
    "CLIPTextEncode",
    "LTXVImgToVideo",
    "LTXVConditioning",
    "LTXVScheduler",
    "KSamplerSelect",
    "SamplerCustom",
    "VAEDecode",
    "CreateVideo",
    "SaveVideo",
    "LoadImage",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(path: str, timeout: int = 15) -> dict:
    """GET JSON from ComfyUI, raising with the HTTP status on failure."""
    url = COMFY_URL + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from GET {url}: {e.reason}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach ComfyUI at {COMFY_URL}: {e.reason}\n"
                 "Start ComfyUI: cd ~/.local/share/code-anime/ComfyUI && "
                 ".venv/bin/python main.py --listen 127.0.0.1 --port 8188 --lowvram")


def _post(path: str, payload: dict, timeout: int = 30) -> dict:
    """POST JSON to ComfyUI."""
    url = COMFY_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"HTTP {e.code} from POST {url}: {e.reason}\n{body[:800]}")
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach ComfyUI at {COMFY_URL}: {e.reason}")


def check_comfyui() -> dict:
    print("● Checking ComfyUI is alive …")
    stats = _get("/system_stats")
    device = stats["devices"][0]
    print(f"  ComfyUI {stats['system']['comfyui_version']} | "
          f"device={device['name']} | "
          f"vram_free={device['vram_free'] / 1e9:.1f} GB")
    return stats


def check_models() -> None:
    print("● Checking required model files …")
    missing = []
    for role, info in REQUIRED_MODELS.items():
        p = info["path"]
        if not p.exists():
            missing.append((role, p, info["url"], "not found"))
        elif p.stat().st_size < info["min_bytes"]:
            sz = p.stat().st_size
            missing.append((role, p, info["url"],
                            f"too small: {sz:,} bytes (may still be downloading)"))
        else:
            sz = p.stat().st_size
            print(f"  ✓ {role}: {p.name} ({sz / 1e9:.2f} GB)")

    if missing:
        print("\n✗ Missing or incomplete model files:")
        for role, p, url, reason in missing:
            print(f"  {role}: {p.name} — {reason}")
            print(f"    Download: curl -L -C - '{url}' -o '{p}'")
        sys.exit(1)


def check_nodes() -> None:
    print("● Validating required ComfyUI nodes via object_info …")
    info = _get("/object_info")
    missing = [n for n in REQUIRED_NODES if n not in info]
    if missing:
        sys.exit(f"✗ Missing nodes in live ComfyUI: {missing}\n"
                 "Run 'pip install comfyui-ltxvideo' or reinstall ComfyUI.")
    print(f"  ✓ All {len(REQUIRED_NODES)} required nodes present")

    # Validate CLIPLoader device options
    clip_info = info.get("CLIPLoader", {})
    device_opts = (clip_info.get("input", {})
                             .get("optional", {})
                             .get("device", [[]])[0])
    if device_opts and "cpu" not in device_opts:
        print(f"  ⚠ CLIPLoader 'device' does not list 'cpu' — available: {device_opts}")
        print("    MPS float8 is unsupported; will fall back to default and hope for auto-cast.")


def build_workflow(args: argparse.Namespace) -> dict:
    """Load base workflow and patch for smoke/prod params."""
    with open(WORKFLOW_PATH) as f:
        wf = json.load(f)

    # Ensure fp8 encoder is set (in case workflow was edited)
    wf["38"]["inputs"]["clip_name"] = "t5xxl_fp8_e4m3fn.safetensors"
    wf["38"]["inputs"]["device"] = "cpu"  # MPS has no float8 kernels

    # Image: copy reference.png into ComfyUI input dir
    ref_src = REPO_ROOT / "assets/reference.png"
    if not ref_src.exists():
        sys.exit(f"✗ Reference image not found: {ref_src}")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = INPUT_DIR / "reference.png"
    shutil.copy2(str(ref_src), str(dest))
    wf["78"]["inputs"]["image"] = "reference.png"

    # Prompts
    positive = args.prompt or (
        "A young anime girl slowly sits up in bed, morning sunlight streaming "
        "through the window, gentle motion, soft shadows, studio ghibli style, "
        "high quality, smooth animation, detailed background."
    )
    negative = (
        "low quality, worst quality, deformed, distorted, disfigured, "
        "motion smear, motion artifacts, ugly, blurry, watermark."
    )
    wf["6"]["inputs"]["text"] = positive
    wf["7"]["inputs"]["text"] = negative

    # Seed
    wf["72"]["inputs"]["noise_seed"] = args.seed

    if args.smoke:
        # Tiny: 256×160, 9 frames (min valid = 8*1+1), 2 steps
        # Width/height must be multiples of 32
        wf["77"]["inputs"]["width"] = 256
        wf["77"]["inputs"]["height"] = 160
        wf["77"]["inputs"]["length"] = 9   # 8n+1 min; 9 = 8*1+1 ✓
        wf["71"]["inputs"]["steps"] = 2
        wf["81"]["inputs"]["filename_prefix"] = "video/LTXV_smoke"
        print("  ● Smoke mode: 256×160, 9 frames, 2 steps")
    else:
        wf["77"]["inputs"]["width"] = 512
        wf["77"]["inputs"]["height"] = 320
        wf["77"]["inputs"]["length"] = 25  # 8*3+1
        wf["71"]["inputs"]["steps"] = 20
        wf["81"]["inputs"]["filename_prefix"] = "video/LTXV"
        print(f"  ● Production mode: 512×320, 25 frames, 20 steps")

    return wf


def queue_prompt(wf: dict) -> str:
    print("● Queuing prompt …")
    resp = _post("/prompt", {"prompt": wf})
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        sys.exit(f"✗ No prompt_id in response: {resp}")
    print(f"  prompt_id = {prompt_id}")
    return prompt_id


def wait_for_result(prompt_id: str, timeout: int = 300) -> dict:
    """Poll /history until prompt_id appears or timeout expires."""
    print(f"● Waiting for generation (max {timeout}s) …")
    deadline = time.time() + timeout
    last_status = ""
    while time.time() < deadline:
        # Check queue status
        try:
            queue = _get("/queue", timeout=10)
            running = [x[1] for x in queue.get("queue_running", [])]
            pending = [x[1] for x in queue.get("queue_pending", [])]
            status = (f"running={len(running)} pending={len(pending)}")
            if status != last_status:
                print(f"  Queue: {status}")
                last_status = status
        except SystemExit:
            pass

        # Check history
        hist = _get(f"/history/{prompt_id}", timeout=15)
        if prompt_id in hist:
            entry = hist[prompt_id]
            if entry.get("status", {}).get("completed"):
                return entry
            if entry.get("status", {}).get("status_str") == "error":
                msgs = entry.get("status", {}).get("messages", [])
                sys.exit(f"✗ ComfyUI generation error: {msgs}")
        time.sleep(3)

    sys.exit(f"✗ Timed out after {timeout}s waiting for prompt_id={prompt_id}")


def find_output_video(result: dict) -> Path:
    """Extract the video file path from a history result entry."""
    outputs = result.get("outputs", {})
    for node_id, node_out in outputs.items():
        for key in ("videos", "gifs", "images"):
            for item in node_out.get(key, []):
                fname = item.get("filename", "")
                subfolder = item.get("subfolder", "")
                if fname:
                    candidate = OUTPUT_DIR / subfolder / fname
                    if candidate.exists():
                        return candidate
                    # Try without subfolder
                    candidate2 = OUTPUT_DIR / fname
                    if candidate2.exists():
                        return candidate2
    # Fallback: newest file in output/video/
    video_dir = OUTPUT_DIR / "video"
    if video_dir.exists():
        candidates = sorted(video_dir.glob("LTXV*.mp4"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return candidates[-1]
    sys.exit(f"✗ Could not find output video in ComfyUI output dir.\n"
             f"  outputs dict: {json.dumps(outputs, indent=2)[:600]}")


def validate_video(path: Path) -> None:
    """Use ffprobe to verify the output is a valid video with duration > 0."""
    print(f"● ffprobe validation: {path}")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("  ⚠ ffprobe not found — skipping container validation")
        return
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration,size,format_name:stream=codec_type,width,height,nb_frames",
        "-of", "json",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"✗ ffprobe failed (invalid/corrupt video):\n{r.stderr}")
    info = json.loads(r.stdout)
    fmt = info.get("format", {})
    duration = float(fmt.get("duration", 0) or 0)
    size = int(fmt.get("size", 0) or 0)
    fmt_name = fmt.get("format_name", "?")
    if duration <= 0:
        sys.exit(f"✗ ffprobe: video has duration={duration} — likely empty/corrupt")
    print(f"  ✓ Valid {fmt_name}: duration={duration:.2f}s, size={size:,} bytes")
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            w = stream.get("width", "?")
            h = stream.get("height", "?")
            nb = stream.get("nb_frames", "?")
            print(f"    video stream: {w}×{h}, {nb} frames")


def copy_to_output(src: Path) -> Path:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    dest = FINAL_DIR / f"ltx_i2v_{ts}.mp4"
    shutil.copy2(str(src), str(dest))
    print(f"✓ Output copied to: {dest}")
    return dest


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LTX-Video 2B I2V via local ComfyUI")
    parser.add_argument("--smoke", action="store_true",
                        help="Tiny 256×160 9-frame 2-step smoke test")
    parser.add_argument("--prompt", default="",
                        help="Override positive prompt")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed (default 42)")
    args = parser.parse_args()

    print("\n══ LTX-Video 2B I2V Generator (local ComfyUI / MPS) ══\n")

    # 1. ComfyUI alive?
    check_comfyui()

    # 2. Model files present and complete?
    check_models()

    # 3. Required nodes registered?
    check_nodes()

    # 4. Build patched workflow
    wf = build_workflow(args)

    # 5. Queue
    prompt_id = queue_prompt(wf)

    # 6. Wait (5 min max)
    result = wait_for_result(prompt_id, timeout=300)
    print(f"  ✓ Generation completed")

    # 7. Find output video
    video_path = find_output_video(result)
    print(f"  ✓ Raw output: {video_path}")

    # 8. Validate with ffprobe
    validate_video(video_path)

    # 9. Copy to repo output/
    final = copy_to_output(video_path)

    print(f"\n✓ Done. Video: {final}\n")


if __name__ == "__main__":
    main()
