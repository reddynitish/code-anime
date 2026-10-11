# Local anime practice shot — 2026-10-11

Goal: a 10-second local animation of the reference character getting out of bed,
walking to the rear right bedroom door, and opening it. No generated video,
no generated images, and no manual frame drawings.

## Approach

Reconstruct the reference as a stylized 3D set using Python and Blender. A single
image cannot supply hidden surfaces or a complete character, so this is a visual
reconstruction rather than a pixel-exact animation of the supplied illustration.

Procedural geometry is the reusable design stage. Articulated mesh parts and
joint targets replace hand-drawn poses. Explicit timed poses replace key drawings;
numeric interpolation replaces in-between drawing. Cel shading and outlines replace
inking/coloring. Blender renders local PNG frames; FFmpeg encodes the MP4.

## Shot

| Seconds | Action |
|---|---|
| 0–1 | Establish the man lying on the bed |
| 1–3 | Lift torso, sit, swing legs toward right edge |
| 3–4 | Plant feet and stand |
| 4–7 | Walk the clear aisle toward the bedroom door |
| 7–8 | Reach handle |
| 8–9.5 | Open hinged door while hand follows handle |
| 9.5–10 | Hold the open door |

## Implementation and checks

1. Preserve `assets/reference.png`; create room, bed, window, desk, lamp, posters.
2. Create gray-clothed, dark-haired articulated humanoid with face details.
3. Animate joint targets with foot plants and two-segment limb solving; attach hand
   target to the rotating handle for the opening phase.
4. Use a fixed exterior window camera. Render key action frames and inspect framing,
   bed clearance, foot placement, reach, and visible opening before full rendering.
5. Render 120 unique frames at 12 fps. Encode with duplicated frames to 24 fps.
6. Verify 10-second duration, dimensions, frame count, and representative frames.

Research: Blender's Shader to RGB supports non-photorealistic toon shading in EEVEE:
https://docs.blender.org/manual/en/latest/render/shader_nodes/color/shader_to_rgb.html

Gemini collaboration uses the installed `~/.local/bin/agy` CLI, not browser Gemini.
The first CLI request was blocked by headless file-read permissions; the follow-up
requests a text-only review without tool use. Its actual output is preserved separately.

This first deliverable tests the production pipeline. Detailed anime character
modeling, cloth simulation, and exact illustration matching remain later work.
