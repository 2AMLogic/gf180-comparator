#!/usr/bin/env python3
"""PDK-free regressions for the vendored-rulebook byte-identity pin (#168).

Covers the shared check (signoff/check_rulebook_pin.py) and both callers:
signoff/verify-report.py (check 0, which must fail before klt is looked up)
and signoff/regenerate.sh (which must fail before installing or grading).
Every mutation happens in a temporary copy of the files involved; the
committed rulebook, pin and report are hashed before and after the suite to
prove they were left untouched. No klt, PDK or network needed.

    python3 signoff/tests/test_check_rulebook_pin.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHECK = _load("check_rulebook_pin_under_test", "signoff/check_rulebook_pin.py")
VERIFY = _load("verify_report_under_test", "signoff/verify-report.py")

# Committed files these tests must never modify.
GUARDED = (
    CHECK.RULEBOOK,
    CHECK.PIN_FILE,
    "signoff/signoff-report.json",
    "signoff/block-manifest.json",
)

# Files copied into each temporary tree.
TREE_FILES = GUARDED + (
    "signoff/check_rulebook_pin.py",
    "signoff/verify-report.py",
    "signoff/regenerate.sh",
)

# A prose-only edit: appended commentary that touches no item heading, id,
# count, status or reason, so the grade-drift comparison could not see it.
PROSE_EDIT = "\nAn editorial clarification that changes no graded item.\n"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RulebookPinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {rel: _digest(REPO_ROOT / rel) for rel in GUARDED}

    @classmethod
    def tearDownClass(cls):
        after = {rel: _digest(REPO_ROOT / rel) for rel in GUARDED}
        assert after == cls.before, "committed signoff evidence was modified by the tests"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel in TREE_FILES:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, dst)

    # -- helpers -------------------------------------------------------------

    def _prose_edit(self):
        doc = self.root / CHECK.RULEBOOK
        doc.write_bytes(doc.read_bytes() + PROSE_EDIT.encode())

    def _refresh_pin(self):
        doc = self.root / CHECK.RULEBOOK
        (self.root / CHECK.PIN_FILE).write_text(
            f"{_digest(doc)}  {CHECK.RULEBOOK}\n"
        )

    def _run(self, *cmd, timeout=60):
        return subprocess.run(
            list(cmd), cwd=self.root, capture_output=True, text=True, timeout=timeout
        )

    # -- the shared check ----------------------------------------------------

    def test_committed_rulebook_matches_pin(self):
        self.assertEqual(CHECK.check(REPO_ROOT), [])
        self.assertEqual(CHECK.pinned_hash(REPO_ROOT), _digest(REPO_ROOT / CHECK.RULEBOOK))

    def test_pin_file_is_sha256sum_compatible(self):
        sha256sum = shutil.which("sha256sum")
        if not sha256sum:
            self.skipTest("sha256sum not available")
        proc = subprocess.run(
            [sha256sum, "-c", CHECK.PIN_FILE], cwd=REPO_ROOT, capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_prose_only_edit_fails_with_named_mismatch(self):
        self._prose_edit()
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn("rulebook hash mismatch", errs[0])
        self.assertIn(CHECK.RULEBOOK, errs[0])

    def test_missing_rulebook_fails_clearly(self):
        (self.root / CHECK.RULEBOOK).unlink()
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn("missing", errs[0])
        self.assertIn("no fallback", errs[0])

    def test_missing_pin_file_fails(self):
        (self.root / CHECK.PIN_FILE).unlink()
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn(CHECK.PIN_FILE, errs[0])

    def test_malformed_pin_fails(self):
        (self.root / CHECK.PIN_FILE).write_text("not-a-hash  signoff/design-evidence-tiers.md\n")
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn("malformed", errs[0])

    def test_pin_for_other_path_fails(self):
        pin = self.root / CHECK.PIN_FILE
        pin.write_text(pin.read_text().replace(CHECK.RULEBOOK, "docs/design-evidence-tiers.md"))
        errs = CHECK.check(self.root)
        self.assertEqual(len(errs), 1)
        self.assertIn("not the vendored rulebook", errs[0])

    def test_refreshed_pin_permits_deliberate_revendor(self):
        self._prose_edit()
        self.assertTrue(CHECK.check(self.root))
        self._refresh_pin()
        self.assertEqual(CHECK.check(self.root), [])

    # -- verify-report.py (check 0 and source_doc_content_hash) --------------

    def test_verify_report_fails_on_prose_edit_before_grading(self):
        self._prose_edit()
        proc = self._run(sys.executable, "signoff/verify-report.py")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("rulebook hash mismatch", proc.stderr)
        # Failed at check 0: never reached the wrappers, klt lookup or grader.
        self.assertNotIn("no klt binary", proc.stderr)
        self.assertNotIn("wrapper", proc.stderr)
        self.assertIn("1 signoff verification problem", proc.stderr)

    def test_verify_report_fails_on_missing_rulebook(self):
        (self.root / CHECK.RULEBOOK).unlink()
        proc = self._run(sys.executable, "signoff/verify-report.py")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(f"vendored rulebook {CHECK.RULEBOOK} is missing", proc.stderr)

    def test_verify_report_shares_the_check(self):
        self._prose_edit()
        self.assertEqual(VERIFY.verify_rulebook_pin(self.root), CHECK.check(self.root))
        self.assertEqual(VERIFY.verify_rulebook_pin(REPO_ROOT), [])

    def test_report_content_hash_must_match_pin(self):
        pin = CHECK.pinned_hash(REPO_ROOT)
        good = {"source_doc": VERIFY.VENDORED_DOC_PATH, "source_doc_content_hash": f"sha256:{pin}"}
        self.assertEqual(VERIFY.verify_vendored_doc(good, dict(good)), [])
        legacy = {"source_doc": VERIFY.VENDORED_DOC_PATH}  # pre-#2191 report schema
        self.assertEqual(VERIFY.verify_vendored_doc(legacy, dict(legacy)), [])
        bad = dict(good, source_doc_content_hash="sha256:" + "0" * 64)
        errs = VERIFY.verify_vendored_doc(good, bad)
        self.assertEqual(len(errs), 1)
        self.assertIn("rulebook hash mismatch", errs[0])
        self.assertIn("fresh grade", errs[0])

    def test_grade_drift_checks_retained(self):
        # Re-vendoring via a pin refresh does not bypass grade drift.
        committed = {"t1_item_count": 11, "items": []}
        fresh = {"t1_item_count": 10, "items": []}
        errs = VERIFY.grade_drift(fresh, committed)
        self.assertTrue(any("t1_item_count" in e for e in errs))

    # -- regenerate.sh -------------------------------------------------------

    def _regenerate(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available")
        report = self.root / "signoff" / "signoff-report.json"
        before = _digest(report)
        proc = self._run(bash, "signoff/regenerate.sh")
        self.assertEqual(_digest(report), before, "regenerate.sh rewrote the report")
        return proc

    def test_regenerate_refuses_prose_edited_rulebook(self):
        self._prose_edit()
        proc = self._regenerate()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("rulebook hash mismatch", proc.stderr)

    def test_regenerate_refuses_missing_rulebook(self):
        (self.root / CHECK.RULEBOOK).unlink()
        proc = self._regenerate()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("is missing", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
