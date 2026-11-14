#!/usr/bin/env python3
"""PDK-free regressions for layout/pex/design_lever_study.py (#323).

No ngspice, no klt, no fleet. Covers the device-W transforms, fail-closed
inputs, the lever plan against the committed extracted DUT, the declared
request budget, and (#358) the committed design-levers evidence: every stage
still verifies, and an edit to the study's own source is provenance drift
rather than a verify error (#249).

    python3 layout/tests/test_design_lever_study.py
"""

from __future__ import annotations

import contextlib
import io
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


class CommittedEvidence(unittest.TestCase):
    """The two guards parasitic_attribution's committed evidence already has
    and this study lacked (#358)."""

    def stages(self):
        stages = sorted((dl.HERE / "artifacts" / "design-levers").glob("*/stage.json"))
        self.assertTrue(stages, "no committed design-levers stage found")
        return stages

    def test_verify_every_committed_design_levers_stage(self):
        for st in self.stages():
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = dl.main(["verify", str(st.parent)])
            self.assertEqual(rc, 0, f"{st.parent}:\n{out.getvalue()}")

    def test_source_edit_alone_cannot_break_committed_verification(self):
        """#249 for this study (#358): perturbing what `pa.file_sha` returns
        for the three Python sources a lever stage records -- including
        `design_lever_study.py`, which no allowlist names -- plus the tb.json
        pin must be reported as provenance drift, never fail `verify`."""
        stages = self.stages()
        real_sha, real_pin, real_check = pa.file_sha, pa.TB_JSON_CONSUMED_SHA256, pa.check_bench
        code = {(dl.HERE / "pex_measure.py").resolve(),
                (dl.HERE / "parasitic_attribution.py").resolve(),
                Path(dl.__file__).resolve()}

        def edited_file_sha(path):
            h = real_sha(path)
            return ("0" * 64 if h != "0" * 64 else "1" * 64) if Path(path).resolve() in code else h

        try:
            pa.file_sha = edited_file_sha
            # a re-pin of tb.json's consumed fields moves the constant and
            # tb.json together; the bench gate itself is not under test here
            pa.TB_JSON_CONSUMED_SHA256 = "f" * 64
            pa.check_bench = lambda: None
            for st in stages:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    rc = dl.main(["verify", str(st.parent)])
                text = out.getvalue()
                self.assertEqual(rc, 0, f"{st.parent}:\n{text}")
                self.assertIn("provenance drift", text)
                for key in ("design_lever_study_py", "parasitic_attribution_py",
                            "pex_measure_py", "tb_json_consumed_fields"):
                    self.assertIn(key, text, f"{st.parent}: {key}")
        finally:
            pa.file_sha, pa.TB_JSON_CONSUMED_SHA256, pa.check_bench = \
                real_sha, real_pin, real_check


if __name__ == "__main__":
    unittest.main()
