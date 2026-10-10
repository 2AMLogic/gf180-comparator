#!/usr/bin/env python3
"""PDK-free regressions for the targeted-run path of scripts/run-pdk-free-tests.sh (#212).

A single-file targeted run must apply the same ResourceWarning policy as a
named step: a finalizer-time leak is printed by Python but exits 0, so the
runner has to reject it itself.

    python3 signoff/tests/test_run_pdk_free_tests.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "run-pdk-free-tests.sh"

LEAK = """import gc, tempfile
f = open(tempfile.gettempdir() + '/run-pdk-free-tests-leak-data', 'w')
f.write('deliberate probe')
del f
gc.collect()
"""
CLEAN = "with open(__file__) as f:\n    f.read()\n"


def run_target(path: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    env["PYTHON"] = sys.executable
    return subprocess.run(
        ["bash", str(RUNNER), str(path)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False,
    )


class TargetedRunWarningPolicy(unittest.TestCase):
    def _write(self, d: str, name: str, body: str) -> Path:
        p = Path(d) / name
        p.write_text(body)
        return p

    def test_clean_script_passes(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_target(self._write(d, "test_clean.py", CLEAN))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_finalizer_leak_in_script_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_target(self._write(d, "test_leak.py", LEAK))
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ResourceWarning", r.stdout)

    def test_finalizer_leak_in_unittest_discovery_fails(self):
        # The runner matches sim/harness/tests/* by path prefix, so a temporary
        # file is placed there for the duration of the run.
        tests_dir = REPO_ROOT / "sim" / "harness" / "tests"
        probe = tests_dir / "test_zz_runner_leak_probe.py"
        probe.write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_leak(self):\n"
            "        import gc, tempfile\n"
            "        f = open(tempfile.gettempdir() + '/run-pdk-free-tests-leak-data', 'w')\n"
            "        del f\n"
            "        gc.collect()\n"
        )
        try:
            r = run_target(probe.relative_to(REPO_ROOT))
        finally:
            probe.unlink()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ResourceWarning", r.stdout)


if __name__ == "__main__":
    unittest.main()
