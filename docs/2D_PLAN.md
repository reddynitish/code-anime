# Successive anime drawings — revised production plan

Use the newly supplied detailed 2D image as the source and permanent style/camera
reference. The rejected procedural 3D work is retained separately and not reused.

1. Connect Luminal's image-only Ideogram 4.5 Precise Edit API; save credentials
   outside this repository with owner-only permissions. Never call a video model.
2. Validate three anchor drawings: seated on the bed edge, standing in the aisle,
   and holding the open door. High quality costs $0.20 per delivered drawing.
3. Masks constrain edits to the old/new character area, then the doorway when
   opening. Keep foreground chair/window, lamp, desk and walls fixed. Use the original
   and approved neighboring drawings as references to reduce identity drift.
4. Produce intermediate successive pose drawings for the action: rest 0–0.8 s;
   sit up 0.8–2.0 s; turn and lower legs 2–3 s; stand 3–4 s; walk 4–7 s;
   reach 7–8 s; open 8–9.5 s; hold 9.5–10 s.
5. Target 120 drawings at 12 drawings/s. Hold each for two video frames at24fps.
   Assembly, timing, masking checks and encoding run locally. No optical-flow
   video generation and no substitute 3D render.
6. Inspect contact sheets and motion for doubled characters, anatomy errors,
   inconsistent footprints, moving furniture, costume drift, and door continuity.
   Rework failed drawings before final encoding; do not claim studio quality.

Budget: first pass limited to $15, including prototypes, key drawings and intermediate
edits. Accepted jobs and generation IDs persist under `output/2d/jobs/`. A network
failure after submission requires reconciliation rather than blind paid retries.

An image-editing model produces individual drawings remotely through Luminal;
Python coordinates them and FFmpeg builds the video locally. This is not entirely
local inference. It is explicitly an image-by-image production workflow.

Sources:
- https://www.luminal.com/pricing
- https://images.luminal.cloud/docs/
- https://developer.ideogram.ai/api-reference/images/precise-edit/ideogram-4-5
