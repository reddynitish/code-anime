# Kaggle Wan 2.2 Orchestration Architecture & Plan

## 1. Overview & Architecture
Bounded local orchestration for headless Wan 2.2 image-to-video (I2V) and first-last-frame (FLF2V) generation on Kaggle's free GPU tier.

### Ownership Boundary
- **Owned by Codex**:
  - `docs/KAGGLE_WAN.md`: Architecture, plan, specifications, and runbook.
  - `scripts/kaggle_wan.py`: Local CLI orchestrator (`prepare`, `submit`, `status`, `download`).
  - `kaggle/wan_runner.py`: Remote Kaggle kernel script running headless ComfyUI.
  - `scripts/hf_wan_flf.py`: Free HF ZeroGPU fallback script guarded with strict quota error handling.
  - `tests/test_kaggle_wan.py`: Offline unit test suite.
- **Not touched**: `docs/research/` (GeminiX), `output/` (picker), studio fixes (Kirocloud).

---

## 2. Security & Credentials Boundary
1. **Never Read or Print Keys**: Neither `scripts/kaggle_wan.py` nor tests will ever inspect or print the contents of `~/.kaggle/kaggle.json` or any API token.
2. **Credential Presence Requirement**: Real `submit` or remote API operations verify only file presence (`test -f ~/.kaggle/kaggle.json` or `~/.kaggle/access_token` or `KAGGLE_API_TOKEN` env). If absent, `submit` fails immediately with an informative message stating user phone verification and token setup are still required.
3. **Dry-Run / Prepare Without Credentials**: `prepare` and `--dry-run` operate completely offline without requiring any Kaggle credentials, tokens, or network calls.
4. **Ownership Validation**: Kernel and dataset slugs require `--owner <username>` or extraction from Kaggle CLI config. The username is strictly validated (alphanumeric/hyphens) and never guessed.

---

## 3. Remote ComfyUI & GGUF Node Analysis
- **Node Classes**:
  - `WanImageToVideo`: Standard ComfyUI native node for conditioning Wan 2.1 / 2.2 I2V.
  - `WanFirstLastFrameToVideo`: Native ComfyUI node for first-and-last frame boundary conditioning.
  - `UnetLoaderGGUF`: ComfyUI-GGUF loader from `models/unet` / `models/diffusion_models`.
  - `CreateVideo` and `SaveVideo`: Core ComfyUI video assembly nodes.
- **Model Sizes & Weights**:
  - High-noise & low-noise Q4_K_M UNET: ~9.65 GB each (`QuantStack/Wan2.2-I2V-A14B-GGUF`).
  - UMT5 XXL FP8 text encoder: ~4.9 GB (`Comfy-Org/Wan_2.2_ComfyUI_Repackaged`).
  - Wan 2.1 VAE: ~0.3 GB.
  - Lightx2v 4-step LoRAs: ~0.1 GB each.
- **Hardware & VRAM Reality Check**:
  - Kaggle provides T4 (16 GB VRAM) and P100 (16 GB VRAM) or 2xT4.
  - **No claim T4 fits until tested**: 9.65 GB UNET + 4.9 GB text encoder + latents easily exceed 14 GB unless ComfyUI aggressively offloads text encoders to CPU before sampling. While ComfyUI supports CPU offload by default (`--lowvram` / `--normalvram`), actual fit and inference speed on a single T4 remain unverified until real execution on Kaggle.

---

## 4. Local CLI: `scripts/kaggle_wan.py`
Subcommands:
1. `prepare`:
   - Validates input jobs manifest (JSON).
   - Validates image paths (prevents directory traversal outside allowed project directory).
   - Stages private dataset folder: `staging/dataset/jobs.json`, `staging/dataset/img/*`, `staging/dataset/dataset-metadata.json`.
   - Stages kernel folder: `staging/kernel/wan_runner.py`, `staging/kernel/kernel-metadata.json`.
   - Embeds source commit version hash (`git rev-parse HEAD`) into metadata.
   - Enforces `is_private: true`, `enable_gpu: true`, `enable_internet: true`.
2. `submit`:
   - Checks presence of Kaggle credentials file (`~/.kaggle/kaggle.json`). If missing, halts.
   - Does NOT submit without explicit user command.
   - Uploads dataset (`kaggle datasets create -p staging/dataset` or `kaggle datasets version`).
   - Pushes kernel (`kaggle kernels push -p staging/kernel`).
3. `status`:
   - Bounded polling with timeout and interval (`--poll`, `--timeout`, `--interval`).
   - Queries `kaggle kernels status <owner>/<kernel-slug>`.
   - Handles `queued`, `running`, `complete`, `error`.
4. `download`:
   - Downloads kernel output via `kaggle kernels output <owner>/<kernel-slug> -p <output_dir>`.
   - Parses `results.json`.
   - File skip validation: checks **fingerprint** (valid non-empty MP4 container header `ftyp` box and file size > 1KB), not just bare file existence.

---

## 5. Hugging Face Fallback Guard (`scripts/hf_wan_flf.py`)
- Explicit quota error handling: catches ZeroGPU quota exhaustion (429, "ZeroGPU", "exceeded", "quota", "Rate limit").
- Immediate graceful exit without retry loops, circumventing headers, or automatic paid fallback.
- Never spends HF quota recklessly.

---

## 6. Bedroom Door Shot Plan (3 Parts, 10 Seconds)
Target: 10-second sequence of the reference male character getting out of bed and opening the door (`assets/references/ref3_latest_male_night.png`).

1. **Job 0 (Baseline / Single Test, 3.5s)**:
   - `id`: `bed_test_single`
   - `start_image`: `output/keyframes/bedroom_door_k0_redraw/aligned/k0_lying_00.png`
   - `prompt`: "anime style, man lying in bed under blankets in a dimly lit night bedroom, begins waking up and sitting up"
   - `seconds`: 3.5, `seed`: 42, `width`: 832, `height`: 480
2. **Part 1 (Lying to Standing, 3.5s)**:
   - `id`: `bed_part1_stand`
   - `start_image`: `output/keyframes/bedroom_door_k0_redraw/aligned/k0_lying_00.png`
   - `end_image`: `output/keyframes/bedroom_door_r1/aligned/k2_stand_05.png`
   - `prompt`: "anime style, man waking up, sitting on edge of bed, swinging legs down and standing up"
   - `seconds`: 3.5, `seed`: 101, `width`: 832, `height`: 480
3. **Part 2 (Walking to Door, 3.5s)**:
   - `id`: `bed_part2_walk`
   - `start_image`: `output/keyframes/bedroom_door_r1/aligned/k2_stand_05.png`
   - `end_image`: `output/keyframes/bedroom_door_r1/aligned/k4_handle_01.png`
   - `prompt`: "anime style, man walks across dimly lit wooden floor bedroom toward the closed door, steps forward"
   - `seconds`: 3.5, `seed`: 202, `width`: 832, `height`: 480
4. **Part 3 (Hand on Handle & Door Opens, 3.5s)**:
   - `id`: `bed_part3_door`
   - `start_image`: `output/keyframes/bedroom_door_r1/aligned/k4_handle_01.png`
   - `end_image`: `output/keyframes/bedroom_door_r1/aligned/k5_door_open_01.png`
   - `prompt`: "anime style, man reaches hand to metallic door handle, turns latch and pushes door open into dark corridor"
   - `seconds`: 3.5, `seed`: 303, `width`: 832, `height`: 480
