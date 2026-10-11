"""Offline tests for the Luminal asset registry.

Fixtures are REAL-shaped keyframes.py JOB records (not synthetic asset rows):
one job with one or more image ``outputs``, ``reserved_usd`` / ``charged_usd``
(the latter possibly a string), ``generation_id`` and ``key``. No real images,
credentials, or secret files are read — the registry works from metadata alone.
"""

import io
import json
import os
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
    assets_from_job_record,
    import_job_sidecars,
    load_registry,
    save_registry,
)


# --- real-shaped job records -------------------------------------------------

def job_n1(**overrides):
    """A completed single-output job, exactly like the reviewer's example."""
    rec = {
        "key": "char_turn_front",
        "state": "completed",
        "quality": "high",
        "n": 1,
        "reserved_usd": 0.2,
        "charged_usd": "0.2000",  # provider-reported as a STRING
        "generation_id": "example-generation",
        "outputs": ["char_turn_front_00.png"],
    }
    rec.update(overrides)
    return rec


def job_n2(**overrides):
    """A two-output job: cost must be split across the two outputs."""
    rec = {
        "key": "char_turn_side",
        "state": "completed",
        "quality": "high",
        "n": 2,
        "reserved_usd": 0.4,
        "charged_usd": "0.4000",
        "generation_id": "gen-side",
        "outputs": ["char_turn_side_00.png", "char_turn_side_01.png"],
    }
    rec.update(overrides)
    return rec


class CostTests(unittest.TestCase):
    def test_reserved_and_charged_are_separate_and_unverified(self):
        c = Cost(reserved=0.2, charged=0.2, unit="usd")
        c.validate()
        self.assertFalse(c.invoice_verified)

    def test_invoice_verified_true_is_rejected(self):
        with self.assertRaises(AssetError):
            Cost(reserved=0.1, charged=0.1, invoice_verified=True).validate()

    def test_negative_cost_rejected(self):
        with self.assertRaises(AssetError):
            Cost(reserved=-1).validate()
        with self.assertRaises(AssetError):
            Cost(charged=-0.5).validate()


class AssetModelTests(unittest.TestCase):
    def test_video_anchor_valid_but_plain_video_is_not(self):
        Asset(asset_id="a1", kind="video_anchor", path="frames/last.png").validate()
        self.assertIn("video_anchor", ASSET_KINDS)
        self.assertNotIn("video", ASSET_KINDS)

    def test_absolute_and_traversing_paths_rejected(self):
        for bad in ("/etc/passwd", "../../secret.png", ""):
            with self.assertRaises(AssetError):
                Asset(asset_id="a1", kind="prop", path=bad).validate()

    def test_roundtrip_preserves_all_fields(self):
        a = Asset(
            asset_id="gen#0-abc",
            kind="character",
            path="assets/char_00.png",
            source_ids=["gen-1"],
            model="luminal-image",
            generation_id="gen-1",
            output_index=0,
            source_output="/abs/char_00.png",
            cost=Cost(reserved=0.1, charged=0.1, unit="usd"),
            origin="luminal_keyframe_job",
            provenance={"job_key": "char"},
        )
        restored = Asset.from_dict(json.loads(json.dumps(a.to_dict())))
        self.assertEqual(restored.to_dict(), a.to_dict())


class JobRecordImportTests(unittest.TestCase):
    def test_single_output_job_imports_with_full_provenance(self):
        assets = assets_from_job_record(job_n1(), default_kind="character")
        self.assertEqual(len(assets), 1)
        a = assets[0]
        self.assertEqual(a.kind, "character")
        self.assertEqual(a.path, "char_turn_front_00.png")
        self.assertEqual(a.generation_id, "example-generation")
        self.assertEqual(a.source_ids, ["example-generation"])
        self.assertEqual(a.review_state, DEFAULT_REVIEW_STATE)
        # String charged_usd parsed to float.
        self.assertAlmostEqual(a.cost.charged, 0.2)
        self.assertAlmostEqual(a.cost.reserved, 0.2)
        self.assertFalse(a.cost.invoice_verified)
        # Real job fields preserved as provenance.
        self.assertEqual(a.provenance["job_key"], "char_turn_front")
        self.assertEqual(a.provenance["job_state"], "completed")
        self.assertEqual(a.provenance["charged_usd_raw"], "0.2000")

    def test_n2_job_imports_two_assets_and_splits_cost(self):
        assets = assets_from_job_record(job_n2(), default_kind="character")
        self.assertEqual(len(assets), 2)
        self.assertEqual([a.output_index for a in assets], [0, 1])
        self.assertEqual([a.path for a in assets],
                         ["char_turn_side_00.png", "char_turn_side_01.png"])
        # Full job charge (0.4) split across the two outputs, not counted twice.
        self.assertAlmostEqual(sum(a.cost.charged for a in assets), 0.4)
        self.assertAlmostEqual(assets[0].cost.charged, 0.2)
        self.assertAlmostEqual(sum(a.cost.reserved for a in assets), 0.4)
        # Distinct deterministic ids.
        self.assertNotEqual(assets[0].asset_id, assets[1].asset_id)

    def test_deterministic_ids_are_stable(self):
        a1 = assets_from_job_record(job_n2(), default_kind="character")
        a2 = assets_from_job_record(job_n2(), default_kind="character")
        self.assertEqual([a.asset_id for a in a1], [a.asset_id for a in a2])

    def test_default_kind_and_classification_override(self):
        # default kind applies...
        a = assets_from_job_record(job_n1(), default_kind="storyboard")[0]
        self.assertEqual(a.kind, "storyboard")
        # ...and an explicit mapping by job key overrides it.
        a = assets_from_job_record(
            job_n1(), default_kind="storyboard", classification={"char_turn_front": "character"}
        )[0]
        self.assertEqual(a.kind, "character")

    def test_missing_outputs_rejected(self):
        with self.assertRaises(AssetError):
            assets_from_job_record(job_n1(outputs=[]), default_kind="character")
        with self.assertRaises(AssetError):
            assets_from_job_record({"key": "x"}, default_kind="character")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(AssetError):
            assets_from_job_record(job_n1(), default_kind="video")

    def test_string_and_numeric_charged_usd_both_parse(self):
        a = assets_from_job_record(job_n1(charged_usd=0.2), default_kind="character")[0]
        self.assertAlmostEqual(a.cost.charged, 0.2)
        a = assets_from_job_record(job_n1(charged_usd="0.2000"), default_kind="character")[0]
        self.assertAlmostEqual(a.cost.charged, 0.2)
        with self.assertRaises(AssetError):
            assets_from_job_record(job_n1(charged_usd="not-a-number"), default_kind="character")


class AbsoluteOutputTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.asset_root = self.root / "approved_assets"
        self.asset_root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_absolute_output_requires_asset_root(self):
        rec = job_n1(outputs=[str(self.asset_root / "char_00.png")])
        with self.assertRaises(AssetError):
            assets_from_job_record(rec, default_kind="character", asset_root=None)

    def test_absolute_output_normalized_relative_to_asset_root(self):
        abs_out = self.asset_root / "chars" / "char_00.png"
        rec = job_n1(outputs=[str(abs_out)])
        a = assets_from_job_record(rec, default_kind="character", asset_root=self.asset_root)[0]
        self.assertEqual(a.path, "chars/char_00.png")
        self.assertEqual(a.source_output, str(abs_out))

    def test_output_outside_asset_root_rejected(self):
        outside = self.root / "elsewhere" / "secret.png"
        rec = job_n1(outputs=[str(outside)])
        with self.assertRaises(AssetError):
            assets_from_job_record(rec, default_kind="character", asset_root=self.asset_root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_output_symlink_escaping_asset_root_rejected(self):
        # A symlink *inside* the asset root pointing OUTSIDE it must be rejected.
        secret_dir = self.root / "secret"
        secret_dir.mkdir()
        (secret_dir / "leak.png").write_bytes(b"x")
        link = self.asset_root / "leak.png"
        try:
            os.symlink(secret_dir / "leak.png", link)
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlink in this environment")
        rec = job_n1(outputs=[str(link)])
        with self.assertRaises(AssetError) as ctx:
            assets_from_job_record(rec, default_kind="character", asset_root=self.asset_root)
        self.assertIn("outside approved asset root", str(ctx.exception))


class RegistryUpsertTests(unittest.TestCase):
    def test_repeat_import_is_idempotent_and_preserves_review(self):
        reg = AssetRegistry()
        built = assets_from_job_record(job_n1(), default_kind="character")
        asset, created = reg.upsert(built[0])
        self.assertTrue(created)
        # Human marks it accepted.
        reg.set_review_state(asset.asset_id, "accepted")
        # Re-import the same job output: must map to the same id and keep accepted.
        again = assets_from_job_record(job_n1(), default_kind="character")[0]
        _, created2 = reg.upsert(again)
        self.assertFalse(created2)
        self.assertEqual(len(reg.assets), 1)
        self.assertEqual(reg.by_id(asset.asset_id).review_state, "accepted")

    def test_rejected_state_also_preserved_on_reimport(self):
        reg = AssetRegistry()
        a = assets_from_job_record(job_n1(), default_kind="character")[0]
        reg.upsert(a)
        reg.set_review_state(a.asset_id, "rejected")
        reg.upsert(assets_from_job_record(job_n1(), default_kind="character")[0])
        self.assertEqual(reg.by_id(a.asset_id).review_state, "rejected")


class SidecarDirImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.sidecars = self.root / "sidecars"
        self.sidecars.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, rec):
        (self.sidecars / name).write_text(json.dumps(rec))

    def test_import_dir_counts_created_and_updated(self):
        self._write("front.json", job_n1())
        self._write("side.json", job_n2())
        reg = AssetRegistry()
        touched, created, updated = import_job_sidecars(reg, self.sidecars, default_kind="character")
        self.assertEqual(created, 3)  # 1 + 2 outputs
        self.assertEqual(updated, 0)
        self.assertEqual(len(reg.assets), 3)

        # Second pass over the same sidecars: all updates, no new assets.
        touched, created, updated = import_job_sidecars(reg, self.sidecars, default_kind="character")
        self.assertEqual(created, 0)
        self.assertEqual(updated, 3)
        self.assertEqual(len(reg.assets), 3)

    def test_invalid_json_names_the_file(self):
        (self.sidecars / "broken.json").write_text("{not json")
        with self.assertRaises(AssetError) as ctx:
            import_job_sidecars(AssetRegistry(), self.sidecars, default_kind="character")
        self.assertIn("broken.json", str(ctx.exception))

    def test_missing_directory_errors(self):
        with self.assertRaises(AssetError):
            import_job_sidecars(AssetRegistry(), self.root / "nope", default_kind="character")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_symlinked_sidecar_escaping_root_rejected(self):
        outside_dir = self.root / "outside"
        outside_dir.mkdir()
        real = outside_dir / "evil.json"
        real.write_text(json.dumps(job_n1()))
        link = self.sidecars / "evil.json"
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlink in this environment")
        with self.assertRaises(AssetError) as ctx:
            import_job_sidecars(AssetRegistry(), self.sidecars, default_kind="character")
        self.assertIn("symlink", str(ctx.exception))


class AssetCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry_dir = self.root / "registry"
        self.sidecars = self.root / "sidecars"
        self.sidecars.mkdir()
        (self.sidecars / "front.json").write_text(json.dumps(job_n1()))
        (self.sidecars / "side.json").write_text(json.dumps(job_n2()))

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, argv):
        from studio.cli import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_cli_import_list_review_flow(self):
        code, out = self._run(
            ["assets", "import", str(self.sidecars), "--kind", "character",
             "--registry-dir", str(self.registry_dir)]
        )
        self.assertEqual(code, 0)
        self.assertIn("3 output(s)", out)

        reg = load_registry(self.registry_dir)
        self.assertEqual(len(reg.assets), 3)
        for a in reg.assets:
            self.assertEqual(a.review_state, "candidate")  # never auto-accepted

        asset_id = reg.assets[0].asset_id
        code, out = self._run(
            ["assets", "review", asset_id, "accepted", "--registry-dir", str(self.registry_dir)]
        )
        self.assertEqual(code, 0)

        # Re-import must preserve the accepted decision.
        self._run(
            ["assets", "import", str(self.sidecars), "--kind", "character",
             "--registry-dir", str(self.registry_dir)]
        )
        self.assertEqual(load_registry(self.registry_dir).by_id(asset_id).review_state, "accepted")

    def test_cli_classify_override(self):
        code, out = self._run(
            ["assets", "import", str(self.sidecars), "--kind", "storyboard",
             "--classify", "char_turn_front=character",
             "--registry-dir", str(self.registry_dir)]
        )
        self.assertEqual(code, 0)
        reg = load_registry(self.registry_dir)
        kinds = {a.provenance["job_key"]: a.kind for a in reg.assets}
        self.assertEqual(kinds["char_turn_front"], "character")
        self.assertEqual(kinds["char_turn_side"], "storyboard")


if __name__ == "__main__":
    unittest.main()
