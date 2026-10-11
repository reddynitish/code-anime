"""Minimal localhost-only web UI: stdlib http.server, vanilla JS, JSON API.

Binds to 127.0.0.1 only — never 0.0.0.0 or any other interface. Media is
served only from inside the requesting project's own directory via
safe_join; arbitrary filesystem paths are refused.
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from studio.assemble import AssembleError, assemble_project
from studio.config import load_config
from studio.doctor import run_doctor
from studio.generate import GenerateError, generate_shot
from studio.manifest import (
    ProjectError,
    create_project,
    list_projects,
    load_project,
    resolve_project_media,
    save_project,
)
from studio.paths import UnsafePathError
from studio.shotplan import default_bedroom_plan

import urllib.parse

_PROJECT_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_MUTEX = threading.Lock()


def get_project_lock(project_name: str) -> threading.Lock:
    with _LOCKS_MUTEX:
        if project_name not in _PROJECT_LOCKS:
            _PROJECT_LOCKS[project_name] = threading.Lock()
        return _PROJECT_LOCKS[project_name]


def _check_and_recover_stale_shots(config, project):
    """If server restarted while a shot was running/queued, mark manageable failed state."""
    lock = get_project_lock(project.name)
    if lock.locked():
        return
    changed = False
    for s in project.shots:
        if s.status in ("running", "queued"):
            s.status = "failed"
            s.error = "stale job interrupted by server restart"
            changed = True
    if changed:
        save_project(config.projects_root, project)


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Code Anime Studio</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}
code{background:#eee;padding:2px 4px}</style></head>
<body>
<h1>Code Anime Studio</h1>
<p>Free, local, multi-backend anime shot generation over a local ComfyUI server.</p>
<h2>Doctor</h2><pre id="doctor">loading...</pre>
<h2>Projects</h2>
<div id="projects">loading...</div>
<h3>Create project</h3>
<input id="newname" placeholder="project name">
<input id="newscene" placeholder="scene / story (optional)" style="width:300px">
<button onclick="createProject()">Plan 10s scene</button>
<pre id="log"></pre>
<script>
async function j(url, opts) { const r = await fetch(url, opts); return r.json(); }
async function refreshDoctor() {
  const d = await j('/api/doctor');
  document.getElementById('doctor').textContent = JSON.stringify(d, null, 2);
}
async function refreshProjects() {
  const names = await j('/api/projects');
  const el = document.getElementById('projects');
  el.innerHTML = '';
  for (const name of names) {
    const p = await j('/api/projects/' + encodeURIComponent(name));
    const div = document.createElement('div');
    let rows = p.shots.map(s => `<tr><td>${s.index}</td><td>${s.start}-${s.end}s</td>
      <td>${s.status}</td><td>${s.backend||''}</td>
      <td>${s.output ? `<a href="/media/${name}/${s.output}">play</a>` : ''}</td>
      <td><button onclick="generate('${name}',${s.index})">generate (anisora)</button></td></tr>`).join('');
    div.innerHTML = `<h3>${name}</h3><table><tr><th>#</th><th>time</th><th>status</th><th>backend</th><th>output</th><th></th></tr>${rows}</table>
      <button onclick="assemble('${name}')">assemble final</button>`;
    el.appendChild(div);
  }
}
async function createProject() {
  const name = document.getElementById('newname').value;
  const scene = document.getElementById('newscene').value;
  const r = await j('/api/projects', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, scene})});
  document.getElementById('log').textContent = JSON.stringify(r);
  refreshProjects();
}
async function generate(name, shot) {
  const r = await j(`/api/projects/${name}/generate`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({shot, backend:'anisora'})});
  document.getElementById('log').textContent = JSON.stringify(r);
}
async function assemble(name) {
  const r = await j(`/api/projects/${name}/assemble`, {method:'POST'});
  document.getElementById('log').textContent = JSON.stringify(r);
  refreshProjects();
}
refreshDoctor(); refreshProjects();
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "StudioHTTP/0.1"

    def log_message(self, fmt, *args):  # quieter default logging
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        config = load_config()
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(INDEX_HTML)
            return

        if path == "/api/doctor":
            report = run_doctor(config)
            self._send_json(
                {
                    "comfy_reachable": report.comfy_reachable,
                    "comfy_error": report.comfy_error,
                    "ffmpeg_present": report.ffmpeg_present,
                    "backends": [
                        {"key": b.key, "name": b.name, "ready": b.ready, "reasons": b.reasons}
                        for b in report.backends
                    ],
                }
            )
            return

        if path == "/api/projects":
            self._send_json(list_projects(config.projects_root))
            return

        if path.startswith("/api/projects/"):
            name = path[len("/api/projects/") :]
            try:
                project = load_project(config.projects_root, name)
                _check_and_recover_stale_shots(config, project)
            except ProjectError as exc:
                self._send_json({"error": str(exc)}, status=404)
                return
            self._send_json(
                {
                    "name": project.name,
                    "reference_image": project.reference_image,
                    "shots": [vars(s) for s in project.shots],
                }
            )
            return

        if path.startswith("/media/"):
            raw_rest = path[len("/media/") :]
            rest = urllib.parse.unquote(raw_rest)
            if "/" not in rest:
                self._send_json({"error": "expected /media/<project>/<relpath>"}, status=400)
                return
            name, relpath = rest.split("/", 1)
            try:
                file_path = resolve_project_media(config.projects_root, name, relpath)
            except (UnsafePathError, ProjectError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            if not file_path.is_file():
                self._send_json({"error": "not found"}, status=404)
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        config = load_config()
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/projects":
            body = self._read_json_body()
            name = body.get("name")
            scene = body.get("scene") or body.get("story")
            if not name:
                self._send_json({"error": "missing 'name'"}, status=400)
                return
            reference_source = config.repo_root / "assets" / "reference.png"
            if not reference_source.is_file():
                reference_source = None
            try:
                project = create_project(config.projects_root, name, reference_source)
            except ProjectError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            project.shots = default_bedroom_plan(scene=scene)
            save_project(config.projects_root, project)
            self._send_json({"created": project.name, "shots": len(project.shots)})
            return

        if path.endswith("/generate") and path.startswith("/api/projects/"):
            name = path[len("/api/projects/") : -len("/generate")]
            body = self._read_json_body()
            shot = body.get("shot")
            backend = body.get("backend")
            smoke = bool(body.get("smoke", False))
            if backend not in ("anisora", "wan2.2", "ltx"):
                self._send_json({"error": "backend must be a local, enabled backend"}, status=400)
                return

            lock = get_project_lock(name)
            if not lock.acquire(blocking=False):
                self._send_json({"error": f"project {name} is already generating a shot"}, status=409)
                return

            def _run():
                try:
                    generate_shot(config, config.projects_root, name, shot, backend, smoke=smoke)
                except (GenerateError, ProjectError, KeyError):
                    pass  # failure is recorded on the shot itself; nothing to fake here
                finally:
                    lock.release()

            threading.Thread(target=_run, daemon=True).start()
            self._send_json({"accepted": True, "project": name, "shot": shot, "backend": backend})
            return

        if path.endswith("/assemble") and path.startswith("/api/projects/"):
            name = path[len("/api/projects/") : -len("/assemble")]
            try:
                project = load_project(config.projects_root, name)
                out_path = assemble_project(config.projects_root, project)
            except (AssembleError, ProjectError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"assembled": str(out_path.relative_to(out_path.parents[1]))})
            return

        self._send_json({"error": "not found"}, status=404)


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("studio webui only binds to 127.0.0.1 (loopback)")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving on http://127.0.0.1:{port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

