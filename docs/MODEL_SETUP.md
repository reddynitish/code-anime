# Local Video Generation Runtime & Model Setup

This document describes the local video generation runtime on Apple Silicon (M4, 16 GB Unified RAM, macOS).

> **Last verified**: 2026-10-11 · ComfyUI 0.39.0 · PyTorch 2.14.1 · device=mps

---

## 1. Environment & Architecture Overview

| Item | Value |
|---|---|
| Hardware | Apple M4, 16 GB Unified RAM, ~63 GB free disk |
| Inference Engine | ComfyUI 0.39.0 at `~/.local/share/code-anime/ComfyUI` |
| Python | 3.12.13 in `.venv` (isolated from repo) |
| PyTorch | 2.14.1 with MPS (Metal Performance Shaders) backend |
| Server | `http://127.0.0.1:8188` with `--lowvram` |

---

## 2. Service Management

```bash
./scripts/setup_studio_runtime.sh    # clone ComfyUI + install deps
./scripts/setup_studio_service.sh start   # start ComfyUI on port 8188
./scripts/setup_studio_service.sh status  # PID + health check
./scripts/setup_studio_service.sh stop    # graceful stop
./scripts/setup_studio_health.sh     # full preflight diagnostics
```

PID: `runtime/comfyui.pid` · Log: `runtime/comfyui.log`

---

## 3. Backends & Model Status

Catalog source: [`runtime/models.json`](../runtime/models.json)

| Backend | License | Hardware fit (16 GB) | Node status | Weights status | Download size |
|---|---|---|---|---|---|
| **LTX-Video 2B** | Lightricks Open | ✅ Viable with fp8 encoder | Native ComfyUI nodes | **Downloading** | ~10.8 GB total |
| **Wan2.2 5B** | Apache 2.0 | ⚠️ Borderline — needs fp8 unet | Native ComfyUI nodes | Not downloaded | ~16.9 GB total |
| **AniSora** | Apache 2.0 | ❌ Custom nodes not installed | Missing | Not downloaded | >10 GB |
| **Seedance** | Proprietary | 🚫 Disabled | Cloud only | N/A | paid API |

### AniSora / Wan — real sources (not invented checkpoints)

- **AniSora (Index-AniSora)**: model weights at `https://huggingface.co/bilibili/Index-anisora` — the filename `anisora_v2.safetensors` listed in the original `runtime/models.json` does **not** exist; actual release uses HuggingFace model-card with `model.safetensors` shards. Custom ComfyUI node must be installed first (`ComfyUI-WanVideo` or similar wrapper) before any workflow can run.
- **Wan2.2**: ComfyUI-repackaged files live at `https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged` (Wan 2.1 repack — Wan 2.2 had no Comfy-Org repack as of 2026-10). Raw Wan2.2 weights at `https://huggingface.co/Wan-AI/Wan2.2`. The diffusion model (~10.5 GB) + UMT5 fp8 encoder (~5 GB) + VAE (~1.4 GB) = ~16.9 GB. This barely fits 16 GB only with `weight_dtype=fp8_e4m3fn` on the UNETLoader node — the current workflow uses `"default"` which will OOM. Until that workflow is fixed the backend should remain `enabled: false`.

---

## 4. LTX-Video 2B — Memory Math & fp8 Requirement

> [!IMPORTANT]
> **t5xxl_fp16 does NOT fit on 16 GB unified RAM alongside the checkpoint.**
>
> | File | Size |
> |---|---|
> | `ltx-video-2b-v0.9.5.safetensors` (checkpoint) | **5.91 GB** |
> | `t5xxl_fp8_e4m3fn.safetensors` (text encoder, **required**) | **4.89 GB** |
> | `t5xxl_fp16.safetensors` (fp16 variant, **DO NOT USE on 16 GB**) | **9.12 GB** |
>
> Checkpoint + fp8 encoder = **~10.8 GB** weights → fits with `--lowvram`.  
> Checkpoint + fp16 encoder = **~15.0 GB** weights → leaves <1 GB for activations → OOM.
>
> MPS has **no native float8 compute kernels** as of PyTorch 2.14. ComfyUI's CLIPLoader
> must run the T5 fp8 model on **CPU** (`"device": "cpu"` in node 38). This is already
> set in `runtime/workflows/ltx_i2v.json`.

---

## 5. Verified Workflow: `runtime/workflows/ltx_i2v.json`

All node IDs verified against live `/object_info` (ComfyUI 0.39.0):

| Node ID | Class | Key input |
|---|---|---|
| `38` | `CLIPLoader` | `clip_name=t5xxl_fp8_e4m3fn.safetensors`, `type=ltxv`, `device=cpu` |
| `44` | `CheckpointLoaderSimple` | `ckpt_name=ltx-video-2b-v0.9.5.safetensors` |
| `78` | `LoadImage` | `image=reference.png` |
| `6` | `CLIPTextEncode` | positive prompt |
| `7` | `CLIPTextEncode` | negative prompt |
| `77` | `LTXVImgToVideo` | `width`, `height`, `length` (must satisfy 8n+1), `strength` |
| `69` | `LTXVConditioning` | `frame_rate=25` |
| `71` | `LTXVScheduler` | `steps`, `max_shift=2.05`, `base_shift=0.95` |
| `73` | `KSamplerSelect` | `sampler_name=euler` |
| `72` | `SamplerCustom` | model, sigmas, cfg=3.0, seed |
| `8` | `VAEDecode` | samples, vae |
| `80` | `CreateVideo` | `fps=24` |
| `81` | `SaveVideo` | `filename_prefix=video/LTXV` |

**Frame count rule**: `length` must equal `8n + 1` (9, 17, 25, 33 … 97). Smoke test uses 9 frames.  
**Dimension rule**: width and height must be multiples of 32.

---

## 6. Resumable Download Commands

### LTX-Video 2B (Recommended — fits 16 GB)

```bash
# Resume-capable checkpoint download (~5.91 GB)
curl -L -C - \
  "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors" \
  -o ~/.local/share/code-anime/ComfyUI/models/checkpoints/ltx-video-2b-v0.9.5.safetensors

# Resume-capable T5-XXL fp8 encoder download (~4.89 GB) — fp8 REQUIRED
curl -L -C - \
  "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" \
  -o ~/.local/share/code-anime/ComfyUI/models/clip/t5xxl_fp8_e4m3fn.safetensors
```

> [!WARNING]
> Do **not** download `t5xxl_fp16.safetensors` for use with the checkpoint on 16 GB — it is 9.12 GB and will cause OOM.

### Generate after download completes

```bash
# Smoke test: 256×160, 9 frames, 2 steps (~2-3 min on M4)
python scripts/generate_ltx_i2v.py --smoke

# Full generation: 512×320, 25 frames, 20 steps
python scripts/generate_ltx_i2v.py --prompt "anime girl waking up, morning light, studio ghibli style"
```

---

## 7. Wan2.2 Download (Future / On-Demand)

> [!CAUTION]
> The current `wan22_i2v.json` workflow uses `weight_dtype: "default"` on the UNETLoader node.
> Wan 5B fp16 (~10.5 GB) + VAE (~1.4 GB) + umt5 fp8 encoder (~5 GB) ≈ 16.9 GB before
> activations → **will OOM on 16 GB**. Set `weight_dtype: "fp8_e4m3fn"` first.

Real Wan files (verified HuggingFace paths — Wan 2.1 repackaged, the closest available):

```bash
# Diffusion model (~10.5 GB)
curl -L -C - \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_480p_14B_bf16.safetensors" \
  -o ~/.local/share/code-anime/ComfyUI/models/diffusion_models/wan2.1_i2v_480p_14B_bf16.safetensors

# Text encoder fp8 (~5 GB)
curl -L -C - \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
  -o ~/.local/share/code-anime/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors

# VAE (~1.4 GB)
curl -L -C - \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors" \
  -o ~/.local/share/code-anime/ComfyUI/models/vae/wan_2.1_vae.safetensors
```

---

## 8. Free Hosted Demos

- **LTX-Video**: https://huggingface.co/spaces/Lightricks/LTX-Video
- **Wan2.1**: https://huggingface.co/spaces/Wan-AI/Wan2.1
- **AniSora**: https://github.com/bilibili/Index-anisora
