"""Project/shot manifest: the on-disk project state, with path-safe I/O.

Layout under <projects_root>/<name>/:
  manifest.json
  input/reference.png     (copy of the original reference image only)
  output/shot_<n>.mp4      (per-shot generated clips)
  output/final.mp4          (assembled result)
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from studio.paths import UnsafePathError, ensure_dir, safe_join

MANIFEST_FILENAME = "manifest.json"


class ProjectError(ValueError):
    pass


@dataclass
class Shot:
    index: int
    start: float
    end: float
    description: str
    prompt: str
    negative_prompt: str = ""
    status: str = "planned"  # planned | queued | running | done | failed
    backend: str | None = None
    output: str | None = None  # path relative to project dir
    prompt_id: str | None = None
    error: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Project:
    name: str
    created_at: float
    reference_image: str | None  # path relative to project dir, or None
    shots: list[Shot] = field(default_factory=list)

    def shot(self, index: int) -> Shot:
        for s in self.shots:
            if s.index == index:
                return s
        raise ProjectError(f"no shot {index} in project {self.name}")

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        shots = [Shot(**s) for s in data.get("shots", [])]
        return cls(
            name=data["name"],
            created_at=data["created_at"],
            reference_image=data.get("reference_image"),
            shots=shots,
        )


def project_dir(projects_root: Path, name: str) -> Path:
    """Resolve the directory for an existing or about-to-be-created project.

    Does not create anything; callers that need the directory to exist must
    call ensure_dir explicitly (create_project does this).
    """
    if not name or any(c in name for c in "/\\") or name in (".", ".."):
        raise ProjectError(f"invalid project name: {name!r}")
    return safe_join(projects_root, name)


def manifest_path(projects_root: Path, name: str) -> Path:
    return project_dir(projects_root, name) / MANIFEST_FILENAME


def save_project(projects_root: Path, project: Project) -> Path:
    path = manifest_path(projects_root, project.name)
    path.write_text(json.dumps(project.to_dict(), indent=2))
    return path


def load_project(projects_root: Path, name: str) -> Project:
    path = manifest_path(projects_root, name)
    if not path.is_file():
        raise ProjectError(f"no project named {name!r} (no manifest at {path})")
    return Project.from_dict(json.loads(path.read_text()))


def list_projects(projects_root: Path) -> list[str]:
    root = ensure_dir(projects_root)
    names = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
            names.append(child.name)
    return names


def create_project(
    projects_root: Path, name: str, reference_source: Path | None, force: bool = False
) -> Project:
    pdir = project_dir(projects_root, name)
    mpath = pdir / MANIFEST_FILENAME
    if mpath.is_file() and not force:
        raise ProjectError(f"project {name!r} already exists; use force to overwrite")

    ensure_dir(pdir / "input")
    ensure_dir(pdir / "output")
    ensure_dir(pdir / "jobs")

    reference_image = None
    if reference_source is not None:
        reference_source = Path(reference_source)
        if not reference_source.is_file():
            raise ProjectError(f"reference image not found: {reference_source}")
        dest = safe_join(pdir, "input", "reference.png")
        shutil.copyfile(reference_source, dest)
        reference_image = "input/reference.png"

    project = Project(name=name, created_at=time.time(), reference_image=reference_image, shots=[])
    save_project(projects_root, project)
    return project


def resolve_project_media(projects_root: Path, name: str, relative_path: str) -> Path:
    """Resolve a project-relative media path safely, refusing escapes.

    relative_path must be a simple relative path like 'output/shot_1.mp4';
    UnsafePathError propagates for traversal attempts.
    """
    pdir = project_dir(projects_root, name)
    parts = Path(relative_path).parts
    if not parts:
        raise UnsafePathError("empty media path")
    return safe_join(pdir, *parts)
