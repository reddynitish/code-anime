"""A small, stdlib-only asset registry for Luminal image outputs.

This module is deliberately standalone: it does NOT touch backends
(`studio/catalog.py`), the project/shot manifest (`studio/manifest.py`), the
Kaggle runner/orchestrator, or any generation spec. It only records metadata
*about* already-produced assets so they can be catalogued, reviewed, and
reused — it never generates anything, contacts a model, or reads credentials.

Input format: real ``keyframes.py`` sidecars are JOB records (one job, one or
more image outputs), e.g.::

    {"key": "char_turn_front", "state": "completed", "quality": "high",
     "n": 1, "reserved_usd": 0.2, "charged_usd": "0.2000",
     "generation_id": "example-generation",
     "outputs": ["/abs/.../char_turn_front_00.png"]}

They carry no ``path``/``kind``/``review`` fields, so the importer takes one
asset per entry in ``outputs``, assigns a kind from the caller (default or an
explicit classification mapping), and splits the job cost across the outputs.

Important boundaries:
  * Images and video are kept separate. Luminal produces images only; it is
    NOT a verified video generator, so no asset here is ever labelled a video.
    The one video-adjacent kind, ``video_anchor``, is explicitly a still frame
    extracted from an *accepted* video shot, not a video.
  * Importing never implies acceptance. Imported assets start in the
    ``candidate`` review state and must be moved to ``accepted`` deliberately.
    Re-importing preserves any existing accepted/rejected decision.
  * Cost tracks ``reserved`` vs provider-reported ``charged`` USD separately and
    never claims a verified invoice (``invoice_verified`` is always False). The
    full job charge is split across its outputs, never counted once per output.
  * Nothing here claims a "character identity lock" or any guarantee of visual
    identity. ``character_id`` / ``scene_id`` are plain descriptive labels for
    grouping and reuse, with no correctness guarantee attached.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
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
    """Per-asset generation cost, keeping *reserved* and *charged* separate.

    * ``reserved`` is the amount the job set aside up-front (an estimate/hold).
    * ``charged`` is the amount the provider reported as actually charged.

    When a single job produces multiple outputs, each output carries only its
    *share* of the job totals (job total / number of outputs) so the full job
    charge is never counted once per output.

    ``invoice_verified`` is always False here: ``charged`` is a provider-reported
    figure from the job sidecar, not an audited/reconciled invoice. We never
    claim a verified invoice.
    """

    reserved: float = 0.0
    charged: float = 0.0
    unit: str = "usd"
    invoice_verified: bool = False  # provider-reported, not an audited invoice

    def validate(self) -> None:
        for name, value in (("reserved", self.reserved), ("charged", self.charged)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise AssetError(f"cost {name} must be a number, got {value!r}")
            if value < 0:
                raise AssetError(f"cost {name} must be >= 0, got {value}")
        if not self.unit or not str(self.unit).strip():
            raise AssetError("cost unit must be a non-empty string")
        if self.invoice_verified:
            # Defensive: nothing in this module may assert a verified invoice.
            raise AssetError("invoice_verified must be False; charged is provider-reported only")


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
    output_index: int | None = None  # which output of the job this asset is (0-based)
    source_output: str | None = None  # original (pre-normalization) output path from the job
    cost: Cost = field(default_factory=Cost)
    review_state: str = DEFAULT_REVIEW_STATE
    origin: str | None = None  # e.g. "luminal_image", "import_sidecar", "video_frame"
    created_at: float = field(default_factory=time.time)
    provenance: dict = field(default_factory=dict)  # preserved real job provenance

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
        if not isinstance(cost_data, dict):
            raise AssetError(f"cost must be an object, got {cost_data!r}")
        cost = Cost(
            reserved=cost_data.get("reserved", 0.0),
            charged=cost_data.get("charged", 0.0),
            unit=cost_data.get("unit", "usd"),
            invoice_verified=bool(cost_data.get("invoice_verified", False)),
        )
        return cls(
            asset_id=data["asset_id"],
            kind=data["kind"],
            path=data["path"],
            character_id=data.get("character_id"),
            scene_id=data.get("scene_id"),
            source_ids=list(data.get("source_ids", [])),
            model=data.get("model"),
            generation_id=data.get("generation_id"),
            output_index=data.get("output_index"),
            source_output=data.get("source_output"),
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

    def upsert(self, asset: Asset) -> tuple[Asset, bool]:
        """Insert ``asset``, or refresh an existing one with the same id.

        Returns ``(asset, created)``. Re-importing is idempotent: metadata is
        refreshed from the incoming record but the existing human
        ``review_state`` is preserved (a prior accepted/rejected decision is
        never silently reset by a repeat import).
        """
        asset.validate()
        for i, existing in enumerate(self.assets):
            if existing.asset_id == asset.asset_id:
                asset.review_state = existing.review_state  # preserve human decision
                asset.created_at = existing.created_at  # preserve first-seen time
                self.assets[i] = asset
                return asset, False
        self.assets.append(asset)
        return asset, True

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


# ---------------------------------------------------------------------------
# Importer for real keyframes.py job-record sidecars.
#
# A real sidecar is a JOB record, not an asset record. Example:
#   {"key": "char_turn_front", "state": "completed", "quality": "high",
#    "n": 1, "reserved_usd": 0.2, "charged_usd": "0.2000",
#    "generation_id": "example-generation",
#    "outputs": ["/abs/.../char_turn_front_00.png"]}
# One job may produce several outputs (``n`` of them in ``outputs``). We import
# ONE asset per output, splitting the job cost across the outputs so the full
# job charge is never counted once per output. There is no path/kind/review in
# the record; kind comes from the caller (default or an explicit mapping).
# ---------------------------------------------------------------------------


def _coerce_usd(value) -> float:
    """Parse a USD figure that may be a number or a string like ``"0.2000"``."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise AssetError(f"USD value must be numeric, got bool {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0.0
        try:
            return float(s)
        except ValueError:
            raise AssetError(f"USD value is not a number: {value!r}")
    raise AssetError(f"USD value has unsupported type {type(value).__name__}: {value!r}")


def _deterministic_asset_id(generation_id: str | None, key: str | None, index: int, output: str) -> str:
    """Stable id so re-importing the same job output is idempotent.

    Built from the generation id (or job key) plus the output index and path, so
    two different outputs of the same job never collide and a repeat import of
    the same output maps back to the same asset.
    """
    base = generation_id or key or "job"
    digest = hashlib.sha1(f"{base}|{index}|{output}".encode("utf-8")).hexdigest()[:12]
    label = (key or base).strip() or "job"
    return f"{label}#{index}-{digest}"


def _resolve_output_path(
    output: str, asset_root: Path | None
) -> tuple[str, str]:
    """Return ``(stored_path, source_output)`` for one job output.

    * A relative output is stored as-is (after rejecting ``..``/empty).
    * An absolute output is normalized to a path relative to ``asset_root`` —
      but ONLY when its real location resolves *inside* that approved root.
      This both enables normalization and rejects symlinks that escape the
      asset root. Without an ``asset_root``, absolute outputs are refused (we
      will not register an uncontrolled absolute path).
    """
    source_output = output
    p = Path(output)

    if not output or not output.strip():
        raise AssetError("job output path is empty")

    if not p.is_absolute():
        _validate_relative_path(output)
        return output, source_output

    # Absolute output: require an approved asset root to normalize against.
    if asset_root is None:
        raise AssetError(
            f"absolute output {output!r} requires an approved --asset-root to normalize against"
        )

    root_real = Path(os.path.realpath(asset_root))
    out_real = Path(os.path.realpath(output))  # resolves symlinks in the output path
    try:
        rel = out_real.relative_to(root_real)
    except ValueError:
        raise AssetError(
            f"output {output!r} resolves to {out_real} which is outside approved asset root {root_real} "
            "(possible symlink escape) — refusing to register"
        )
    rel_str = rel.as_posix()
    _validate_relative_path(rel_str)
    return rel_str, source_output


def _reject_symlinked_sidecar(sidecar: Path, sidecar_root: Path) -> None:
    """Reject a sidecar file that is a symlink pointing outside the sidecar root."""
    if sidecar.is_symlink():
        target_real = Path(os.path.realpath(sidecar))
        root_real = Path(os.path.realpath(sidecar_root))
        try:
            target_real.relative_to(root_real)
        except ValueError:
            raise AssetError(
                f"sidecar {sidecar.name} is a symlink escaping the approved sidecar root "
                f"{root_real} — refusing to read"
            )


def assets_from_job_record(
    data: dict,
    *,
    default_kind: str,
    classification: dict[str, str] | None = None,
    asset_root: Path | None = None,
    origin: str = "luminal_keyframe_job",
) -> list[Asset]:
    """Build one Asset per output in a keyframes.py job record.

    ``default_kind`` is used unless ``classification`` maps the job ``key`` (or
    an exact output path) to a specific kind. Cost is split evenly across the
    outputs. Review state always starts at the default (``candidate``) — this
    function never accepts.
    """
    if not isinstance(data, dict):
        raise AssetError(f"job record must be a JSON object, got {type(data).__name__}")

    outputs = data.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise AssetError("job record has no 'outputs' list to import")
    if any(not isinstance(o, str) for o in outputs):
        raise AssetError("job record 'outputs' must be a list of strings")

    key = data.get("key")
    generation_id = data.get("generation_id")
    classification = classification or {}

    n_outputs = len(outputs)
    reserved_total = _coerce_usd(data.get("reserved_usd"))
    charged_total = _coerce_usd(data.get("charged_usd"))
    # Per-output share so the full job charge is not counted once per output.
    reserved_share = reserved_total / n_outputs
    charged_share = charged_total / n_outputs

    # Job-level provenance preserved on every asset (real, unmodified fields).
    job_provenance = {
        "job_key": key,
        "job_state": data.get("state"),
        "job_quality": data.get("quality"),
        "job_n": data.get("n"),
        "job_outputs_count": n_outputs,
        "reserved_usd_job_total": reserved_total,
        "charged_usd_job_total": charged_total,
        "charged_usd_raw": data.get("charged_usd"),
    }

    assets: list[Asset] = []
    for index, output in enumerate(outputs):
        kind = classification.get(output) or (classification.get(key) if key else None) or default_kind
        if kind not in ASSET_KINDS:
            raise AssetError(f"unknown asset kind {kind!r}; expected one of {ASSET_KINDS}")

        stored_path, source_output = _resolve_output_path(output, asset_root)

        cost = Cost(
            reserved=reserved_share,
            charged=charged_share,
            unit="usd",
            invoice_verified=False,  # provider-reported, never a verified invoice
        )

        asset = Asset(
            asset_id=_deterministic_asset_id(generation_id, key, index, output),
            kind=kind,
            path=stored_path,
            character_id=None,
            scene_id=None,
            source_ids=[generation_id] if generation_id else [],
            model=data.get("model"),
            generation_id=generation_id,
            output_index=index,
            source_output=source_output,
            cost=cost,
            review_state=DEFAULT_REVIEW_STATE,
            origin=origin,
            provenance=dict(job_provenance),
        )
        asset.validate()
        assets.append(asset)
    return assets


def import_job_sidecars(
    registry: AssetRegistry,
    sidecar_dir: Path,
    *,
    default_kind: str,
    classification: dict[str, str] | None = None,
    asset_root: Path | None = None,
) -> tuple[list[Asset], int, int]:
    """Import every ``*.json`` job sidecar in ``sidecar_dir`` into ``registry``.

    Returns ``(assets, created_count, updated_count)``. Importing is idempotent
    (deterministic ids + upsert), and a repeat import preserves any existing
    accepted/rejected review state. Symlinked sidecars escaping ``sidecar_dir``
    are rejected, as are output symlinks escaping ``asset_root``.
    """
    sidecar_dir = Path(sidecar_dir)
    if not sidecar_dir.is_dir():
        raise AssetError(f"sidecar directory not found: {sidecar_dir}")
    if default_kind not in ASSET_KINDS:
        raise AssetError(f"unknown default kind {default_kind!r}; expected one of {ASSET_KINDS}")

    touched: list[Asset] = []
    created = updated = 0
    for sidecar in sorted(sidecar_dir.glob("*.json")):
        _reject_symlinked_sidecar(sidecar, sidecar_dir)
        try:
            data = json.loads(sidecar.read_text())
        except json.JSONDecodeError as exc:
            raise AssetError(f"sidecar {sidecar.name} is not valid JSON: {exc}") from exc
        try:
            built = assets_from_job_record(
                data,
                default_kind=default_kind,
                classification=classification,
                asset_root=asset_root,
            )
            for asset in built:
                _, was_created = registry.upsert(asset)
                created += int(was_created)
                updated += int(not was_created)
                touched.append(asset)
        except AssetError as exc:
            raise AssetError(f"sidecar {sidecar.name}: {exc}") from exc
    return touched, created, updated
