"""#154: report summaries treat non-finite measurements as failures and the
JSON record is strict (no NaN/Infinity tokens). PDK-free."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import report  # noqa: E402
from harness.corners import CORNERS, PvtPoint  # noqa: E402
from harness.runner import PointResult  # noqa: E402


def _result(idx: int, value: float) -> PointResult:
    point = PvtPoint(corner=CORNERS["tt"], temp_c=27.0 + idx, vdd=3.3, index=idx)
    return PointResult(point=point, status="ok", measurements={"vos_mv": value})


def _tb(checks=None):
    return types.SimpleNamespace(measure={"vos_mv": "v(out)"}, checks=checks or {})


class SummarizeFiniteTest(unittest.TestCase):
    def test_finite_values_summarized_without_failures(self):
        s = report.summarize(_tb({"vos_mv": {"max": 5.0}}), [_result(0, 1.0), _result(1, 3.0)])["vos_mv"]
        self.assertEqual((s.minimum, s.maximum, s.failures), (1.0, 3.0, []))

    def test_nan_and_inf_are_failures_not_statistics(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            tb = _tb({"vos_mv": {"max": 5.0}})
            s = report.summarize(tb, [_result(0, 1.0), _result(1, bad)])["vos_mv"]
            self.assertTrue(any("NONFINITE_MEASUREMENT" in f for f in s.failures), (bad, s.failures))
            self.assertEqual(list(s.values.values()), [1.0])
            self.assertTrue(all(v == v for v in (s.minimum, s.maximum, s.mean)))

    def test_all_nonfinite_fails_even_without_check(self):
        s = report.summarize(_tb(), [_result(0, float("nan"))])["vos_mv"]
        self.assertTrue(s.failures)
        self.assertEqual(s.values, {})


class PointCheckOutcomeTest(unittest.TestCase):
    """#255: the corner table's pass/fail column is the point-local bound verdict."""

    def _checked(self, checks):
        return types.SimpleNamespace(measure={"vos_mv": "v(out)"}, checks=checks)

    def test_in_bound_point_passes_and_out_of_bound_fails(self):
        tb = self._checked({"vos_mv": {"min": 0.0, "max": 1.0}})
        ok = report.point_check_outcome(tb, _result(0, 0.5))
        hi = report.point_check_outcome(tb, _result(1, 2.0))
        lo = report.point_check_outcome(tb, _result(2, -1.0))
        self.assertEqual(ok, {"status": "pass", "failures": []})
        self.assertEqual(hi["status"], "fail")
        self.assertIn("2 > allowed max 1", hi["failures"][0])
        self.assertIn("-1 < required min 0", lo["failures"][0])

    def test_nonfinite_or_absent_measurement_never_passes(self):
        tb = self._checked({"vos_mv": {"max": 1.0}})
        self.assertEqual(report.point_check_outcome(tb, _result(0, float("nan")))["status"], "fail")
        empty = _result(1, 0.0)
        empty.measurements = {}
        self.assertEqual(report.point_check_outcome(tb, empty)["status"], "fail")

    def test_grid_only_spread_failure_is_not_a_point_failure(self):
        tb = self._checked({"vos_mv": {"max_spread_pct": 1.0}})
        results = [_result(0, 1.0), _result(1, 3.0)]
        self.assertTrue(report.summarize(tb, results)["vos_mv"].failures)
        for r in results:
            self.assertEqual(report.point_check_outcome(tb, r)["status"], "pass")

    def test_failed_simulation_not_evaluated(self):
        r = _result(0, 1.0)
        r.status = "failed"
        out = report.point_check_outcome(self._checked({"vos_mv": {"max": 0.0}}), r)
        self.assertEqual(out["status"], "not_evaluated")


class RecordOutputOutcomeTest(unittest.TestCase):
    """#255: the written markdown rows and JSON check_outcome agree. PDK-free."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "tb.spice").write_text("* tb\n")
        (self.root / "dut.spice").write_text("* dut\n")

    def _tb(self, checks):
        return types.SimpleNamespace(
            measure={"vos_mv": "v(out)"}, checks=checks, claim="c", evidence={},
            experiment="exp", experiment_dir=self.root / "exp",
            netlist=self.root / "tb.spice", netlist_sha256="0" * 64,
            manifest_sha256="1" * 64, provenance=lambda: {"experiment": "exp"},
        )

    def _context(self, rid):
        return {
            "record_id": rid, "dut_id": "d", "dut_provenance": "schematic",
            "dut_netlist": "dut.spice", "dut_netlist_sha256": "2" * 64,
            "commit": "abc", "dirty": False,
            "pdk": {"variant": "v", "open_pdks_version": "1", "discovered_via": "x"},
            "toolchain": {"observed": {"ngspice": "n", "python": "p"}, "drift": []},
        }

    def _write(self, tb, results, rid):
        path = report.write_record(
            tb, results, report.summarize(tb, results), self._context(rid),
            self.root / "dut.spice",
        )
        md = (tb.experiment_dir / "records" / f"{rid}.md").read_text()
        doc = json.loads((tb.experiment_dir / "records" / f"{rid}.json").read_text())
        return md, doc, path

    def _rows(self, md):
        return [ln for ln in md.splitlines() if ln.lstrip().startswith("| `tt")]

    def test_in_bound_and_high_low_failures(self):
        tb = self._tb({"vos_mv": {"min": 0.0, "max": 1.0}})
        results = [_result(0, 0.5), _result(1, 2.0), _result(2, -1.0)]
        md, doc, _ = self._write(tb, results, "r1")
        rows = self._rows(md)
        self.assertTrue(rows[0].rstrip().endswith("| PASS |"))
        self.assertIn("**FAIL**: vos_mv 2 > allowed max 1", rows[1])
        self.assertIn("**FAIL**: vos_mv -1 < required min 0", rows[2])
        self.assertEqual(
            [p["check_outcome"]["status"] for p in doc["points"]],
            ["pass", "fail", "fail"],
        )
        self.assertIn("aggregate checks over", md)

    def test_absent_measurement_renders_and_fails(self):
        tb = self._tb({"vos_mv": {"max": 1.0}})
        empty = _result(0, 0.0)
        empty.measurements = {}
        md, doc, _ = self._write(tb, [empty], "r2")
        self.assertIn("| — | **FAIL**: vos_mv missing or non-finite |", self._rows(md)[0])
        self.assertEqual(doc["points"][0]["check_outcome"]["status"], "fail")

    def test_nonfinite_measurement_fails_in_both_artifacts(self):
        tb = self._tb({"vos_mv": {"max": 1.0}})
        md, doc, _ = self._write(tb, [_result(0, float("nan"))], "r3")
        self.assertIn("**FAIL**: vos_mv missing or non-finite", self._rows(md)[0])
        self.assertEqual(doc["points"][0]["check_outcome"]["status"], "fail")

    def test_grid_only_failure_keeps_local_pass(self):
        tb = self._tb({"vos_mv": {"max_spread_pct": 1.0}})
        md, doc, _ = self._write(tb, [_result(0, 1.0), _result(1, 3.0)], "r4")
        for row in self._rows(md):
            self.assertTrue(row.rstrip().endswith("| PASS |"), row)
        self.assertEqual(
            [p["check_outcome"]["status"] for p in doc["points"]], ["pass", "pass"]
        )
        self.assertIn("- **Verdict**: FAIL", md)
        self.assertTrue(doc["summary"]["vos_mv"]["failures"])

    def test_failed_simulation_is_not_evaluated(self):
        tb = self._tb({"vos_mv": {"max": 0.0}})
        bad = _result(0, 1.0)
        bad.status = "failed"
        bad.message = "ngspice died"
        md, doc, _ = self._write(tb, [bad], "r5")
        self.assertIn("**FAILED**: ngspice died", self._rows(md)[0])
        self.assertEqual(doc["points"][0]["check_outcome"]["status"], "not_evaluated")


class StrictJsonTest(unittest.TestCase):
    def test_nonfinite_replaced_and_located(self):
        omitted: list[str] = []
        out = report._strict_json_safe({"a": [1.0, float("nan")], "b": {"c": float("inf")}}, "$", omitted)
        self.assertEqual(out, {"a": [1.0, None], "b": {"c": None}})
        self.assertEqual(omitted, ["$.a[1]", "$.b.c"])
        json.dumps(out, allow_nan=False)  # must not raise


if __name__ == "__main__":
    unittest.main()
