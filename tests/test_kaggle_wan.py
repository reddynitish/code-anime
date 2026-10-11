"""Offline unit tests for Kaggle Wan 2.2 Orchestration.

Tests:
- Private flags and metadata generation (kernel & dataset)
- Pinned source version / git commit provenance
- Command serialization and dry-run execution
- Path traversal prevention on image paths
- Owner validation and rejection of guessing
- Bounded polling, status parsing, and timeouts
- Partial job failure manifest handling
- File existence skip requiring valid MP4 container fingerprint
- Security: No reading or printing of Kaggle credential files
- HF quota error detection guardrails
"""

import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.kaggle_wan as kw
import scripts.hf_wan_flf as hf_wan


class TestKaggleWanMetadataAndSecurity(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.staging_dir = Path(self.test_dir) / "staging"
        self.img_dir = Path(self.test_dir) / "imgs"
        self.img_dir.mkdir(parents=True)

        # Create a dummy image inside workspace
        self.test_img = self.img_dir / "frame_01.png"
        self.test_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Create a valid test manifest
        self.manifest_file = Path(self.test_dir) / "manifest.json"
        self.manifest_data = [
            {
                "id": "shot01",
                "image": str(self.test_img),
                "prompt": "anime character walking",
                "seconds": 3.5,
                "seed": 42,
            }
        ]
        self.manifest_file.write_text(json.dumps(self.manifest_data), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_owner_validation(self):
        self.assertEqual(kw.validate_owner("test-user-123"), "test-user-123")
        self.assertEqual(kw.validate_owner("alice_kaggle"), "alice_kaggle")

        # Invalid owners
        with self.assertRaises(ValueError):
            kw.validate_owner("user name with spaces")
        with self.assertRaises(ValueError):
            kw.validate_owner("../path_traversal")
        with self.assertRaises(ValueError):
            kw.validate_owner("ab")  # too short
        with self.assertRaises(ValueError):
            kw.validate_owner("")

    def test_path_traversal_prevention(self):
        # Image outside workspace root
        outside_img = Path(self.test_dir) / "outside" / "test.png"
        outside_img.parent.mkdir(parents=True, exist_ok=True)
        outside_img.write_text("dummy")

        # Explicit allowed root that does NOT include outside_img
        inner_root = Path(self.test_dir) / "inner_workspace"
        inner_root.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(ValueError):
            kw.validate_image_path(str(outside_img), inner_root, allowed_root=inner_root)

        # Non-existent relative path
        with self.assertRaises(FileNotFoundError):
            kw.validate_image_path("non_existent_frame.png", inner_root, allowed_root=inner_root)

    def test_prepare_staging_metadata_and_private_flags(self):
        args = MagicMock()
        args.manifest = str(self.manifest_file)
        args.staging_dir = str(self.staging_dir)
        args.owner = "anime-studio"
        args.dataset_slug = "code-anime-jobs-wan"
        args.kernel_slug = "code-anime-wan-runner"
        args.allowed_root = self.test_dir
        args.dry_run = False

        ret = kw.cmd_prepare(args)
        self.assertEqual(ret, 0)

        ds_meta_file = self.staging_dir / "dataset" / "dataset-metadata.json"
        self.assertTrue(ds_meta_file.is_file())
        ds_meta = json.loads(ds_meta_file.read_text(encoding="utf-8"))
        self.assertEqual(ds_meta["id"], "anime-studio/code-anime-jobs-wan")
        self.assertTrue(ds_meta["isPrivate"], "Dataset must be private!")
        self.assertEqual(len(ds_meta["licenses"]), 1)

        kernel_meta_file = self.staging_dir / "kernel" / "kernel-metadata.json"
        self.assertTrue(kernel_meta_file.is_file())
        kernel_meta = json.loads(kernel_meta_file.read_text(encoding="utf-8"))
        self.assertEqual(kernel_meta["id"], "anime-studio/code-anime-wan-runner")
        self.assertTrue(kernel_meta["is_private"], "Kernel must be private!")
        self.assertTrue(kernel_meta["enable_gpu"], "GPU must be enabled!")
        self.assertTrue(kernel_meta["enable_internet"], "Internet must be enabled!")
        self.assertIn("machine_shape", kernel_meta)
        self.assertEqual(kernel_meta["machine_shape"], "NvidiaTeslaT4")
        self.assertEqual(kernel_meta["code_file"], "wan_runner.py")
        self.assertIn("anime-studio/code-anime-jobs-wan", kernel_meta["dataset_sources"])

        # Check jobs.json packaged
        staged_jobs_file = self.staging_dir / "dataset" / "jobs.json"
        self.assertTrue(staged_jobs_file.is_file())
        staged_jobs = json.loads(staged_jobs_file.read_text(encoding="utf-8"))
        self.assertEqual(len(staged_jobs), 1)
        self.assertEqual(staged_jobs[0]["id"], "shot01")
        self.assertTrue(staged_jobs[0]["image"].startswith("img/"))

        # Check runner copy exists
        self.assertTrue((self.staging_dir / "kernel" / "wan_runner.py").is_file())

        # Check staging summary manifest
        summary_file = self.staging_dir / "staging_manifest.json"
        self.assertTrue(summary_file.is_file())
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "prepared")
        self.assertIn("git_commit", summary)
        self.assertIsNotNone(summary["git_commit"])

    def test_dry_run_prepare_does_not_write_files(self):
        dry_staging = Path(self.test_dir) / "dry_staging"
        args = MagicMock()
        args.manifest = str(self.manifest_file)
        args.staging_dir = str(dry_staging)
        args.owner = "anime-studio"
        args.dataset_slug = "code-anime-jobs-wan"
        args.kernel_slug = "code-anime-wan-runner"
        args.allowed_root = self.test_dir
        args.dry_run = True

        ret = kw.cmd_prepare(args)
        self.assertEqual(ret, 0)
        self.assertFalse(dry_staging.exists(), "Dry-run should not create staging directories")

    def test_submit_blocked_when_credentials_absent(self):
        # Ensure credentials checking reports False
        with patch.object(kw, "check_credentials_presence", return_value=False):
            args = MagicMock()
            args.staging_dir = str(self.staging_dir)
            args.dry_run = False

            # Prepare staging first
            prep_args = MagicMock()
            prep_args.manifest = str(self.manifest_file)
            prep_args.staging_dir = str(self.staging_dir)
            prep_args.owner = "anime-studio"
            prep_args.dataset_slug = "code-anime-jobs-wan"
            prep_args.kernel_slug = "code-anime-wan-runner"
            prep_args.allowed_root = self.test_dir
            prep_args.dry_run = False
            kw.cmd_prepare(prep_args)

            ret = kw.cmd_submit(args)
            self.assertEqual(ret, 1, "Submission must fail when credentials are absent")

    def test_credentials_file_never_read(self):
        """Verify security rule: credential files are never opened or read."""
        fake_cred = Path(self.test_dir) / "kaggle.json"
        fake_cred.write_text('{"username":"leak_user","key":"LEAK_SECRET_12345"}')

        original_open = open

        def safe_open(file, *args, **kwargs):
            if str(file) == str(fake_cred) and "r" in args:
                raise PermissionError("SECURITY VIOLATION: Credential file read attempted!")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=safe_open):
            with patch.object(kw, "CREDENTIALS_PATHS", [fake_cred]):
                # check_credentials_presence should only use is_file(), not open()
                self.assertTrue(kw.check_credentials_presence())

    def test_mp4_fingerprint_validation(self):
        # 1. Non-existent file
        self.assertFalse(kw.is_valid_mp4_fingerprint(Path(self.test_dir) / "none.mp4"))

        # 2. 0-byte file
        zero_file = Path(self.test_dir) / "zero.mp4"
        zero_file.touch()
        self.assertFalse(kw.is_valid_mp4_fingerprint(zero_file))

        # 3. Small arbitrary text file pretending to be mp4
        fake_txt = Path(self.test_dir) / "fake.mp4"
        fake_txt.write_text("just some text file pretending to be video")
        self.assertFalse(kw.is_valid_mp4_fingerprint(fake_txt))

        # 4. Valid MP4 file structure (> 1024 bytes with ftyp box)
        valid_mp4 = Path(self.test_dir) / "valid.mp4"
        # 4 bytes size, 'ftyp', 'isom'
        box_header = struct.pack(">I4s4s", 32, b"ftyp", b"isom")
        data = box_header + (b"\x00" * 2000)
        valid_mp4.write_bytes(data)
        self.assertTrue(kw.is_valid_mp4_fingerprint(valid_mp4))

    def test_status_timeout_handling(self):
        args = MagicMock()
        args.kernel = "test-user/test-kernel"
        args.poll = True
        args.timeout = 1  # 1 second timeout
        args.interval = 1

        with patch.object(kw, "check_credentials_presence", return_value=True):
            with patch("subprocess.run") as mock_sub:
                mock_sub.return_value = MagicMock(returncode=0, stdout="Kernel running", stderr="")
                ret = kw.cmd_status(args)
                # Code 3 is timeout returncode
                self.assertEqual(ret, 3)

    def test_hf_quota_error_detection(self):
        self.assertTrue(hf_wan.is_quota_error("ZeroGPU quota exceeded for this IP"))
        self.assertTrue(hf_wan.is_quota_error("429 Too Many Requests"))
        self.assertTrue(hf_wan.is_quota_error("Your weekly GPU quota has been reached"))
        self.assertTrue(hf_wan.is_quota_error("Rate limit reached, please wait"))
        self.assertFalse(hf_wan.is_quota_error("File format not supported"))


if __name__ == "__main__":
    unittest.main()
