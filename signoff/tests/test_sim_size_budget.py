#!/usr/bin/env python3
"""PDK-free regressions for signoff/check_sim_size_budget.py (#246).

    python3 signoff/tests/test_sim_size_budget.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_sim_size_budget_under_test", REPO_ROOT / "signoff" / "check_sim_size_budget.py")
CHECK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CHECK)

MIB = 1024 * 1024
BIG = "sim/comparator-x/corners/20261010-000000-abcdef0/report.json"


def run_repo(size: int, allow: dict | None, path: str = BIG):
    """Commit one file of `size` bytes in a temp repo and run main()."""
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        f = repo / path
        f.parent.mkdir(parents=True)
        f.write_bytes(b"\0" * size)
        for cmd in (["init", "-q"], ["add", "-A"],
                    ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"]):
            subprocess.run(["git", *cmd], cwd=repo, check=True)
        al = Path(d) / "allow.json"
        if allow is not None:
            al.write_text(json.dumps(allow))
        out = io.StringIO()
        with redirect_stdout(out):
            rc = CHECK.main(["--repo", str(repo), "--allowlist", str(al)])
        return rc, out.getvalue()


ARCH = "layout/pex/artifacts/ground-c-budget/20261010-154019-b9fff0f/big.json"
ARCH_EDITABLE = "layout/pex/artifacts/ground-c-budget/README.md"


class SizeBudget(unittest.TestCase):
    def test_under_budget(self):
        rc, out = run_repo(1 * MIB, None)
        self.assertEqual(rc, 0)
        self.assertNotIn("WARN", out)

    def test_warn_band(self):
        rc, out = run_repo(6 * MIB, None)
        self.assertEqual(rc, 0)
        self.assertIn("WARN", out)

    def test_over_budget_without_allowlist(self):
        rc, out = run_repo(26 * MIB, None)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", out)
        self.assertIn(BIG, out)

    def test_over_budget_with_allowlist(self):
        rc, out = run_repo(26 * MIB, {BIG: "full-grid campaign, record cites it"})
        self.assertEqual(rc, 0)
        self.assertIn("GRANDFATHERED", out)

    def test_allowlist_requires_reason(self):
        rc, out = run_repo(26 * MIB, {BIG: "  "})
        self.assertEqual(rc, 1)
        self.assertIn("no reason", out)

    def test_stale_allowlist_entry_fails(self):
        rc, out = run_repo(1 * MIB, {"sim/comparator-x/corners/gone.json": "old"})
        self.assertEqual(rc, 1)
        self.assertIn("stale", out)

    def test_unprotected_path_not_budgeted(self):
        rc, _ = run_repo(26 * MIB, None, path="sim/comparator-x/testbench/big.spice")
        self.assertEqual(rc, 0)

    def test_archive_oversized_blob_fails(self):
        rc, out = run_repo(26 * MIB, None, path=ARCH)
        self.assertEqual(rc, 1)
        self.assertIn(ARCH, out)

    def test_archive_warn_and_grandfather(self):
        rc, out = run_repo(6 * MIB, None, path=ARCH)
        self.assertEqual((rc, "WARN" in out), (0, True))
        rc, out = run_repo(26 * MIB, {ARCH: "diagnostic grid, cited by study"}, path=ARCH)
        self.assertEqual(rc, 0)
        self.assertIn("GRANDFATHERED", out)

    def test_archive_unprotected_sibling_not_budgeted(self):
        rc, _ = run_repo(26 * MIB, None, path=ARCH_EDITABLE)
        self.assertEqual(rc, 0)

    def test_committed_allowlist_passes_on_repo(self):
        self.assertEqual(CHECK.main(["--repo", str(REPO_ROOT)]), 0)


if __name__ == "__main__":
    unittest.main()
