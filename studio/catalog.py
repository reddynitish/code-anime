"""Model backend catalog: AniSora, Wan2.2, LTX (local ComfyUI) and the
permanently-disabled Seedance cloud provider.

The node IDs and workflow paths here are the *contract* studio expects a real
ComfyUI export to satisfy. Studio never fabricates a graph: it only validates
whatever JSON file is actually present at `workflow_path` (owned by Gemini,
under runtime/) against this contract before using it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Backend:
    key: str
    name: str
    kind: str
    enabled: bool
    workflow_path: str | None = None
    image_node_id: str | None = None
    image_node_class: str | None = None
    positive_prompt_node_id: str | None = None
    positive_prompt_input_key: str = "text"
    negative_prompt_node_id: str | None = None
    negative_prompt_input_key: str = "text"
    output_node_id: str | None = None
    output_node_class: str | None = None
    output_keys: tuple[str, ...] = ()
    checkpoint_node_id: str | None = None
    checkpoint_node_class: str | None = None
    checkpoint_input_key: str | None = None
    required_checkpoint: str | None = None
    required_object_info_classes: tuple[str, ...] = ()
    required_files: tuple[dict[str, Any], ...] = ()
    latent_node_id: str | None = None
    latent_length_key: str | None = None
    latent_width_key: str | None = None
    latent_height_key: str | None = None
    steps_node_id: str | None = None
    steps_input_key: str | None = None
    fps_node_id: str | None = None
    fps_input_key: str | None = None
    disabled_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def load_catalog(catalog_path: Path) -> list[Backend]:
    data = json.loads(catalog_path.read_text())
    backends = []
    for entry in data["backends"]:
        backends.append(
            Backend(
                key=entry["key"],
                name=entry["name"],
                kind=entry["kind"],
                enabled=bool(entry.get("enabled", False)),
                workflow_path=entry.get("workflow_path"),
                image_node_id=entry.get("image_node_id"),
                image_node_class=entry.get("image_node_class"),
                positive_prompt_node_id=entry.get("positive_prompt_node_id"),
                positive_prompt_input_key=entry.get("positive_prompt_input_key", "text"),
                negative_prompt_node_id=entry.get("negative_prompt_node_id"),
                negative_prompt_input_key=entry.get("negative_prompt_input_key", "text"),
                output_node_id=entry.get("output_node_id"),
                output_node_class=entry.get("output_node_class"),
                output_keys=tuple(entry.get("output_keys", ())),
                checkpoint_node_id=entry.get("checkpoint_node_id"),
                checkpoint_node_class=entry.get("checkpoint_node_class"),
                checkpoint_input_key=entry.get("checkpoint_input_key"),
                required_checkpoint=entry.get("required_checkpoint"),
                required_object_info_classes=tuple(entry.get("required_object_info_classes", ())),
                required_files=tuple(entry.get("required_files", ())),
                latent_node_id=entry.get("latent_node_id"),
                latent_length_key=entry.get("latent_length_key"),
                latent_width_key=entry.get("latent_width_key"),
                latent_height_key=entry.get("latent_height_key"),
                steps_node_id=entry.get("steps_node_id"),
                steps_input_key=entry.get("steps_input_key"),
                fps_node_id=entry.get("fps_node_id"),
                fps_input_key=entry.get("fps_input_key"),
                disabled_reason=entry.get("disabled_reason"),
                raw=entry,
            )
        )
    return backends


def get_backend(catalog_path: Path, key: str) -> Backend:
    for backend in load_catalog(catalog_path):
        if backend.key == key:
            return backend
    raise KeyError(f"unknown backend: {key}")
