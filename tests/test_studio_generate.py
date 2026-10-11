import dataclasses
import shutil
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

            # Shot 1 in the default plan targets 3.0s; the fixture must supply a
            # source at least that long or the (correct) duration gate rejects it.
            video_bytes = self._make_test_video_bytes(3.0)
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

    def test_check_output_duration_rejects_render_that_misses_target(self):
        from studio.generate import _check_output_duration

        # A near-single-frame clip (~0.04s) against a 3s target must be rejected.
        with self.assertRaises(GenerateError):
            _check_output_duration(0.04, 3.0, fps=24)
        # A clip at half the target (the OLD lenient threshold) must now be
        # rejected: a 1.5s output for a planned 3s shot breaks the 10s cut.
        with self.assertRaises(GenerateError):
            _check_output_duration(1.5, 3.0, fps=24)
        # Even a small miss beyond the frame tolerance is rejected.
        with self.assertRaises(GenerateError):
            _check_output_duration(2.8, 3.0, fps=24)

    def test_check_output_duration_accepts_only_on_target_within_frame_tolerance(self):
        from studio.generate import _check_output_duration

        # Exact target and within ~2 frames (at 24 fps, ~0.083s) must pass.
        _check_output_duration(3.0, 3.0, fps=24)
        _check_output_duration(2.95, 3.0, fps=24)
        _check_output_duration(3.05, 3.0, fps=24)
        # No target (or non-positive) means no duration gate.
        _check_output_duration(0.01, None, fps=24)
        _check_output_duration(0.01, 0.0, fps=24)

    def test_check_source_long_enough_rejects_short_source(self):
        from studio.generate import _check_source_long_enough

        # Trimming cannot lengthen a source: a 1.5s source cannot yield a 3s cut.
        with self.assertRaises(GenerateError):
            _check_source_long_enough(1.5, 3.0, fps=24)
        with self.assertRaises(GenerateError):
            _check_source_long_enough(0.04, 3.0, fps=24)
        # A source at/above the target (within frame tolerance) is fine, as is a
        # longer source (it gets trimmed down by ffmpeg -t).
        _check_source_long_enough(3.0, 3.0, fps=24)
        _check_source_long_enough(2.95, 3.0, fps=24)
        _check_source_long_enough(5.0, 3.0, fps=24)
        _check_source_long_enough(0.5, None, fps=24)

    def test_probe_duration_rejects_non_finite_and_non_positive(self):
        import unittest.mock as mock

        from studio.generate import _probe_duration

        def fake_run(values):
            completed = mock.Mock()
            completed.returncode = 0
            completed.stdout = values
            completed.stderr = ""
            return completed

        for bad in ("nan", "inf", "-inf", "0", "-2.0", "N/A"):
            with mock.patch("studio.generate.subprocess.run", return_value=fake_run(bad)):
                with self.assertRaises(GenerateError):
                    _probe_duration(Path("/tmp/whatever.mp4"))

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed"
    )
    def test_underlength_download_is_rejected_full_length_is_accepted(self):
        # End-to-end proof through the real ffmpeg path: a 1.0s clip for the
        # planned 3.0s shot 1 must be rejected, while a 3.0s clip is accepted.
        def run_once(source_duration: float):
            with FakeComfyServer() as server:
                server.state["object_info"] = {
                    "LoadImage": {},
                    "VHS_VideoCombine": {},
                    "CheckpointLoaderSimple": {
                        "input": {"required": {"ckpt_name": [["anisora_v2.safetensors"]]}}
                    },
                }
                config = self._config_for(server)
                server.state["view_files"]["shot1.mp4"] = self._make_test_video_bytes(source_duration)
                server.state["history"]["fake-prompt-1"] = {
                    "status": {"status_str": "success"},
                    "outputs": {
                        "20": {"gifs": [{"filename": "shot1.mp4", "subfolder": "", "type": "output"}]}
                    },
                }
                return generate_shot(config, self.projects_root, "demo", 1, "anisora")

        # Underlength (1.0s vs planned 3.0s) -> rejected, shot marked failed.
        with self.assertRaises(GenerateError):
            run_once(1.0)
        self.assertEqual(load_project(self.projects_root, "demo").shot(1).status, "failed")

        # Full-length (3.0s) -> accepted.
        shot = run_once(3.0)
        self.assertEqual(shot.status, "done")
        self.assertEqual(load_project(self.projects_root, "demo").shot(1).status, "done")

    def test_seedance_is_not_a_selectable_cli_backend(self):
        from studio.cli import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["generate", "--project", "demo", "--shot", "1", "--backend", "seedance"])


if __name__ == "__main__":
    unittest.main()
