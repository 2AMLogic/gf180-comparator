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


class StrictJsonTest(unittest.TestCase):
    def test_nonfinite_replaced_and_located(self):
        omitted: list[str] = []
        out = report._strict_json_safe({"a": [1.0, float("nan")], "b": {"c": float("inf")}}, "$", omitted)
        self.assertEqual(out, {"a": [1.0, None], "b": {"c": None}})
        self.assertEqual(omitted, ["$.a[1]", "$.b.c"])
        json.dumps(out, allow_nan=False)  # must not raise


if __name__ == "__main__":
    unittest.main()
