"""#260: dirty_paths() fails closed when git cannot be inspected.
PDK-free; subprocess.run is mocked."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import report  # noqa: E402


def _cp(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(["git"], returncode, stdout, stderr)


def _patch(**kw):
    return mock.patch.object(report.subprocess, "run", **kw)


class FailClosedTests(unittest.TestCase):
    def test_nonzero_status_empty_stdout_raises(self):
        with _patch(return_value=_cp("", 128, "fatal: not a git repository")):
            with self.assertRaises(report.GitInspectionError) as cm:
                report.dirty_paths()
        self.assertIn("not a git repository", str(cm.exception))

    def test_missing_git_raises(self):
        with _patch(side_effect=FileNotFoundError("git")):
            with self.assertRaises(report.GitInspectionError):
                report.dirty_paths()

    def test_timeout_raises(self):
        with _patch(side_effect=subprocess.TimeoutExpired("git", 60)):
            with self.assertRaises(report.GitInspectionError):
                report.dirty_paths()


class SuccessTests(unittest.TestCase):
    def test_empty_success_is_clean(self):
        with _patch(return_value=_cp("")):
            self.assertEqual(report.dirty_paths(), [])

    def test_tracked_modification_is_dirty(self):
        with _patch(return_value=_cp(" M sim/harness/cli.py\n")):
            self.assertEqual(report.dirty_paths(), ["M sim/harness/cli.py"])

    def test_untracked_evidence_dirs_excluded(self):
        out = ("?? sim/x/records/y.json\n?? sim/x/corners/r1/\n"
               "?? sim/x/netlist-snapshots/s\n")
        with _patch(return_value=_cp(out)):
            self.assertEqual(report.dirty_paths(), [])

    def test_untracked_elsewhere_is_dirty(self):
        with _patch(return_value=_cp("?? sim/x/tb.sp\n")):
            self.assertEqual(report.dirty_paths(), ["?? sim/x/tb.sp"])


if __name__ == "__main__":
    unittest.main()
