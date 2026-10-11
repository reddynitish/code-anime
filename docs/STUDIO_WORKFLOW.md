# Studio Production Workflow

## Architecture Overview

The `studio/` subsystem implements a local-first, reproducible anime video production pipeline designed for ComfyUI.

### Modules
- `studio.config`: Central configuration referencing `runtime/models.json` by default, configurable endpoints and ports.
- `studio.catalog`: Backend catalog loading without invented node IDs; loads required files, contracts, and disabled policy flags.
- `studio.doctor`: Live preflight inspection. Checks ComfyUI reachability, ffmpeg availability, custom node classes, and file availability across `CheckpointLoaderSimple`, `UNETLoader`, `CLIPLoader`, and `VAELoader`. Rejects unknown loaders and blocks paid fallbacks.
- `studio.workflow`: Dynamic binding derivation by verified node classes (`LTXVImgToVideo`, `Wan22ImageToVideoLatent`, `VHS_VideoCombine`, `CreateVideo`). Handles frame quantization (LTX $8n+1$, Wan $4n+1$), step configuration, and smoke test presets.
- `studio.generate`: Execution engine. Extracts true last frames using ffprobe frame count + select (with reverse decode fallback), validates container decodability with ffprobe post-download, trims to exact cut durations (exact 3+4+3 seconds, no looping manufactured animation), and transcodes to standard H.264 MP4.
- `studio.assemble`: Concatenates generated clips with ffmpeg into the final sequence cut.
- `studio.webui`: Localhost loopback server (`127.0.0.1:8787`). Protected by per-project generation locks against race conditions, with automatic stale job recovery and safe media path resolution.
- `studio.cli`: Commands for `doctor`, `plan` (with `--scene`), `status`, `generate` (with `--smoke`), `assemble`, `serve`, and background service control (`server start|stop|status`).

## Duration & Quantization Rules

1. **LTX-Video 2B**: Latent frame counts must satisfy $8n + 1$. For 24 fps:
   - 3.0s target: $\text{round}((72 - 1)/8) = 9 \implies 8 \times 9 + 1 = 73$ frames.
   - 4.0s target: $\text{round}((96 - 1)/8) = 12 \implies 8 \times 12 + 1 = 97$ frames.
2. **Wan2.2 5B**: Latent frame counts must satisfy $4n + 1$. For 24 fps:
   - 3.0s target: $\text{round}((72 - 1)/4) = 18 \implies 4 \times 18 + 1 = 73$ frames.
   - 4.0s target: $\text{round}((96 - 1)/4) = 24 \implies 4 \times 24 + 1 = 97$ frames.
3. **Exact Cut Assembly**: The output postprocessing trims extra quantized frames down to the exact 3+4+3 second timeline (3.0s + 4.0s + 3.0s = 10.0s). Never loops or fabricates synthetic frames.

## Current Model Readiness

- **LTX-Video 2B** (`ltx`):
  - Checkpoint: `ltx-video-2b-v0.9.5.safetensors`
  - Text Encoder: `t5xxl_fp16.safetensors`
  - Status: Preflight passes on local ComfyUI.
- **Wan2.2 5B** (`wan2.2`):
  - Missing weights: `wan2.2_ti2v_5B_fp16.safetensors` (UNET), `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (CLIP), `wan2.2_vae.safetensors` (VAE).
  - Status: Preflight fails cleanly until weights are placed.
- **AniSora** (`anisora`):
  - Missing custom nodes and checkpoint in ComfyUI.
  - Status: Preflight fails cleanly.
- **Seedance** (`seedance`):
  - Permanently disabled by policy (`cloud_disabled`). No fallback allowed.
