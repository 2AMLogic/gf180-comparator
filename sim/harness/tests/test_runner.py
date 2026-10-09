"""Unit tests for ``harness.runner.run_point``'s error-visibility contract.

Regression coverage for #7: ``run_point()`` used to consult
``proc.returncode`` / ``_ERROR_RE`` only inside the ``if missing:`` branch,
so a non-fatal ngspice error (non-zero exit, or an Error/Fatal/doAnalyses:
line) was silently discarded whenever every requested measurement still
happened to parse -- the point came back ``status="ok"`` with no trace of
what ngspice reported. These tests stub the ``ngspice`` subprocess call (and
``compose_deck``, which is exercised by ``harness/testbench.py``'s own
fixtures already) so they run without ngspice installed and without a real
testbench/PDK/DUT.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.corners import CORNERS, PvtPoint  # noqa: E402
from harness.runner import PointResult, run_point  # noqa: E402


def _fake_completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["ngspice", "-b", "deck.spice"], returncode=returncode, stdout=stdout, stderr=""
    )


class RunPointWarningsTest(unittest.TestCase):
    def setUp(self):
        self.point = PvtPoint(corner=CORNERS["tt"], temp_c=27.0, vdd=3.3, index=0)
        self.tb = types.SimpleNamespace(measure={"vos_mv": "v(out)"})
        self.pdk = types.SimpleNamespace()
        self.dut = types.SimpleNamespace()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workdir = Path(self._tmp.name)

    def _run(self, stdout: str, returncode: int = 0) -> PointResult:
        with mock.patch("harness.runner.compose_deck", return_value="* stub deck\n"), \
             mock.patch(
                 "harness.runner.subprocess.run",
                 return_value=_fake_completed(stdout, returncode),
             ):
            return run_point(self.tb, self.pdk, self.dut, self.point, self.workdir)

    def test_clean_run_has_no_warnings(self):
        """returncode == 0, no _ERROR_RE match -> status=ok, warnings=[]."""
        result = self._run("m_vos_mv = 6.9043645202e-01\n")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.warnings, [])

    def test_nonzero_returncode_with_all_measurements_parsed_is_still_ok_but_warns(self):
        """The bug in #7: a non-fatal error must not be discarded just
        because every requested measurement still printed."""
        result = self._run("m_vos_mv = 6.9043645202e-01\n", returncode=1)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.warnings, "non-zero returncode must surface a warning")
        self.assertTrue(any("1" in w for w in result.warnings))

    def test_error_re_match_with_all_measurements_parsed_is_still_ok_but_warns(self):
        stdout = "doAnalyses: convergence problem, retrying\nm_vos_mv = 6.9043645202e-01\n"
        result = self._run(stdout, returncode=0)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.warnings, "an _ERROR_RE match must surface a warning")
        self.assertTrue(any("doAnalyses" in w for w in result.warnings))

    def test_missing_measurement_still_fails_and_carries_warnings(self):
        result = self._run("Error: singular matrix\n", returncode=1)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.missing, ["vos_mv"])
        self.assertTrue(result.warnings)

    def test_overflowed_exponent_cannot_complete_point(self):
        """1e999 parses as inf: the required measurement is rejected, not ok."""
        result = self._run("m_vos_mv = 1e999\n")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.missing, ["vos_mv"])
        self.assertNotIn("vos_mv", result.measurements)
        self.assertTrue(any("NONFINITE_MEASUREMENT" in w and "vos_mv" in w for w in result.warnings))
        self.assertIn("non-finite", result.message)

    def test_negative_overflow_rejected_and_later_finite_value_wins_nothing_stale(self):
        result = self._run("m_vos_mv = 6.9e-01\nm_vos_mv = -1e999\n")
        self.assertEqual(result.status, "failed")
        self.assertNotIn("vos_mv", result.measurements)

    def test_as_dict_includes_warnings_only_when_present(self):
        clean = self._run("m_vos_mv = 6.9043645202e-01\n")
        self.assertNotIn("warnings", clean.as_dict())

        warned = self._run("m_vos_mv = 6.9043645202e-01\n", returncode=1)
        self.assertIn("warnings", warned.as_dict())
        self.assertEqual(warned.as_dict()["warnings"], warned.warnings)


class OffsetProbeWarningsTest(unittest.TestCase):
    """#86: probe diagnostics propagate into the enclosing PointResult."""

    MAIN = "m_vos_mv = 6.9e-01\n"

    def setUp(self):
        self.point = PvtPoint(corner=CORNERS["tt"], temp_c=27.0, vdd=3.3, index=0)
        self.tb = types.SimpleNamespace(measure={"vos_mv": "v(out)"})
        self.probe_tb = types.SimpleNamespace()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workdir = Path(self._tmp.name)

    def _run(self, probe, main=None):
        """probe/main: CompletedProcess or an exception to raise."""
        calls = []
        outcomes = [probe] + ([main] if main is not None else [])

        def fake(*a, **kw):
            calls.append(a)
            out = outcomes[len(calls) - 1]
            if isinstance(out, BaseException):
                raise out
            return out

        with mock.patch("harness.runner.compose_deck", return_value="* stub\n"), \
             mock.patch("harness.runner.subprocess.run", side_effect=fake):
            result = run_point(self.tb, types.SimpleNamespace(), types.SimpleNamespace(),
                               self.point, self.workdir, probe_tb=self.probe_tb)
        return result, len(calls)

    def test_clean_probe_adds_no_warning(self):
        result, _ = self._run(_fake_completed("m_dut_vos = 1.5e-03\n"),
                              _fake_completed(self.MAIN))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.measurements["dut_vos_v"], 1.5e-03)

    def test_probe_nonzero_exit_with_value_warns(self):
        result, _ = self._run(_fake_completed("m_dut_vos = 1.5e-03\n", 1),
                              _fake_completed(self.MAIN))
        self.assertEqual(result.status, "ok")
        self.assertTrue(any("offset probe" in w and "exited 1" in w and "vosprobe.log" in w
                            for w in result.warnings))
        self.assertEqual(result.as_dict()["warnings"], result.warnings)

    def test_probe_error_lines_with_value_warn(self):
        stdout = "doAnalyses: timestep too small\nFatal: boom\nm_dut_vos = 1.5e-03\n"
        result, _ = self._run(_fake_completed(stdout), _fake_completed(self.MAIN))
        self.assertEqual(result.status, "ok")
        self.assertTrue(any("offset probe" in w and "doAnalyses" in w for w in result.warnings))
        self.assertTrue(any("Fatal" in w for w in result.warnings))

    def test_probe_and_main_warnings_both_kept(self):
        result, _ = self._run(_fake_completed("m_dut_vos = 1e-3\n", 1),
                              _fake_completed(self.MAIN, 2))
        self.assertTrue(any(w.startswith("offset probe") for w in result.warnings))
        self.assertIn("ngspice exited 2", result.warnings)

    def test_missing_offset_stops_main_and_keeps_warnings(self):
        result, ncalls = self._run(_fake_completed("Error: singular matrix\n", 1))
        self.assertEqual(ncalls, 1)
        self.assertEqual(result.status, "failed")
        self.assertIn("no dut_vos", result.message)
        self.assertTrue(any("singular matrix" in w for w in result.warnings))

    def test_probe_timeout_stops_main(self):
        result, ncalls = self._run(subprocess.TimeoutExpired("ngspice", 1800))
        self.assertEqual(ncalls, 1)
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.log.endswith("vosprobe.log"))

    # -- timeout diagnostics (#148) ---------------------------------------

    def _read(self, name):
        return (self.workdir / name).read_text()

    def test_probe_timeout_keeps_partial_output_and_diagnostic(self):
        exc = subprocess.TimeoutExpired(
            "ngspice", 1800, output="PROBE_OUT_SENTINEL\n", stderr="PROBE_ERR_SENTINEL\n")
        result, ncalls = self._run(exc)
        self.assertEqual(ncalls, 1)
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.log.endswith("vosprobe.log"))
        log = self._read(result.log)
        self.assertIn("PROBE_OUT_SENTINEL", log)
        self.assertIn("PROBE_ERR_SENTINEL", log)
        self.assertTrue(log.rstrip().endswith("TIMEOUT after 1800s"))
        self.assertIn("offset probe timed out after 1800s", result.message)
        self.assertTrue(any(w.startswith("offset probe (") and "TIMEOUT after 1800s" in w
                            for w in result.warnings))

    def test_main_timeout_keeps_output_and_probe_warning(self):
        exc = subprocess.TimeoutExpired(
            "ngspice", 600, output=b"MAIN_OUT_SENTINEL\n", stderr=b"MAIN_ERR_SENTINEL\n")
        result, ncalls = self._run(_fake_completed("m_dut_vos = 1e-3\n", 1), exc)
        self.assertEqual(ncalls, 2)
        self.assertEqual(result.status, "error")
        log = self._read(result.log)
        self.assertIn("MAIN_OUT_SENTINEL", log)
        self.assertIn("MAIN_ERR_SENTINEL", log)
        self.assertTrue(log.rstrip().endswith("TIMEOUT after 600s"))
        self.assertFalse(result.log.endswith("vosprobe.log"))
        self.assertTrue(any(w.startswith("offset probe") and "exited 1" in w
                            for w in result.warnings))
        self.assertTrue(any("main deck" in w and "TIMEOUT after 600s" in w
                            for w in result.warnings))
        record = result.as_dict()
        self.assertEqual(record["warnings"], result.warnings)
        self.assertEqual(record["status"], "error")

    def test_timeout_output_types_do_not_raise(self):
        for out, err in ((b"\xff\xfebytes", b""), ("text", "text"), (None, None)):
            with self.subTest(out=out, err=err):
                exc = subprocess.TimeoutExpired("ngspice", 1800, output=out, stderr=err)
                result, _ = self._run(exc)
                self.assertEqual(result.status, "failed")
                self.assertIn("TIMEOUT after 1800s", self._read(result.log))
                exc = subprocess.TimeoutExpired("ngspice", 600, output=out, stderr=err)
                result, _ = self._run(_fake_completed("m_dut_vos = 1e-3\n"), exc)
                self.assertEqual(result.status, "error")
                self.assertIn("TIMEOUT after 600s", self._read(result.log))


if __name__ == "__main__":
    unittest.main()


class ParseMeasurementsFiniteTest(unittest.TestCase):
    def test_finite_values_kept(self):
        from harness.runner import parse_measurements
        self.assertEqual(parse_measurements("m_a = 1.5e-3\nm_b = -2\n"), {"a": 1.5e-3, "b": -2.0})

    def test_nonfinite_dropped_and_reported(self):
        from harness.runner import parse_measurements
        bad: list[str] = []
        self.assertEqual(parse_measurements("m_a = 1e999\nm_b = 3\n", bad), {"b": 3.0})
        self.assertEqual(bad, ["a"])

