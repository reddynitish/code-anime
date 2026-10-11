import tempfile
import unittest
from pathlib import Path

from studio.comfy_client import (
    ComfyClient,
    ComfyExecutionError,
    ComfyUnreachable,
    find_video_output,
)
from tests.fixtures.fake_comfy_server import FakeComfyServer


class ComfyClientTests(unittest.TestCase):
    def test_upload_submit_poll_download_happy_path(self):
        with FakeComfyServer() as server:
            client = ComfyClient(server.base_url, timeout=5)

            with tempfile.TemporaryDirectory() as tmp:
                img_path = Path(tmp) / "seed.png"
                img_path.write_bytes(b"fake-png-bytes")

                upload = client.upload_image(img_path)
                self.assertEqual(upload["name"], "seed.png")
                self.assertEqual(len(server.state["uploads"]), 1)
                self.assertEqual(server.state["uploads"][0]["content"], b"fake-png-bytes")

                prompt_id = client.submit_workflow({"1": {"class_type": "X", "inputs": {}}})
                self.assertEqual(len(server.state["prompt_calls"]), 1)

                server.state["history"][prompt_id] = {
                    "status": {"status_str": "success"},
                    "outputs": {"20": {"gifs": [{"filename": "out.mp4", "subfolder": "", "type": "output"}]}},
                }
                server.state["view_files"]["out.mp4"] = b"fake-mp4-bytes"

                history = client.wait_for_completion(prompt_id, poll_interval=0.01, timeout=2)
                video = find_video_output(history, "20", ("gifs", "videos"))
                self.assertEqual(video["filename"], "out.mp4")

                data = client.view_bytes("out.mp4", subfolder="", folder_type="output")
                self.assertEqual(data, b"fake-mp4-bytes")
                self.assertEqual(server.state["view_calls"][0]["filename"], "out.mp4")

    def test_unreachable_server_raises_comfy_unreachable(self):
        client = ComfyClient("http://127.0.0.1:1", timeout=1)
        with self.assertRaises(ComfyUnreachable):
            client.system_stats()

    def test_image_only_output_is_rejected_not_treated_as_video(self):
        history = {
            "status": {"status_str": "success"},
            "outputs": {"20": {"images": [{"filename": "frame.png", "subfolder": "", "type": "output"}]}},
        }
        with self.assertRaises(ComfyExecutionError):
            find_video_output(history, "20", ("gifs", "videos"))

    def test_execution_error_status_raises(self):
        with FakeComfyServer() as server:
            client = ComfyClient(server.base_url, timeout=5)
            server.state["history"]["bad-id"] = {"status": {"status_str": "error", "messages": []}, "outputs": {}}
            with self.assertRaises(ComfyExecutionError):
                client.wait_for_completion("bad-id", poll_interval=0.01, timeout=2)


if __name__ == "__main__":
    unittest.main()
