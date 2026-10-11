# Kiro Starter Task: Studio Code Review & Implementation Grounding

## Task Objective
Perform a code review of the `studio/` subsystem and prepare the next local generation milestone grounded strictly in current repository capabilities and constraints.

## Current State Summary
- **Studio Subsystem (`studio/`)**: Local-first Python framework for ComfyUI integration (`doctor`, `plan`, `generate`, `assemble`, `serve`).
- **Backend Status**:
  - `ltx` (LTX-Video 2B): Weights and T5 text encoder present in local ComfyUI; preflight passing. Uses $8n + 1$ frame quantization.
  - `wan2.2` (Wan2.2 5B): Workflows ready; missing weights.
  - `anisora`: Missing custom nodes/weights.
  - `seedance`: Permanently disabled by policy (`cloud_disabled`). Zero paid calls allowed.
- **Pipeline v2 Status**: Hybrid keyframe generation with local in-betweening (`docs/PIPELINE_V2.md`). Pixel distance auto-picker (`pick_inbetween.py`) is unreliable.
- **Test Suite**: 51 studio unit tests passing locally via `python3 -m unittest discover -s tests -p "test_studio*.py"`.

## Constraints & Environment Rules
- **Hardware Target**: Apple Silicon M4, 16 GB unified memory.
- **Kiro Cloud Network & Host Isolation**:
  - Kiro Cloud cannot access Mac `localhost:8188` (ComfyUI) or `localhost:8787` (Studio server).
  - Repository-only network access: no external research, downloads, or external APIs.
  - GPU availability in Kiro Cloud has not been verified; mock or unit-test offline logic rather than assuming GPU availability.
- **CLI-Only Policy**: Use Claude/Gemini strictly via CLI; no web browser automation unless explicitly requested.
- **Cost & Assets**: No paid calls or new subscriptions. Never reuse rejected old 2D drawings.
- **Labor Delegation**: Labor tasks delegated to Kiro / subagents; main agent reviews and verifies all code before acceptance.
- **Hygiene**: Never commit secrets (e.g. `luminal.json` stored in `~/.config/code-anime/luminal.json`), generated video outputs (`output/`), or transcripts.

## Next Implementation Focus
1. **Code Review**:
   - Audit `studio/workflow.py`, `studio/generate.py`, and `studio/doctor.py` for edge cases in LTX-Video $8n + 1$ quantization, last-frame extraction via ffprobe, and decodability validation.
   - Verify proper error handling when running in environments without live ComfyUI access.
2. **Offline Mode & Test Hardening**:
   - Ensure all CLI commands gracefully handle unreachable ComfyUI instances with actionable exit messages.
   - Maintain 100% test pass rate on unit tests.
3. **In-Between Quality / Picker Improvements**:
   - Review gap-picking logic (`scripts/review_gaps.py` and `scripts/pick_inbetween.py`) to replace brittle pixel-distance picking with silhouette matching or structured visual analysis without paid APIs.

## Test Verification
Run the standard studio test discovery:
```bash
python3 -m unittest discover -s tests -p "test_studio*.py"
```
