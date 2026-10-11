"""Offline unit tests for the requirements.txt filter in kaggle/wan_runner.py.

wan_runner.py runs Kaggle-only side effects at module import time (nvidia-smi,
jobs.json lookup, etc.), so it can't be imported directly in a test. Instead we
pull the two pure helper functions out of the real source file via ast and exec
them in an isolated namespace, so the test exercises the actual production
code without triggering those side effects.
"""
import ast
import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / 'kaggle' / 'wan_runner.py'
PROTECTED_TORCH_PACKAGES = {'torch', 'torchvision', 'torchaudio'}


def _load_helpers():
    tree = ast.parse(SOURCE.read_text())
    wanted = {'normalize_dist_name', 'requirement_package_name'}
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {f.name for f in funcs} == wanted, 'helpers missing/renamed in kaggle/wan_runner.py'
    ns = {'re': re}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), filename=str(SOURCE), mode='exec'), ns)
    return ns['normalize_dist_name'], ns['requirement_package_name']


normalize_dist_name, requirement_package_name = _load_helpers()


class TestRequirementPackageName(unittest.TestCase):
    def test_parses_name_from_various_version_specifiers(self):
        cases = {
            'torch': 'torch',
            'torch==2.1.0': 'torch',
            'torch>=2.0,<3.0': 'torch',
            'torchvision==0.16.0': 'torchvision',
            'torchaudio': 'torchaudio',
            'torchsde': 'torchsde',
            'torchsde==0.2.6': 'torchsde',
            'numpy>=1.24': 'numpy',
            'transformers==4.40.0': 'transformers',
            '# a comment': None,
            '': None,
            '   ': None,
        }
        for line, expected in cases.items():
            self.assertEqual(requirement_package_name(line), expected, msg=line)

    def test_torchsde_is_not_treated_as_a_torch_prefix_match(self):
        # Regression: a naive `startswith('torch')` filter also drops torchsde,
        # which comfy.k_diffusion.sampling imports unconditionally.
        self.assertNotEqual(requirement_package_name('torchsde'), 'torch')
        self.assertNotIn(requirement_package_name('torchsde'), PROTECTED_TORCH_PACKAGES)


class TestNormalizeDistName(unittest.TestCase):
    def test_handles_pep503_separators_and_case(self):
        self.assertEqual(normalize_dist_name('Torch_SDE'), 'torch-sde')
        self.assertEqual(normalize_dist_name('torch.sde'), 'torch-sde')
        self.assertEqual(normalize_dist_name('TORCH'), 'torch')


class TestRequirementsFilter(unittest.TestCase):
    def test_keeps_torchsde_and_drops_protected_torch_builds(self):
        requirements_txt = '\n'.join([
            'torch==2.1.0',
            'torchvision==0.16.0',
            'torchaudio==2.1.0',
            'torchsde',
            'numpy>=1.24',
            'transformers==4.40.0',
            '# comment',
            '',
        ])
        kept = [l for l in requirements_txt.splitlines()
                if requirement_package_name(l) not in PROTECTED_TORCH_PACKAGES and requirement_package_name(l) is not None]

        self.assertIn('torchsde', kept)
        self.assertIn('numpy>=1.24', kept)
        self.assertIn('transformers==4.40.0', kept)
        self.assertFalse(any(requirement_package_name(l) in PROTECTED_TORCH_PACKAGES for l in kept))


if __name__ == '__main__':
    unittest.main()
