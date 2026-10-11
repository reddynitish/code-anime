#!/usr/bin/env python3
"""Bounded Kaggle Wan 2.2 Orchestration CLI.

Orchestrates headless Wan 2.2 image-to-video / first-last-frame generation
on Kaggle's free GPU tier via ComfyUI.

Subcommands:
  prepare   Package dataset and kernel metadata into staging without credentials.
  submit    Push dataset and kernel to Kaggle (explicit action, requires credentials file).
  status    Check or poll kernel execution status (bounded timeout).
  download  Retrieve kernel output files, verifying MP4 fingerprints for skipping.

Ownership:
  Owned exclusively by Codex per AGENTS.md / docs/KAGGLE_WAN.md.
  Never reads or prints Kaggle API keys or tokens.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = WORKSPACE_ROOT / "staging" / "kaggle_wan"
DEFAULT_KAGGLE_BIN = WORKSPACE_ROOT / "runtime" / "hfclient" / "bin" / "kaggle"
CREDENTIALS_PATHS = [
    Path.home() / ".kaggle" / "kaggle.json",
    Path.home() / ".kaggle" / "access_token",
]

OWNER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


def get_kaggle_bin() -> str:
    """Return path to kaggle CLI binary."""
    if DEFAULT_KAGGLE_BIN.is_file() and os.access(DEFAULT_KAGGLE_BIN, os.X_OK):
        return str(DEFAULT_KAGGLE_BIN)
    sys_bin = shutil.which("kaggle")
    if sys_bin:
        return sys_bin
    return str(DEFAULT_KAGGLE_BIN)


def check_credentials_presence() -> bool:
    """Check if credentials file or environment variable exists.

    CRITICAL SECURITY RULE: NEVER read or print the contents of these files.
    """
    if os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("KAGGLE_KEY"):
        return True
    for p in CREDENTIALS_PATHS:
        if p.is_file():
            return True
    return False


def validate_owner(owner: Optional[str]) -> str:
    """Validate username or extract from Kaggle CLI config without reading keys."""
    if owner:
        owner_clean = owner.strip()
        if not OWNER_PATTERN.match(owner_clean):
            raise ValueError(
                f"Invalid owner name '{owner}'. Must match {OWNER_PATTERN.pattern}"
            )
        return owner_clean

    # Try extracting username from `kaggle config view`
    kaggle_bin = get_kaggle_bin()
    if check_credentials_presence():
        try:
            res = subprocess.run(
                [kaggle_bin, "config", "view"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            for line in res.stdout.splitlines():
                if line.strip().startswith("user:"):
                    detected = line.split(":", 1)[1].strip()
                    if detected and OWNER_PATTERN.match(detected):
                        return detected
        except Exception:
            pass

    raise ValueError(
        "Kaggle owner not provided and cannot be inferred. "
        "Provide explicit --owner <username> (no guessing allowed)."
    )


def get_git_commit() -> str:
    """Get current git commit hash for version provenance."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown-commit"


def validate_image_path(image_str: str, base_dir: Path, allowed_root: Optional[Path] = None) -> Path:
    """Ensure image path exists and does not traverse outside the workspace."""
    root = (allowed_root or WORKSPACE_ROOT).resolve()
    if Path(image_str).is_absolute():
        p = Path(image_str).resolve()
    else:
        # Check relative to base_dir first, then relative to WORKSPACE_ROOT
        cand1 = (base_dir / image_str).resolve()
        cand2 = (WORKSPACE_ROOT / image_str).resolve()
        if cand1.is_file():
            p = cand1
        elif cand2.is_file():
            p = cand2
        else:
            p = cand1  # for error message

    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError(f"Path traversal detected: {image_str} is outside allowed root {root}")
    if not p.is_file():
        raise FileNotFoundError(f"Keyframe image not found: {image_str} (resolved to {p})")
    return p


def is_valid_mp4_fingerprint(path: Path) -> bool:
    """Validate that path points to a non-corrupt, valid MP4 video.

    Checks minimum size (> 1024 bytes) and ISO Base Media File Format box header ('ftyp').
    """
    if not path.is_file():
        return False
    try:
        if path.stat().st_size < 1024:
            return False
        with open(path, "rb") as f:
            header = f.read(12)
            if len(header) < 12:
                return False
            # Standard MP4 box header: bytes 4-8 are 'ftyp'
            if header[4:8] == b"ftyp":
                return True
            # Alternative: QuickTime or raw container box
            if header[4:8] in (b"moov", b"mdat", b"wide"):
                return True
    except Exception:
        return False
    return False


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_prepare(args: argparse.Namespace) -> int:
    """Prepare dataset packaging and kernel staging."""
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        sys.stderr.write(f"Manifest file not found: {manifest_path}\n")
        return 1

    with open(manifest_path, "r", encoding="utf-8") as f:
        raw_manifest = json.load(f)

    jobs = raw_manifest.get("jobs", raw_manifest) if isinstance(raw_manifest, dict) else raw_manifest
    if not isinstance(jobs, list) or len(jobs) == 0:
        sys.stderr.write("Invalid manifest: must contain a non-empty list of jobs.\n")
        return 1

    try:
        owner = validate_owner(args.owner)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    staging_dir = Path(args.staging_dir).resolve()
    ds_dir = staging_dir / "dataset"
    img_dir = ds_dir / "img"
    kernel_dir = staging_dir / "kernel"

    if not args.dry_run:
        img_dir.mkdir(parents=True, exist_ok=True)
        kernel_dir.mkdir(parents=True, exist_ok=True)

    prepared_jobs: List[Dict[str, Any]] = []
    allowed_root = Path(getattr(args, "allowed_root", None)).resolve() if getattr(args, "allowed_root", None) else WORKSPACE_ROOT

    for i, job in enumerate(jobs):
        job_id = job.get("id", f"job_{i:02d}")
        if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
            sys.stderr.write(f"Invalid job ID '{job_id}'. Must be alphanumeric.\n")
            return 1

        prompt = job.get("prompt", "")
        if not prompt:
            sys.stderr.write(f"Job {job_id} is missing 'prompt'.\n")
            return 1

        start_img_rel = job.get("image") or job.get("start_image")
        if not start_img_rel:
            sys.stderr.write(f"Job {job_id} is missing 'image' or 'start_image'.\n")
            return 1

        try:
            start_path = validate_image_path(start_img_rel, manifest_path.parent, allowed_root=allowed_root)
        except Exception as e:
            sys.stderr.write(f"Job {job_id} start image error: {e}\n")
            return 1

        staged_start_name = f"{job_id}_start{start_path.suffix}"
        if not args.dry_run:
            shutil.copy2(start_path, img_dir / staged_start_name)

        job_entry: Dict[str, Any] = {
            "id": job_id,
            "prompt": prompt,
            "negative": job.get("negative"),
            "image": f"img/{staged_start_name}",
            "seconds": float(job.get("seconds", 3.5)),
            "width": int(job.get("width", 832)),
            "height": int(job.get("height", 480)),
            "seed": int(job.get("seed", 42)),
        }

        end_img_rel = job.get("end_image")
        if end_img_rel:
            try:
                end_path = validate_image_path(end_img_rel, manifest_path.parent, allowed_root=allowed_root)
            except Exception as e:
                sys.stderr.write(f"Job {job_id} end image error: {e}\n")
                return 1
            staged_end_name = f"{job_id}_end{end_path.suffix}"
            if not args.dry_run:
                shutil.copy2(end_path, img_dir / staged_end_name)
            job_entry["end_image"] = f"img/{staged_end_name}"

        prepared_jobs.append(job_entry)

    git_commit = get_git_commit()
    dataset_slug = args.dataset_slug
    kernel_slug = args.kernel_slug

    ds_metadata = {
        "title": f"Code Anime Wan Jobs {dataset_slug}",
        "id": f"{owner}/{dataset_slug}",
        "licenses": [{"name": "CC0-1.0"}],
        "isPrivate": True,
    }

    kernel_metadata = {
        "id": f"{owner}/{kernel_slug}",
        "title": kernel_slug,
        "code_file": "wan_runner.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": getattr(args, "machine_shape", None) if isinstance(getattr(args, "machine_shape", None), str) else "NvidiaTeslaT4",
        "dataset_sources": [f"{owner}/{dataset_slug}"],
    }

    runner_src = WORKSPACE_ROOT / "kaggle" / "wan_runner.py"
    if not runner_src.is_file():
        sys.stderr.write(f"Runner source not found: {runner_src}\n")
        return 1

    if not args.dry_run:
        (ds_dir / "jobs.json").write_text(json.dumps(prepared_jobs, indent=2), encoding="utf-8")
        (ds_dir / "dataset-metadata.json").write_text(json.dumps(ds_metadata, indent=2), encoding="utf-8")
        shutil.copy2(runner_src, kernel_dir / "wan_runner.py")
        (kernel_dir / "kernel-metadata.json").write_text(json.dumps(kernel_metadata, indent=2), encoding="utf-8")

        summary_manifest = {
            "status": "prepared",
            "git_commit": git_commit,
            "owner": owner,
            "dataset_ref": f"{owner}/{dataset_slug}",
            "kernel_ref": f"{owner}/{kernel_slug}",
            "job_count": len(prepared_jobs),
            "jobs": prepared_jobs,
            "timestamp": time.time(),
        }
        (staging_dir / "staging_manifest.json").write_text(json.dumps(summary_manifest, indent=2), encoding="utf-8")

    print(f"Staging complete for {len(prepared_jobs)} jobs.")
    print(f"  Dataset: {owner}/{dataset_slug} (private)")
    print(f"  Kernel:  {owner}/{kernel_slug} (private, GPU, internet enabled)")
    print(f"  Git ref: {git_commit}")
    print(f"  Target:  {staging_dir}")
    if args.dry_run:
        print("  (Dry-run mode: no files written)")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    """Submit staged dataset and kernel to Kaggle."""
    staging_dir = Path(args.staging_dir).resolve()
    ds_dir = staging_dir / "dataset"
    kernel_dir = staging_dir / "kernel"

    if not (ds_dir / "dataset-metadata.json").is_file():
        sys.stderr.write(f"Dataset not prepared in {ds_dir}. Run prepare first.\n")
        return 1
    if not (kernel_dir / "kernel-metadata.json").is_file():
        sys.stderr.write(f"Kernel not prepared in {kernel_dir}. Run prepare first.\n")
        return 1

    # Check credentials presence (never inspect or print keys)
    has_creds = check_credentials_presence()
    if not has_creds:
        sys.stderr.write(
            "\n[SUBMISSION_BLOCKED] Kaggle credentials absent.\n"
            "Requirements:\n"
            "  1. Verified phone on Kaggle account.\n"
            "  2. Valid token configured in ~/.kaggle/kaggle.json or KAGGLE_API_TOKEN env.\n"
            "Refusing to make unauthenticated calls or upload files.\n"
        )
        return 1

    kaggle_bin = get_kaggle_bin()
    print(f"Using Kaggle CLI: {kaggle_bin}")

    if args.dry_run:
        print("[DRY-RUN] Submission commands that would run:")
        print(f"  $ {kaggle_bin} datasets create -p {ds_dir} (or version)")
        print(f"  $ {kaggle_bin} kernels push -p {kernel_dir}")
        return 0

    # Read kernel metadata to check kernel status
    kernel_meta_data = json.loads((kernel_dir / "kernel-metadata.json").read_text(encoding="utf-8"))
    kernel_slug_ref = kernel_meta_data.get("id")
    if kernel_slug_ref:
        check_active = subprocess.run([kaggle_bin, "kernels", "status", kernel_slug_ref], capture_output=True, text=True, check=False)
        out_active = (check_active.stdout or check_active.stderr).lower()
        if any(term in out_active for term in ("running", "queued")):
            sys.stderr.write(f"\n[SUBMISSION_BLOCKED] Active kernel job already in progress for {kernel_slug_ref}:\n{check_active.stdout.strip()}\nDo not submit duplicate active kernel job.\n")
            return 1

    # 1. Dataset push (use -r zip to preserve subdirectories like img/)
    ds_cmd = [kaggle_bin, "datasets", "version", "-p", str(ds_dir), "-r", "zip", "-m", f"update_{int(time.time())}"]
    print(f"Pushing dataset ({ds_dir})...")
    res_ds = subprocess.run(ds_cmd, capture_output=True, text=True, check=False)
    if res_ds.returncode != 0:
        # If version failed, try initial create
        print("Dataset version failed, attempting create...")
        create_cmd = [kaggle_bin, "datasets", "create", "-p", str(ds_dir), "-r", "zip"]
        res_create = subprocess.run(create_cmd, capture_output=True, text=True, check=False)
        if res_create.returncode != 0:
            sys.stderr.write(f"Dataset creation failed:\n{res_create.stderr or res_create.stdout}\n")
            return 1
        print(res_create.stdout.strip())
    else:
        print(res_ds.stdout.strip())

    # 2. Kernel push
    kernel_cmd = [kaggle_bin, "kernels", "push", "-p", str(kernel_dir)]
    print(f"Pushing kernel ({kernel_dir})...")
    res_kernel = subprocess.run(kernel_cmd, capture_output=True, text=True, check=False)
    if res_kernel.returncode != 0:
        sys.stderr.write(f"Kernel push failed:\n{res_kernel.stderr or res_kernel.stdout}\n")
        return 1
    print(res_kernel.stdout.strip())

    # Detect if Kaggle created a different slug from URL (e.g. kaggle.com/code/owner/actual-slug)
    pushed_ref = kernel_slug_ref
    match_url = re.search(r"kaggle\.com/code/([^/\s]+)/([^/\s]+)", res_kernel.stdout)
    if match_url:
        pushed_ref = f"{match_url.group(1)}/{match_url.group(2)}"

    # Update manifest
    manifest_file = staging_dir / "staging_manifest.json"
    if manifest_file.is_file():
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest_data["status"] = "submitted"
        manifest_data["submitted_at"] = time.time()
        if pushed_ref:
            manifest_data["kernel_ref"] = pushed_ref
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    print("Submission completed successfully.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Check status of Kaggle kernel."""
    kernel_ref = args.kernel
    if not kernel_ref:
        staging_dir = Path(args.staging_dir).resolve()
        manifest_file = staging_dir / "staging_manifest.json"
        if manifest_file.is_file():
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            kernel_ref = data.get("kernel_ref")
    if not kernel_ref:
        sys.stderr.write("Kernel reference required: specify --kernel <owner>/<kernel-slug>.\n")
        return 1

    kaggle_bin = get_kaggle_bin()
    if not check_credentials_presence():
        sys.stderr.write("Kaggle credentials not found. Status check cannot be performed.\n")
        return 1

    timeout_s = args.timeout
    interval_s = args.interval
    poll = args.poll
    t0 = time.time()

    while True:
        res = subprocess.run([kaggle_bin, "kernels", "status", kernel_ref], capture_output=True, text=True, check=False)
        raw_out = (res.stdout or res.stderr).strip()
        print(f"[{time.strftime('%H:%M:%S')}] {kernel_ref}: {raw_out}")

        status_lower = raw_out.lower()
        if not poll:
            return 0 if res.returncode == 0 else 1

        if any(term in status_lower for term in ("complete", "finished", "ready")):
            print("Kernel execution completed successfully.")
            return 0
        if any(term in status_lower for term in ("error", "failed", "cancel")):
            print("Kernel execution failed or was canceled.")
            return 2

        if time.time() - t0 >= timeout_s:
            sys.stderr.write(f"Polling timed out after {timeout_s}s.\n")
            return 3

        time.sleep(interval_s)


def cmd_download(args: argparse.Namespace) -> int:
    """Download kernel outputs and verify fingerprint."""
    kernel_ref = args.kernel
    staging_dir = Path(args.staging_dir).resolve()
    manifest_file = staging_dir / "staging_manifest.json"
    manifest_data: Dict[str, Any] = {}
    if manifest_file.is_file():
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not kernel_ref:
            kernel_ref = manifest_data.get("kernel_ref")

    if not kernel_ref:
        sys.stderr.write("Kernel reference required: specify --kernel <owner>/<kernel-slug>.\n")
        return 1

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    kaggle_bin = get_kaggle_bin()
    if not check_credentials_presence():
        sys.stderr.write("Kaggle credentials not found. Download cannot be performed.\n")
        return 1

    print(f"Downloading outputs for {kernel_ref} to {out_dir}...")
    res = subprocess.run([kaggle_bin, "kernels", "output", kernel_ref, "-p", str(out_dir)],
                         capture_output=True, text=True, check=False)
    if res.returncode != 0:
        sys.stderr.write(f"Download failed: {res.stderr or res.stdout}\n")
        return 1

    print(res.stdout.strip())

    # Check results.json if produced
    results_file = out_dir / "results.json"
    if results_file.is_file():
        try:
            results = json.loads(results_file.read_text(encoding="utf-8"))
            print(f"\nExecution summary ({len(results)} jobs):")
            for r in results:
                status_str = "OK" if r.get("ok") else f"FAILED: {r.get('error', '')[:100]}"
                print(f"  - {r.get('id')}: {status_str}")
        except Exception as e:
            print(f"Could not parse results.json: {e}")

    # Verify and report MP4 files with fingerprint check
    mp4_files = list(out_dir.glob("**/*.mp4"))
    print(f"\nDownloaded {len(mp4_files)} MP4 file(s):")
    for f in mp4_files:
        valid = is_valid_mp4_fingerprint(f)
        size_kb = f.stat().st_size / 1024
        status_msg = "VALID FINGERPRINT" if valid else "CORRUPT/INVALID"
        print(f"  - {f.name} ({size_kb:.1f} KB): {status_msg}")

    return 0


# ── Main Entrypoint ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bounded Kaggle Wan 2.2 Orchestration CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subs = p.add_subparsers(dest="command", required=True)

    # prepare
    p_prep = subs.add_parser("prepare", help="Prepare dataset & kernel staging")
    p_prep.add_argument("--manifest", required=True, help="Path to jobs manifest JSON")
    p_prep.add_argument("--staging-dir", default=str(DEFAULT_STAGING), help="Staging output directory")
    p_prep.add_argument("--owner", help="Kaggle owner username (alphanumeric)")
    p_prep.add_argument("--dataset-slug", default="code-anime-jobs-wan", help="Dataset slug")
    p_prep.add_argument("--kernel-slug", default="code-anime-wan-runner", help="Kernel slug")
    p_prep.add_argument("--machine-shape", default="NvidiaTeslaT4", help="Kaggle machine shape (e.g. NvidiaTeslaT4, NvidiaTeslaP100)")
    p_prep.add_argument("--dry-run", action="store_true", help="Validate without writing files")

    # submit
    p_sub = subs.add_parser("submit", help="Submit staged jobs to Kaggle")
    p_sub.add_argument("--staging-dir", default=str(DEFAULT_STAGING), help="Staging output directory")
    p_sub.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    # status
    p_stat = subs.add_parser("status", help="Check kernel execution status")
    p_stat.add_argument("--kernel", help="Kernel reference <owner>/<kernel-slug>")
    p_stat.add_argument("--staging-dir", default=str(DEFAULT_STAGING), help="Staging output directory")
    p_stat.add_argument("--poll", action="store_true", help="Poll until completion or timeout")
    p_stat.add_argument("--timeout", type=int, default=1800, help="Max poll timeout in seconds")
    p_stat.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")

    # download
    p_down = subs.add_parser("download", help="Download kernel outputs")
    p_down.add_argument("--kernel", help="Kernel reference <owner>/<kernel-slug>")
    p_down.add_argument("--staging-dir", default=str(DEFAULT_STAGING), help="Staging output directory")
    p_down.add_argument("--out-dir", default=str(WORKSPACE_ROOT / "output" / "wan_kaggle"), help="Output directory")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "prepare":
        sys.exit(cmd_prepare(args))
    elif args.command == "submit":
        sys.exit(cmd_submit(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))
    elif args.command == "download":
        sys.exit(cmd_download(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
