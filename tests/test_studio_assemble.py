import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio.assemble import AssembleError, assemble_project
from studio.manifest import create_project, save_project
from studio.shotplan import default_bedroom_plan


def _make_test_clip(path: Path, duration: float, color: str) -> None:
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:s=160x90:d={duration}:r=24",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"test fixture ffmpeg failed: {result.stderr}")


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
class AssembleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.projects_root = Path(self._tmp.name)
        ref = Path(self._tmp.name) / "ref.png"
        ref.write_bytes(b"fake")
        self.project = create_project(self.projects_root, "demo", ref)
        self.project.shots = default_bedroom_plan()

    def tearDown(self):
        self._tmp.cleanup()

    def test_assemble_fails_when_shots_missing(self):
        save_project(self.projects_root, self.project)
        with self.assertRaises(AssembleError):
            assemble_project(self.projects_root, self.project)

    def test_assemble_concatenates_real_clips_to_expected_duration(self):
        pdir = self.projects_root / "demo"
        colors = ["red", "green", "blue"]
        for shot, color in zip(self.project.shots, colors):
            out_rel = f"output/shot_{shot.index}.mp4"
            _make_test_clip(pdir / out_rel, shot.duration, color)
            shot.status = "done"
            shot.output = out_rel
        save_project(self.projects_root, self.project)

        out_path = assemble_project(self.projects_root, self.project, width=160, height=90, fps=24)
        self.assertTrue(out_path.is_file())

        duration = _ffprobe_duration(out_path)
        self.assertAlmostEqual(duration, 10.0, delta=0.5)


class AssembleSmokeRejectionTests(unittest.TestCase):
    """Smoke-render rejection runs before any ffmpeg call, so it is offline-safe."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.projects_root = Path(self._tmp.name)
        ref = Path(self._tmp.name) / "ref.png"
        ref.write_bytes(b"fake")
        self.project = create_project(self.projects_root, "demo", ref)
        self.project.shots = default_bedroom_plan()

    def tearDown(self):
        self._tmp.cleanup()

    def _mark_all_done(self, smoke_indices=()):
        pdir = self.projects_root / "demo"
        (pdir / "output").mkdir(parents=True, exist_ok=True)
        for shot in self.project.shots:
            out_rel = f"output/shot_{shot.index}.mp4"
            # Create placeholder files so the "missing output file" check passes
            # and we reach the smoke gate specifically.
            (pdir / out_rel).write_bytes(b"placeholder")
            shot.status = "done"
            shot.output = out_rel
            shot.smoke = shot.index in smoke_indices
        save_project(self.projects_root, self.project)

    def test_assemble_rejects_smoke_shots(self):
        # One shot is a smoke render -> assembly must refuse, naming the shot.
        self._mark_all_done(smoke_indices=(2,))
        with self.assertRaises(AssembleError) as ctx:
            assemble_project(self.projects_root, self.project)
        msg = str(ctx.exception)
        self.assertIn("smoke", msg.lower())
        self.assertIn("2", msg)

    def test_assemble_rejects_when_all_shots_are_smoke(self):
        self._mark_all_done(smoke_indices=(1, 2, 3))
        with self.assertRaises(AssembleError) as ctx:
            assemble_project(self.projects_root, self.project)
        self.assertIn("smoke", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
