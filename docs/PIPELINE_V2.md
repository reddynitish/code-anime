# Pipeline v2: Ideogram keyframes + local LTX in-betweens

Started 2026-10-11 by Claude Code after taking over from Codex. The user wants
the Luminal credits (about $1,990 at the start) used heavily.

## Why this shape

- Luminal serves **Ideogram 4.5 images** and **DeepSeek V4.1 Flash text** only. It has no video.
- Ideogram holds the reference's style, room and camera very well. Its edits
  drift less than about 0.5% in zoom, and `align_keys.py` corrects that drift.
- LTX-Video 2B runs locally on the M4. On large pose gaps it **ghosts the
  character** (a translucent crossfade instead of motion). Dense keyframes keep
  each gap small. This is the traditional key → in-between split: Ideogram plays
  the key/in-between animator and LTX does the final smoothing.

## Steps

1. `scripts/keyframes.py <spec> --n N --quality high --cap $`: generates N
   candidates per key with the Generate endpoint in edit mode. It's resumable and
   never resubmits paid jobs. 429 and 503 errors are uncharged and retried.
2. `scripts/align_keys.py <run_dir> <reference>`: ORB + RANSAC homography onto
   the reference camera at 1024×576. Writes `aligned/` and `alignment.json`.
3. `scripts/review_gaps.py <spec> <anchors.json>`: cropped A | candidates | B sheets for picking.
4. Midpoint rounds: give Ideogram both neighbors and ask for the exact halfway
   frame. Round 1 produces anchors, round 2 halves the gaps, round 3 quarters them.
5. `scripts/ltx_inbetween.py A B`: pins A at frame 0 and B at the last frame
   (`LTXVAddGuide`), and saves PNG frames.
6. `scripts/render_shot.py <keys.json>`: renders every segment and assembles `shot.mp4`.

## Specs and picks (bedroom door shot)

- Reference: `assets/references/ref3_latest_male_night.png` (the user's latest image).
- `specs/bedroom_door.json`: round 1 anchors. Picks: k1_sit_edge_05, k1_sit_edge_03,
  k2_stand_05, k3_walk_05, k4_handle_01, k5_door_open_01.
- `specs/bedroom_door_r2_mid.json`: round 2. Picks: a0a1=04, a1a2=01, a2a3=03, a3a4=05, a4a5=03, a5a6=05.
- `specs/bedroom_door_keys_v2.json`: the resulting 13-key sequence.
- `specs/bedroom_door_r3_quarter.json`: round 3 (24 gaps, 25 keys).

## Measurements (M4, 16 GB)

- LTX 768×448, 25 frames, 20 steps: **239 s**. Character ghosts across a big pose gap.
- LTX 1024×576, 25 frames, 40 steps: about 11.5 s per step, with heavy swap (21 GB).
- Ideogram high: $0.20 per image. In-flight and per-minute rate limits hit at
  about 16 images in flight.

## Known gaps

- `pick_inbetween.py`, the pixel-distance auto-picker, agreed with manual picks only
  1 time in 6. Don't trust it. Next options: a silhouette comparison against an empty-room
  plate, or a vision model (Gemini through `agy`) as the picker.
- DeepSeek text endpoint: the base URL isn't on the public docs, and the user
  needs to copy it from the dashboard.
