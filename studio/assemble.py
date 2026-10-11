"""Assemble per-shot videos into a final cut with ffmpeg (argv list, no shell)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from studio.manifest import Project, project_dir


class AssembleError(RuntimeError):
    pass


def assemble_project(
    projects_root: Path, project: Project, width: int = 832, height: int = 480, fps: int = 24
) -> Path:
    pdir = project_dir(projects_root, project.name)

    if not project.shots:
        raise AssembleError("project has no shots planned")

    missing = [s.index for s in project.shots if s.status != "done" or not s.output]
    if missing:
        raise AssembleError(f"shots not yet generated: {missing}")

    inputs: list[Path] = []
    for shot in sorted(project.shots, key=lambda s: s.index):
        path = pdir / shot.output
        if not path.is_file():
            raise AssembleError(f"missing output file for shot {shot.index}: {path}")
        inputs.append(path)

    out_path = pdir / "output" / "final.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y"]
    for p in inputs:
        cmd += ["-i", str(p)]

    filter_parts = []
    concat_inputs = []
    for i in range(len(inputs)):
        filter_parts.append(f"[{i}:v]scale={width}:{height},fps={fps},setsar=1[v{i}]")
        concat_inputs.append(f"[v{i}]")
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(inputs)}:v=1:a=0[outv]")
    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssembleError(f"ffmpeg assembly failed: {result.stderr}")

    return out_path
