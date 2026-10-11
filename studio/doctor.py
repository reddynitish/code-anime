"""Live preflight checks. Every READY/NOT READY verdict here comes from an
actual check performed at call time — never an assumption, never a stub."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from studio.catalog import Backend, load_catalog
from studio.comfy_client import ComfyClient, ComfyError
from studio.config import AppConfig
from studio.workflow import WorkflowError, load_workflow, validate_workflow


@dataclass
class BackendStatus:
    key: str
    name: str
    ready: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class DoctorReport:
    comfy_reachable: bool
    comfy_error: str | None
    ffmpeg_present: bool
    backends: list[BackendStatus]

    def all_ready(self) -> bool:
        return self.comfy_reachable and self.ffmpeg_present and any(b.ready for b in self.backends)


def check_backend(
    backend: Backend, config: AppConfig, client: ComfyClient, comfy_reachable: bool
) -> BackendStatus:
    reasons: list[str] = []

    if not backend.enabled or backend.kind == "cloud_disabled":
        return BackendStatus(
            backend.key,
            backend.name,
            ready=False,
            reasons=[backend.disabled_reason or "disabled by policy"],
        )

    if backend.workflow_path is None:
        return BackendStatus(backend.key, backend.name, ready=False, reasons=["no workflow_path configured"])

    workflow_file = config.repo_root / backend.workflow_path
    try:
        graph = load_workflow(workflow_file)
        validate_workflow(graph, backend)
    except WorkflowError as exc:
        reasons.append(str(exc))

    if not comfy_reachable:
        reasons.append(f"ComfyUI unreachable at {config.comfy_base_url}")
    else:
        try:
            info = client.object_info()
        except ComfyError as exc:
            reasons.append(f"/object_info failed: {exc}")
            info = {}
        missing_classes = [c for c in backend.required_object_info_classes if c not in info]
        if missing_classes:
            reasons.append(f"missing custom nodes: {missing_classes}")

        if backend.required_checkpoint and backend.checkpoint_node_class:
            node_info = info.get(backend.checkpoint_node_class, {})
            options = (
                node_info.get("input", {})
                .get("required", {})
                .get(backend.checkpoint_input_key, [[]])
            )
            available = options[0] if options else []
            if backend.required_checkpoint not in available:
                reasons.append(
                    f"checkpoint {backend.required_checkpoint!r} not found among "
                    f"{backend.checkpoint_node_class} options"
                )

        for req_file in backend.required_files:
            filename = req_file.get("filename")
            if not filename:
                continue
            role = req_file.get("role", "").lower()
            target_dir = req_file.get("target_dir", "").lower()

            loader_class = None
            input_key = None
            if role in ("checkpoint", "model") or "checkpoints" in target_dir:
                loader_class = backend.checkpoint_node_class or "CheckpointLoaderSimple"
                input_key = backend.checkpoint_input_key or "ckpt_name"
            elif role in ("diffusion_model", "unet") or "diffusion_models" in target_dir:
                loader_class = "UNETLoader"
                input_key = "unet_name"
            elif role in ("text_encoder", "clip") or "clip" in target_dir or "text_encoders" in target_dir:
                loader_class = "CLIPLoader"
                input_key = "clip_name"
            elif role in ("vae",) or "vae" in target_dir:
                loader_class = "VAELoader"
                input_key = "vae_name"
            else:
                reasons.append(f"required file {filename!r}: unknown loader class for role {role!r}")
                continue

            if loader_class not in info:
                reasons.append(f"loader node {loader_class!r} not found in ComfyUI for {filename!r}")
            else:
                loader_opts = (
                    info[loader_class]
                    .get("input", {})
                    .get("required", {})
                    .get(input_key, [[]])
                )
                available = loader_opts[0] if loader_opts else []
                if filename not in available:
                    reasons.append(f"required file {filename!r} not found in {loader_class} options")

    return BackendStatus(backend.key, backend.name, ready=not reasons, reasons=reasons)



def run_doctor(config: AppConfig) -> DoctorReport:
    client = ComfyClient(config.comfy_base_url, timeout=config.request_timeout)
    comfy_reachable = True
    comfy_error = None
    try:
        client.system_stats()
    except ComfyError as exc:
        comfy_reachable = False
        comfy_error = str(exc)

    backends = load_catalog(config.catalog_path)
    statuses = [check_backend(b, config, client, comfy_reachable) for b in backends]

    return DoctorReport(
        comfy_reachable=comfy_reachable,
        comfy_error=comfy_error,
        ffmpeg_present=shutil.which("ffmpeg") is not None,
        backends=statuses,
    )


def format_report(report: DoctorReport) -> str:
    lines = []
    lines.append(f"ComfyUI: {'REACHABLE' if report.comfy_reachable else 'UNREACHABLE'}" +
                  (f" ({report.comfy_error})" if report.comfy_error else ""))
    lines.append(f"ffmpeg: {'present' if report.ffmpeg_present else 'MISSING'}")
    for b in report.backends:
        verdict = "READY" if b.ready else "NOT READY"
        lines.append(f"  [{verdict}] {b.name} ({b.key})")
        for reason in b.reasons:
            lines.append(f"      - {reason}")
    return "\n".join(lines)
