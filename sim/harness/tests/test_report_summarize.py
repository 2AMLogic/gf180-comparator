"""#176: ``report.summarize`` bound checks and the per-axis sensitivity
guard (skipped vs failed-flat vs failed-weakest/strongest-slice).
PDK-free; synthetic ``PointResult`` grids only."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import report  # noqa: E402
from harness.corners import CORNERS, PvtPoint  # noqa: E402
from harness.runner import PointResult  # noqa: E402


def _result(value, corner="tt", temp=27.0, vdd=3.3, idx=0) -> PointResult:
    point = PvtPoint(corner=CORNERS[corner], temp_c=temp, vdd=vdd, index=idx)
    return PointResult(point=point, status="ok", measurements={"m": value})


def _tb(checks=None):
    return types.SimpleNamespace(measure={"m": "v(out)"}, checks={"m": checks} if checks else {})


def _summ(checks, results):
    return report.summarize(_tb(checks), results)["m"]


def _temp_grid(values, corner="tt"):
    """Grid sweeping temperature only."""
    return [_result(v, corner=corner, temp=-40.0 + 40.0 * i, idx=i) for i, v in enumerate(values)]


def _process_grid(values):
    names = ["tt", "ss", "ff", "sf", "fs"]
    return [_result(v, corner=names[i], idx=i) for i, v in enumerate(values)]


def _supply_grid(values):
    return [_result(v, vdd=3.0 + 0.3 * i, idx=i) for i, v in enumerate(values)]


class SpreadPctTest(unittest.TestCase):
    def test_fewer_than_two_values_is_zero(self):
        self.assertEqual(report.spread_pct([]), 0.0)
        self.assertEqual(report.spread_pct([5.0]), 0.0)

    def test_peak_to_peak_over_mean(self):
        # (12-8)/10 * 100
        self.assertAlmostEqual(report.spread_pct([8.0, 12.0]), 40.0)

    def test_uses_abs_mean(self):
        self.assertAlmostEqual(report.spread_pct([-12.0, -8.0]), 40.0)

    def test_zero_mean_large_positive_no_error(self):
        s = report.spread_pct([-1.0, 1.0])
        self.assertGreater(s, 1e30)
        self.assertEqual(s, 2.0 / 1e-30 * 100.0)

    def test_all_zero_is_zero(self):
        self.assertEqual(report.spread_pct([0.0, 0.0]), 0.0)

    def test_near_zero_mean_large_positive(self):
        s = report.spread_pct([-1.0, 1.0 + 2e-6])
        self.assertGreater(s, 1e6)

    def test_flat_is_zero(self):
        self.assertEqual(report.spread_pct([3.0, 3.0, 3.0]), 0.0)


class SweptAxesTest(unittest.TestCase):
    def test_one_point_sweeps_nothing(self):
        self.assertEqual(report.swept_axes([_result(1.0)]), set())

    def test_each_axis_independently(self):
        self.assertEqual(report.swept_axes(_process_grid([1, 2])), {"process"})
        self.assertEqual(report.swept_axes(_temp_grid([1, 2])), {"temperature"})
        self.assertEqual(report.swept_axes(_supply_grid([1, 2])), {"supply"})

    def test_all_axes(self):
        rs = [_result(1, "tt", 27, 3.3), _result(2, "ss", 85, 3.0)]
        self.assertEqual(report.swept_axes(rs), {"process", "temperature", "supply"})


class PerAxisSpreadsTest(unittest.TestCase):
    def test_unswept_axes_do_not_vary(self):
        axes = report.per_axis_spreads(_temp_grid([10.0, 20.0]), "m")
        self.assertTrue(axes["temperature"].varies)
        self.assertFalse(axes["process"].varies)
        self.assertFalse(axes["supply"].varies)

    def test_weakest_and_strongest_slices(self):
        # Two temperature slices (distinct vdd), tt corner.
        rs = [
            _result(10.0, temp=0, vdd=3.0, idx=0), _result(10.0 + 1.0, temp=50, vdd=3.0, idx=1),
            _result(10.0, temp=0, vdd=3.6, idx=2), _result(10.0 + 4.0, temp=50, vdd=3.6, idx=3),
        ]
        ax = report.per_axis_spreads(rs, "m")["temperature"]
        self.assertTrue(ax.varies)
        self.assertAlmostEqual(ax.weakest, report.spread_pct([10.0, 11.0]))
        self.assertAlmostEqual(ax.strongest, report.spread_pct([10.0, 14.0]))
        self.assertLess(ax.weakest, ax.strongest)

    def test_slices_bucket_by_other_axes(self):
        # Diagonal grid: every point has unique (temp, vdd) -> no process slice.
        rs = [_result(1.0, "tt", 27, 3.3), _result(2.0, "ss", 85, 3.0)]
        axes = report.per_axis_spreads(rs, "m")
        self.assertFalse(any(a.varies for a in axes.values()))

    def test_missing_measurement_ignored(self):
        self.assertFalse(any(a.varies for a in report.per_axis_spreads(_temp_grid([1, 2]), "other").values()))


class ScalarBoundsTest(unittest.TestCase):
    def test_min_pass_and_fail(self):
        self.assertEqual(_summ({"min": 1.0}, _temp_grid([1.0, 2.0])).failures, [])
        f = _summ({"min": 1.5}, _temp_grid([1.0, 2.0])).failures
        self.assertEqual(len(f), 1)
        self.assertIn("min 1", f[0])
        self.assertIn("required 1.5", f[0])

    def test_max_pass_and_fail(self):
        self.assertEqual(_summ({"max": 2.0}, _temp_grid([1.0, 2.0])).failures, [])
        f = _summ({"max": 1.5}, _temp_grid([1.0, 2.0])).failures
        self.assertEqual(len(f), 1)
        self.assertIn("max 2", f[0])
        self.assertIn("allowed 1.5", f[0])

    def test_max_spread_pct_pass_and_fail(self):
        g = _temp_grid([8.0, 12.0])  # 40 %
        self.assertEqual(_summ({"max_spread_pct": 40.0}, g).failures, [])
        f = _summ({"max_spread_pct": 30.0}, g).failures
        self.assertEqual(len(f), 1)
        self.assertIn("> allowed 30", f[0])

    def test_min_spread_pct_pass_and_fail(self):
        g = _temp_grid([8.0, 12.0])
        self.assertEqual(_summ({"min_spread_pct": 40.0}, g).failures, [])
        f = _summ({"min_spread_pct": 50.0}, g).failures
        self.assertEqual(len(f), 1)
        self.assertIn("< required 50", f[0])

    def test_at_min_at_max_reported(self):
        s = _summ({"min": 0.0}, _temp_grid([5.0, 1.0, 9.0]))
        self.assertEqual((s.minimum, s.maximum), (1.0, 9.0))
        self.assertNotEqual(s.at_min, s.at_max)

    def test_no_values_fails(self):
        r = PointResult(point=_result(1.0).point, status="failed", measurements={})
        s = _summ({"min": 0.0}, [r])
        self.assertEqual(len(s.failures), 1)
        self.assertIn("no completed points", s.failures[0])

    def test_non_ok_points_excluded(self):
        bad = _result(-100.0, temp=85.0, idx=5)
        bad.status = "failed"
        s = _summ({"min": 0.0}, _temp_grid([1.0, 2.0]) + [bad])
        self.assertEqual(s.failures, [])
        self.assertEqual(s.minimum, 1.0)


class MinSpreadByAxisTest(unittest.TestCase):
    CHK = {"min_spread_pct_by_axis": {"temperature": 10.0}}

    def test_one_point_grid_is_skipped_not_failed(self):
        s = _summ(self.CHK, [_result(1.0)])
        self.assertEqual(s.failures, [])
        self.assertEqual(len(s.skipped), 1)
        self.assertIn("min_spread_pct_by_axis[temperature]", s.skipped[0])
        self.assertIn("SKIPPED", s.skipped[0])

    def test_unswept_axis_skipped_on_swept_grid(self):
        s = _summ({"min_spread_pct_by_axis": {"supply": 1.0}}, _temp_grid([1.0, 2.0]))
        self.assertEqual(s.failures, [])
        self.assertEqual(len(s.skipped), 1)

    def test_swept_and_moving_passes(self):
        s = _summ(self.CHK, _temp_grid([8.0, 12.0]))
        self.assertEqual((s.failures, s.skipped), ([], []))

    def test_swept_but_flat_fails_weakest_slice(self):
        # This is the --sabotage-corners shape: axis swept, value constant.
        s = _summ(self.CHK, _temp_grid([5.0, 5.0, 5.0]))
        self.assertEqual(s.skipped, [])
        self.assertEqual(len(s.failures), 1)
        self.assertIn("weakest temperature slice", s.failures[0])

    def test_sabotage_process_axis_flat_fails(self):
        s = _summ({"min_spread_pct_by_axis": {"process": 1.0}}, _process_grid([5.0] * 5))
        self.assertEqual(s.skipped, [])
        self.assertIn("weakest process slice", s.failures[0])

    def test_weakest_slice_below_bound_fails_even_if_other_strong(self):
        rs = [
            _result(10.0, temp=0, vdd=3.0, idx=0), _result(10.0, temp=50, vdd=3.0, idx=1),
            _result(10.0, temp=0, vdd=3.6, idx=2), _result(20.0, temp=50, vdd=3.6, idx=3),
        ]
        s = _summ(self.CHK, rs)
        self.assertEqual(len(s.failures), 1)
        self.assertIn("weakest temperature slice spread 0 %", s.failures[0])

    def test_swept_axis_with_no_slice_never_varies(self):
        # Diagonal grid: process is swept but no two points share (temp, vdd).
        rs = [_result(1.0, "tt", 27, 3.3), _result(2.0, "ss", 85, 3.0)]
        s = _summ({"min_spread_pct_by_axis": {"process": 1.0}}, rs)
        self.assertEqual(s.skipped, [])
        self.assertEqual(len(s.failures), 1)
        self.assertIn("never varies", s.failures[0])


class MaxSpreadByAxisTest(unittest.TestCase):
    CHK = {"max_spread_pct_by_axis": {"supply": 50.0}}

    def test_one_point_grid_is_skipped_not_failed(self):
        s = _summ(self.CHK, [_result(1.0)])
        self.assertEqual(s.failures, [])
        self.assertEqual(len(s.skipped), 1)
        self.assertIn("max_spread_pct_by_axis[supply]", s.skipped[0])

    def test_unswept_axis_skipped(self):
        s = _summ(self.CHK, _temp_grid([1.0, 2.0]))
        self.assertEqual((s.failures, len(s.skipped)), ([], 1))

    def test_within_bound_passes(self):
        s = _summ(self.CHK, _supply_grid([9.0, 11.0]))  # 20 %
        self.assertEqual((s.failures, s.skipped), ([], []))

    def test_strongest_slice_over_bound_fails(self):
        s = _summ(self.CHK, _supply_grid([5.0, 15.0]))  # 100 %
        self.assertEqual(s.skipped, [])
        self.assertEqual(len(s.failures), 1)
        self.assertIn("strongest supply slice", s.failures[0])
        self.assertIn("> allowed 50", s.failures[0])

    def test_strongest_slice_is_the_one_checked(self):
        rs = [
            _result(10.0, temp=0, vdd=3.0, idx=0), _result(10.0, temp=0, vdd=3.6, idx=1),
            _result(5.0, temp=85, vdd=3.0, idx=2), _result(15.0, temp=85, vdd=3.6, idx=3),
        ]
        s = _summ(self.CHK, rs)
        self.assertEqual(len(s.failures), 1)

    def test_swept_axis_with_no_slice_never_varies(self):
        rs = [_result(1.0, "tt", 27, 3.3), _result(2.0, "ss", 85, 3.0)]
        s = _summ({"max_spread_pct_by_axis": {"temperature": 50.0}}, rs)
        self.assertEqual(s.skipped, [])
        self.assertIn("never varies", s.failures[0])


class ZeroMeanSummarizeTest(unittest.TestCase):
    def test_zero_mean_grid_does_not_raise(self):
        s = _summ({"max_spread_pct": 1000.0}, _temp_grid([-1.0, 1.0]))
        self.assertGreater(s.spread, 1e30)
        self.assertEqual(len(s.failures), 1)

    def test_near_zero_mean_by_axis(self):
        s = _summ({"min_spread_pct_by_axis": {"temperature": 1e6}}, _temp_grid([-1.0, 1.0 + 2e-6]))
        self.assertEqual(s.failures, [])


if __name__ == "__main__":
    unittest.main()
