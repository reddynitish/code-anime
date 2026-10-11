"""Minimal client for a locally running ComfyUI server's real HTTP API.

Only the endpoints ComfyUI actually exposes are used:
  POST /upload/image   (multipart/form-data)
  POST /prompt          (JSON: {"prompt": <graph>, "client_id": <id>})
  GET  /history/{id}
  GET  /view            (?filename=&subfolder=&type=)
  GET  /object_info[/{class_type}]
  GET  /system_stats

No other hosts or endpoints are ever contacted by this module.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class ComfyError(RuntimeError):
    pass


class ComfyUnreachable(ComfyError):
    pass


class ComfyTimeout(ComfyError):
    pass


class ComfyExecutionError(ComfyError):
    pass


VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 10.0, client_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = client_id or uuid.uuid4().hex

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get_json(self, path: str) -> Any:
        req = urllib.request.Request(self._url(path), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise ComfyUnreachable(f"could not reach {self._url(path)}: {exc}") from exc

    def system_stats(self) -> dict:
        return self._get_json("/system_stats")

    def object_info(self, class_type: str | None = None) -> dict:
        path = "/object_info" if class_type is None else f"/object_info/{urllib.parse.quote(class_type)}"
        return self._get_json(path)

    def upload_image(self, image_path: Path, subfolder: str = "", overwrite: bool = True) -> dict:
        """Upload a local file via multipart/form-data to /upload/image.

        Returns the JSON response: {"name", "subfolder", "type"}.
        """
        image_path = Path(image_path)
        boundary = uuid.uuid4().hex
        content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        data = image_path.read_bytes()

        parts: list[bytes] = []

        def field(name: str, value: str) -> None:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode(
                    "utf-8"
                )
            )

        field("overwrite", "true" if overwrite else "false")
        field("type", "input")
        if subfolder:
            field("subfolder", subfolder)
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(data)
        parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        req = urllib.request.Request(
            self._url("/upload/image"),
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise ComfyUnreachable(f"upload failed: {exc}") from exc

    def submit_workflow(self, graph: dict) -> str:
        """POST a validated graph to /prompt. Returns the prompt_id."""
        payload = json.dumps({"prompt": graph, "client_id": self.client_id}).encode("utf-8")
        req = urllib.request.Request(
            self._url("/prompt"),
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ComfyExecutionError(f"/prompt rejected the graph ({exc.code}): {body}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise ComfyUnreachable(f"submit failed: {exc}") from exc

        if "error" in result:
            raise ComfyExecutionError(f"/prompt returned an error: {result['error']}")
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise ComfyExecutionError(f"/prompt response had no prompt_id: {result}")
        return prompt_id

    def get_history(self, prompt_id: str) -> dict | None:
        result = self._get_json(f"/history/{urllib.parse.quote(prompt_id)}")
        return result.get(prompt_id)

    def wait_for_completion(
        self, prompt_id: str, poll_interval: float = 2.0, timeout: float = 1800.0
    ) -> dict:
        """Poll /history/{id} until the job has outputs or fails. Returns the history entry."""
        deadline = time.monotonic() + timeout
        while True:
            entry = self.get_history(prompt_id)
            if entry is not None:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyExecutionError(f"job {prompt_id} failed: {status}")
                outputs = entry.get("outputs")
                if outputs:
                    return entry
            if time.monotonic() >= deadline:
                raise ComfyTimeout(f"job {prompt_id} did not complete within {timeout}s")
            time.sleep(poll_interval)

    def view_bytes(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        query = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": folder_type}
        )
        req = urllib.request.Request(self._url(f"/view?{query}"), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise ComfyUnreachable(f"view failed: {exc}") from exc


def find_video_output(history_entry: dict, output_node_id: str, output_keys: tuple[str, ...]) -> dict:
    """Pick a real video output from a history entry's outputs for one node.

    Rejects image-only outputs: raises ComfyExecutionError rather than ever
    returning an image file as if it were a video.
    """
    outputs = history_entry.get("outputs", {})
    node_outputs = outputs.get(output_node_id)
    if not node_outputs:
        raise ComfyExecutionError(f"no outputs recorded for node {output_node_id}")

    # Prefer the configured keys, but fall back to scanning every key so a
    # ComfyUI/node version that names the output list differently still
    # works — the video-ness check below is what actually gates acceptance.
    ordered_keys = list(output_keys) + [k for k in node_outputs if k not in output_keys]
    for key in ordered_keys:
        for item in node_outputs.get(key, []):
            filename = item.get("filename", "")
            fmt = item.get("format", "")
            ext = Path(filename).suffix.lower()
            if ext in VIDEO_EXTENSIONS or fmt.startswith("video/"):
                return item

    raise ComfyExecutionError(
        f"node {output_node_id} produced no video-typed output "
        f"(only found: {list(node_outputs.keys())}) — refusing to treat images as video"
    )
