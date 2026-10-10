#!/usr/bin/env python3
"""PDK-free regressions for the pure helpers in layout/pex/pex_measure.py (#190).

Synthetic strings/dicts only: no ngspice, no klt, no bench files, and none of
the bench sha256 pins are read (the module has no import-time side effects;
`_check_pins` runs only from `measure`).

    python3 layout/tests/test_pex_measure.py
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PEX = Path(__file__).resolve().parents[1] / "pex" / "pex_measure.py"
_spec = importlib.util.spec_from_file_location("pex_measure", PEX)
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)


class CornerId(unittest.TestCase):
    def test_format(self):
        self.assertEqual(pm.corner_id("tt", 27.0, 3.3), "tt_27c_3.30v")
        self.assertEqual(pm.corner_id("ss", -40.0, 2.97), "ss_-40c_2.97v")
        self.assertEqual(pm.corner_id("ff", 125, 3.63), "ff_125c_3.63v")


class ReplaceOnce(unittest.TestCase):
    def test_single_match_replaced(self):
        self.assertEqual(pm._replace_once("a X b", "X", "Y", "w"), "a Y b")

    def test_absent_anchor_exits(self):
        with self.assertRaises(SystemExit) as cm:
            pm._replace_once("a b", "X", "Y", "where.spice")
        self.assertIn("where.spice", str(cm.exception))
        self.assertIn("found 0", str(cm.exception))

    def test_duplicate_anchor_exits(self):
        with self.assertRaises(SystemExit) as cm:
            pm._replace_once("X a X", "X", "Y", "w")
        self.assertIn("found 2", str(cm.exception))


class StripComments(unittest.TestCase):
    def test_full_line_comments_dropped_including_indented(self):
        text = "* header\nr1 a b 1k\n   * indented\n.meas tran x trig v(a)"
        self.assertEqual(pm._strip_comments(text),
                         "r1 a b 1k\n.meas tran x trig v(a)")

    def test_meas_text_and_inline_star_kept(self):
        # Only lines that START with '*' go; a '*' inside an expression or a
        # trailing position is left alone (current behaviour, pinned here).
        text = ".meas tran p param='a*b'\nr1 a b 1k * trailing"
        self.assertEqual(pm._strip_comments(text), text)


class AssertVddValOnlyOnSupplies(unittest.TestCase):
    def test_supply_lines_allowed_case_insensitive_name(self):
        pm._assert_vdd_val_only_on_supplies(
            "VSUP vdd 0 dc {vdd_val}\nvsupa vdda 0 {vdd_val}\nr1 a b 1k",
            ("vsup", "vsupa"), "w")

    def test_no_reference_passes(self):
        pm._assert_vdd_val_only_on_supplies("r1 a b 1k", ("vsup",), "w")

    def test_reference_outside_supplies_exits(self):
        with self.assertRaises(SystemExit) as cm:
            pm._assert_vdd_val_only_on_supplies(
                "vsup vdd 0 {vdd_val}\nvclk clk 0 pulse(0 {vdd_val} 1n)",
                ("vsup",), "tb.spice")
        self.assertIn("tb.spice", str(cm.exception))
        self.assertIn("vclk", str(cm.exception))


class VosSource(unittest.TestCase):
    def points(self):
        # Distinct value per (temp, supply) so the nesting order is visible.
        return {(t, v): 1e-3 * (10 * i + j + 1)
                for i, t in enumerate(pm.TEMPERATURES_C)
                for j, v in enumerate(pm.SUPPLIES_V)}

    def test_renders_one_branch_per_point(self):
        pts = self.points()
        src = pm._vos_source(pts)
        self.assertTrue(src.startswith("Bvos vos 0 v = '"))
        for val in pts.values():
            self.assertEqual(src.count(repr(val)), 1, val)

    def test_stable_order_and_thresholds(self):
        pts = self.points()
        src = pm._vos_source(pts)
        self.assertEqual(src, pm._vos_source(dict(reversed(list(pts.items())))))
        # Temperature outer, supply inner, ascending, cold/low-supply first.
        order = [src.index(repr(pts[(t, v)]))
                 for t in pm.TEMPERATURES_C for v in pm.SUPPLIES_V]
        self.assertEqual(order, sorted(order))
        self.assertIn("temper < -6.5", src)
        self.assertIn("temper < 76", src)
        self.assertIn("v(vdd) < 3.135", src)
        self.assertIn("v(vdd) < 3.465", src)

    def test_missing_point_raises(self):
        pts = self.points()
        del pts[(27.0, 3.3)]
        with self.assertRaises(KeyError):
            pm._vos_source(pts)


class Derive(unittest.TestCase):
    RAW = {"td_a": 1.0e-9, "td_b": 2.0e-9, "td_c": 2.0e-9 + 2.302585093e-10,
           "da_end": 3.3, "da_first": 0.1, "db_end": 3.2, "db_first": 0.2,
           "dc_end": 3.1, "dc_first": 0.3,
           "i_stat": -2.0e-4, "vsup_v": 3.3, "q_dec": 1.0e-12}

    def test_values(self):
        out = pm._derive(self.RAW)
        self.assertAlmostEqual(out["td_od50_ns"], 1.0)
        self.assertAlmostEqual(out["td_od1_ns"], 2.0)
        self.assertAlmostEqual(out["tau_ps"], 100.0, places=3)
        self.assertAlmostEqual(out["resolve_decades"], 2.0e-9 / 1.0e-10, places=3)
        self.assertAlmostEqual(out["i_static_ua"], 200.0)
        self.assertAlmostEqual(out["p_static_uw"], 660.0)
        self.assertAlmostEqual(
            out["e_dec_fj"], abs(1.0e-12 - (-2.0e-4) * 8.1e-9) * 3.3 * 1e15)
        self.assertEqual(out["dout_od50_end"], 3.3)
        self.assertEqual(out["dout_od01_first"], 0.3)

    def test_none_inputs_give_none_not_numbers(self):
        out = pm._derive({})
        for k in ("td_od50_ns", "td_od1_ns", "td_od01_ns", "tau_ps",
                  "resolve_decades", "i_static_ua", "e_dec_fj", "p_static_uw"):
            self.assertIsNone(out[k], k)
        raw = dict(self.RAW, td_a=None, i_stat=None)
        out = pm._derive(raw)
        self.assertIsNone(out["td_od50_ns"])
        self.assertIsNone(out["p_static_uw"])
        self.assertIsNone(out["e_dec_fj"])
        self.assertIsNotNone(out["td_od1_ns"])
        self.assertIsNotNone(out["tau_ps"])

    def test_equal_td_b_td_c_has_no_tau(self):
        out = pm._derive(dict(self.RAW, td_c=self.RAW["td_b"]))
        self.assertIsNone(out["tau_ps"])
        self.assertIsNone(out["resolve_decades"])


class Grade(unittest.TestCase):
    def test_none_is_error_never_pass(self):
        self.assertEqual(pm._grade("td_od50_ns", None, {}), "error")
        self.assertEqual(pm._grade("anything", None, {"anything": {"min": 0}}),
                         "error")

    def test_no_check_with_value_passes(self):
        self.assertEqual(pm._grade("tau_ps", 12.0, {}), "pass")

    def test_min_max_boundaries_inclusive(self):
        checks = {"x": {"min": 1.0, "max": 2.0}}
        self.assertEqual(pm._grade("x", 1.0, checks), "pass")
        self.assertEqual(pm._grade("x", 2.0, checks), "pass")
        self.assertEqual(pm._grade("x", 0.999, checks), "fail")
        self.assertEqual(pm._grade("x", 2.001, checks), "fail")

    def test_spec_limits(self):
        lim = pm.SPEC_TD_OD50_NS_MAX
        self.assertEqual(pm._grade("td_od50_ns", lim, {}), "pass")
        self.assertEqual(pm._grade("td_od50_ns", lim + 1e-9, {}), "fail")
        lim = pm.SPEC_P_STATIC_UW_MAX
        self.assertEqual(pm._grade("p_static_uw", lim, {}), "pass")
        self.assertEqual(pm._grade("p_static_uw", lim + 1e-6, {}), "fail")

    def test_spec_limit_applies_even_if_check_is_looser(self):
        checks = {"td_od50_ns": {"max": 100.0}}
        self.assertEqual(pm._grade("td_od50_ns", 5.0, checks), "fail")

    def test_dut_vos_must_be_strictly_inside_probe_span(self):
        s = pm.PROBE_VSPAN
        self.assertEqual(pm._grade("dut_vos_v", s * 0.99, {}), "pass")
        self.assertEqual(pm._grade("dut_vos_v", -s * 0.99, {}), "pass")
        self.assertEqual(pm._grade("dut_vos_v", s, {}), "fail")
        self.assertEqual(pm._grade("dut_vos_v", -s, {}), "fail")


if __name__ == "__main__":
    unittest.main()
