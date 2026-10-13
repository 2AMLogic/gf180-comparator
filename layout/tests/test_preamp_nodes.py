#!/usr/bin/env python3
"""PDK-free regressions for layout/pex/preamp_nodes.py (#202).

The mapping must be derived from connectivity and must FAIL CLOSED when the
connectivity changes or a node is ambiguous.

    python3 layout/tests/test_preamp_nodes.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pex"))

import preamp_nodes as pn  # noqa: E402

PINS = "CLK DOUT DOUTB IBIAS VDD VINN VINP VSS"

# Hub names are deliberately NOT aop/aon (n7/n9): the mapping is structural.
BASE = """\
.SUBCKT COMPARATOR {pins}
M$1 n9__t1 vinp__t0 tl__t1 vss__t1 nfet_03v3 L=2U W=30U
M$2 n7__t1 vinn__t0 tl__t2 vss__t2 nfet_03v3 L=2U W=30U
M$3 tl__t0 ibias__t0 vss__t0 vss__t3 nfet_03v3 L=4U W=10U
M$4 q__t0 n7__t2 vss__t4 vss__t5 nfet_03v3 L=0.5U W=8U
M$5 r__t0 n9__t2 vss__t6 vss__t7 nfet_03v3 L=0.5U W=8U
X$6 n9__t0 vdd__t0 vss__t8 ppolyf_u_1k r_length=120U r_width=1U m=1
X$7 vdd__t1 n7__t0 vss__t9 ppolyf_u_1k r_length=120U r_width=1U m=1
{legs}
.ENDS COMPARATOR
"""
LEGS = "\n".join(
    f"R{n} {n} {n.rsplit('__t', 1)[0]} 10.0"
    for n in ("n9__t0 n9__t1 n9__t2 n7__t0 n7__t1 n7__t2 tl__t0 tl__t1 tl__t2 "
              "vinp__t0 vinn__t0 ibias__t0 vdd__t0 vdd__t1 q__t0 r__t0 "
              "vss__t0 vss__t1 vss__t2 vss__t3 vss__t4 vss__t5 vss__t6 vss__t7 "
              "vss__t8 vss__t9").split()
)


def net(body=None, legs=LEGS, pins=PINS):
    text = BASE.format(pins=pins, legs=legs)
    return text if body is None else body(text)


class Derive(unittest.TestCase):
    def test_structural_mapping(self):
        m = pn.derive(net())
        # vinn-gated device drives the aop-sense output (n7); vinp -> n9.
        self.assertEqual(m["aop"]["hub"], "n7")
        self.assertEqual(m["aon"]["hub"], "n9")
        self.assertEqual(m["aop"]["drain_leg"], "n7__t1")
        self.assertEqual(m["aop"]["load_resistor"], "X$7")
        self.assertEqual(m["tail_hub"], "tl")
        self.assertEqual(pn.observation_nodes(m, "xd.xl")["aon"]["hub"], "xd.xl.n9")

    def test_label_crosscheck_detects_renamed_or_swapped(self):
        with self.assertRaises(pn.MappingError):
            pn.crosscheck_labels(pn.derive(net()))  # hubs are n7/n9, not aop/aon

    def test_report_crosscheck(self):
        m = pn.derive(net())
        good = {"parasitics": {"nets": [
            {"net": "n7", "terminals": [{"device": "$2"}, {"device": "$4"}, {"device": "$7"}]},
            {"net": "n9", "terminals": [{"device": "$1"}, {"device": "$5"}, {"device": "$6"}]}]}}
        pn.crosscheck_report(m, good)
        bad = {"parasitics": {"nets": [
            {"net": "n7", "terminals": [{"device": "$2"}, {"device": "$7"}]},
            {"net": "n9", "terminals": [{"device": "$1"}, {"device": "$5"}, {"device": "$6"}]}]}}
        with self.assertRaises(pn.MappingError):
            pn.crosscheck_report(m, bad)
        with self.assertRaises(pn.MappingError):
            pn.crosscheck_report(m, {"parasitics": {"nets": []}})

    def test_no_parasitic_legs_fails(self):
        with self.assertRaisesRegex(pn.MappingError, "parasitics"):
            pn.derive(net(legs=""))

    def test_wrong_pin_set_fails(self):
        with self.assertRaises(pn.MappingError):
            pn.derive(net(pins="A B C"))

    def test_extra_terminal_on_output_is_ambiguous(self):
        extra = lambda t: t.replace(".ENDS", "M$9 z__t0 n7__t2 vss__t4 vss__t5 nfet_03v3 L=1U W=1U\n.ENDS")
        with self.assertRaisesRegex(pn.MappingError, "extra terminals"):
            pn.derive(net(extra))

    def test_missing_latch_gate_fails(self):
        drop = lambda t: t.replace("M$5 r__t0 n9__t2 vss__t6 vss__t7 nfet_03v3 L=0.5U W=8U\n", "")
        with self.assertRaisesRegex(pn.MappingError, "extra terminals"):
            pn.derive(net(drop))

    def test_both_inputs_same_gate_fails(self):
        same = lambda t: t.replace("M$2 n7__t1 vinn__t0", "M$2 n7__t1 vinp__t0")
        with self.assertRaisesRegex(pn.MappingError, "gated by"):
            pn.derive(net(same))

    def test_resistor_not_on_vdd_fails(self):
        bad = lambda t: t.replace("X$6 n9__t0 vdd__t0", "X$6 n9__t0 q__t0")
        with self.assertRaisesRegex(pn.MappingError, "exactly one terminal on vdd"):
            pn.derive(net(bad))

    def test_resistor_substrate_off_vss_fails(self):
        bad = lambda t: t.replace("X$6 n9__t0 vdd__t0 vss__t8", "X$6 n9__t0 vdd__t0 tl__t1")
        with self.assertRaisesRegex(pn.MappingError, "substrate"):
            pn.derive(net(bad))

    def test_input_bulk_off_vss_fails(self):
        bad = lambda t: t.replace("tl__t1 vss__t1 nfet", "tl__t1 vdd__t1 nfet")
        with self.assertRaisesRegex(pn.MappingError, "bulk"):
            pn.derive(net(bad))

    def test_split_tail_fails(self):
        bad = lambda t: t.replace("M$2 n7__t1 vinn__t0 tl__t2", "M$2 n7__t1 vinn__t0 q__t0")
        with self.assertRaisesRegex(pn.MappingError, "tail"):
            pn.derive(net(bad))

    def test_missing_tail_device_fails(self):
        bad = lambda t: t.replace("M$3 tl__t0 ibias__t0", "M$3 tl__t0 q__t0")
        with self.assertRaisesRegex(pn.MappingError, "tail NMOS"):
            pn.derive(net(bad))

    def test_third_resistor_fails(self):
        bad = lambda t: t.replace(".ENDS", "X$8 q__t0 vdd__t0 vss__t8 ppolyf_u_1k r_length=1U r_width=1U m=1\n.ENDS")
        with self.assertRaisesRegex(pn.MappingError, "exactly 2"):
            pn.derive(net(bad))

    def test_real_netlist_if_present(self):
        p = Path(__file__).resolve().parents[1] / "lvs" / "comparator.dut-layout.spice"
        if not p.exists():
            self.skipTest("scratch DUT netlist not generated")
        m = pn.derive(p.read_text())
        pn.crosscheck_labels(m)


if __name__ == "__main__":
    unittest.main()
