"""A tiny fake ComfyUI HTTP server for offline tests.

Implements just enough of the real API surface (system_stats, object_info,
upload/image, prompt, history, view) to exercise studio.comfy_client and
studio.generate without any real network access or real ComfyUI install.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


def _parse_multipart(body: bytes, boundary: str) -> dict:
    """Minimal multipart/form-data parser sufficient for our own client's output."""
    delim = ("--" + boundary).encode("utf-8")
    fields: dict[str, dict] = {}
    for chunk in body.split(delim):
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        if b"\r\n\r\n" not in chunk:
            continue
        header_part, _, content = chunk.partition(b"\r\n\r\n")
        content = content[:-2] if content.endswith(b"\r\n") else content
        headers = header_part.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        filename_match = re.search(r'filename="([^"]+)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        if filename_match:
            fields[name] = {"filename": filename_match.group(1), "content": content}
        else:
            fields[name] = {"value": content.decode("utf-8", errors="replace")}
    return fields


class FakeComfyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    @property
    def state(self):
        return self.server.state  # type: ignore[attr-defined]

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        state = self.state

        if path == "/system_stats":
            if state.get("unreachable"):
                self.connection.close()
                return
            self._send_json({"system": {"os": "fake"}})
            return

        if path == "/object_info":
            self._send_json(state["object_info"])
            return

        if path.startswith("/object_info/"):
            class_type = path[len("/object_info/") :]
            self._send_json({class_type: state["object_info"].get(class_type, {})})
            return

        if path.startswith("/history/"):
            prompt_id = path[len("/history/") :]
            entry = state["history"].get(prompt_id)
            self._send_json({prompt_id: entry} if entry else {})
            return

        if path == "/view":
            filename = query.get("filename", [""])[0]
            state["view_calls"].append(dict(filename=filename, subfolder=query.get("subfolder", [""])[0],
                                             type=query.get("type", [""])[0]))
            data = state["view_files"].get(filename, b"")
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        state = self.state
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)

        if path == "/upload/image":
            content_type = self.headers.get("Content-Type", "")
            boundary_match = re.search(r"boundary=(.+)$", content_type)
            boundary = boundary_match.group(1) if boundary_match else ""
            fields = _parse_multipart(body, boundary)
            image_field = fields.get("image", {})
            state["uploads"].append(
                {"filename": image_field.get("filename"), "content": image_field.get("content")}
            )
            self._send_json({"name": image_field.get("filename", "upload.png"), "subfolder": "", "type": "input"})
            return

        if path == "/prompt":
            payload = json.loads(body.decode("utf-8"))
            state["prompt_calls"].append(payload)
            if state.get("reject_prompt"):
                self._send_json({"error": state["reject_prompt"]}, status=400)
                return
            prompt_id = f"fake-prompt-{len(state['prompt_calls'])}"
            state["last_prompt_id"] = prompt_id
            self._send_json({"prompt_id": prompt_id, "number": len(state["prompt_calls"])})
            return

        self._send_json({"error": "not found"}, status=404)


class FakeComfyServer:
    def __init__(self):
        self.state = {
            "object_info": {},
            "history": {},
            "prompt_calls": [],
            "uploads": [],
            "view_calls": [],
            "view_files": {},
            "unreachable": False,
            "reject_prompt": None,
            "last_prompt_id": None,
        }
        self._server = HTTPServer(("127.0.0.1", 0), FakeComfyHandler)
        self._server.state = self.state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://127.0.0.1:{port}"

    def __enter__(self) -> "FakeComfyServer":
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
