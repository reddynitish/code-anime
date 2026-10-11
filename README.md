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

## Historical: Procedural 3D Bedroom Prototype

An earlier procedural 3D cel-shaded prototype in Blender (`scripts/build_scene.py`, `scripts/render.sh`) based on `assets/reference.png`. Kept strictly for historical and staging reference; superseded by the open-weights video studio pipeline.
