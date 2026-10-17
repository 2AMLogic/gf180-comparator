#!/usr/bin/env python3
"""PDK-free regressions for layout/pex/design_lever_study.py (#323).

No ngspice, no klt, no fleet. Covers the device-W transforms, fail-closed
inputs, the lever plan against the committed extracted DUT, and the declared
request budget.

    python3 layout/tests/test_design_lever_study.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pex"))

import design_lever_study as dl  # noqa: E402
import parasitic_attribution as pa  # noqa: E402

SYN = """\
.SUBCKT COMPARATOR a vss
M$1 x__t0 a__t0 vss__t0 vss__t1 nfet_03v3 L=0.5U W=2U AS=1P AD=1P PS=5U PD=5U
M$2 y__t0 a__t0 vss__t2 vss__t3 nfet_03v3 L=0.5U W=8U AS=4P AD=4P PS=17U
+ PD=17U
Rx_t0 x__t0 x 10.0
Cx x vsubs 1e-14
.ENDS COMPARATOR
"""


class Transform(unittest.TestCase):
    def test_identity_returns_same_object(self):
        self.assertIs(dl.scale_devices(SYN, {"M$1": 1.0}), SYN)

    def test_scales_w_and_junctions_only_on_target(self):
        out = dl.scale_devices(SYN, {"M$2": 1.5})
        self.assertIn("M$1 x__t0 a__t0 vss__t0 vss__t1 nfet_03v3 L=0.5U W=2U AS=1P", out)
        self.assertIn("W=12U AS=6P AD=6P PS=25U PD=25U", out)
        self.assertNotIn("\n+ PD=17U", out)
        self.assertEqual([l for l in SYN.splitlines() if l.startswith(("R", "C"))],
                         [l for l in out.splitlines() if l.startswith(("R", "C"))])

    def test_round_trip(self):
        out = dl.scale_devices(dl.scale_devices(SYN, {"M$2": 2.0}), {"M$2": 0.5})
        self.assertEqual(dl.device_widths_um(out), dl.device_widths_um(SYN))

    def test_fail_closed(self):
        for bad in (0, -1.0, float("nan"), float("inf"), True, "2", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                dl.scale_devices(SYN, {"M$1": bad})
        with self.assertRaises(ValueError):
            dl.scale_devices(SYN, {})
        with self.assertRaises(ValueError):
            dl.scale_devices(SYN, {"M$99": 1.5})
        with self.assertRaises(ValueError):
            dl.lever_factors({"nope": 1.5})


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pa.load_extracted()
        cls.plan = dl.lever_variants(cls.text)

    def test_devices_exist_with_expected_roles(self):
        w = dl.device_widths_um(self.text)
        self.assertEqual(w["M$12"], 16.0)
        for devs in dl.DEVICES.values():
            for d in devs:
                self.assertIn(d, w)

    def test_ctrl_is_source_and_levers_change_only_named_devices(self):
        ctrl = self.plan[0]
        self.assertIs(ctrl["dut"], self.text)
        base = dl.device_widths_um(self.text)
        for v in self.plan[1:-1]:
            now = dl.device_widths_um(v["dut"])
            changed = {d for d in now if now[d] != base[d]}
            self.assertEqual(changed, set(v["factors"]), v["id"])

    def test_budget_within_declared_cap(self):
        self.assertEqual(dl.check_budget(self.plan, pa.budget_points("two")), 23)
        with self.assertRaises(ValueError):
            dl.check_budget(self.plan + self.plan[:1], pa.budget_points("two"))

    def test_duplicate_ids_refused(self):
        with self.assertRaises(ValueError):
            dl.lever_variants(self.text, dl.LEVERS + dl.LEVERS[:1])


if __name__ == "__main__":
    unittest.main()
