# 10-Second Anime Sequence Review & Assembly Status

## Executive Summary
This document records the exact state, inspection results, remote GPU job status, and assembly pipeline for the 10-second bedroom-to-door anime sequence.

- **Target Duration**: Exactly 10.000 seconds (160 frames @ 16 fps).
- **Target Layout**: 832x480 (16:9 / 26:15 canvas-normalized, preserved room camera aspect ratio, zero non-uniform stretch).
- **Segmentation Strategy**: 3 consecutive cuts:
  - **Part 1 (0.00s - 3.56s)**: Bed wake-up, swing legs, body rises to almost standing (57 quantized frames @ 16 fps).
  - **Part 2 (3.56s - 7.06s)**: Stand upright and walk across bedroom wooden floor toward door handle (57 quantized frames @ 16 fps).
  - **Part 3 (7.06s - 10.00s)**: Hand reaches handle, turns latch, opens bedroom door into hallway (49 quantized frames @ 16 fps).

---

## 1. Local Accepted Take Audit: Part 1 (`test_i2v_aoti.mp4`)
- **File**: `output/wan/test_i2v_aoti.mp4`
- **Resolution**: 832x480, pixel format `yuv420p`, progressive.
- **Framerate**: 16 fps (`nb_frames: 57`, `duration: 3.5625s`).
- **Motion Verification**:
  - Starts with boy lying in bed under nighttime ambient lighting (lamp + monitor glow).
  - Body lifts torso, swings legs off the mattress smoothly, reaches near standing pose.
  - Background window silhouette and room architecture remain locked in fixed POV.
- **Continuity Extraction**:
  - Frame 56 (the exact last frame of the usable take) extracted to `output/wan_final/part1_final_frame.png` (832x480 PNG).
  - This frame serves as the exact starting conditioning frame for Part 2 to prevent any seam or jump-cut.
- **Contact Sheet**: `output/wan_final/contact_sheet_part1.jpg` generated and inspected.

---

## 2. Remote Kaggle Free GPU Status & Monitor
- **Active Kernel**: `nick0363/wan-runner-code-anime-wan-runner` (Version 4).
- **Incident & Root Cause Diagnosis**:
  - The previous submission at 18:43 pushed dataset version 2 containing 2 jobs, but the kernel execution raced with Kaggle dataset availability or pulled the prior cached dataset version 1 (which had only `bedroom_test_k0_3_5s`).
  - As a result, the completed run output downloaded at 19:03 was the stale single-job baseline run (`bedroom_test_k0_3_5s.mp4`), not the 2 batch jobs.
  - Corrected submission: Verified dataset `nick0363/code-anime-jobs-wan` is `ready` and contains all 2 jobs (`bed_door_part2_walk`, `bed_door_part3_door`). Kernel Version 4 pushed at 19:07 EDT with `KernelWorkerStatus.RUNNING`.
- **Current Live Status**: `KernelWorkerStatus.RUNNING` (verified active via `kaggle kernels status`).
- **Constraint Compliance**:
  - Strict single active run enforced; duplicate submissions blocked.
  - Zero paid API / cloud calls permitted; strictly using free Kaggle GPU tier (T4).
  - Credentials preserved in `~/.kaggle/` and never printed or exposed.
- **Estimated Completion**: ~19:28 - 19:32 EDT (~20-25 mins: ~4.5m setup/weights, ~8m Part 2, ~8m Part 3). Well ahead of the 8:00 PM deadline.

---

## 3. Staged Job Specification (`kaggle/jobs_bedroom_door_final.json`)
The specification for remaining segments is prepared and saved:
```json
[
  {
    "id": "bed_door_part2_walk",
    "image": "output/wan_final/part1_final_frame.png",
    "end_image": "output/keyframes/bedroom_door_r1/aligned/k4_handle_01.png",
    "prompt": "Fixed static exterior window-frame shot, dim bedroom at night, camera does not move. Young man, short dark messy hair, grey t-shirt, olive-grey sweatpants, barefoot, stands fully upright beside the bed, turns toward the closed wooden door on the right, walks smoothly past the desk toward bedroom door, single continuous take.",
    "negative": "static, still image, blurry, low quality, worst quality, deformed, extra limbs, bad anatomy, ghosting, 3d render, duplicate body",
    "seconds": 3.5,
    "width": 832,
    "height": 480,
    "seed": 202
  },
  {
    "id": "bed_door_part3_door",
    "image": "output/keyframes/bedroom_door_r1/aligned/k4_handle_01.png",
    "end_image": "output/keyframes/bedroom_door_r1/aligned/k5_door_open_01.png",
    "prompt": "Fixed static exterior window-frame shot, dim bedroom at night. Same young man grips door handle, turns handle, pushes bedroom door open smoothly revealing hallway, single continuous figure, no camera movement.",
    "negative": "static, still image, blurry, low quality, worst quality, deformed, extra limbs, bad anatomy, ghosting, 3d render, duplicate body, floating handle",
    "seconds": 3.0,
    "width": 832,
    "height": 480,
    "seed": 303
  }
]
```

---

## 4. Final Assembly Plan & Quality Gates
Once Kaggle completes generation and outputs are downloaded:
1. **Per-Job Motion Audit**:
   - Verify single continuous body silhouette (reject ghost limbs, double heads, or phantom duplicates).
   - Verify hand contacts door handle without disconnect, and door rotates strictly on door hinges.
2. **Contact Sheet Inspection**:
   - Render multi-frame contact sheets for part 2 and part 3.
3. **FFmpeg Assembly Execution**:
   - Concatenate part 1 (57 frames trimmed to 3.5s / 56 frames), part 2 (3.5s / 56 frames), part 3 (3.0s / 48 frames) to reach exactly 160 frames (10.00s) @ 16 fps, 832x480.
   - Attach ambient room audio (`output/room_audio.wav`) if level is non-distracting, with zero fabricated studio quality claims.
   - Output to `output/wan_final/final_10s.mp4`.
