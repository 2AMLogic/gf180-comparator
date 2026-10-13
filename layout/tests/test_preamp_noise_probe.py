#!/usr/bin/env python3
"""PDK-free, ngspice-free regressions for layout/pex/preamp_noise_probe.py (#208).

Covers the fail-closed helpers and the deck builder that generates the
sha256-pinned preamp-noise decks.

    python3 layout/tests/test_preamp_noise_probe.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pex"))

import preamp_noise_probe as pnp  # noqa: E402

KEYS = ("av_dc", "onoise_uv", "onoise_hf_uv", "vn_in_uv", "vn_in_hf_uv")
NODES = {"aop": {"hub": "xdut.p_hub", "drain_leg": "xdut.p_leg"},
         "aon": {"hub": "xdut.n_hub", "drain_leg": "xdut.n_leg"}}
PDK = SimpleNamespace(design_include="/pdk/design.ngspice", model_lib="/pdk/sm141064.ngspice")
PARAMS = {"dut_ib": 1e-05, "dut_vcm": 1.65}


def good(names=("hub",)):
    return {f"m_{n}_{k}": 1.0 for n in names for k in KEYS}


class CheckFinitePositive(unittest.TestCase):
    def test_all_good(self):
        self.assertEqual(pnp.check_finite_positive(good(), ["hub"]), [])

    def test_bad_values_reported_by_name(self):
        cases = {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf"),
                 "zero": 0.0, "negative": -1.0}
        for label, v in cases.items():
            for k in KEYS:
                vals = good()
                vals[f"m_hub_{k}"] = v
                bad = pnp.check_finite_positive(vals, ["hub"])
                self.assertEqual(len(bad), 1, (label, k, bad))
                self.assertTrue(bad[0].startswith(f"hub.{k}="), bad)

    def test_missing_key(self):
        for k in KEYS:
            vals = good()
            del vals[f"m_hub_{k}"]
            self.assertEqual(pnp.check_finite_positive(vals, ["hub"]), [f"hub.{k}=None"])

    def test_empty_vals_all_missing(self):
        self.assertEqual(len(pnp.check_finite_positive({}, ["hub"])), len(KEYS))

    def test_each_observation_checked(self):
        vals = good(("hub", "drain_leg"))
        vals["m_drain_leg_av_dc"] = 0.0
        bad = pnp.check_finite_positive(vals, ["hub", "drain_leg"])
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith("drain_leg.av_dc="))

    def test_unlisted_observation_not_checked(self):
        self.assertEqual(pnp.check_finite_positive({}, []), [])


class ParseMeasures(unittest.TestCase):
    LOG = "\n".join([
        "Circuit: * foo",
        "i_vsup_ua = 1.234500e+02",
        "M_HUB_AV_DC = 5.0E+00",
        "  m_hub_onoise_uv   =   -3.5e-01  ",
        "m_hub_bad = nan",
        "m_hub_inf = inf",
        "no equals here 12",
        "x = 1 2",
        "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000",
        "",
    ])

    def test_parse(self):
        v = pnp.parse_measures(self.LOG)
        self.assertEqual(v["i_vsup_ua"], 123.45)
        self.assertEqual(v["m_hub_av_dc"], 5.0)  # key case-folded
        self.assertEqual(v["m_hub_onoise_uv"], -0.35)
        self.assertNotIn("M_HUB_AV_DC", v)

    def test_non_matching_lines_ignored(self):
        v = pnp.parse_measures(self.LOG)
        self.assertNotIn("m_hub_bad", v)   # 'nan' is not in the numeric class
        self.assertNotIn("m_hub_inf", v)
        self.assertNotIn("x", v)
        self.assertNotIn("TEMP", v)

    def test_nan_in_log_fails_closed_via_missing(self):
        vals = pnp.parse_measures("m_hub_av_dc = nan\n")
        self.assertEqual(vals, {})
        self.assertEqual(len(pnp.check_finite_positive(vals, ["hub"])), len(KEYS))

    def test_empty(self):
        self.assertEqual(pnp.parse_measures(""), {})


class ObservationPoints(unittest.TestCase):
    def test_without_leg(self):
        self.assertEqual(pnp.observation_points("x", NODES, False),
                         [("hub", "xdut.p_hub", "xdut.n_hub")])

    def test_with_leg(self):
        self.assertEqual(pnp.observation_points("x", NODES, True),
                         [("hub", "xdut.p_hub", "xdut.n_hub"),
                          ("drain_leg", "xdut.p_leg", "xdut.n_leg")])

    def test_label_unused(self):
        self.assertEqual(pnp.observation_points("a", NODES, True),
                         pnp.observation_points("b", NODES, True))


class BuildDeck(unittest.TestCase):
    def deck(self, label, dut="/d/dut.cir", leg=False, c_route="0", c_nodes=None, tie=False):
        obs = pnp.observation_points(label, NODES, leg)
        return pnp.build_deck(label, dut, PDK, obs, c_route, c_nodes, PARAMS, tie)

    def cases(self):
        cn = ("xdut.p_hub", "xdut.n_hub")
        return {
            "schematic_bench_croute": self.deck("schematic_bench_croute", c_route="10f", c_nodes=cn),
            "schematic_croute0": self.deck("schematic_croute0"),
            "extracted": self.deck("extracted", leg=True),
            "extracted_vsubs_tied": self.deck("extracted_vsubs_tied", leg=True, tie=True),
        }

    def test_deterministic(self):
        self.assertEqual(self.cases(), self.cases())

    def test_header_and_includes(self):
        d = self.deck("t")
        self.assertTrue(d.startswith("* t -- GENERATED by layout/pex/preamp_noise_probe.py"))
        self.assertIn('.include "/pdk/design.ngspice"', d)
        self.assertIn('.include "/d/dut.cir"', d)
        for s in pnp.TT_SECTIONS:
            self.assertIn(f'.lib "/pdk/sm141064.ngspice" {s}', d)
        self.assertIn(".param dut_ib=1e-05", d)
        self.assertIn(".param dut_vcm=1.65", d)
        self.assertTrue(d.endswith(".end\n"))

    def test_c_nodes_only_for_bench_croute(self):
        for name, d in self.cases().items():
            has = "Cwp " in d and "Cwn " in d
            self.assertEqual(has, name == "schematic_bench_croute", name)
        d = self.cases()["schematic_bench_croute"]
        self.assertIn("Cwp xdut.p_hub 0 10f", d)
        self.assertIn("Cwn xdut.n_hub 0 10f", d)

    def test_c_route_zero_or_no_nodes_omits_caps(self):
        cn = ("a", "b")
        self.assertNotIn("Cwp", self.deck("t", c_route="0", c_nodes=cn))
        self.assertNotIn("Cwp", self.deck("t", c_route="10f", c_nodes=None))

    def test_vsubs_tie_only_when_tied(self):
        for name, d in self.cases().items():
            self.assertEqual("Vsubs_sens vsubs 0 dc 0" in d, name.endswith("vsubs_tied"), name)

    def test_leg_observation_only_with_leg(self):
        for name, d in self.cases().items():
            self.assertEqual("m_drain_leg_av_dc" in d, name.startswith("extracted"), name)
            self.assertIn("m_hub_av_dc", d)

    def test_measure_names_cover_checked_keys(self):
        d = self.deck("t", leg=True)
        for n in ("hub", "drain_leg"):
            for k in KEYS:
                self.assertIn(f"print m_{n}_{k}", d)

    def test_noise_plot_indices(self):
        d = self.deck("t", leg=True)
        self.assertIn("noise2.onoise_total", d)    # hub: plots 1/3 -> totals 2/4
        self.assertIn("noise4.onoise_total", d)
        self.assertIn("noise6.onoise_total", d)    # leg: plots 5/7 -> totals 6/8
        self.assertIn("noise8.onoise_total", d)

    def test_cases_differ_pairwise(self):
        decks = list(self.cases().values())
        self.assertEqual(len(set(decks)), len(decks))


if __name__ == "__main__":
    unittest.main()
