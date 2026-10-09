#!/usr/bin/env python3
"""PDK-free regressions for layout/routing_table.py's --check guard (#121).

Each case copies routing_table.py plus the three files it reads into a
temporary directory and runs the copy as a subprocess, so the script's
HERE-relative paths resolve inside the tmpdir. Committed files are never
touched.

    python3 layout/tests/test_routing_table.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAYOUT = Path(__file__).resolve().parents[1]
FILES = ("routing_table.py", "comparator.routing.json",
         "comparator.gen-compose.json", "README.md")


class RoutingTableCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        for name in FILES:
            shutil.copy(LAYOUT / name, self.dir / name)

    def run_mode(self, *args):
        return subprocess.run(
            [sys.executable, str(self.dir / "routing_table.py"), *args],
            capture_output=True, text=True)

    def test_committed_readme_is_current(self):
        r = self.run_mode("--check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_doctored_routing_json_fails_check_then_write_fixes(self):
        path = self.dir / "comparator.routing.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["nets"][0]["route_length_um"] += 123.4
        path.write_text(json.dumps(data), encoding="utf-8")

        r = self.run_mode("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("STALE", r.stderr)

        self.assertEqual(self.run_mode("--write").returncode, 0)
        r = self.run_mode("--check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_net_mismatch_is_a_hard_error(self):
        path = self.dir / "comparator.routing.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["nets"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        r = self.run_mode("--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("disagrees", r.stderr)


if __name__ == "__main__":
    unittest.main()
