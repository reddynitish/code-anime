"""A self-contained backend/catalog fixture for tests.

Deliberately independent of studio/data/models.json so that production
catalog edits (new real workflow mappings as Gemini installs backends)
never silently change what these tests exercise.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from studio.catalog import Backend, load_catalog

FIXTURE_BACKEND_ENTRY = {
    "key": "anisora",
    "name": "Fixture Backend",
    "kind": "local_comfyui",
    "enabled": True,
    "workflow_path": "runtime/workflows/anisora_i2v.json",
    "image_node_id": "10",
    "image_node_class": "LoadImage",
    "positive_prompt_node_id": "6",
    "positive_prompt_input_key": "text",
    "negative_prompt_node_id": "7",
    "negative_prompt_input_key": "text",
    "output_node_id": "20",
    "output_node_class": "VHS_VideoCombine",
    "output_keys": ["gifs", "videos"],
    "checkpoint_node_id": "4",
    "checkpoint_node_class": "CheckpointLoaderSimple",
    "checkpoint_input_key": "ckpt_name",
    "required_checkpoint": "anisora_v2.safetensors",
    "required_object_info_classes": ["LoadImage", "VHS_VideoCombine", "CheckpointLoaderSimple"],
}


def write_fixture_catalog(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"backends": [FIXTURE_BACKEND_ENTRY]}, indent=2))
    return path


def make_fixture_backend() -> Backend:
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"backends": [FIXTURE_BACKEND_ENTRY]}, f)
        path = Path(f.name)
    try:
        return load_catalog(path)[0]
    finally:
        path.unlink()
