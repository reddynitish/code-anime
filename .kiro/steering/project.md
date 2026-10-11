# Project Steering: Code Anime

## Project Context
- **Repository**: Private GitHub repo (`code-anime`).
- **Core Mission**: Local-first, reproducible anime shot production workflow.
- **Hardware Profile**: Apple Silicon M4, 16 GB unified memory. GPU availability in the Kiro Cloud environment has not been verified.

## Environment & Boundary Constraints
1. **Cloud & Network Boundaries**:
   - Kiro Cloud runs in a restricted repository-only network environment; external research and model weight downloads are blocked.
   - Kiro Cloud cannot reach Mac `localhost` / `127.0.0.1`. Do not attempt network calls to local Mac ports (e.g., ComfyUI on `8188` or studio server on `8787`).
   - GPU availability in the cloud runtime has not been verified; do not assume GPU hardware is present.
2. **Subprocess & CLI Preferences**:
   - Claude and Gemini must be invoked strictly via their CLIs (e.g. `agy` / CLI tools) or `loadout handoff`. Never attempt web browser automation unless explicitly requested by the user.
3. **No New Spending / Subscriptions; Existing Luminal Credits Allowed Within Caps**:
   - No new paid cloud API calls, no new subscriptions, and no new accounts (the Seedance backend remains permanently disabled by policy).
   - Exception: **existing, already-purchased Luminal image credits may be used** for image generation (character references, backgrounds, props, storyboards), subject to an explicit **per-batch cap** agreed before each batch. Spending must stay within already-owned credits — never top up, upgrade, or add a subscription.
   - Luminal is an **image** generator only; it is NOT a verified video generator. Do not route video generation through it, and do not assume its API/endpoint details until they are documented.
   - Record generation cost (estimated or actual, with units) and per-batch totals so credit usage stays auditable and within cap. Favour free, local tools whenever they suffice.
4. **Drawing & Asset Policy**:
   - Never reuse rejected old 2D drawings or hallucinate continuity.
   - Multi-frame sequences must maintain true visual continuity and character consistency.
5. **Delegation & Workflow Model**:
   - Delegate mechanical coding, file inspection, and tests to subagents / Kiro.
   - Main agent maintains authority, performs code reviews, and approves changes.
6. **Git & Privacy Hygiene**:
   - Never commit secrets, authentication tokens (e.g., `luminal.json` resides strictly outside repo in `~/.config/code-anime/luminal.json`), generated outputs (`output/*`), or session transcripts.

## Verification Command
To verify studio components and CLI contracts:
```bash
python3 -m unittest discover -s tests -p "test_studio*.py"
```
Ensure all 51+ unit tests pass without errors.
