#!/usr/bin/env python3
"""PDK-free regressions for signoff/check_klt_pin.py (#128).

Each case copies the pin-bearing files into a temp tree, mutates one site,
and asserts the check names it. Committed files are never touched.

    python3 signoff/tests/test_check_klt_pin.py
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_klt_pin_under_test", REPO_ROOT / "signoff" / "check_klt_pin.py"
)
CHECK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CHECK)


class KltPinTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel in [CHECK.SOURCE] + [r for r, _ in CHECK.SITES]:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / rel, dst)

    def _sub(self, rel, old, new, count=1):
        p = self.root / rel
        text = p.read_text()
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, count))

    def test_committed_tree_is_consistent(self):
        self.assertEqual(CHECK.check(REPO_ROOT), [])

    def test_workflow_drift_named(self):
        self._sub(".github/workflows/signoff.yml",
                  "pip install klayout-tools==", "pip install klayout-tools==9")
        errs = CHECK.check(self.root)
        self.assertTrue(errs)
        self.assertTrue(all(".github/workflows/signoff.yml" in e for e in errs))

    def test_verify_report_hint_drift_named(self):
        self._sub("signoff/verify-report.py",
                  "pip install klayout-tools==", "pip install klayout-tools==9")
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn("signoff/verify-report.py", errs[0])

    def test_readme_drift_named(self):
        self._sub("signoff/README.md", "`klayout-tools==", "`klayout-tools==9")
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn("signoff/README.md", errs[0])

    def test_source_change_flags_all_sites(self):
        self._sub("signoff/regenerate.sh", 'KLT_VERSION="', 'KLT_VERSION="9.')
        errs = CHECK.check(self.root)
        for rel in (".github/workflows/signoff.yml", "signoff/verify-report.py",
                    "signoff/README.md"):
            self.assertTrue(any(rel in e for e in errs), rel)

    def test_missing_pin_in_workflow_fails(self):
        p = self.root / ".github/workflows/signoff.yml"
        p.write_text(p.read_text().replace("klayout-tools==", "klayout-tools "))
        errs = CHECK.check(self.root)
        self.assertTrue(any("no klayout-tools==" in e for e in errs))

    def test_missing_source_fails(self):
        self._sub("signoff/regenerate.sh", "KLT_VERSION=", "OTHER=")
        self.assertIn("KLT_VERSION", CHECK.check(self.root)[0])


if __name__ == "__main__":
    unittest.main()
