"""Load and validate a ComfyUI API-format workflow graph against a backend's
declared node-id contract. Studio never constructs a graph from scratch —
it only accepts and fills in a real graph file that already exists on disk.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from studio.catalog import Backend


class WorkflowError(ValueError):
    pass


def load_workflow(workflow_path: Path) -> dict:
    if not workflow_path.is_file():
        raise WorkflowError(f"workflow file not found: {workflow_path}")
    try:
        graph = json.loads(workflow_path.read_text())
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"workflow file is not valid JSON: {workflow_path}: {exc}") from exc
    if not isinstance(graph, dict) or not graph:
        raise WorkflowError(f"workflow file is not a non-empty node map: {workflow_path}")
    for node_id, node in graph.items():
        if not isinstance(node, dict) or "class_type" not in node or "inputs" not in node:
            raise WorkflowError(f"node {node_id!r} is not a valid API-format node: {node}")
    return graph


def validate_workflow(graph: dict, backend: Backend) -> None:
    """Check that the configured node IDs exist in the graph with the expected class_type."""
    checks = [
        (backend.image_node_id, backend.image_node_class, "image node"),
        (backend.positive_prompt_node_id, None, "positive prompt node"),
        (backend.output_node_id, backend.output_node_class, "output node"),
    ]
    for node_id, expected_class, label in checks:
        if node_id is None:
            continue
        node = graph.get(node_id)
        if node is None:
            raise WorkflowError(f"{label} id {node_id!r} is not present in workflow graph")
        if expected_class and node.get("class_type") != expected_class:
            raise WorkflowError(
                f"{label} id {node_id!r} has class_type {node.get('class_type')!r}, "
                f"expected {expected_class!r}"
            )

    if backend.checkpoint_node_id:
        node = graph.get(backend.checkpoint_node_id)
        if node is None:
            raise WorkflowError(f"checkpoint node id {backend.checkpoint_node_id!r} not in graph")
        if backend.checkpoint_node_class and node.get("class_type") != backend.checkpoint_node_class:
            raise WorkflowError(
                f"checkpoint node id {backend.checkpoint_node_id!r} has class_type "
                f"{node.get('class_type')!r}, expected {backend.checkpoint_node_class!r}"
            )


def quantize_frame_count(
    target_frames: int, backend_key: str | None = None, node_class: str | None = None
) -> int:
    """Compute frame count satisfying LTX (8n+1) or Wan (4n+1) constraint."""
    if backend_key == "ltx" or node_class == "LTXVImgToVideo":
        n = max(1, round((target_frames - 1) / 8))
        return 8 * n + 1
    elif backend_key in ("wan2.2", "wan") or node_class == "Wan22ImageToVideoLatent":
        n = max(1, round((target_frames - 1) / 4))
        return 4 * n + 1
    return max(1, target_frames)


def find_duration_bindings(graph: dict, backend: Backend) -> dict[str, str | None]:
    """Derive duration, dimension, and step bindings from backend contract or known node classes."""
    # 1. Backend contract if specified
    if backend.latent_node_id and backend.latent_node_id in graph:
        return {
            "latent_node_id": backend.latent_node_id,
            "latent_length_key": backend.latent_length_key or "length",
            "latent_width_key": backend.latent_width_key or "width",
            "latent_height_key": backend.latent_height_key or "height",
            "steps_node_id": backend.steps_node_id,
            "steps_input_key": backend.steps_input_key or "steps",
            "fps_node_id": backend.fps_node_id,
            "fps_input_key": backend.fps_input_key or "fps",
            "conditioning_node_id": None,
            "conditioning_fps_key": None,
            "node_class": graph[backend.latent_node_id].get("class_type"),
        }

    # 2. Derive by known verified node classes
    # LTXVImgToVideo
    for node_id, node in graph.items():
        if node.get("class_type") == "LTXVImgToVideo":
            scheduler_id = next(
                (s_id for s_id, s_node in graph.items() if s_node.get("class_type") == "LTXVScheduler"),
                None,
            )
            video_id = next(
                (v_id for v_id, v_node in graph.items() if v_node.get("class_type") == "CreateVideo"),
                None,
            )
            conditioning_id = next(
                (c_id for c_id, c_node in graph.items() if c_node.get("class_type") == "LTXVConditioning"),
                None,
            )
            return {
                "latent_node_id": node_id,
                "latent_length_key": "length",
                "latent_width_key": "width",
                "latent_height_key": "height",
                "steps_node_id": scheduler_id,
                "steps_input_key": "steps",
                "fps_node_id": video_id,
                "fps_input_key": "fps",
                "conditioning_node_id": conditioning_id,
                "conditioning_fps_key": "frame_rate",
                "node_class": "LTXVImgToVideo",
            }

    # Wan22ImageToVideoLatent
    for node_id, node in graph.items():
        if node.get("class_type") == "Wan22ImageToVideoLatent":
            sampler_id = next(
                (
                    s_id
                    for s_id, s_node in graph.items()
                    if s_node.get("class_type") in ("KSampler", "KSamplerSelect")
                ),
                None,
            )
            video_id = next(
                (v_id for v_id, v_node in graph.items() if v_node.get("class_type") == "CreateVideo"),
                None,
            )
            return {
                "latent_node_id": node_id,
                "latent_length_key": "length",
                "latent_width_key": "width",
                "latent_height_key": "height",
                "steps_node_id": sampler_id,
                "steps_input_key": "steps",
                "fps_node_id": video_id,
                "fps_input_key": "fps",
                "conditioning_node_id": None,
                "conditioning_fps_key": None,
                "node_class": "Wan22ImageToVideoLatent",
            }

    # Video combining nodes without dedicated latent node
    for node_id, node in graph.items():
        if node.get("class_type") == "VHS_VideoCombine":
            return {
                "latent_node_id": None,
                "fps_node_id": node_id,
                "fps_input_key": "frame_rate",
                "node_class": "VHS_VideoCombine",
            }
        elif node.get("class_type") == "CreateVideo":
            return {
                "latent_node_id": None,
                "fps_node_id": node_id,
                "fps_input_key": "fps",
                "node_class": "CreateVideo",
            }

    return {}


def inject_inputs(
    graph: dict,
    backend: Backend,
    image_filename: str,
    positive_prompt: str,
    negative_prompt: str | None = None,
    duration: float | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    fps: int = 24,
    smoke: bool = False,
) -> dict:
    """Return a copy of graph with the image/prompt and duration/resolution inputs filled in."""
    graph = copy.deepcopy(graph)

    if backend.image_node_id:
        graph[backend.image_node_id]["inputs"]["image"] = image_filename

    if backend.positive_prompt_node_id:
        graph[backend.positive_prompt_node_id]["inputs"][
            backend.positive_prompt_input_key
        ] = positive_prompt

    if backend.negative_prompt_node_id and negative_prompt is not None:
        graph[backend.negative_prompt_node_id]["inputs"][
            backend.negative_prompt_input_key
        ] = negative_prompt

    has_duration_req = (
        duration is not None
        or smoke
        or width is not None
        or height is not None
        or steps is not None
    )
    if has_duration_req:
        bindings = find_duration_bindings(graph, backend)
        if not bindings:
            raise WorkflowError(
                f"cannot bind duration/resolution for backend {backend.key!r}: "
                "no verified node class or duration bindings found in workflow"
            )

        latent_id = bindings.get("latent_node_id")
        node_class = bindings.get("node_class")

        if latent_id and latent_id in graph:
            latent_node = graph[latent_id]["inputs"]
            if duration is not None:
                target_frames = int(round(duration * fps))
                quantized_length = quantize_frame_count(target_frames, backend.key, node_class)
                length_key = bindings.get("latent_length_key") or "length"
                latent_node[length_key] = quantized_length

            if smoke:
                if width is None:
                    width = 512 if node_class == "LTXVImgToVideo" else 640
                if height is None:
                    height = 320 if node_class == "LTXVImgToVideo" else 360
                if steps is None:
                    steps = 5

            width_key = bindings.get("latent_width_key") or "width"
            height_key = bindings.get("latent_height_key") or "height"
            if width is not None and width_key in latent_node:
                latent_node[width_key] = width
            if height is not None and height_key in latent_node:
                latent_node[height_key] = height

        steps_id = bindings.get("steps_node_id")
        steps_key = bindings.get("steps_input_key") or "steps"
        if steps is not None and steps_id and steps_id in graph:
            graph[steps_id]["inputs"][steps_key] = steps

        fps_id = bindings.get("fps_node_id")
        fps_key = bindings.get("fps_input_key") or "fps"
        if fps_id and fps_id in graph:
            graph[fps_id]["inputs"][fps_key] = fps

        cond_id = bindings.get("conditioning_node_id")
        cond_key = bindings.get("conditioning_fps_key") or "frame_rate"
        if cond_id and cond_id in graph:
            graph[cond_id]["inputs"][cond_key] = fps

    return graph


