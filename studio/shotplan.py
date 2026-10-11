"""Deterministic shot plans. No AI planning — these are fixed, explicit
templates. The default is the approved 10s bedroom scene: out of bed (3s),
walk across the room (4s), open the door (3s).
"""

from __future__ import annotations

from studio.manifest import Shot

STYLE_CLAUSE = (
    "Match the exact character design, outfit, color palette, lighting, and bedroom "
    "background from the reference image. Keep the room layout, furniture, and camera "
    "framing consistent across the whole scene."
)


def default_bedroom_plan(scene: str | None = None) -> list[Shot]:
    """The explicit 3+4+3 second scene, in order, starting at t=0.

    If scene is provided, custom text is incorporated clearly into the prompts
    without fake AI planning.
    """
    if scene and scene.strip():
        custom = scene.strip()
        return [
            Shot(
                index=1,
                start=0.0,
                end=3.0,
                description=f"Part 1: Initial action for scene: {custom}",
                prompt=(
                    f"{STYLE_CLAUSE} Beginning of scene: {custom}. "
                    "Shot 1/3: Character initiates movement in the room. Calm motion, 3 seconds."
                ),
                negative_prompt="extra limbs, deformed hands, flickering background, changing outfit",
            ),
            Shot(
                index=2,
                start=3.0,
                end=7.0,
                description=f"Part 2: Main action for scene: {custom}",
                prompt=(
                    f"{STYLE_CLAUSE} Middle of scene: {custom}. "
                    "Shot 2/3: Character continues action across the room, natural pacing, 4 seconds."
                ),
                negative_prompt="extra limbs, deformed hands, sliding feet, changing outfit, teleporting",
            ),
            Shot(
                index=3,
                start=7.0,
                end=10.0,
                description=f"Part 3: Resolving action for scene: {custom}",
                prompt=(
                    f"{STYLE_CLAUSE} End of scene: {custom}. "
                    "Shot 3/3: Character completes the action and reaches conclusion, 3 seconds."
                ),
                negative_prompt="extra limbs, deformed hands, door clipping through character, changing outfit",
            ),
        ]

    shots = [
        Shot(
            index=1,
            start=0.0,
            end=3.0,
            description="Character wakes and gets out of bed.",
            prompt=(
                f"{STYLE_CLAUSE} The character sits up in bed, swings their legs over the "
                "edge, and stands up beside the bed. Calm, early-morning motion, 3 seconds."
            ),
            negative_prompt="extra limbs, deformed hands, flickering background, changing outfit",
        ),
        Shot(
            index=2,
            start=3.0,
            end=7.0,
            description="Character walks across the room toward the door.",
            prompt=(
                f"{STYLE_CLAUSE} The character walks at a natural pace straight across the "
                "bedroom toward the door on the far wall, in a clear walking cycle, 4 seconds."
            ),
            negative_prompt="extra limbs, deformed hands, sliding feet, changing outfit, teleporting",
        ),
        Shot(
            index=3,
            start=7.0,
            end=10.0,
            description="Character reaches the door and opens it.",
            prompt=(
                f"{STYLE_CLAUSE} The character reaches for the door handle, turns it, and "
                "pushes the door open, revealing the space beyond. 3 seconds."
            ),
            negative_prompt="extra limbs, deformed hands, door clipping through character, changing outfit",
        ),
    ]
    return shots


def total_duration(shots: list[Shot]) -> float:
    return sum(s.duration for s in shots)
