"""PDK-free, klt-free tests for the extracted-transient feasibility contract
(issue #219): ``sim/tools/extracted_tran_feasibility.py``.

Synthetic fixtures only. Every refusal path the issue names has a fixture:
missing/ambiguous observation nodes, invalid gain, missing/non-finite
ingredients, out-of-range trips, wrong endpoint decisions, late flips, plus the
feasibility-specific gates (mismatch not exercised, edge margin, probe not
bracketed, identity, body bias, mismatch support).
"""

from __future__ import annotations

import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM = Path(__file__).resolve().parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM / "tools"))

import extracted_tran_feasibility as ef  # noqa: E402
import mk_klt_request as mk  # noqa: E402
from harness import testbench as htb  # noqa: E402

TB = htb.load(SIM / ef.BENCH)
P = TB.params
STEP, V0, LEAD = P["stair_step_mv"], P["stair_v0_mv"], int(P["stair_lead_cycles"])
T0, PER = P["stair_t0_ns"] * 1e-9, P["stair_period_ns"] * 1e-9


def draw(k, **kw):
    """A valid single draw whose decision first flips at staircase level k."""
    d = {"t_trip": T0 + (k + LEAD) * PER + 5e-9, "dn_start": 0.0, "dn_end": 1.0,
         "dd_start": -0.1, "dd_end": 0.1, "ap_start": 2.0}
    d.update(kw)
    return d


def population(levels, **kw):
    return {f"mc{i}": draw(k, **kw) for i, k in enumerate(levels)}


LEVELS = [28, 30, 31, 32, 32, 33, 34, 36]  # a spread around the middle of 64


def trip_mv(centre, k):
    return centre + V0 + k * STEP - STEP / 2


class Stimulus(unittest.TestCase):
    def test_pwl_matches_committed_schematic_staircase_at_centre_zero(self):
        committed = (SIM / "comparator-offset-tran/testbench/tb_offset_tran.spice").read_text()
        want = re.search(r"^vsd sd 0 pwl\((.*?)^\+ \)", committed, re.S | re.M).group(1)
        got = ef.stair_pwl(0.0, V0 * 1e-3, STEP * 1e-3, 64, P["stair_t0_ns"],
                           P["stair_period_ns"], LEAD)
        num = lambda s: [(float(t[:-1]), float(v[:-1]))  # noqa: E731
                         for t, v in re.findall(r"([-\d.]+n)\s+([-\d.]+m)", s)]
        a, b = num(want), num(got)
        self.assertEqual(len(a), len(b))
        for (ta, va), (tb, vb) in zip(a, b):
            self.assertEqual(ta, tb)
            self.assertAlmostEqual(va, vb, places=3)

    def test_centre_shifts_every_level(self):
        got = ef.stair_pwl(-21.57e-3, V0 * 1e-3, STEP * 1e-3, 64, 4.0, 24.0, LEAD)
        vals = [float(v[:-1]) for v in re.findall(r"([-\d.]+m)", got)]
        self.assertAlmostEqual(min(vals), -21.57 + V0, places=3)
        self.assertAlmostEqual(max(vals), -21.57 - V0, places=3)

    def test_probe_centre_rounding_and_refusals(self):
        def rep(status="pass", t=3e-5, v=-0.0215682):
            return {"corners": [{"corner_id": "tt/27C", "status": status, "measurements": [
                {"name": "t_flip", "value": t}, {"name": "vos_v", "value": v}]}]}
        c = ef.centre_from_probe(rep(), {}, 0.01, 40.0)
        self.assertAlmostEqual(c["centre_mv"], -21.57)
        self.assertAlmostEqual(c["trip_mv"], -21.5682)
        for bad, code in ((rep(status="error"), "PROBE_FAILED"),
                          (rep(v=None), "PROBE_NONFINITE"),
                          (rep(v=float("nan")), "PROBE_NONFINITE"),
                          (rep(v=-0.039), "PROBE_AT_SPAN_EDGE"),
                          ({"corners": []}, "PROBE_UNITS")):
            with self.assertRaises(ef.Refusal) as cm:
                ef.centre_from_probe(bad, {}, 0.01, 40.0)
            self.assertEqual(cm.exception.code, code)
        with self.assertRaises(ef.Refusal) as cm:
            ef.centre_from_probe(rep(), {"monte_carlo": {"n": 3}}, 0.01, 40.0)
        self.assertEqual(cm.exception.code, "PROBE_NOT_MISMATCH_FREE")


class Population(unittest.TestCase):
    CID, CENTRE = "ff_125c_3.63v", -21.57

    def ev(self, raw, probe=None, n=None, centre=None):
        centre = self.CENTRE if centre is None else centre
        return ef.evaluate_population(TB, self.CID, raw, centre,
                                      trip_mv(centre, 32) if probe is None else probe,
                                      len(raw) if n is None else n)

    def refused(self, code, *a, **k):
        with self.assertRaises(ef.Refusal) as cm:
            self.ev(*a, **k)
        self.assertEqual(cm.exception.code, code, cm.exception.msg)
        return cm.exception.msg

    def test_valid_population_reports_absolute_mean_and_separate_sigma(self):
        r = self.ev(population(LEVELS))
        trips = [trip_mv(self.CENTRE, k) for k in LEVELS]
        self.assertAlmostEqual(r["trip_abs_mean_mv"], sum(trips) / len(trips), places=6)
        # ABSOLUTE: the deterministic layout offset is visible, centre not subtracted.
        self.assertLess(r["trip_abs_mean_mv"], -20.0)
        self.assertEqual(r["centre_mv"], self.CENTRE)
        self.assertGreater(r["sig_trip_raw_mv"], r["sig_trip_mv"] > 0 and r["sig_trip_mv"] or 0)
        self.assertGreater(r["sig_trip_mv"], 0)
        self.assertEqual(r["trip_levels"], [28, 36])
        self.assertNotIn("sig_vos_pre_mv", r)       # decomposition withheld
        self.assertNotIn("sig_rload_mv", r)         # hand budget withheld

    def test_mean_independent_of_how_the_centre_is_labelled(self):
        # the SAME level pattern at two centres moves the absolute mean one-for-one
        a = self.ev(population(LEVELS), centre=-21.57, probe=-21.57 - 0.4)["trip_abs_mean_mv"]
        b = self.ev(population(LEVELS), centre=-8.22, probe=-8.22 - 0.4)["trip_abs_mean_mv"]
        self.assertAlmostEqual(b - a, -8.22 + 21.57, places=6)

    def test_wrong_endpoint_decisions(self):
        raw = population(LEVELS)
        raw["mc0"]["dn_start"] = 0.9
        self.assertIn("BAD_ENDPOINT_DECISION", self.refused("DRAW_VALIDATION", raw))
        raw = population(LEVELS)
        raw["mc1"]["dn_end"] = 0.2
        self.assertIn("BAD_ENDPOINT_DECISION", self.refused("DRAW_VALIDATION", raw))

    def test_trip_out_of_range(self):
        for k in (0, 64, -1, 70):
            raw = population(LEVELS)
            raw["mc0"] = draw(k)
            self.assertIn("TRIP_OUT_OF_RANGE", self.refused("DRAW_VALIDATION", raw))

    def test_late_flip(self):
        raw = population(LEVELS)
        raw["mc2"]["t_trip"] += 8.5e-9   # 13.5 ns after the rise, past the 8 ns clock-high
        self.assertIn("LATE_FLIP", self.refused("DRAW_VALIDATION", raw))

    def test_invalid_gain(self):
        raw = population(LEVELS)
        raw["mc3"]["dd_end"] = raw["mc3"]["dd_start"] - 0.01
        self.assertIn("ZERO_GAIN", self.refused("DRAW_VALIDATION", raw))
        raw = population(LEVELS)
        raw["mc3"]["dd_end"] = raw["mc3"]["dd_start"]
        self.assertIn("ZERO_GAIN", self.refused("DRAW_VALIDATION", raw))

    def test_missing_and_nonfinite_ingredients(self):
        for bad in (None, float("nan"), float("inf")):
            raw = population(LEVELS)
            raw["mc4"]["t_trip"] = bad
            self.assertIn("NONFINITE_INGREDIENT", self.refused("DRAW_VALIDATION", raw))
        raw = population(LEVELS)
        del raw["mc4"]["dd_end"]
        self.assertIn("NONFINITE_INGREDIENT", self.refused("DRAW_VALIDATION", raw))

    def test_mismatch_not_exercised(self):
        self.refused("MISMATCH_NOT_EXERCISED", population([32] * 8))

    def test_edge_margin(self):
        self.refused("EDGE_MARGIN", population([1, 2, 30, 31, 32, 33, 34, 35]))
        self.refused("EDGE_MARGIN", population([28, 30, 31, 32, 33, 34, 61, 62]))

    def test_probe_not_bracketed(self):
        # the mismatch-free probe lies 5 mV above everything the draws flipped at
        self.refused("PROBE_NOT_BRACKETED", population(LEVELS), probe=trip_mv(self.CENTRE, 32) + 5.0)

    def test_sample_count(self):
        self.refused("SAMPLE_COUNT", population(LEVELS), n=len(LEVELS) + 2)


# ---- netlist contract fixtures ---------------------------------------------

PINS = "CLK DOUT DOUTB IBIAS VDD VINN VINP VSS"
BASE = """\
.SUBCKT COMPARATOR {pins}
M$1 n9__t1 vinp__t0 tl__t1 vss__t1 nfet_03v3 L=2U W=30U
M$2 n7__t1 vinn__t0 tl__t2 vss__t2 nfet_03v3 L=2U W=30U
M$3 tl__t0 ibias__t0 vss__t0 vss__t3 nfet_03v3 L=4U W=10U
M$4 q__t0 n7__t2 vss__t4 {b4} nfet_03v3 L=0.5U W=8U
M$5 r__t0 n9__t2 vdd__t6 vdd__t7 pfet_03v3 L=0.5U W=8U
X$6 n9__t0 vdd__t0 vss__t8 ppolyf_u_1k r_length=120U r_width=1U m=1
X$7 vdd__t1 n7__t0 vss__t9 ppolyf_u_1k r_length=120U r_width=1U m=1
{legs}
.ENDS COMPARATOR
"""
LEGS = "\n".join(
    f"R{n} {n} {n.rsplit('__t', 1)[0]} 10.0"
    for n in ("n9__t0 n9__t1 n9__t2 n7__t0 n7__t1 n7__t2 tl__t0 tl__t1 tl__t2 "
              "vinp__t0 vinn__t0 ibias__t0 vdd__t0 vdd__t1 q__t0 r__t0 vdd__t6 vdd__t7 "
              "vss__t0 vss__t1 vss__t2 vss__t3 vss__t4 vss__t5 vss__t8 vss__t9").split())
NET = BASE.format(pins=PINS, legs=LEGS, b4="vss__t5")
#: The schematic-side equivalent: same (model, L, W) multiset, different spelling.
SCH = """\
XM1 a b c vss nfet_03v3 L=2u W=30u nf=1
XM2 a b c vss nfet_03v3 L=2u W=30u nf=1
XM3 a b c vss nfet_03v3 L=4u W=10u nf=1
XM4 a b c vss nfet_03v3 L=0.5u W=8u nf=1
XM5 a b c vdd pfet_03v3 L=0.5u W=8u nf=1
XR1 a b vss ppolyf_u_1k r_length=120u r_width=1u m=1
XR2 a b vss ppolyf_u_1k r_length=120u r_width=1u m=1
"""
PDK_OK = """\
.lib fets_mm
.subckt nfet_03v3 d g s b w=1e-5 l=2.8e-7
.param mis_vth=agauss(0,1m,1)
m0 d g s b nfet_03v3 w=w l=l delvto='mis_vth*sw_stat_mismatch'
.ends nfet_03v3
.subckt pfet_03v3 d g s b w=1e-5 l=2.8e-7
.param mis_vth=agauss(0,1m,1)
m0 d g s b pfet_03v3 w=w l=l delvto='mis_vth*sw_stat_mismatch'
.ends pfet_03v3
.endl
"""
REPORT = {"unbiased_pmos_body_nets": [], "missing_flavour_markers": [],
          "parasitics": {"nets": []}}


class Contract(unittest.TestCase):
    def test_standard_adapter_form_is_refused_as_bypassing_mismatch(self):
        # the shipped adapter writes bare `M... nfet_03v3` instances of the PDK .model
        with self.assertRaises(ef.Refusal) as cm:
            ef.check_device_mismatch_support(NET, SCH, PDK_OK)
        self.assertEqual(cm.exception.code, "ADAPTED_MOS_BYPASS_MISMATCH")
        self.assertIn("changes NOTHING", cm.exception.msg)

    def test_mismatch_capable_variant_ok_and_counts(self):
        v = ef.mismatch_capable(NET)
        r = ef.check_device_mismatch_support(v, SCH, PDK_OK)
        self.assertEqual(r["mos_devices"], 5)
        self.assertEqual(r["card_form"], "subckt call")
        self.assertTrue(r["geometry_multiset_equals_schematic"])

    def test_variant_changes_only_the_mos_card_prefix(self):
        v = ef.mismatch_capable(NET).splitlines()
        for old, new in zip(NET.splitlines(), v):
            if re.match(r"M\$", old):
                self.assertEqual(new, "X" + old[1:])
            else:
                self.assertEqual(new, old)
        self.assertTrue(all(c["form"] == "subckt" for c in ef.mos_cards("\n".join(v))))

    def test_mismatch_model_without_switch_is_refused(self):
        lib = PDK_OK.replace("sw_stat_mismatch", "0*1")
        with self.assertRaises(ef.Refusal) as cm:
            ef.check_device_mismatch_support(ef.mismatch_capable(NET), SCH, lib)
        self.assertEqual(cm.exception.code, "PDK_MISMATCH_MODEL_MISSING")

    def test_duplicate_pdk_model_is_ambiguous(self):
        with self.assertRaises(ef.Refusal) as cm:
            ef.check_device_mismatch_support(ef.mismatch_capable(NET), SCH, PDK_OK + PDK_OK)
        self.assertEqual(cm.exception.code, "PDK_MISMATCH_MODEL_AMBIGUOUS")

    def test_geometry_change_is_refused(self):
        with self.assertRaises(ef.Refusal) as cm:
            ef.check_device_mismatch_support(ef.mismatch_capable(NET.replace("L=2U W=30U", "L=2U W=20U", 1)), SCH, PDK_OK)
        self.assertEqual(cm.exception.code, "DEVICE_GEOMETRY_MISMATCH")

    def test_committed_schematic_geometry_parses(self):
        ms = ef.device_multiset((REPO / "design/comparator.spice").read_text())
        self.assertEqual(sum(ms.values()), 29)  # 27 MOS + 2 load resistors, as extracted

    def test_body_bias(self):
        r = ef.check_body_bias(NET, REPORT)
        ef.check_body_bias(ef.mismatch_capable(NET), REPORT)   # both card forms
        self.assertEqual((r["nmos_bulk_hub"], r["pmos_bulk_hub"]), ("vss", "vdd"))
        bad = BASE.format(pins=PINS, legs=LEGS, b4="vdd__t7")   # NMOS body on vdd
        with self.assertRaises(ef.Refusal) as cm:
            ef.check_body_bias(bad, REPORT)
        self.assertEqual(cm.exception.code, "BODY_NOT_BIASED")
        with self.assertRaises(ef.Refusal) as cm:
            ef.check_body_bias(NET, dict(REPORT, unbiased_pmos_body_nets=["n5"]))
        self.assertEqual(cm.exception.code, "EXTRACTION_BODY_WARNINGS")

    def test_observation_nodes_structural(self):
        with mock.patch.object(ef.pn, "crosscheck_labels"), \
                mock.patch.object(ef.pn, "crosscheck_report"):
            o = ef.observation_nodes(NET, REPORT)
        # hubs are n7/n9 here: derived structurally, never aop/aon by name
        self.assertEqual({o["aop"], o["aon"]}, {"xa.xlayout_dut.n7", "xa.xlayout_dut.n9"})

    def test_observation_nodes_missing_or_ambiguous(self):
        def refused(net, patch=True):
            ctx = (mock.patch.object(ef.pn, "crosscheck_labels"),
                   mock.patch.object(ef.pn, "crosscheck_report")) if patch else ()
            with self.assertRaises(ef.Refusal) as cm:
                for c in ctx:
                    c.start()
                try:
                    ef.observation_nodes(net, REPORT)
                finally:
                    mock.patch.stopall()
            self.assertEqual(cm.exception.code, "OBSERVATION_NODES")
            return cm.exception.msg
        refused(NET.replace("X$7 vdd__t1 n7__t0", "X$7 vdd__t1 q__t0"))        # shared output hub
        refused("\n".join(l for l in NET.splitlines() if not l.startswith("X$7")))  # missing load
        refused(NET.replace("R", "*R"))                                          # no legs: not parasitic
        # labels disagree with the structural answer (hubs are n7/n9, not aop/aon)
        refused(NET, patch=False)

    def test_identity(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.spice"
            raw.write_text("x")
            sha = ef.sha256_file(raw)
            self.assertTrue(ef.check_report_identity({"netlist_sha256": sha}, raw, "0.6.0")["match"])
            with self.assertRaises(ef.Refusal) as cm:
                ef.check_report_identity({"netlist_sha256": "0" * 64}, raw, "0.7.0")
            self.assertEqual(cm.exception.code, "EXTRACTION_IDENTITY")


class Scope(unittest.TestCase):
    def test_points_and_campaign_size_are_bounded(self):
        with self.assertRaises(ef.Refusal) as cm:
            ef.prepare(Path("/nonexistent-feas"), "ss_-40c_2.97v", "probe")
        self.assertEqual(cm.exception.code, "POINT_NOT_ALLOWED")
        self.assertEqual(set(ef.POINTS), {"tt_27c_3.30v", "ff_125c_3.63v"})
        self.assertLessEqual(ef.MAX_MC_N, 50)

    def test_production_refusal_is_untouched(self):
        src = (SIM / "tools/mk_klt_request.py").read_text()
        self.assertIn('if dut.provenance != "schematic":', src)
        self.assertIn("supports the schematic binding only", src)

    def test_feasibility_never_mints_records(self):
        src = (SIM / "tools/extracted_tran_feasibility.py").read_text()
        self.assertNotIn('"records"', src)
        self.assertIn("feasibility_only", src)


if __name__ == "__main__":
    unittest.main()
