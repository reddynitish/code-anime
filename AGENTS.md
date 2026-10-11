# User preferences

- When the user asks to use Gemini or Claude, use their CLIs or the loadout-handoff skill. Do not use Gemini or Claude through a web browser unless the user explicitly requests browser access. This preference applies to research as well as coding.

# Project constraints

- The anime production workflow uses real video generation powered by local open weights (e.g. ComfyUI / LTX-Video). Zero paid calls permitted, and never reuse rejected old 2D frames.
- Luminal authentication is configured outside the repository in `~/.config/code-anime/luminal.json`. Never print or commit the key.
- Inspect generated video sequences and verify continuity and decodability before claiming finished animation quality.

<!-- loadout:handoff:start -->

## Handoff inbox

At the start of a session, and whenever you finish a task, run:

```bash
loadout handoff codex
```

If it lists pending tasks, work them in order and run the `loadout handoff --done`
command it prints for each one. If it reports none, continue as normal.

<!-- loadout:handoff:end -->
