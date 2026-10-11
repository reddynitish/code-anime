"""Offline tests for the Luminal asset registry.

All fixtures are synthetic metadata written in-test. No real generated images,
no credentials, and no secret files are read — the cloud cannot see local
images, so the registry must work from metadata alone.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from studio.assets import (
    ASSET_KINDS,
    DEFAULT_REVIEW_STATE,
    Asset,
    AssetError,
    AssetRegistry,
    Cost,
    asset_from_sidecar,
    import_sidecars,
    load_registry,
    save_registry,
)


def _sidecar(kind="character", **overrides):
    data = {
        "kind": kind,
        "path": "assets/characters/hero_front.png",
        "character_id": "hero",
        "scene_id": "bedroom",
        "model": "luminal-image-v1",
        "generation_id": "gen-123",
        "cost_amount": 2.5,
        "cost_unit": "credits",
        "cost_recorded": True,
    }
    data.update(overrides)
    return data


class AssetModelTests(unittest.TestCase):
    def test_valid_asset_passes_validation(self):
        a = Asset(asset_id="a1", kind="character", path="assets/x.png")
        a.validate()  # should not raise
        self.assertEqual(a.review_state, DEFAULT_REVIEW_STATE)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="video", path="assets/x.png").validate()

    def test_video_anchor_is_a_valid_kind_but_images_are_separate(self):
        # video_anchor is allowed (a still from accepted video); plain "video" is not.
        Asset(asset_id="a1", kind="video_anchor", path="frames/last.png").validate()
        self.assertIn("video_anchor", ASSET_KINDS)
        self.assertNotIn("video", ASSET_KINDS)

    def test_absolute_and_traversing_paths_rejected(self):
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="prop", path="/etc/passwd").validate()
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="prop", path="../../secret.png").validate()
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="prop", path="").validate()

    def test_negative_and_bad_cost_rejected(self):
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="prop", path="p.png", cost=Cost(amount=-1)).validate()
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="prop", path="p.png", cost=Cost(amount=1, unit="")).validate()

    def test_bad_review_state_rejected(self):
        with self.assertRaises(AssetError):
            Asset(asset_id="a1", kind="prop", path="p.png", review_state="nope").validate()

    def test_roundtrip_preserves_all_fields(self):
        a = Asset(
            asset_id="a1",
            kind="storyboard",
            path="assets/sb/01.png",
            character_id="hero",
            scene_id="bedroom",
            source_ids=["parent-1", "parent-2"],
            model="luminal-image-v1",
            generation_id="gen-9",
            cost=Cost(amount=3.0, unit="credits", recorded=True),
            origin="luminal_image",
            provenance={"batch_id": "b-42"},
        )
        restored = Asset.from_dict(json.loads(json.dumps(a.to_dict())))
        self.assertEqual(restored.to_dict(), a.to_dict())


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_missing_registry_is_empty(self):
        reg = load_registry(self.dir)
        self.assertEqual(reg.assets, [])

    def test_add_save_load_roundtrip(self):
        reg = AssetRegistry()
        reg.add(Asset(asset_id="a1", kind="character", path="assets/a.png"))
        save_registry(self.dir, reg)

        reloaded = load_registry(self.dir)
        self.assertEqual(len(reloaded.assets), 1)
        self.assertEqual(reloaded.assets[0].asset_id, "a1")

    def test_duplicate_id_rejected(self):
        reg = AssetRegistry()
        reg.add(Asset(asset_id="a1", kind="prop", path="p.png"))
        with self.assertRaises(AssetError):
            reg.add(Asset(asset_id="a1", kind="prop", path="q.png"))

    def test_set_review_state_and_invalid_rejected(self):
        reg = AssetRegistry()
        reg.add(Asset(asset_id="a1", kind="prop", path="p.png"))
        reg.set_review_state("a1", "accepted")
        self.assertEqual(reg.by_id("a1").review_state, "accepted")
        with self.assertRaises(AssetError):
            reg.set_review_state("a1", "bogus")
        with self.assertRaises(AssetError):
            reg.set_review_state("missing", "accepted")


class SidecarImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.sidecars = self.dir / "sidecars"
        self.sidecars.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, data):
        (self.sidecars / name).write_text(json.dumps(data))

    def test_import_preserves_provenance_and_lineage(self):
        self._write("one.json", _sidecar(source_ids=["ref-0"], batch_id="b-7", extra="keep-me"))
        reg = AssetRegistry()
        added = import_sidecars(reg, self.sidecars)
        self.assertEqual(len(added), 1)
        a = added[0]
        self.assertEqual(a.character_id, "hero")
        self.assertEqual(a.source_ids, ["ref-0"])
        self.assertEqual(a.cost.amount, 2.5)
        self.assertTrue(a.cost.recorded)
        # Unknown keys are preserved, never dropped.
        self.assertEqual(a.provenance.get("batch_id"), "b-7")
        self.assertEqual(a.provenance.get("extra"), "keep-me")

    def test_import_never_auto_accepts(self):
        # A sidecar claiming "accepted" must still land as candidate.
        self._write("accepted.json", _sidecar(review_state="accepted"))
        reg = AssetRegistry()
        added = import_sidecars(reg, self.sidecars)
        self.assertEqual(added[0].review_state, DEFAULT_REVIEW_STATE)
        # ...but the upstream claim is retained as provenance for auditing.
        self.assertEqual(added[0].provenance.get("_imported_review_state_claim"), "accepted")

    def test_import_generates_id_when_missing(self):
        self._write("noid.json", _sidecar())
        reg = AssetRegistry()
        added = import_sidecars(reg, self.sidecars)
        self.assertTrue(added[0].asset_id.startswith("asset-"))

    def test_import_rejected_review_state_is_honoured(self):
        self._write("rej.json", _sidecar(review_state="rejected"))
        reg = AssetRegistry()
        added = import_sidecars(reg, self.sidecars)
        self.assertEqual(added[0].review_state, "rejected")

    def test_sidecar_missing_path_or_kind_errors_with_filename(self):
        self._write("bad.json", {"kind": "character"})  # no path
        reg = AssetRegistry()
        with self.assertRaises(AssetError) as ctx:
            import_sidecars(reg, self.sidecars)
        self.assertIn("bad.json", str(ctx.exception))

    def test_invalid_json_sidecar_errors_with_filename(self):
        (self.sidecars / "broken.json").write_text("{not json")
        reg = AssetRegistry()
        with self.assertRaises(AssetError) as ctx:
            import_sidecars(reg, self.sidecars)
        self.assertIn("broken.json", str(ctx.exception))

    def test_missing_directory_errors(self):
        with self.assertRaises(AssetError):
            import_sidecars(AssetRegistry(), self.dir / "nope")

    def test_import_does_not_require_the_image_file_to_exist(self):
        # The cloud cannot see local images; import must work from metadata only.
        self._write("meta.json", _sidecar(path="assets/characters/not_on_disk.png"))
        reg = AssetRegistry()
        added = import_sidecars(reg, self.sidecars)
        self.assertEqual(added[0].path, "assets/characters/not_on_disk.png")


class AssetCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.registry_dir = self.dir / "registry"
        self.sidecars = self.dir / "sidecars"
        self.sidecars.mkdir()
        (self.sidecars / "one.json").write_text(json.dumps(_sidecar()))

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, argv):
        from studio.cli import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_cli_import_list_and_review_flow(self):
        code, out = self._run(
            ["assets", "import", str(self.sidecars), "--registry-dir", str(self.registry_dir)]
        )
        self.assertEqual(code, 0)
        self.assertIn("imported 1 asset", out)

        # The imported asset is a candidate, never auto-accepted.
        reg = load_registry(self.registry_dir)
        self.assertEqual(len(reg.assets), 1)
        asset_id = reg.assets[0].asset_id
        self.assertEqual(reg.assets[0].review_state, "candidate")

        code, out = self._run(["assets", "list", "--registry-dir", str(self.registry_dir)])
        self.assertEqual(code, 0)
        self.assertIn(asset_id, out)
        self.assertIn("review=candidate", out)

        code, out = self._run(
            ["assets", "review", asset_id, "accepted", "--registry-dir", str(self.registry_dir)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(load_registry(self.registry_dir).by_id(asset_id).review_state, "accepted")

    def test_cli_list_filters_by_review_state(self):
        self._run(["assets", "import", str(self.sidecars), "--registry-dir", str(self.registry_dir)])
        code, out = self._run(
            ["assets", "list", "--registry-dir", str(self.registry_dir), "--review-state", "accepted"]
        )
        self.assertEqual(code, 0)
        self.assertIn("no assets", out)


if __name__ == "__main__":
    unittest.main()
