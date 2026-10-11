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
3. **No Paid Services / New Subscriptions**:
   - Zero paid cloud API calls allowed (Seedance backend is permanently disabled by policy).
   - Only free, local generation tools or pre-existing configured pipelines are permitted.
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
