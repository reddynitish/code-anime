"""Path helpers, including traversal-safe joins for project-local media."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIO_ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = STUDIO_ROOT / "projects"


class UnsafePathError(ValueError):
    """Raised when a requested path would escape its intended base directory."""


def safe_join(base: Path, *parts: str) -> Path:
    """Join parts onto base, refusing to escape base via `..`, symlinks, or absolute parts.

    Raises UnsafePathError instead of silently clamping, so callers cannot
    accidentally serve or write outside the intended directory.
    """
    base = base.resolve()
    candidate = base
    for part in parts:
        if not part or part in (".", ".."):
            raise UnsafePathError(f"unsafe path segment: {part!r}")
        p = Path(part)
        if p.is_absolute() or ".." in p.parts:
            raise UnsafePathError(f"unsafe path segment: {part!r}")
        candidate = candidate / p
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise UnsafePathError(f"path {resolved} escapes base {base}") from None
    return resolved


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
