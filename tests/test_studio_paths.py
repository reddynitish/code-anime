import tempfile
import unittest
from pathlib import Path

from studio.paths import UnsafePathError, safe_join


class SafeJoinTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_simple_join_stays_inside_base(self):
        result = safe_join(self.base, "a", "b.txt")
        self.assertEqual(result, (self.base / "a" / "b.txt").resolve())

    def test_dotdot_segment_rejected(self):
        with self.assertRaises(UnsafePathError):
            safe_join(self.base, "..", "etc", "passwd")

    def test_dotdot_inside_single_part_rejected(self):
        with self.assertRaises(UnsafePathError):
            safe_join(self.base, "a/../../etc/passwd")

    def test_absolute_part_rejected(self):
        with self.assertRaises(UnsafePathError):
            safe_join(self.base, "/etc/passwd")

    def test_empty_segment_rejected(self):
        with self.assertRaises(UnsafePathError):
            safe_join(self.base, "")


if __name__ == "__main__":
    unittest.main()
