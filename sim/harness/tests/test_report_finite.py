"""#154: report summaries treat non-finite measurements as failures and the
JSON record is strict (no NaN/Infinity tokens). PDK-free."""

from __future__ import annotations

import json
import sys
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


class StrictJsonTest(unittest.TestCase):
    def test_nonfinite_replaced_and_located(self):
        omitted: list[str] = []
        out = report._strict_json_safe({"a": [1.0, float("nan")], "b": {"c": float("inf")}}, "$", omitted)
        self.assertEqual(out, {"a": [1.0, None], "b": {"c": None}})
        self.assertEqual(omitted, ["$.a[1]", "$.b.c"])
        json.dumps(out, allow_nan=False)  # must not raise


if __name__ == "__main__":
    unittest.main()
