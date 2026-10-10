#!/usr/bin/env python3
"""PDK-free tests for layout/run_drc.py's `klt drc` exit-code contract (#184).

`subprocess.run` is mocked: exit 0 (clean) and 3 (violations) both carry a
JSON payload on stdout; any other exit code is a hard failure that forwards
stderr and raises SystemExit. `main()` returns 0 only for `status: clean`;
any other status fails closed (klt's own code, or 1 if klt exited 0).

    python3 layout/tests/test_run_drc.py
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LAYOUT = Path(__file__).resolve().parents[1]
if str(LAYOUT) not in sys.path:
    sys.path.insert(0, str(LAYOUT))

import run_drc  # noqa: E402


def _proc(code: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


def _report(status: str) -> dict:
    return {
        "status": status,
        "violation_count": 0 if status == "clean" else 2,
        "rule_counts": {} if status == "clean" else {"m1.s": 2},
        "provenance": {"deck": {"name": "gf180mcu", "content_hash": "abc"},
                       "klt_version": "0.0.0"},
    }


class RunDrcContract(unittest.TestCase):
    def test_exit_0_and_3_return_payload_and_code(self):
        for code, status in ((0, "clean"), (3, "violations")):
            rep = _report(status)
            with mock.patch.object(run_drc.subprocess, "run",
                                   return_value=_proc(code, json.dumps(rep))):
                got, rc = run_drc.run_drc()
            self.assertEqual(got, rep)
            self.assertEqual(rc, code)

    def test_invocation(self):
        with mock.patch.object(run_drc.subprocess, "run",
                               return_value=_proc(0, "{}")) as m:
            run_drc.run_drc()
        cmd = m.call_args.args[0]
        self.assertEqual(cmd[:2], ["klt", "drc"])
        self.assertIn(run_drc.DECK, cmd)
        self.assertIn(run_drc.TOP, cmd)
        self.assertEqual(cmd[cmd.index("--format") + 1], "json")
        self.assertEqual(m.call_args.kwargs["cwd"], run_drc.REPO_ROOT)

    def test_other_exit_codes_raise_and_forward_stderr(self):
        for code in (1, 2, 4, 127):
            err = io.StringIO()
            with mock.patch.object(run_drc.subprocess, "run",
                                   return_value=_proc(code, "", "boom\n")), \
                    contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    run_drc.run_drc()
            self.assertIn(f"exit {code}", str(cm.exception))
            self.assertEqual(err.getvalue(), "boom\n")


class MainAndReport(unittest.TestCase):
    def _main(self, code, status):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(run_drc, "OUTDIR", d), \
                mock.patch.object(run_drc, "run_drc",
                                  return_value=(_report(status), code)), \
                mock.patch.object(run_drc, "write_report") as w, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = run_drc.main()
        w.assert_called_once()
        return rc

    def test_main_zero_only_when_clean(self):
        self.assertEqual(self._main(0, "clean"), 0)
        self.assertEqual(self._main(3, "violations"), 3)
        # a non-clean status never maps to 0, even with klt exit code 0
        self.assertEqual(self._main(0, "violations"), 1)
        self.assertEqual(self._main(0, "error"), 1)

    def test_write_report_deterministic(self):
        rep = {"b": 1, "a": {"z": 2, "y": [3]}}
        with tempfile.TemporaryDirectory() as d:
            p1, p2 = str(Path(d) / "1.json"), str(Path(d) / "2.json")
            run_drc.write_report(rep, p1)
            run_drc.write_report(dict(reversed(list(rep.items()))), p2)
            t1, t2 = Path(p1).read_text(), Path(p2).read_text()
        self.assertEqual(t1, t2)
        self.assertTrue(t1.endswith("}\n"))
        self.assertFalse(t1.endswith("\n\n"))
        self.assertLess(t1.index('"a"'), t1.index('"b"'))
        self.assertEqual(json.loads(t1), rep)


if __name__ == "__main__":
    unittest.main()
