#!/usr/bin/env python3
"""PDK-free regressions for the pure helpers in layout/pex/pex_measure.py (#190).

Synthetic strings/dicts only, plus (#241) the committed bench inputs for the
pin/manifest preflight and temp-file mutations of them: no ngspice, no klt, no
PDK, no fleet. The module has no import-time side effects; `_check_pins` runs
only from `measure`.

    python3 layout/tests/test_pex_measure.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import shutil
import tempfile
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


class PinPreflight(unittest.TestCase):
    """#241: tb.json pinned by deck fields + graded bounds; fragments whole."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tb = json.loads(Path(pm.TB_JSON).read_text())
        self.saved = (pm.TB_JSON, pm.TB_MAIN, pm.TB_PROBE, dict(pm.PINNED_SHA256))
        self.addCleanup(self._restore)

    def _restore(self):
        pm.TB_JSON, pm.TB_MAIN, pm.TB_PROBE = self.saved[:3]
        pm.PINNED_SHA256.clear()
        pm.PINNED_SHA256.update(self.saved[3])

    def _use_tb(self, tb, raw=None):
        p = self.tmp / "tb.json"
        p.write_text(raw if raw is not None else json.dumps(tb, indent=3))
        pm.TB_JSON = str(p)

    def _refusal(self, fn=None):
        with self.assertRaises(SystemExit) as cm:
            (fn or pm._check_pins)()
        return str(cm.exception)

    def test_committed_inputs_pass(self):
        pm._check_pins()
        pm._check_meas_against_manifest()

    def test_metadata_formatting_and_supplemental_checks_float(self):
        tb = json.loads(json.dumps(self.tb))
        tb["description"] = "changed"
        tb["checks"]["td_od50_ns"]["description"] = "changed"
        tb["checks"]["td_od1_over_tau"]["min"] = 7.0
        tb["checks"]["brand_new_supplemental"] = {"min": 1.0}
        tb = dict(reversed(list(tb.items())))
        self._use_tb(tb)
        pm._check_pins()
        pm._check_meas_against_manifest()

    def test_canonical_hash_is_key_order_independent_and_matches_attribution(self):
        a = pm._tb_deck_sha256(self.tb)
        self.assertEqual(a, pm._tb_deck_sha256(dict(reversed(list(self.tb.items())))))
        self.assertEqual(a, pm.TB_JSON_DECK_SHA256)

    def test_deck_field_mutations_refuse(self):
        for mut in (lambda t: t["options"].append("itl1=1"),
                    lambda t: t["analyses"].__setitem__(0, "tran 5p 61n"),
                    lambda t: t["offset_probe"]["analyses"].__setitem__(0, "tran 1n 80u")):
            tb = json.loads(json.dumps(self.tb))
            mut(tb)
            self._use_tb(tb)
            self.assertIn("deck-field contract", self._refusal())

    def test_missing_or_malformed_fields_refuse(self):
        for key in ("options", "analyses", "offset_probe", "checks"):
            tb = json.loads(json.dumps(self.tb))
            del tb[key]
            self._use_tb(tb)
            msg = self._refusal()
            self.assertTrue("missing" in msg or "required" in msg, msg)
        tb = json.loads(json.dumps(self.tb))
        tb["options"] = "reltol=1e-4"
        self._use_tb(tb)
        self.assertIn("malformed", self._refusal())
        self._use_tb(None, raw="{not json")
        self.assertIn("cannot be read as JSON", self._refusal())
        self._use_tb(None, raw="[]")
        self.assertIn("not a JSON object", self._refusal())

    def test_missing_emitted_check_refuses(self):
        tb = json.loads(json.dumps(self.tb))
        del tb["checks"]["tau_ps"]
        self._use_tb(tb)
        self.assertIn("graded check 'tau_ps'", self._refusal())

    def test_emitted_row_bound_change_refuses(self):
        for name in pm.GRADED_CHECK_ROWS:
            tb = json.loads(json.dumps(self.tb))
            chk = tb["checks"][name]
            key = "min" if "min" in chk else "max"
            chk[key] = chk[key] + 0.5
            self._use_tb(tb)
            self.assertIn("grading-subset contract", self._refusal(), name)
        tb = json.loads(json.dumps(self.tb))
        del tb["checks"]["td_od50_ns"]["max"]
        self._use_tb(tb)
        self.assertIn("grading-subset contract", self._refusal())

    def test_fragment_one_byte_change_refuses(self):
        for attr in ("TB_MAIN", "TB_PROBE"):
            src = Path(getattr(pm, attr))
            copy = self.tmp / (attr + ".spice")
            copy.write_bytes(src.read_bytes() + b" ")
            pm.PINNED_SHA256[str(copy)] = self.saved[3][str(src)]
            setattr(pm, attr, str(copy))
            msg = self._refusal()
            self.assertIn("SPICE fragment sha256", msg)
            self.assertIn(attr + ".spice", msg)
            setattr(pm, attr, str(src))
            pm.PINNED_SHA256.pop(str(copy))

    def test_measure_refuses_before_any_work(self):
        tb = json.loads(json.dumps(self.tb))
        tb["options"].append("x=1")
        self._use_tb(tb)
        work = self.tmp / "work"
        with self.assertRaises(SystemExit):
            pm.measure("schematic", pm.SCHEMATIC_NETLIST, str(work), "local")
        self.assertFalse(work.exists())

    def test_meas_manifest_check_refuses_malformed(self):
        tb = json.loads(json.dumps(self.tb))
        tb["analyses"] = "tran"
        self._use_tb(tb)
        self.assertIn("malformed", self._refusal(pm._check_meas_against_manifest))


if __name__ == "__main__":
    unittest.main()
