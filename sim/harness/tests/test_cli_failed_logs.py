"""``cli._print_failed_logs`` surfaces a failed scratch point's ngspice log
(issue #336). PDK-free and ngspice-free."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import cli  # noqa: E402


def _result(status, log="", message="", warnings=()):
    return SimpleNamespace(
        status=status, log=log, message=message, warnings=list(warnings),
        point=SimpleNamespace(corner_id="tt_27C"),
    )


class PrintFailedLogsTest(unittest.TestCase):
    def _capture(self, results, log_dir):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._print_failed_logs(results, log_dir)
        return out.getvalue()

    def test_failed_point_prints_message_and_log_tail(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tt_27C.log").write_text("line1\nError: boom\n")
            text = self._capture(
                [_result("failed", "tt_27C.log", "Error: boom")], Path(d))
        self.assertIn("FAILED POINT tt_27C: Error: boom", text)
        self.assertIn("| Error: boom", text)

    def test_ok_point_is_silent_and_missing_log_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            text = self._capture(
                [_result("ok", "a.log"), _result("failed", "gone.log", "x")],
                Path(d))
        self.assertEqual(text.count("FAILED POINT"), 1)
        self.assertIn("no ngspice log found", text)


if __name__ == "__main__":
    unittest.main()
