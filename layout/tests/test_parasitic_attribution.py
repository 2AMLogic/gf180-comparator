#!/usr/bin/env python3
"""PDK-free regressions for layout/pex/parasitic_attribution.py (#229).

No ngspice, no klt, no fleet. Covers: the netlist edits on a synthetic
star-model extraction; the variant plan derived from the committed extracted
DUT; byte-identity of the control's decks with the cited `klt pex` decks; and
`verify` over the committed attribution evidence.

    python3 layout/tests/test_parasitic_attribution.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pex"))

import parasitic_attribution as pa  # noqa: E402

SYN = """\
.GLOBAL vsubs
.SUBCKT COMPARATOR a b vdd vss
M$1 x__t0 a__t0 vss__t0 vss__t1 nfet_03v3 L=0.5U W=2U AS=1P AD=1P PS=5U PD=5U
M$2 y__t0 b__t0 vss__t2 vss__t3 nfet_03v3 L=0.5U W=8U AS=4P AD=4P PS=17U
+ PD=17U
X$3 x__t1 vdd__t0 vss__t4 ppolyf_u_1k r_length=120U r_width=1U m=1
Rx_t0 x__t0 x 10.0
Rx_t1 x__t1 x 20.0
Cx x vsubs 1e-14
Ry_t0 y__t0 y 5.0
Cy y vsubs 2e-15
Ra_t0 a__t0 a 1.0
Ca a vsubs 1e-16
Rb_t0 b__t0 b 1.0
Cb b vsubs 1e-16
Rvdd_t0 vdd__t0 vdd 1.0
Cvdd vdd vsubs 1e-15
Rvss_t0 vss__t0 vss 1.0
Rvss_t1 vss__t1 vss 1.0
Rvss_t2 vss__t2 vss 1.0
Rvss_t3 vss__t3 vss 1.0
Rvss_t4 vss__t4 vss 1.0
Cvss vss vsubs 1e-15
Ccc_x_y x y 3e-17
Ccc_vdd_vss vdd vss 1e-17
Rvsubs_dctie vsubs 0 1e+12
.ENDS COMPARATOR
"""


class Parse(unittest.TestCase):
    def test_cards_by_shape(self):
        p = pa.parse(SYN)
        self.assertEqual(p["nets"], ["a", "b", "vdd", "vss", "x", "y"])
        self.assertEqual(p["legs"]["x"], [(0, 10.0), (1, 20.0)])
        self.assertEqual(p["cg"]["x"], 1e-14)
        self.assertEqual(sorted((a, b) for a, b, _ in p["cc"]), [("vdd", "vss"), ("x", "y")])
        self.assertEqual(p["vsubs_tie_ohm"], 1e12)

    def test_coupling_card_is_not_a_ground_cap(self):
        self.assertNotIn("cc_x_y", pa.parse(SYN)["cg"])

    def test_no_parasitics_refused(self):
        with self.assertRaises(ValueError):
            pa.parse(".SUBCKT T a\nM1 a a a a nfet_03v3 L=1U W=1U\n.ENDS\n")

    def test_si(self):
        self.assertAlmostEqual(pa.si("0.5U"), 0.5e-6)
        self.assertAlmostEqual(pa.si("2.5P"), 2.5e-12)
        self.assertAlmostEqual(pa.si("1e+12"), 1e12)


class Edits(unittest.TestCase):
    def test_drop_r_merges_terminals_and_drops_legs(self):
        out = pa.drop_r(SYN, {"x"})
        self.assertNotIn("Rx_t", out)
        self.assertIn("M$1 x a__t0 vss__t0", out)
        self.assertIn("X$3 x vdd__t0", out)
        self.assertNotIn("x__t", out)
        # other nets untouched
        self.assertIn("Ry_t0 y__t0 y 5.0", out)
        self.assertIn("Cx x vsubs 1e-14", out)

    def test_drop_r_does_not_touch_prefix_nets(self):
        text = "M$1 xx__t0 x__t0 0 0 nfet_03v3 L=1U W=1U\nRx_t0 x__t0 x 1\nRxx_t0 xx__t0 xx 1\nCx x vsubs 1e-15\n"
        out = pa.drop_r(text, {"x"})
        self.assertIn("M$1 xx__t0 x 0 0", out)
        self.assertIn("Rxx_t0 xx__t0 xx 1", out)

    def test_drop_cg_only_named_net(self):
        out = pa.drop_cg(SYN, {"x"})
        self.assertNotIn("Cx x vsubs", out)
        self.assertIn("Cy y vsubs", out)
        self.assertIn("Ccc_x_y x y", out)

    def test_drop_cc(self):
        out = pa.drop_cc(SYN)
        self.assertNotIn("Ccc_", out)
        self.assertIn("Cx x vsubs", out)

    def test_tie_vsubs(self):
        out = pa.tie_vsubs(SYN)
        self.assertIn(f"Rvsubs_dctie vsubs 0 {pa.VSUBS_TIE_OHM}", out)
        with self.assertRaises(ValueError):
            pa.tie_vsubs(out.replace("Rvsubs_dctie", "Rother"))

    def test_device_geometry_schematic_convention(self):
        out = pa.schematic_device_geometry(SYN)
        m2 = [l for l in out.splitlines() if l.startswith("M$2")][0]
        # continuation joined, old geometry gone, schematic geometry in
        self.assertNotIn("AS=4P", m2)
        self.assertNotIn("PD=17U", m2)
        self.assertIn("AS=1.44P AD=1.44P PS=16.36U PD=16.36U", m2)
        self.assertIn("NRS=0.0225 NRD=0.0225 SA=0 SB=0 SD=0", m2)
        self.assertFalse(any(l.startswith("+") for l in out.splitlines()))
        # parasitic cards untouched
        self.assertIn("Rx_t0 x__t0 x 10.0", out)


class CommittedNetlist(unittest.TestCase):
    """The committed extracted DUT (no PDK needed to read it)."""

    @classmethod
    def setUpClass(cls):
        cls.text = pa.load_extracted()
        cls.plan = pa.variants(cls.text)

    def test_every_net_gets_r_and_cg_variants(self):
        ids = {v["id"] for v in self.plan}
        for n in pa.parse(self.text)["nets"]:
            self.assertIn(f"r0-{n}", ids)
            self.assertIn(f"cg0-{n}", ids)
        for vid in ("ctrl", "ctrl-ctr0", "r0-all", "cg0-all", "cc0-all", "c0-all", "rc0-all",
                    "vsubs-tied", "devgeom", "devgeom-rc0-all", "sch", "sch-probed"):
            self.assertIn(vid, ids)

    def test_rc0_all_has_no_parasitic_cards(self):
        (v,) = [v for v in self.plan if v["id"] == "rc0-all"]
        cards = [l for l in v["dut"].splitlines() if not l.startswith("*")]
        self.assertFalse([l for l in cards if "__t" in l])
        self.assertFalse([l for l in cards if l.startswith("C")])
        # the substrate tie is the extraction's DC path, not a parasitic
        self.assertEqual([l for l in cards if " vsubs " in l], ["Rvsubs_dctie vsubs 0 1e+12"])

    def test_control_decks_are_the_cited_decks(self):
        (ctrl,) = [v for v in self.plan if v["id"] == "ctrl"]
        vos = pa.cited_vos("extracted")
        for p in pa.PROCESSES:
            cited = json.loads((pa.CITED_MEASURE / "extracted" / f"ladder-{p}.report.json")
                               .read_text())["environment"]["netlist_sha256"]
            deck = pa.ladder_deck(ctrl["dut"], "extracted", p, "probed",
                                  vos[(p, pa.TEMP_C, pa.VDD_V)])
            self.assertEqual(pa.sha(deck), cited, p)
        cited_probe = json.loads((pa.CITED_MEASURE / "extracted" / "probe.report.json")
                                 .read_text())["environment"]["netlist_sha256"]
        self.assertEqual(pa.sha(pa.probe_deck(ctrl["dut"])), cited_probe)

    def test_schematic_control_decks_are_the_cited_decks(self):
        (sch,) = [v for v in self.plan if v["id"] == "sch"]
        for p in pa.PROCESSES:
            cited = json.loads((pa.CITED_MEASURE / "schematic" / f"ladder-{p}.report.json")
                               .read_text())["environment"]["netlist_sha256"]
            self.assertEqual(pa.sha(pa.ladder_deck(sch["dut"], "schematic", p, "zero", None)),
                             cited, p)

    def test_bench_consumed_fields_pinned(self):
        pa.check_bench()


class CommittedEvidence(unittest.TestCase):
    def test_verify_every_committed_run(self):
        runs = sorted(p for p in (pa.HERE / "artifacts" / "parasitic-attribution").glob("*")
                      if (p / "attribution.json").exists())
        self.assertTrue(runs, "no committed attribution run")
        for run in runs:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = pa.main(["verify", str(run)])
            self.assertEqual(rc, 0, f"{run.name}:\n{out.getvalue()}")


class BudgetScaling(unittest.TestCase):
    """Finite ground-C scaling (#243), on the synthetic netlist."""

    def changed(self, a, b):
        return {x for x, y in zip(a.splitlines(), b.splitlines()) if x != y}

    def test_scaling_changes_only_the_intended_c_cards(self):
        out = pa.scale_cg(SYN, {"x", "y"}, 0.5)
        self.assertEqual(len(out.splitlines()), len(SYN.splitlines()))
        self.assertEqual(self.changed(SYN, out), {"Cx x vsubs 1e-14", "Cy y vsubs 2e-15"})
        p = pa.parse(out)
        self.assertAlmostEqual(p["cg"]["x"], 5e-15)
        self.assertAlmostEqual(p["cg"]["y"], 1e-15)
        # every other card, R legs, coupling C, tie and devices untouched
        q = pa.parse(SYN)
        self.assertEqual(p["legs"], q["legs"])
        self.assertEqual(p["cc"], q["cc"])
        self.assertEqual(p["vsubs_tie_ohm"], q["vsubs_tie_ohm"])
        for n in ("a", "b", "vdd", "vss"):
            self.assertEqual(p["cg"].get(n), q["cg"].get(n))

    def test_unit_factor_reproduces_exactly(self):
        self.assertIs(pa.scale_cg(SYN, {"x", "y"}, 1.0), SYN)
        self.assertEqual(pa.scale_cg(SYN, {"x"}, 1), SYN)

    def test_zero_factor_is_the_229_endpoint(self):
        self.assertEqual(pa.scale_cg(SYN, {"x", "y"}, 0.0), pa.drop_cg(SYN, {"x", "y"}))

    def test_invalid_factors_rejected(self):
        for bad in (-0.1, 1.0001, 2, float("nan"), float("inf"), float("-inf"), True, "0.5", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                pa.scale_cg(SYN, {"x"}, bad)
            with self.assertRaises(ValueError, msg=repr(bad)):
                pa.validate_fraction(bad)

    def test_invalid_nets_rejected(self):
        with self.assertRaises(ValueError):
            pa.scale_cg(SYN, set(), 0.5)
        with self.assertRaises(ValueError):
            pa.scale_cg(SYN, {"nosuch"}, 0.5)

    def test_variant_plan_refuses_duplicates_and_unit(self):
        with self.assertRaises(ValueError):
            pa.budget_variants(SYN, [0.5, 0.5], ("x",))
        with self.assertRaises(ValueError):
            pa.budget_variants(SYN, [1.0], ("x",))

    def test_retained_ff_reports_actual_card_values(self):
        out = pa.scale_cg(SYN, {"x"}, 0.25)
        self.assertAlmostEqual(pa.retained_ff(out, ["x", "y"])["x"], 2.5)
        self.assertAlmostEqual(pa.retained_ff(out, ["x", "y"])["y"], 2.0)


class BudgetCommitted(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pa.load_extracted()

    def test_starting_nets_match_the_229_attribution(self):
        d = json.loads((pa.HERE / "artifacts" / "parasitic-attribution"
                        / "20261010-120720-230574b" / "attribution.json").read_text())
        top = [r["id"] for r in d["ranking_single_net"] if r["id"].startswith("cg0-")][:4]
        self.assertEqual(set(top), {f"cg0-{n}" for n in pa.BUDGET_NETS})
        share = sum(r["mean_share"] for r in d["ranking_single_net"]
                    if r["id"] in {f"cg0-{n}" for n in pa.BUDGET_NETS})
        self.assertAlmostEqual(share, 0.71, delta=0.01)

    def test_unit_scaling_of_committed_dut_is_the_control(self):
        self.assertEqual(pa.scale_cg(self.text, pa.BUDGET_NETS, 1.0), self.text)
        plan = pa.budget_variants(self.text, pa.BUDGET_FRACTIONS)
        self.assertEqual(plan[0]["id"], "ctrl")
        self.assertEqual(plan[0]["dut"], self.text)

    def test_committed_dut_scaling_touches_four_cards_only(self):
        out = pa.scale_cg(self.text, pa.BUDGET_NETS, 0.5)
        a, b = self.text.splitlines(), out.splitlines()
        self.assertEqual(len(a), len(b))
        diff = [x for x, y in zip(a, b) if x != y]
        self.assertEqual(sorted(l.split()[0] for l in diff), sorted(f"C{n}" for n in pa.BUDGET_NETS))

    def test_failing_points_are_the_seven_cited_corners(self):
        pts = pa.budget_points("seven")
        self.assertEqual(len(pts), 7)
        self.assertIn(("ss", 125.0, 2.97), pts)
        self.assertIn(("tt", 125.0, 2.97), pts)

    def test_two_point_control_ladder_deck_is_the_cited_deck(self):
        vos = pa.cited_vos("extracted")
        for p in pa.PROCESSES:
            cited = json.loads((pa.CITED_MEASURE / "extracted" / f"ladder-{p}.report.json")
                               .read_text())["environment"]["netlist_sha256"]
            deck = pa.budget_ladder_deck(self.text, "extracted", p, "probed",
                                         {(pa.TEMP_C, pa.VDD_V): vos[(p, pa.TEMP_C, pa.VDD_V)]})
            self.assertEqual(pa.sha(deck), cited, p)

    def test_requests_match_229_shape_at_the_same_point(self):
        for p in pa.PROCESSES:
            r = pa.budget_ladder_request("ladder-x", (p, pa.TEMP_C, pa.VDD_V))
            old = pa.ladder_request(p)
            r["netlist"] = old["netlist"]
            self.assertEqual(r, old)


class BudgetCommittedEvidence(unittest.TestCase):
    def test_verify_every_committed_budget_stage(self):
        stages = sorted((pa.HERE / "artifacts" / "ground-c-budget").glob("*/stage*/stage.json"))
        for st in stages:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = pa.main(["budget-verify", str(st.parent)])
            self.assertEqual(rc, 0, f"{st.parent}:\n{out.getvalue()}")

    def test_source_edit_alone_cannot_break_committed_verification(self):
        """#249: an edit to pex_measure.py / this script / the tb.json pin
        (simulated by perturbing what `file_sha` and the pin constant return
        for them) must not fail `budget-verify` on committed stages; it is
        reported as provenance drift only."""
        stages = sorted((pa.HERE / "artifacts" / "ground-c-budget").glob("*/stage*/stage.json"))
        self.assertTrue(stages)
        real_file_sha, real_pin, real_check = pa.file_sha, pa.TB_JSON_CONSUMED_SHA256, pa.check_bench
        code = {(pa.HERE / "pex_measure.py").resolve(),
                Path(pa.__file__).resolve()}

        def edited_file_sha(path):
            h = real_file_sha(path)
            return ("0" * 64 if h != "0" * 64 else "1" * 64) if Path(path).resolve() in code else h
        try:
            pa.file_sha = edited_file_sha
            # a re-pin of tb.json's consumed fields moves the constant and
            # tb.json together; the bench gate itself is not under test here
            pa.TB_JSON_CONSUMED_SHA256 = "f" * 64
            pa.check_bench = lambda: None
            for st in stages:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    rc = pa.cmd_budget_verify(type("A", (), {"outdir": str(st.parent)})())
                self.assertEqual(rc, 0, f"{st.parent}:\n{out.getvalue()}")
                self.assertIn("provenance drift", out.getvalue())
                self.assertIn("pex_measure_py", out.getvalue())
        finally:
            pa.file_sha, pa.TB_JSON_CONSUMED_SHA256, pa.check_bench = \
                real_file_sha, real_pin, real_check

    def test_manifest_diff_still_gates_plan_and_data_inputs(self):
        st = sorted((pa.HERE / "artifacts" / "ground-c-budget").glob("*/stage*/stage.json"))[0]
        man = json.loads(st.read_text())
        self.assertEqual(pa.budget_manifest_diff(man, man), ([], []))
        for mutate in (lambda m: m["source_sha256"].__setitem__("extracted_dut", "0" * 64),
                       lambda m: m["source_sha256"].__setitem__("cited_report", "0" * 64),
                       lambda m: m["variants"][0].__setitem__("probe_deck_sha256", "0" * 64),
                       lambda m: m["points"].pop(),
                       lambda m: m["nets"].pop()):
            other = json.loads(json.dumps(man))
            mutate(other)
            errors, _ = pa.budget_manifest_diff(man, other)
            self.assertTrue(errors)
        other = json.loads(json.dumps(man))
        other["source_sha256"]["pex_measure_py"] = "0" * 64
        other["scope"] = "edited"
        errors, drift = pa.budget_manifest_diff(man, other)
        self.assertEqual(errors, [])
        self.assertEqual(len(drift), 2)


if __name__ == "__main__":
    unittest.main()
