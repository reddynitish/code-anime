"""studio CLI: doctor, plan, serve, generate, status, assemble."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from studio.assemble import AssembleError, assemble_project
from studio.config import load_config
from studio.doctor import format_report, run_doctor
from studio.generate import GenerateError, generate_shot
from studio.manifest import Project, ProjectError, create_project, load_project, save_project
from studio.shotplan import default_bedroom_plan


def _pid_file_path(projects_root: Path) -> Path:
    return projects_root / "studio_server.pid"


def _log_file_path(projects_root: Path) -> Path:
    return projects_root / "studio_server.log"


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config()
    report = run_doctor(config)
    print(format_report(report))
    if args.project:
        try:
            project = load_project(config.projects_root, args.project)
            print(f"\nProject {project.name!r}: {len(project.shots)} shots")
            for shot in project.shots:
                print(f"  shot {shot.index} [{shot.start}-{shot.end}s]: {shot.status}")
        except ProjectError as exc:
            print(f"\nProject check failed: {exc}")
    return 0 if report.all_ready() else 1


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config()
    reference_source = Path(args.reference) if args.reference else (config.repo_root / "assets" / "reference.png")
    if not reference_source.is_file():
        reference_source = None
        print("warning: no reference image found; shot 1 will need --reference at generate time")

    try:
        project = create_project(config.projects_root, args.project, reference_source, force=args.force)
    except ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    project.shots = default_bedroom_plan(scene=args.scene)
    save_project(config.projects_root, project)

    print(f"Created project {project.name!r} with {len(project.shots)} shots:")
    for shot in project.shots:
        print(f"  shot {shot.index}: {shot.start}-{shot.end}s — {shot.description}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        project = load_project(config.projects_root, args.project)
    except ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Project {project.name!r} (reference: {project.reference_image})")
    for shot in project.shots:
        line = f"  shot {shot.index} [{shot.start}-{shot.end}s] backend={shot.backend} status={shot.status}"
        if shot.output:
            line += f" output={shot.output}"
        if shot.error:
            line += f" error={shot.error}"
        print(line)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        shot = generate_shot(
            config, config.projects_root, args.project, args.shot, args.backend, smoke=args.smoke
        )
    except (GenerateError, ProjectError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"shot {shot.index} done: {shot.output}")
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        project = load_project(config.projects_root, args.project)
        out_path = assemble_project(config.projects_root, project)
    except (AssembleError, ProjectError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"assembled: {out_path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from studio.webui import run_server

    run_server(port=args.port)
    return 0


def cmd_server(args: argparse.Namespace) -> int:
    config = load_config()
    pid_file = _pid_file_path(config.projects_root)
    log_file = _log_file_path(config.projects_root)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    action = args.action or "status"

    if action == "start":
        if pid_file.is_file():
            try:
                old_pid = int(pid_file.read_text().strip())
                os.kill(old_pid, 0)
                print(f"[service] studio server already running (PID {old_pid}) on port {args.port}")
                return 0
            except (OSError, ValueError):
                pid_file.unlink(missing_ok=True)

        print(f"[service] Starting studio server on 127.0.0.1:{args.port}...")
        log_handle = open(log_file, "a")
        proc = subprocess.Popen(
            [sys.executable, "-m", "studio", "serve", "--port", str(args.port)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        pid_file.write_text(str(proc.pid))

        # Wait briefly for startup
        started = False
        for _ in range(20):
            time.sleep(0.1)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/doctor", timeout=1) as resp:
                    if resp.status == 200:
                        started = True
                        break
            except Exception:
                pass
        if started:
            print(f"[service] Started studio server with PID {proc.pid}. Responding on http://127.0.0.1:{args.port}")
            return 0
        else:
            print(f"[service] Studio server process started (PID {proc.pid}), check {log_file}")
            return 0

    elif action == "stop":
        if pid_file.is_file():
            try:
                pid = int(pid_file.read_text().strip())
                print(f"[service] Stopping studio server (PID {pid})...")
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            except (OSError, ValueError):
                pass
            pid_file.unlink(missing_ok=True)
            print("[service] Stopped.")
        else:
            print("[service] No PID file found.")
        return 0

    elif action == "status":
        if pid_file.is_file():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                print(f"[service] studio server is RUNNING (PID {pid}) on http://127.0.0.1:{args.port}")
                return 0
            except OSError:
                print(f"[service] Stale PID file found (process {pid} dead).")
                pid_file.unlink(missing_ok=True)
        print("[service] studio server is NOT running.")
        return 1

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="check ComfyUI, ffmpeg, and backend readiness")
    p.add_argument("--project", default=None)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("plan", help="create a project with the default bedroom shot plan")
    p.add_argument("--project", required=True)
    p.add_argument("--reference", default=None, help="path to a reference image (default: assets/reference.png)")
    p.add_argument("--scene", default=None, help="custom scene or story description to incorporate into prompts")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("status", help="show a project's shot statuses")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("generate", help="generate one shot via a ComfyUI backend")
    p.add_argument("--project", required=True)
    p.add_argument("--shot", required=True, type=int)
    p.add_argument("--backend", required=True, choices=["anisora", "wan2.2", "ltx"])
    p.add_argument("--smoke", action="store_true", help="use small smoke test values (fast steps/res)")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("assemble", help="concatenate generated shots into a final cut")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("serve", help="run the local web UI (binds 127.0.0.1 only)")
    p.add_argument("--port", type=int, default=8787)
    p.set_defaults(func=cmd_serve)

    p_srv = sub.add_parser("server", help="manage the studio web UI background service")
    p_srv.add_argument("action", choices=["start", "stop", "status"], default="status", nargs="?")
    p_srv.add_argument("--port", type=int, default=8787)
    p_srv.set_defaults(func=cmd_server)

    return parser



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
