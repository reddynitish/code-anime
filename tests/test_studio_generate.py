import dataclasses
import tempfile
import unittest
from pathlib import Path

from studio.config import load_config
from studio.generate import GenerateError, generate_shot
from studio.manifest import create_project, load_project, save_project
from studio.shotplan import default_bedroom_plan
from tests.fixtures.backend import write_fixture_catalog
from tests.fixtures.fake_comfy_server import FakeComfyServer

FIXTURE = Path(__file__).parent / "fixtures" / "fake_anisora_workflow.json"


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.base_config = load_config()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

        self.projects_root = self.tmp_path / "projects"
        self.repo_root = self.tmp_path / "repo"
        (self.repo_root / "runtime" / "workflows").mkdir(parents=True)
        (self.repo_root / "runtime" / "workflows" / "anisora_i2v.json").write_text(FIXTURE.read_text())

        self.catalog_path = write_fixture_catalog(self.tmp_path / "models.json")

        self.reference = self.tmp_path / "reference.png"
        self.reference.write_bytes(b"fake-reference-png-bytes")

        project = create_project(self.projects_root, "demo", self.reference)
        project.shots = default_bedroom_plan()
        save_project(self.projects_root, project)

    def tearDown(self):
        self._tmp.cleanup()

    def _config_for(self, server):
        return dataclasses.replace(
            self.base_config,
            comfy_base_url=server.base_url,
            repo_root=self.repo_root,
            catalog_path=self.catalog_path,
            request_timeout=5,
            poll_interval=0.01,
            poll_timeout=5,
        )

    def _make_test_video_bytes(self, duration: float = 1.0) -> bytes:
        import subprocess
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=c=blue:s=160x90:d={duration}:r=24",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_happy_path_uploads_submits_polls_and_downloads(self):
        with FakeComfyServer() as server:
            server.state["object_info"] = {
                "LoadImage": {},
                "VHS_VideoCombine": {},
                "CheckpointLoaderSimple": {
                    "input": {"required": {"ckpt_name": [["anisora_v2.safetensors"]]}}
                },
            }
            config = self._config_for(server)

            video_bytes = self._make_test_video_bytes(1.0)
            server.state["view_files"]["shot1.mp4"] = video_bytes
            server.state["history"]["fake-prompt-1"] = {
                "status": {"status_str": "success"},
                "outputs": {"20": {"gifs": [{"filename": "shot1.mp4", "subfolder": "", "type": "output"}]}},
            }

            shot = generate_shot(config, self.projects_root, "demo", 1, "anisora")

            self.assertEqual(shot.status, "done")
            self.assertEqual(len(server.state["uploads"]), 1)
            self.assertEqual(len(server.state["prompt_calls"]), 1)

            out_path = self.projects_root / "demo" / shot.output
            self.assertTrue(out_path.is_file())
            self.assertGreater(out_path.stat().st_size, 0)

            reloaded = load_project(self.projects_root, "demo")
            self.assertEqual(reloaded.shot(1).status, "done")
            self.assertEqual(reloaded.shot(1).backend, "anisora")

    def test_corrupt_or_fake_video_download_is_rejected_no_fakevideo_success(self):
        with FakeComfyServer() as server:
            server.state["object_info"] = {
                "LoadImage": {},
                "VHS_VideoCombine": {},
                "CheckpointLoaderSimple": {
                    "input": {"required": {"ckpt_name": [["anisora_v2.safetensors"]]}}
                },
            }
            config = self._config_for(server)

            server.state["view_files"]["shot1.mp4"] = b"FAKEMP4BYTES_NOT_DECODABLE"
            server.state["history"]["fake-prompt-1"] = {
                "status": {"status_str": "success"},
                "outputs": {"20": {"gifs": [{"filename": "shot1.mp4", "subfolder": "", "type": "output"}]}},
            }

            with self.assertRaises(GenerateError):
                generate_shot(config, self.projects_root, "demo", 1, "anisora")

            reloaded = load_project(self.projects_root, "demo")
            self.assertEqual(reloaded.shot(1).status, "failed")
            self.assertIn("not decodable", reloaded.shot(1).error)


    def test_missing_checkpoint_fails_preflight_before_any_submission(self):
        with FakeComfyServer() as server:
            server.state["object_info"] = {
                "LoadImage": {},
                "VHS_VideoCombine": {},
                "CheckpointLoaderSimple": {
                    "input": {"required": {"ckpt_name": [["some_unrelated_model.safetensors"]]}}
                },
            }
            config = self._config_for(server)

            with self.assertRaises(GenerateError):
                generate_shot(config, self.projects_root, "demo", 1, "anisora")

            # critically: preflight must fail *before* ever uploading or queuing
            self.assertEqual(server.state["uploads"], [])
            self.assertEqual(server.state["prompt_calls"], [])

            reloaded = load_project(self.projects_root, "demo")
            self.assertEqual(reloaded.shot(1).status, "failed")
            self.assertIn("preflight failed", reloaded.shot(1).error)

    def test_unreachable_comfy_fails_preflight(self):
        config = dataclasses.replace(
            self.base_config,
            comfy_base_url="http://127.0.0.1:1",
            repo_root=self.repo_root,
            catalog_path=self.catalog_path,
            request_timeout=1,
        )
        with self.assertRaises(GenerateError):
            generate_shot(config, self.projects_root, "demo", 1, "anisora")
        reloaded = load_project(self.projects_root, "demo")
        self.assertEqual(reloaded.shot(1).status, "failed")

    def test_smoke_render_cannot_seed_a_later_production_shot(self):
        # A smoke render of shot 1 must NOT be usable as the continuity seed
        # for shot 2 — otherwise a fast low-res smoke clip silently becomes the
        # basis of a "production" shot. Tested directly on the continuity
        # resolver so it is exercised even without ffmpeg/ComfyUI available.
        from studio.generate import _input_image_for_shot
        from studio.manifest import project_dir

        project = load_project(self.projects_root, "demo")
        shot1 = project.shot(1)
        shot1.status = "done"
        shot1.output = "output/shot_1.mp4"
        shot1.smoke = True
        save_project(self.projects_root, project)

        pdir = project_dir(self.projects_root, "demo")
        project = load_project(self.projects_root, "demo")
        with self.assertRaises(GenerateError) as ctx:
            _input_image_for_shot(project, pdir, project.shot(2))
        self.assertIn("smoke render", str(ctx.exception))

    def test_production_render_passes_the_smoke_seed_guard(self):
        # Mirror image of the guard above: a non-smoke done shot is a valid seed,
        # so continuity resolution proceeds past the smoke check (and only then
        # hits the real ffmpeg/ComfyUI path). We assert the smoke guard did NOT
        # fire by checking the error is about continuity extraction, not smoke.
        from studio.generate import _input_image_for_shot
        from studio.manifest import project_dir

        project = load_project(self.projects_root, "demo")
        shot1 = project.shot(1)
        shot1.status = "done"
        shot1.output = "output/shot_1.mp4"
        shot1.smoke = False
        save_project(self.projects_root, project)

        pdir = project_dir(self.projects_root, "demo")
        project = load_project(self.projects_root, "demo")
        # The previous clip file does not exist, so extraction eventually fails —
        # but the smoke guard must have passed first (no "smoke render" message).
        with self.assertRaises(Exception) as ctx:
            _input_image_for_shot(project, pdir, project.shot(2))
        self.assertNotIn("smoke render", str(ctx.exception))

    def test_check_output_duration_rejects_truncated_render(self):
        from studio.generate import _check_output_duration

        # A near-single-frame clip (~0.04s) against a 3s target must be rejected.
        with self.assertRaises(GenerateError):
            _check_output_duration(0.04, 3.0)
        # Just under the half-target threshold is also rejected.
        with self.assertRaises(GenerateError):
            _check_output_duration(1.49, 3.0)

    def test_check_output_duration_accepts_full_length_render(self):
        from studio.generate import _check_output_duration

        # At/above the threshold, and the exact target, must pass.
        _check_output_duration(3.0, 3.0)
        _check_output_duration(2.95, 3.0)
        _check_output_duration(1.5, 3.0)
        # No target (or non-positive) means no duration gate.
        _check_output_duration(0.01, None)
        _check_output_duration(0.01, 0.0)

    def test_seedance_is_not_a_selectable_cli_backend(self):
        from studio.cli import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["generate", "--project", "demo", "--shot", "1", "--backend", "seedance"])


if __name__ == "__main__":
    unittest.main()
