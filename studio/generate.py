"""Generate one shot: preflight -> upload -> submit -> poll -> download.

Never queues a job for a backend that failed preflight. Never treats an
image-only ComfyUI output as a finished video.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from studio.catalog import Backend, get_backend
from studio.comfy_client import ComfyClient, find_video_output
from studio.config import AppConfig
from studio.doctor import check_backend
from studio.manifest import Project, Shot, project_dir, save_project
from studio.workflow import inject_inputs, load_workflow, validate_workflow


class GenerateError(RuntimeError):
    pass


def _extract_last_frame(video_path: Path, out_png: Path) -> None:
    """Extract true last frame using ffprobe frame count + select, with reverse fallback."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    frame_count = None
    try:
        cmd_probe = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(video_path),
        ]
        res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        if out.isdigit():
            frame_count = int(out)
    except Exception:
        frame_count = None

    if frame_count is not None and frame_count > 0:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select=eq(n\\,{frame_count - 1})",
            "-vframes",
            "1",
            str(out_png),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 0:
            return

    # Fallback to reverse decode (robust for short clips)
    cmd_rev = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        "reverse",
        "-vframes",
        "1",
        str(out_png),
    ]
    res_rev = subprocess.run(cmd_rev, capture_output=True, text=True)
    if res_rev.returncode != 0 or not out_png.is_file() or out_png.stat().st_size == 0:
        raise GenerateError(f"ffmpeg could not extract last frame from {video_path}: {res_rev.stderr}")


def _validate_and_save_video(
    video_bytes: bytes, original_filename: str, out_path: Path, target_duration: float | None = None
) -> None:
    """Validate video decodability with ffprobe, trim to exact duration, and transcode to MP4."""
    ext = Path(original_filename).suffix.lower() or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = Path(tmp.name)

    try:
        cmd_probe = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(tmp_path),
        ]
        probe_res = subprocess.run(cmd_probe, capture_output=True, text=True)
        if probe_res.returncode != 0:
            raise GenerateError(
                f"downloaded video {original_filename} is not decodable by ffprobe: {probe_res.stderr}"
            )

        try:
            dur = float(probe_res.stdout.strip())
            if dur <= 0:
                raise GenerateError(f"downloaded video {original_filename} has invalid duration <= 0")
        except ValueError:
            raise GenerateError(
                f"downloaded video {original_filename} has unreadable duration: {probe_res.stdout.strip()}"
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(tmp_path)]
        if target_duration is not None and target_duration > 0:
            ffmpeg_cmd.extend(["-t", str(target_duration)])
        ffmpeg_cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)])

        trans_res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if trans_res.returncode != 0:
            raise GenerateError(f"ffmpeg transcode/trim failed: {trans_res.stderr}")

        verify_res = subprocess.run(cmd_probe[:-1] + [str(out_path)], capture_output=True, text=True)
        if verify_res.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            raise GenerateError(f"output video {out_path} is invalid after transcode/trim")
    finally:
        if tmp_path.is_file():
            tmp_path.unlink()


def _input_image_for_shot(project: Project, pdir: Path, shot: Shot) -> Path:
    if shot.index == 1:
        if not project.reference_image:
            raise GenerateError("project has no reference image; shot 1 needs a seed image")
        return pdir / project.reference_image

    prev = project.shot(shot.index - 1)
    if prev.status != "done" or not prev.output:
        raise GenerateError(
            f"shot {shot.index} needs shot {prev.index} to be generated first for continuity"
        )
    prev_video = pdir / prev.output
    frame_path = pdir / "jobs" / f"shot_{shot.index}_seed.png"
    _extract_last_frame(prev_video, frame_path)
    return frame_path


def generate_shot(
    config: AppConfig,
    projects_root: Path,
    project_name: str,
    shot_index: int,
    backend_key: str,
    smoke: bool = False,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
) -> Shot:
    from studio.manifest import load_project

    project = load_project(projects_root, project_name)
    pdir = project_dir(projects_root, project_name)
    shot = project.shot(shot_index)

    backend = get_backend(config.catalog_path, backend_key)
    client = ComfyClient(config.comfy_base_url, timeout=config.request_timeout)

    comfy_reachable = True
    try:
        client.system_stats()
    except Exception:
        comfy_reachable = False

    status = check_backend(backend, config, client, comfy_reachable)
    if not status.ready:
        shot.status = "failed"
        shot.error = "preflight failed: " + "; ".join(status.reasons)
        save_project(projects_root, project)
        raise GenerateError(shot.error)

    try:
        input_image = _input_image_for_shot(project, pdir, shot)
        graph = load_workflow(config.repo_root / backend.workflow_path)
        validate_workflow(graph, backend)

        upload_result = client.upload_image(input_image)
        graph = inject_inputs(
            graph,
            backend,
            image_filename=upload_result["name"],
            positive_prompt=shot.prompt,
            negative_prompt=shot.negative_prompt,
            duration=shot.duration,
            width=width,
            height=height,
            steps=steps,
            smoke=smoke,
        )

        shot.status = "queued"
        shot.backend = backend.key
        save_project(projects_root, project)

        prompt_id = client.submit_workflow(graph)
        shot.prompt_id = prompt_id
        shot.status = "running"
        save_project(projects_root, project)

        history = client.wait_for_completion(
            prompt_id, poll_interval=config.poll_interval, timeout=config.poll_timeout
        )
        video_output = find_video_output(history, backend.output_node_id, backend.output_keys)

        video_bytes = client.view_bytes(
            video_output["filename"],
            subfolder=video_output.get("subfolder", ""),
            folder_type=video_output.get("type", "output"),
        )
        out_rel = f"output/shot_{shot_index}.mp4"
        out_path = pdir / out_rel
        _validate_and_save_video(
            video_bytes=video_bytes,
            original_filename=video_output["filename"],
            out_path=out_path,
            target_duration=shot.duration,
        )

        shot.status = "done"
        shot.output = out_rel
        shot.error = None
    except Exception as exc:  # noqa: BLE001 - surface any failure as a failed shot, never fake success
        shot.status = "failed"
        shot.error = str(exc)
        save_project(projects_root, project)
        raise GenerateError(str(exc)) from exc

    save_project(projects_root, project)
    return shot

