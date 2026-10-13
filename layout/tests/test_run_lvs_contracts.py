#!/usr/bin/env python3
"""Contract checks in layout/run_lvs.py (#177): interface pins and drawn
device geometry, exercised against temporary reference netlists and synthetic
extract reports. PDK-free and klayout-free; committed files are untouched.

    python3 layout/tests/test_run_lvs_contracts.py
"""

from __future__ import annotations

import collections
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "layout"))
import run_lvs  # noqa: E402

PINS = list(run_lvs.INTERFACE_PINS)


class _TempReference(unittest.TestCase):
    """Base: lets a test point run_lvs.REFERENCE at a temp netlist."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        orig = run_lvs.REFERENCE
        self.addCleanup(setattr, run_lvs, "REFERENCE", orig)

    def use_reference(self, text: str) -> None:
        path = os.path.join(self._tmp.name, "ref.spice")
        with open(path, "w") as f:
            f.write(text)
        run_lvs.REFERENCE = path


def _report_pins(names) -> dict:
    return {"nets": [{"name": n, "pin": True} for n in names]
            + [{"name": "internal", "pin": False}, {"name": "nopinkey"}]}


class ParseUmTests(unittest.TestCase):
    def parse(self, v):
        return run_lvs._parse_um(v, where="t", param="L")

    def test_values(self):
        for text, want in [("4u", 4.0), ("120u", 120.0), ("1e-6", 1.0),
                           ("1.6um", 1.6), ("0.18", 180000.0), ("1m", 1e3),
                           ("'4u'", 4.0), ("500n", 0.5)]:
            with self.subTest(text=text):
                self.assertAlmostEqual(self.parse(text), want)

    def test_rejected(self):
        for text in ["0.18meter", "1meg", "5x", "W/nf*0.18u", "abc", ""]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.parse(text)


class InterfaceContractTests(_TempReference):
    def ref(self, pins):
        self.use_reference(
            f"* hdr\n.subckt {run_lvs.REFERENCE_TOP} {' '.join(pins)}\n.ends\n")

    def test_match(self):
        self.ref(PINS)
        self.assertEqual(run_lvs.check_interface_contract(_report_pins(PINS)), [])

    def test_extracted_order_ignored(self):
        self.ref(PINS)
        self.assertEqual(
            run_lvs.check_interface_contract(_report_pins(reversed(PINS))), [])

    def test_reference_order_drift(self):
        self.ref(PINS[1:] + PINS[:1])
        problems = run_lvs.check_interface_contract(_report_pins(PINS))
        self.assertEqual(len(problems), 1)
        self.assertIn("drifted", problems[0])
        self.assertIn(" ".join(PINS[1:] + PINS[:1]), problems[0])
        self.assertIn(" ".join(PINS), problems[0])

    def test_missing_pin(self):
        self.ref(PINS)
        problems = run_lvs.check_interface_contract(_report_pins(PINS[:-1]))
        self.assertEqual(
            problems, [f"layout exposes no top-level pin for: {PINS[-1]}"])

    def test_extra_pin(self):
        self.ref(PINS)
        problems = run_lvs.check_interface_contract(_report_pins(PINS + ["zzz"]))
        self.assertEqual(len(problems), 1)
        self.assertIn("zzz", problems[0])
        self.assertIn("does not name", problems[0])

    def test_missing_and_extra(self):
        self.ref(PINS)
        problems = run_lvs.check_interface_contract(
            _report_pins(PINS[1:] + ["zzz"]))
        self.assertEqual(len(problems), 2)

    def test_no_subckt_line_exits(self):
        self.use_reference("* nothing here\n")
        with self.assertRaises(SystemExit):
            run_lvs.reference_pin_order()


def _dev(cls, l, w) -> dict:
    return {"class": cls, "params": {"l_um": l, "w_um": w}}


BASE = """\
.subckt leaf a b vdd vss
XM1 a b vss vss nfet_03v3 L=2u W=30u nf=1 ad='W/nf * 0.18u'
XM2 a b vdd vdd pfet_03v3 L=1u W=10u
+ nf=1 m=1
XR1 a b vss ppolyf_u_1k r_length=120u r_width=2u
.ends
.subckt top a b vdd vss
XA a b vdd vss leaf
.ends
"""
BASE_DEVS = [_dev("nfet", 2.0, 30.0), _dev("PFET", 1.0, 10.0),
             _dev("ppolyf_u_1k", 120.0, 2.0)]


class GeometryContractTests(_TempReference):
    def test_census_skips_hierarchy_and_joins_continuations(self):
        self.use_reference(BASE)
        self.assertEqual(run_lvs.reference_device_geometry(),
                         collections.Counter({("nfet", 2.0, 30.0): 1,
                                              ("pfet", 1.0, 10.0): 1,
                                              ("ppolyf_u_1k", 120.0, 2.0): 1}))

    def test_identical(self):
        self.use_reference(BASE)
        self.assertEqual(
            run_lvs.check_device_geometry_contract({"devices": BASE_DEVS}), [])

    def test_resistor_length_mismatch(self):
        self.use_reference(BASE)
        devs = BASE_DEVS[:2] + [_dev("ppolyf_u_1k", 100.0, 2.0)]
        problems = run_lvs.check_device_geometry_contract({"devices": devs})
        self.assertEqual(len(problems), 2)
        joined = "\n".join(problems)
        self.assertIn("ppolyf_u_1k L=100um W=2um: layout draws 1, "
                      "design/comparator.spice declares 0", joined)
        self.assertIn("ppolyf_u_1k L=120um W=2um: layout draws 0, "
                      "design/comparator.spice declares 1", joined)

    def test_count_mismatch(self):
        self.use_reference(BASE)
        devs = BASE_DEVS + [_dev("nfet", 2.0, 30.0)]
        problems = run_lvs.check_device_geometry_contract({"devices": devs})
        self.assertEqual(problems, ["nfet L=2um W=30um: layout draws 2, "
                                    "design/comparator.spice declares 1"])

    def test_unmapped_subckt(self):
        self.use_reference(BASE + "XQ a b vss mystery_dev L=1u W=1u\n")
        with self.assertRaises(ValueError) as cm:
            run_lvs.reference_device_geometry()
        self.assertIn("mystery_dev", str(cm.exception))

    def test_nf_and_m_not_one(self):
        for extra in ("nf=2", "m=3"):
            with self.subTest(extra=extra):
                self.use_reference(
                    f"XM1 a b vss vss nfet_03v3 L=2u W=30u {extra}\n")
                with self.assertRaises(ValueError):
                    run_lvs.reference_device_geometry()

    def test_missing_r_length(self):
        self.use_reference("XR1 a b vss ppolyf_u_1k r_width=2u\n")
        with self.assertRaises(ValueError) as cm:
            run_lvs.reference_device_geometry()
        self.assertIn("r_length", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
