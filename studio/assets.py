"""A small, stdlib-only asset registry for Luminal image outputs.

This module is deliberately standalone: it does NOT touch backends
(`studio/catalog.py`), the project/shot manifest (`studio/manifest.py`), the
Kaggle runner/orchestrator, or any generation spec. It only records metadata
*about* already-produced assets so they can be catalogued, reviewed, and
reused — it never generates anything, contacts a model, or reads credentials.

Important boundaries:
  * Images and video are kept separate. Luminal produces images only; it is
    NOT a verified video generator, so no asset here is ever labelled a video.
    The one video-adjacent kind, ``video_anchor``, is explicitly a still frame
    extracted from an *accepted* video shot (recorded via ``source_ids``), not
    a video.
  * Importing never implies acceptance. Imported assets start in the
    ``candidate`` review state and must be moved to ``accepted`` deliberately.
  * Nothing here claims a "character identity lock" or any guarantee of visual
    identity. ``character_id`` / ``scene_id`` are plain descriptive labels for
    grouping and reuse, with no correctness guarantee attached.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

REGISTRY_FILENAME = "assets.json"

# Image kinds are distinct from the single video-adjacent kind. ``video_anchor``
# is a still frame taken from an accepted video shot — it is NOT a video asset.
IMAGE_KINDS = ("character", "background", "prop", "storyboard")
VIDEO_ANCHOR_KIND = "video_anchor"
ASSET_KINDS = IMAGE_KINDS + (VIDEO_ANCHOR_KIND,)

REVIEW_STATES = ("candidate", "accepted", "rejected")
# Importing a brand-new asset must never auto-accept it.
DEFAULT_REVIEW_STATE = "candidate"


class AssetError(ValueError):
    """Raised for any invalid asset metadata or registry operation."""


@dataclass
class Cost:
    """Generation cost with an explicit unit and whether it is estimated.

    ``recorded`` means the value came from the generator/batch log; otherwise
    it is a best-effort estimate. The distinction is preserved so downstream
    cost accounting never mistakes an estimate for an actual charge.
    """

    amount: float = 0.0
    unit: str = "credits"
    recorded: bool = False  # False => estimate, True => measured/charged

    def validate(self) -> None:
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool):
            raise AssetError(f"cost amount must be a number, got {self.amount!r}")
        if self.amount < 0:
            raise AssetError(f"cost amount must be >= 0, got {self.amount}")
        if not self.unit or not str(self.unit).strip():
            raise AssetError("cost unit must be a non-empty string")


@dataclass
class Asset:
    """A single reusable asset and its provenance.

    ``path`` is stored exactly as supplied (a project-relative or caller-chosen
    location). The registry validates that it is a sane relative path but does
    NOT require the file to exist locally — the cloud environment cannot see
    locally generated images, and import must work from metadata alone.
    """

    asset_id: str
    kind: str
    path: str
    character_id: str | None = None
    scene_id: str | None = None
    source_ids: list[str] = field(default_factory=list)  # lineage: parent asset/frame ids
    model: str | None = None  # e.g. a Luminal model name; left None until documented
    generation_id: str | None = None  # upstream generation/job id, if known
    cost: Cost = field(default_factory=Cost)
    review_state: str = DEFAULT_REVIEW_STATE
    origin: str | None = None  # e.g. "luminal_image", "import_sidecar", "video_frame"
    created_at: float = field(default_factory=time.time)
    provenance: dict = field(default_factory=dict)  # preserved unknown/extra sidecar keys

    def validate(self) -> None:
        if not self.asset_id or not str(self.asset_id).strip():
            raise AssetError("asset_id must be a non-empty string")
        if self.kind not in ASSET_KINDS:
            raise AssetError(f"unknown asset kind {self.kind!r}; expected one of {ASSET_KINDS}")
        _validate_relative_path(self.path)
        if self.review_state not in REVIEW_STATES:
            raise AssetError(
                f"invalid review_state {self.review_state!r}; expected one of {REVIEW_STATES}"
            )
        if not isinstance(self.source_ids, list) or any(
            not isinstance(s, str) for s in self.source_ids
        ):
            raise AssetError("source_ids must be a list of strings")
        self.cost.validate()

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Asset":
        cost_data = data.get("cost") or {}
        if isinstance(cost_data, dict):
            cost = Cost(
                amount=cost_data.get("amount", 0.0),
                unit=cost_data.get("unit", "credits"),
                recorded=bool(cost_data.get("recorded", False)),
            )
        else:
            raise AssetError(f"cost must be an object, got {cost_data!r}")
        return cls(
            asset_id=data["asset_id"],
            kind=data["kind"],
            path=data["path"],
            character_id=data.get("character_id"),
            scene_id=data.get("scene_id"),
            source_ids=list(data.get("source_ids", [])),
            model=data.get("model"),
            generation_id=data.get("generation_id"),
            cost=cost,
            review_state=data.get("review_state", DEFAULT_REVIEW_STATE),
            origin=data.get("origin"),
            created_at=data.get("created_at", time.time()),
            provenance=dict(data.get("provenance", {})),
        )


def _validate_relative_path(path: str) -> None:
    """Reject empty, absolute, or traversing paths without touching the filesystem.

    We never require the file to exist (the cloud cannot see local images), but
    we refuse paths that could escape a project directory if later resolved.
    """
    if not path or not str(path).strip():
        raise AssetError("asset path must be a non-empty string")
    p = Path(path)
    if p.is_absolute():
        raise AssetError(f"asset path must be relative, got absolute {path!r}")
    if ".." in p.parts:
        raise AssetError(f"asset path must not contain '..': {path!r}")


@dataclass
class AssetRegistry:
    assets: list[Asset] = field(default_factory=list)

    def by_id(self, asset_id: str) -> Asset:
        for a in self.assets:
            if a.asset_id == asset_id:
                return a
        raise AssetError(f"no asset with id {asset_id!r}")

    def add(self, asset: Asset) -> Asset:
        asset.validate()
        if any(a.asset_id == asset.asset_id for a in self.assets):
            raise AssetError(f"duplicate asset_id {asset.asset_id!r}")
        self.assets.append(asset)
        return asset

    def set_review_state(self, asset_id: str, state: str) -> Asset:
        if state not in REVIEW_STATES:
            raise AssetError(f"invalid review_state {state!r}; expected one of {REVIEW_STATES}")
        asset = self.by_id(asset_id)
        asset.review_state = state
        return asset

    def to_dict(self) -> dict:
        return {"assets": [a.to_dict() for a in self.assets]}

    @classmethod
    def from_dict(cls, data: dict) -> "AssetRegistry":
        return cls(assets=[Asset.from_dict(a) for a in data.get("assets", [])])


def registry_path(registry_dir: Path) -> Path:
    return Path(registry_dir) / REGISTRY_FILENAME


def load_registry(registry_dir: Path) -> AssetRegistry:
    path = registry_path(registry_dir)
    if not path.is_file():
        return AssetRegistry()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise AssetError(f"asset registry is not valid JSON: {path}: {exc}") from exc
    return AssetRegistry.from_dict(data)


def save_registry(registry_dir: Path, registry: AssetRegistry) -> Path:
    registry_dir = Path(registry_dir)
    registry_dir.mkdir(parents=True, exist_ok=True)
    path = registry_path(registry_dir)
    path.write_text(json.dumps(registry.to_dict(), indent=2))
    return path


# Keys the importer understands directly; everything else is preserved under
# ``provenance`` so no upstream information is silently dropped.
_KNOWN_SIDECAR_KEYS = {
    "asset_id",
    "kind",
    "path",
    "file",
    "filename",
    "character_id",
    "scene_id",
    "source_ids",
    "model",
    "generation_id",
    "cost",
    "cost_amount",
    "cost_unit",
    "cost_recorded",
    "origin",
    "review_state",
}


def asset_from_sidecar(data: dict, *, default_origin: str = "import_sidecar") -> Asset:
    """Build an Asset from a single keyframe job sidecar dict.

    The importer is tolerant: it accepts either a nested ``cost`` object or flat
    ``cost_amount``/``cost_unit``/``cost_recorded`` keys, resolves the asset
    file from ``path``/``file``/``filename``, generates an ``asset_id`` if the
    sidecar lacks one, and preserves every unrecognised key under
    ``provenance`` so lineage is never lost. It NEVER imports as accepted.
    """
    if not isinstance(data, dict):
        raise AssetError(f"sidecar must be a JSON object, got {type(data).__name__}")

    path = data.get("path") or data.get("file") or data.get("filename")
    if not path:
        raise AssetError("sidecar is missing an asset path (expected 'path', 'file', or 'filename')")

    kind = data.get("kind")
    if kind is None:
        raise AssetError("sidecar is missing required 'kind'")

    # Cost: nested object preferred, flat keys as a fallback.
    if isinstance(data.get("cost"), dict):
        c = data["cost"]
        cost = Cost(
            amount=c.get("amount", 0.0),
            unit=c.get("unit", "credits"),
            recorded=bool(c.get("recorded", False)),
        )
    else:
        cost = Cost(
            amount=data.get("cost_amount", 0.0),
            unit=data.get("cost_unit", "credits"),
            recorded=bool(data.get("cost_recorded", False)),
        )

    # Review state from a sidecar is clamped: importing must never auto-accept.
    requested_state = data.get("review_state", DEFAULT_REVIEW_STATE)
    if requested_state == "accepted":
        # Preserve the upstream claim as provenance but do not honour it.
        review_state = DEFAULT_REVIEW_STATE
    elif requested_state in REVIEW_STATES:
        review_state = requested_state
    else:
        review_state = DEFAULT_REVIEW_STATE

    provenance = {k: v for k, v in data.items() if k not in _KNOWN_SIDECAR_KEYS}
    if data.get("review_state") == "accepted":
        provenance["_imported_review_state_claim"] = "accepted"

    asset = Asset(
        asset_id=str(data.get("asset_id") or f"asset-{uuid.uuid4().hex[:12]}"),
        kind=kind,
        path=str(path),
        character_id=data.get("character_id"),
        scene_id=data.get("scene_id"),
        source_ids=list(data.get("source_ids", [])),
        model=data.get("model"),
        generation_id=data.get("generation_id"),
        cost=cost,
        review_state=review_state,
        origin=data.get("origin") or default_origin,
        provenance=provenance,
    )
    asset.validate()
    return asset


def import_sidecars(registry: AssetRegistry, sidecar_dir: Path) -> list[Asset]:
    """Import every ``*.json`` sidecar in ``sidecar_dir`` into ``registry``.

    Returns the newly added assets. Raises AssetError if the directory does not
    exist. Individual sidecars that are invalid raise AssetError naming the
    offending file, so a bad sidecar never silently corrupts the registry.
    """
    sidecar_dir = Path(sidecar_dir)
    if not sidecar_dir.is_dir():
        raise AssetError(f"sidecar directory not found: {sidecar_dir}")

    added: list[Asset] = []
    for sidecar in sorted(sidecar_dir.glob("*.json")):
        try:
            data = json.loads(sidecar.read_text())
        except json.JSONDecodeError as exc:
            raise AssetError(f"sidecar {sidecar.name} is not valid JSON: {exc}") from exc
        try:
            asset = asset_from_sidecar(data)
            registry.add(asset)
        except AssetError as exc:
            raise AssetError(f"sidecar {sidecar.name}: {exc}") from exc
        added.append(asset)
    return added
