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


if __name__ == "__main__":
    unittest.main()
