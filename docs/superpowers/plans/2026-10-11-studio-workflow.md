# Studio workflow — implementation plan (2026-10-11)

## Ownership
Claude owns: `studio/`, `tests/test_studio*`, `docs/STUDIO_WORKFLOW.md`, this plan file, `README.md`.
Gemini owns: `runtime/`, `scripts/setup_studio*`, `docs/MODEL_SETUP.md`, and installing ComfyUI + model
weights outside the repo. This plan does not create or edit any file in Gemini's scope, and does not
install inference dependencies.

## Why this supersedes prior work
`docs/PLAN.md`/`docs/2D_PLAN.md` describe a rejected Blender 3D reconstruction and a paid Luminal
image-edit pipeline. The human has now explicitly requested real video generation, which supersedes
the AGENTS.md "no video-generation APIs" rule for this workflow only. No previously generated frames
or drawings (`output/`, `assets/2d/`) are reused as inputs — only the original `assets/reference.png`.

## Architecture
A stdlib-only Python package `studio/` provides:
- `studio/manifest.py` — project/shot manifest model with path-traversal-safe file access.
- `studio/shotplan.py` — deterministic (non-AI) 3+4+3s shot plan for the bed→walk→door scene.
- `studio/catalog.py` + `studio/data/models.json` — backend catalog: AniSora, Wan2.2, LTX (local,
  ComfyUI-backed, disabled until a real workflow file + weights are present) and Seedance (cloud,
  permanently disabled — no paid calls).
- `studio/comfy_client.py` — urllib-based client for ComfyUI's real API: `/upload/image` (multipart),
  `/prompt`, `/history/{id}`, `/view`, `/object_info`, `/system_stats`. No other network calls.
- `studio/workflow.py` — loads a workflow API-format JSON from the path configured per backend and
  validates the configured node IDs actually exist with the expected `class_type` before any
  submission. Studio never invents a node graph; it only validates and fills in a graph that Gemini's
  ComfyUI export must provide at that path.
- `studio/doctor.py` — preflight: ComfyUI reachability, ffmpeg presence, per-backend workflow file +
  `/object_info` node/checkpoint presence. Reports NOT READY with the exact missing piece; never
  reports READY without live verification.
- `studio/generate.py` — preflight → upload reference/previous-frame image → inject prompt → submit →
  poll `/history` with timeout → require an actual video-typed output (reject image-only outputs) →
  download via `/view` → write under the project's own output dir.
- `studio/assemble.py` — ffmpeg concat (subprocess, argv list, no shell) of per-shot videos into a
  final cut; fails if any shot output is missing.
- `studio/webui.py` — stdlib `http.server`, bound to `127.0.0.1` only, serving a small vanilla-JS page
  and a JSON API over the same project/doctor/generate/assemble operations; media served only from
  inside the requesting project's own directory.
- `studio/cli.py` — subcommands `doctor`, `plan`, `serve`, `generate`, `status`, `assemble`.

## Default scene
`studio plan` with no scene override builds the approved 10s scene: character gets out of bed (0–3s),
walks across the room (3–7s), opens the door (7–10s). `assets/reference.png` is copied once into the
new project's `input/` dir as the only seed image (never `output/2d/*`).

## Tests (offline, no real ComfyUI/network)
`tests/test_studio_*.py` (`unittest`, stdlib only) spin up a fake ComfyUI HTTP server on
`127.0.0.1:0` to cover: multipart upload, submit/poll/download happy path, rejection of image-only
("not a video") outputs, rejection when a required checkpoint/node is missing from `/object_info`
(must fail before `/prompt` is ever called), manifest path-safety against traversal, and that Seedance
is never selectable/queued. `assemble` is tested against real tiny ffmpeg-generated clips since ffmpeg
is already present on this machine.

## Honesty constraints carried into code
- No mock/fake "success" paths in production code — only in test fixtures, clearly separated under
  `tests/fixtures/`.
- `doctor`/`generate` report backend status from live checks only, never from assumption.
- Seedance stays `enabled: false` with a stated reason; nothing routes to it.
