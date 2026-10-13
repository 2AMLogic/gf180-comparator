#!/usr/bin/env python3
"""PDK-free regressions for layout/run_extract_sim.py (#188).

Covers the netlist adaptation, positional pin wiring and fail-closed branches
that gate the post-layout evidence. Uses tmp-dir fixture netlists passed
through the module's `raw_netlist`/`dut_netlist` parameters; needs no PDK,
klt or ngspice.

    python3 layout/tests/test_run_extract_sim.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

LAYOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAYOUT))

import run_extract_sim as res  # noqa: E402

# The extractor emits top-cell pins alphabetically, not in interface order.
ALPHA_PINS = sorted(res.INTERFACE_PINS)
MOS = "M1 d g s b nfet L=0.28U W=2U AS=1P AD=1P PS=1U PD=1U"
RES_OLD = "R1 a b sub 1234.5 ppolyf_u_1k L=10U W=1U"
RES_X = "X2 c d sub ppolyf_u_1k r=999 L=5U W=2U"


def raw_text(body=(), pins=None, top=res.TOP):
    pins = ALPHA_PINS if pins is None else pins
    lines = ["* fixture", f".SUBCKT {top} {' '.join(p.upper() for p in pins)}"]
    lines += list(body)
    lines += [".ENDS", ""]
    return "\n".join(lines)


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.dir = Path(t.name)
        self.raw = str(self.dir / "raw.spice")
        self.dut = str(self.dir / "dut.spice")

    def write_raw(self, text):
        Path(self.raw).write_text(text)

    def adapt(self, text):
        self.write_raw(text)
        n = res._adapt_netlist(self.raw, self.dut)
        return n, Path(self.dut).read_text()


class ExtractedTopPins(Base):
    def test_declared_order_not_interface_order(self):
        self.write_raw(raw_text())
        got = res._extracted_top_pins(self.raw)
        self.assertEqual([p.lower() for p in got], ALPHA_PINS)
        self.assertNotEqual([p.lower() for p in got], list(res.INTERFACE_PINS))

    def test_case_insensitive_subckt(self):
        self.write_raw(f".subckt {res.TOP.lower()} a b c\n.ends\n")
        self.assertEqual(res._extracted_top_pins(self.raw), ["a", "b", "c"])

    def test_missing_top_exits(self):
        self.write_raw(raw_text(top="OTHER"))
        with self.assertRaises(SystemExit) as cm:
            res._extracted_top_pins(self.raw)
        self.assertIn("no `.SUBCKT", str(cm.exception))


class AdaptNetlist(Base):
    def test_rewrites_mos_and_both_resistor_spellings(self):
        n, out = self.adapt(raw_text([MOS, RES_OLD, RES_X]))
        self.assertEqual(n, 3)
        self.assertIn("M1 d g s b nfet_03v3 L=0.28U", out)
        self.assertIn("X1 a b sub ppolyf_u_1k r_length=10U r_width=1U m=1", out)
        self.assertIn("X2 c d sub ppolyf_u_1k r_length=5U r_width=2U m=1", out)
        self.assertNotIn("r=999", out)

    def test_pfet_rewritten(self):
        n, out = self.adapt(raw_text(["M2 d g s b pfet L=0.28U W=4U"]))
        self.assertEqual(n, 1)
        self.assertIn("pfet_03v3 L=", out)

    def test_no_devices_counts_zero(self):
        n, _ = self.adapt(raw_text())
        self.assertEqual(n, 0)

    def test_unrecognised_resistor_card_exits(self):
        with self.assertRaises(SystemExit) as cm:
            self.adapt(raw_text(["R9 a b ppolyf_u_1k WEIRD=1"]))
        self.assertIn("unrecognised", str(cm.exception))
        self.assertFalse(Path(self.dut).exists())

    def test_comment_mentioning_resistor_class_is_ignored(self):
        n, out = self.adapt(raw_text(["* note about ppolyf_u_1k cards"]))
        self.assertEqual(n, 0)
        self.assertIn("* note about ppolyf_u_1k cards", out)

    def test_pin_set_mismatch_exits(self):
        with self.assertRaises(SystemExit) as cm:
            self.adapt(raw_text(pins=ALPHA_PINS[:-1]))
        self.assertIn("interface pin set", str(cm.exception))
        self.assertFalse(Path(self.dut).exists())

    def test_wrapper_connects_positionally_in_extracted_order(self):
        _, out = self.adapt(raw_text())
        self.assertIn(f".subckt comparator_dut {' '.join(res.INTERFACE_PINS)}", out)
        inst = [l for l in out.splitlines() if l.startswith("Xlayout_dut ")]
        self.assertEqual(len(inst), 1)
        toks = inst[0].split()
        self.assertEqual(toks[-1], res.TOP)
        self.assertEqual([t.lower() for t in toks[1:-1]], ALPHA_PINS)
        self.assertNotEqual([t.lower() for t in toks[1:-1]],
                            list(res.INTERFACE_PINS))

    def test_extracted_text_preserved_and_wrapper_appended(self):
        _, out = self.adapt(raw_text([MOS]))
        self.assertTrue(out.index(f".SUBCKT {res.TOP}") < out.index(".subckt comparator_dut"))
        self.assertTrue(out.rstrip().endswith(".ends"))


class InterfaceContract(Base):
    def test_generated_wrapper_passes(self):
        self.adapt(raw_text([MOS, RES_OLD]))
        res._check_interface_contract(self.dut)

    def test_reordered_pins_exit(self):
        pins = list(res.INTERFACE_PINS)
        pins[0], pins[1] = pins[1], pins[0]
        Path(self.dut).write_text(f".subckt comparator_dut {' '.join(pins)}\n.ends\n")
        with self.assertRaises(SystemExit) as cm:
            res._check_interface_contract(self.dut)
        self.assertIn("pin order", str(cm.exception))

    def test_missing_comparator_dut_exits(self):
        Path(self.dut).write_text(raw_text())
        with self.assertRaises(SystemExit) as cm:
            res._check_interface_contract(self.dut)
        self.assertIn("<missing>", str(cm.exception))


class CheckReport(unittest.TestCase):
    GOOD = {"parasitics": {"nets": {"n1": {}}},
            "device_counts": {"nfet": 2, "pfet": 2, "ppolyf_u_1k": 1}}

    def test_good_report_passes(self):
        res._check_report(self.GOOD)

    def test_missing_parasitics_exits(self):
        with self.assertRaises(SystemExit) as cm:
            res._check_report({"device_counts": {"nfet": 1}})
        self.assertIn("no parasitics block", str(cm.exception))

    def test_empty_parasitics_exits(self):
        for p in ({}, {"nets": {}}, {"nets": []}, None, []):
            with self.subTest(parasitics=p), self.assertRaises(SystemExit):
                res._check_report({"parasitics": p})

    def test_unmapped_device_class_exits(self):
        rep = {"parasitics": {"nets": {"n": 1}},
               "device_counts": {"nfet": 1, "nfet_hv": 2}}
        with self.assertRaises(SystemExit) as cm:
            res._check_report(rep)
        self.assertIn("nfet_hv", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
