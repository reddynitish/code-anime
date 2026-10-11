import dataclasses
import tempfile
import unittest
from pathlib import Path

from studio.comfy_client import ComfyClient
from studio.config import load_config
from studio.doctor import check_backend, run_doctor
from tests.fixtures.backend import make_fixture_backend
from tests.fixtures.fake_comfy_server import FakeComfyServer

FIXTURE = Path(__file__).parent / "fixtures" / "fake_anisora_workflow.json"


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_comfy_unreachable_marks_all_local_backends_not_ready(self):
        cfg = dataclasses.replace(self.config, comfy_base_url="http://127.0.0.1:1", request_timeout=1)
        report = run_doctor(cfg)
        self.assertFalse(report.comfy_reachable)
        for status in report.backends:
            if status.key != "seedance":
                self.assertFalse(status.ready)

    def test_seedance_is_always_disabled_never_ready(self):
        # Force an unreachable Comfy URL so this stays an offline test even if
        # a real ComfyUI happens to be running on the default port.
        cfg = dataclasses.replace(self.config, comfy_base_url="http://127.0.0.1:1", request_timeout=1)
        report = run_doctor(cfg)
        seedance = next(b for b in report.backends if b.key == "seedance")
        self.assertFalse(seedance.ready)
        self.assertIn("Paid cloud video API", seedance.reasons[0])

    def test_missing_workflow_file_reported_not_ready(self):
        backend = make_fixture_backend()
        with tempfile.TemporaryDirectory() as tmp, FakeComfyServer() as server:
            cfg = dataclasses.replace(
                self.config, comfy_base_url=server.base_url, request_timeout=5, repo_root=Path(tmp)
            )
            client = ComfyClient(cfg.comfy_base_url, timeout=5)
            status = check_backend(backend, cfg, client, comfy_reachable=True)
        self.assertFalse(status.ready)
        self.assertTrue(any("workflow file not found" in r for r in status.reasons))

    def test_ready_when_workflow_valid_and_object_info_satisfied(self):
        backend = make_fixture_backend()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workflow_dir = repo_root / "runtime" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "anisora_i2v.json").write_text(FIXTURE.read_text())

            with FakeComfyServer() as server:
                server.state["object_info"] = {
                    "LoadImage": {},
                    "VHS_VideoCombine": {},
                    "CheckpointLoaderSimple": {
                        "input": {"required": {"ckpt_name": [["anisora_v2.safetensors", "other.safetensors"]]}}
                    },
                }
                cfg = dataclasses.replace(
                    self.config, comfy_base_url=server.base_url, request_timeout=5, repo_root=repo_root
                )
                client = ComfyClient(cfg.comfy_base_url, timeout=5)
                status = check_backend(backend, cfg, client, comfy_reachable=True)

        self.assertTrue(status.ready, status.reasons)

    def test_missing_checkpoint_reported_not_ready(self):
        backend = make_fixture_backend()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workflow_dir = repo_root / "runtime" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "anisora_i2v.json").write_text(FIXTURE.read_text())

            with FakeComfyServer() as server:
                server.state["object_info"] = {
                    "LoadImage": {},
                    "VHS_VideoCombine": {},
                    "CheckpointLoaderSimple": {
                        "input": {"required": {"ckpt_name": [["some_other_model.safetensors"]]}}
                    },
                }
                cfg = dataclasses.replace(
                    self.config, comfy_base_url=server.base_url, request_timeout=5, repo_root=repo_root
                )
                client = ComfyClient(cfg.comfy_base_url, timeout=5)
                status = check_backend(backend, cfg, client, comfy_reachable=True)

        self.assertFalse(status.ready)
        self.assertTrue(any("checkpoint" in r for r in status.reasons))

    def test_missing_custom_nodes_reported_not_ready(self):
        backend = make_fixture_backend()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workflow_dir = repo_root / "runtime" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "anisora_i2v.json").write_text(FIXTURE.read_text())

            with FakeComfyServer() as server:
                server.state["object_info"] = {"LoadImage": {}}  # VHS_VideoCombine missing
                cfg = dataclasses.replace(
                    self.config, comfy_base_url=server.base_url, request_timeout=5, repo_root=repo_root
                )
                client = ComfyClient(cfg.comfy_base_url, timeout=5)
                status = check_backend(backend, cfg, client, comfy_reachable=True)

        self.assertFalse(status.ready)
        self.assertTrue(any("missing custom nodes" in r for r in status.reasons))

    def test_required_files_checked_across_loaders(self):
        backend = dataclasses.replace(
            make_fixture_backend(),
            required_files=(
                {"role": "diffusion_model", "filename": "wan_model.safetensors"},
                {"role": "text_encoder", "filename": "umt5.safetensors"},
                {"role": "vae", "filename": "wan_vae.safetensors"},
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workflow_dir = repo_root / "runtime" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "anisora_i2v.json").write_text(FIXTURE.read_text())

            with FakeComfyServer() as server:
                server.state["object_info"] = {
                    "LoadImage": {},
                    "VHS_VideoCombine": {},
                    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["anisora_v2.safetensors"]]}}},
                    "UNETLoader": {"input": {"required": {"unet_name": [["wan_model.safetensors"]]}}},
                    "CLIPLoader": {"input": {"required": {"clip_name": [["umt5.safetensors"]]}}},
                    "VAELoader": {"input": {"required": {"vae_name": [["wan_vae.safetensors"]]}}},
                }
                cfg = dataclasses.replace(
                    self.config, comfy_base_url=server.base_url, request_timeout=5, repo_root=repo_root
                )
                client = ComfyClient(cfg.comfy_base_url, timeout=5)
                status = check_backend(backend, cfg, client, comfy_reachable=True)
                self.assertTrue(status.ready, status.reasons)

                # Now missing VAE
                server.state["object_info"]["VAELoader"]["input"]["required"]["vae_name"] = [[]]
                status_missing_vae = check_backend(backend, cfg, client, comfy_reachable=True)
                self.assertFalse(status_missing_vae.ready)
                self.assertTrue(any("wan_vae.safetensors" in r for r in status_missing_vae.reasons))

    def test_unknown_required_file_role_marked_not_ready(self):
        backend = dataclasses.replace(
            make_fixture_backend(),
            required_files=(
                {"role": "unknown_future_loader", "filename": "some_file.safetensors"},
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workflow_dir = repo_root / "runtime" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "anisora_i2v.json").write_text(FIXTURE.read_text())

            with FakeComfyServer() as server:
                server.state["object_info"] = {
                    "LoadImage": {},
                    "VHS_VideoCombine": {},
                    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["anisora_v2.safetensors"]]}}},
                }
                cfg = dataclasses.replace(
                    self.config, comfy_base_url=server.base_url, request_timeout=5, repo_root=repo_root
                )
                client = ComfyClient(cfg.comfy_base_url, timeout=5)
                status = check_backend(backend, cfg, client, comfy_reachable=True)
                self.assertFalse(status.ready)
                self.assertTrue(any("unknown loader" in r for r in status.reasons))


if __name__ == "__main__":
    unittest.main()

