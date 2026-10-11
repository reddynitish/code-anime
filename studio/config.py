"""Runtime configuration for the studio CLI/web UI.

Everything here is overridable via environment variables so the ComfyUI
endpoint, timeouts, and catalog location stay configurable without code
changes, per the project's "configurable Comfy API" requirement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from studio.paths import PROJECTS_ROOT, REPO_ROOT, STUDIO_ROOT


@dataclass(frozen=True)
class AppConfig:
    comfy_base_url: str
    request_timeout: float
    poll_interval: float
    poll_timeout: float
    projects_root: Path
    repo_root: Path
    catalog_path: Path
    server_port: int = 8787


def load_config() -> AppConfig:
    return AppConfig(
        comfy_base_url=os.environ.get("STUDIO_COMFY_URL", "http://127.0.0.1:8188").rstrip("/"),
        request_timeout=float(os.environ.get("STUDIO_REQUEST_TIMEOUT", "10")),
        poll_interval=float(os.environ.get("STUDIO_POLL_INTERVAL", "2")),
        poll_timeout=float(os.environ.get("STUDIO_POLL_TIMEOUT", "1800")),
        projects_root=Path(os.environ.get("STUDIO_PROJECTS_ROOT", str(PROJECTS_ROOT))),
        repo_root=REPO_ROOT,
        catalog_path=Path(
            os.environ.get("STUDIO_CATALOG_PATH", str(REPO_ROOT / "runtime" / "models.json"))
        ),
        server_port=int(os.environ.get("STUDIO_PORT", "8787")),
    )

