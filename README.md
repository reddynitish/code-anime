# Code Anime

Local anime shot production workflow using real video generation powered by local open weights. Orchestrated via the local `studio/` package and ComfyUI integration. See [Kiro Starter Guide](docs/KIRO_START.md) and [Studio Workflow](docs/STUDIO_WORKFLOW.md).

> **Policy & Constraints**: 100% local open weights (zero paid cloud API calls). Never reuse rejected old 2D frames. No multi-shot animation sequence is claimed as finished until weights are fully verified, generated, and validated for continuity and decodability.

## Current Studio Workflow

The `studio/` package provides a local, free, reproducible anime shot production pipeline communicating with a local ComfyUI instance (default `http://127.0.0.1:8188`).

### Backend Status
- **LTX-Video 2B** (`ltx`): Checkpoint and text encoder detected in local ComfyUI; preflight passes ($8n + 1$ frame quantization).
- **Wan2.2 5B** (`wan2.2`): Runtime workflows present; weights missing (`wan2.2_ti2v_5B_fp16.safetensors`, `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `wan2.2_vae.safetensors`).
- **AniSora** (`anisora`): Custom nodes and weights not installed in ComfyUI.
- **Seedance** (`seedance`): Permanently disabled by policy (paid cloud API). No paid fallback is permitted.

### CLI Commands
- `python3 -m studio doctor`: Preflight checks across ComfyUI, ffmpeg, and model loader options (UNET, CLIP, VAE).
- `python3 -m studio plan --project <name> [--reference <img.png>] [--scene <text>]`: Plan shot sequence with optional scene text.
- `python3 -m studio generate --project <name> --shot <N> --backend <key> [--smoke]`: Generate shot with frame quantization (LTX $8n+1$ / Wan $4n+1$), robust last-frame extraction, and ffprobe validation.
- `python3 -m studio assemble --project <name>`: Assemble shots into final MP4 cut.
- `python3 -m studio server {start|stop|status} [--port 8787]`: Manage background Web UI service on loopback.
- `python3 -m studio serve [--port 8787]`: Run foreground Web UI.

### Key Documentation
- `docs/KIRO_START.md`: Current Kiro starter task, constraints, and audit tasks.
- `docs/STUDIO_WORKFLOW.md`: Studio architecture, preflight checks, and duration handling.
- `docs/PLAN.md`: Shot planning and production breakdown.
- `docs/PIPELINE_V2.md`: Pipeline v2 notes.

## Project Status & Hackathon Prototype

This repository contains a pre-existing anime production and scene prototype that was extended during the hackathon with:
1. **Free Cloud GPU Video Orchestration (Wan 2.2)**: Bounded headless ComfyUI automation via Kaggle's free GPU tier (`scripts/kaggle_wan.py`, `kaggle/wan_runner.py`) and Hugging Face ZeroGPU fallback (`scripts/hf_wan_flf.py`).
2. **High-Fidelity Production Keyframing (Luminal & Ideogram 4.5)**: Strategic keyframe and turnaround asset generation specs (`specs/luminal_production_batch.json`, `docs/LUMINAL_PRODUCTION.md`, `scripts/keyframes.py`).
3. **Automated Demo Composition & Audio**: Programmatic demo video rendering and soundtrack synthesis (`scripts/demo_video/render_demo_90s.py`, `scripts/demo_audio/generate_music.py`).

### Final Uploaded Demo
- **Demo Video**: [https://youtu.be/QreVPrYYzyM](https://youtu.be/QreVPrYYzyM)

---

## How to Run

### 1. Kaggle Wan 2.2 Video Generation (Free GPU)
Ensure Kaggle credentials are configured in `~/.kaggle/kaggle.json` or `KAGGLE_API_TOKEN` (never committed or exposed).
```bash
# 1. Prepare and stage jobs offline (validates paths, creates dataset & kernel metadata)
python3 scripts/kaggle_wan.py prepare --jobs kaggle/jobs_bedroom_door_final.json --owner <kaggle_username>

# 2. Submit to Kaggle GPU kernel
python3 scripts/kaggle_wan.py submit

# 3. Poll kernel execution status
python3 scripts/kaggle_wan.py status --poll --timeout 1800

# 4. Download generated video takes once finished
python3 scripts/kaggle_wan.py download --out-dir output/wan_kaggle/
```
Detailed guide: [docs/KAGGLE_WAN.md](docs/KAGGLE_WAN.md)

### 2. Luminal Production Asset Generation
Luminal authentication resides outside the repository in `~/.config/code-anime/luminal.json`.
```bash
# Preview batch specification (dry-run)
python3 scripts/keyframes.py specs/luminal_production_batch.json --cap 16.00 --dry-run

# Run bounded batch asset generation (character turnarounds & macro keyframes)
python3 scripts/keyframes.py specs/luminal_production_batch.json --cap 16.00
```
Detailed guide: [docs/LUMINAL_PRODUCTION.md](docs/LUMINAL_PRODUCTION.md)

### 3. Local Studio Workflow & Doctor
```bash
# Check local environment (ComfyUI, ffmpeg, model weights)
python3 -m studio doctor

# Plan and assemble shots locally
python3 -m studio plan --project bedroom --scene "Character waking up and walking to door"
python3 -m studio assemble --project bedroom
```

### 4. Running Offline Unit Tests
```bash
python3 -m unittest discover -s tests
```

---

## Historical: Procedural 3D Bedroom Prototype

An earlier procedural 3D cel-shaded prototype in Blender (`scripts/build_scene.py`, `scripts/render.sh`) based on `assets/reference.png`. Kept strictly for historical and staging reference; superseded by the open-weights video studio pipeline.

