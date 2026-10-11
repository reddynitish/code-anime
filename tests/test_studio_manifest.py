import tempfile
import unittest
from pathlib import Path

from studio.manifest import (
    Project,
    ProjectError,
    create_project,
    list_projects,
    load_project,
    resolve_project_media,
    save_project,
)
from studio.paths import UnsafePathError
from studio.shotplan import default_bedroom_plan


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.projects_root = Path(self._tmp.name)

        self._ref_tmp = tempfile.TemporaryDirectory()
        self.reference_image = Path(self._ref_tmp.name) / "reference.png"
        self.reference_image.write_bytes(b"\x89PNG\r\n\x1a\nfake-but-only-reference")

        self.decoy_drawing = Path(self._ref_tmp.name) / "mask_drawing_013.png"
        self.decoy_drawing.write_bytes(b"not the original reference")

    def tearDown(self):
        self._tmp.cleanup()
        self._ref_tmp.cleanup()

    def test_create_project_copies_only_the_given_reference(self):
        project = create_project(self.projects_root, "demo", self.reference_image)
        self.assertEqual(project.reference_image, "input/reference.png")

        copied = self.projects_root / "demo" / "input" / "reference.png"
        self.assertEqual(copied.read_bytes(), self.reference_image.read_bytes())

        # the decoy ("existing drawing") must never appear in the project
        for p in (self.projects_root / "demo").rglob("*"):
            self.assertNotEqual(p.read_bytes() if p.is_file() else None, self.decoy_drawing.read_bytes())

    def test_create_project_without_reference_leaves_it_unset(self):
        project = create_project(self.projects_root, "noref", reference_source=None)
        self.assertIsNone(project.reference_image)

    def test_create_project_refuses_overwrite_without_force(self):
        create_project(self.projects_root, "demo", self.reference_image)
        with self.assertRaises(ProjectError):
            create_project(self.projects_root, "demo", self.reference_image)
        # force=True is allowed to recreate
        create_project(self.projects_root, "demo", self.reference_image, force=True)

    def test_create_project_rejects_path_like_names(self):
        with self.assertRaises(ProjectError):
            create_project(self.projects_root, "../escape", self.reference_image)
        with self.assertRaises(ProjectError):
            create_project(self.projects_root, "a/b", self.reference_image)

    def test_save_and_load_roundtrip(self):
        project = create_project(self.projects_root, "demo", self.reference_image)
        project.shots = default_bedroom_plan()
        save_project(self.projects_root, project)

        loaded = load_project(self.projects_root, "demo")
        self.assertEqual(len(loaded.shots), 3)
        self.assertEqual(loaded.shots[0].status, "planned")
        self.assertEqual(loaded.reference_image, "input/reference.png")

    def test_smoke_flag_roundtrips_and_defaults_false(self):
        project = create_project(self.projects_root, "demo", self.reference_image)
        project.shots = default_bedroom_plan()
        # Default must be False so a normal render is never treated as a smoke render.
        self.assertFalse(project.shots[0].smoke)
        project.shots[0].smoke = True
        save_project(self.projects_root, project)

        loaded = load_project(self.projects_root, "demo")
        self.assertTrue(loaded.shots[0].smoke)
        self.assertFalse(loaded.shots[1].smoke)

    def test_load_legacy_manifest_without_smoke_key(self):
        # Manifests written before the smoke field existed must still load.
        project = create_project(self.projects_root, "legacy", self.reference_image)
        project.shots = default_bedroom_plan()
        save_project(self.projects_root, project)

        mpath = self.projects_root / "legacy" / "manifest.json"
        import json

        data = json.loads(mpath.read_text())
        for shot in data["shots"]:
            shot.pop("smoke", None)
        mpath.write_text(json.dumps(data))

        loaded = load_project(self.projects_root, "legacy")
        self.assertFalse(loaded.shots[0].smoke)

    def test_list_projects(self):
        create_project(self.projects_root, "demo1", self.reference_image)
        create_project(self.projects_root, "demo2", self.reference_image)
        self.assertEqual(sorted(list_projects(self.projects_root)), ["demo1", "demo2"])

    def test_load_missing_project_raises(self):
        with self.assertRaises(ProjectError):
            load_project(self.projects_root, "does-not-exist")

    def test_resolve_project_media_blocks_traversal(self):
        create_project(self.projects_root, "demo", self.reference_image)
        with self.assertRaises(UnsafePathError):
            resolve_project_media(self.projects_root, "demo", "../../../etc/passwd")

    def test_resolve_project_media_allows_legitimate_path(self):
        create_project(self.projects_root, "demo", self.reference_image)
        resolved = resolve_project_media(self.projects_root, "demo", "input/reference.png")
        self.assertTrue(str(resolved).endswith("input/reference.png"))


if __name__ == "__main__":
    unittest.main()
