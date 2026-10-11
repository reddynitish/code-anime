import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from studio import webui


class WebUiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_env = dict(os.environ)
        os.environ["STUDIO_PROJECTS_ROOT"] = self._tmp.name
        os.environ["STUDIO_COMFY_URL"] = "http://127.0.0.1:1"  # intentionally unreachable
        os.environ["STUDIO_REQUEST_TIMEOUT"] = "1"

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), webui.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp.cleanup()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_server_binds_loopback_only(self):
        with self.assertRaises(ValueError):
            webui.run_server(host="0.0.0.0", port=0)

    def test_doctor_route_reports_unreachable_comfy(self):
        status, body = self._get("/api/doctor")
        self.assertEqual(status, 200)
        self.assertFalse(body["comfy_reachable"])
        seedance = next(b for b in body["backends"] if b["key"] == "seedance")
        self.assertFalse(seedance["ready"])

    def test_create_project_via_api(self):
        status, body = self._post("/api/projects", {"name": "webdemo"})
        self.assertEqual(status, 200)
        self.assertEqual(body["created"], "webdemo")
        self.assertEqual(body["shots"], 3)

        status, listing = self._get("/api/projects")
        self.assertIn("webdemo", listing)

    def test_media_path_traversal_is_rejected(self):
        self._post("/api/projects", {"name": "webdemo"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/media/webdemo/../../../etc/passwd", timeout=5
            )
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()

    def test_generate_rejects_non_local_backend(self):
        self._post("/api/projects", {"name": "webdemo"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/api/projects/webdemo/generate", {"shot": 1, "backend": "seedance"})
        self.assertEqual(ctx.exception.code, 400)
        with ctx.exception as err:
            body = json.loads(err.read().decode("utf-8"))
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()
