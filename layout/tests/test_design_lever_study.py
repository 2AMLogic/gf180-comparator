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
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class CombinedStudy(unittest.TestCase):
    def test_global_rc_and_pair_tail_edits_commute(self):
        text = pa.load_extracted()
        self.assertIs(dl.combined_transform(text, {}, 1, 1), text)
        factors = dl.lever_factors({"pair": 1.5, "tail": 1.5})
        scaled = pa.scale_cg_r(text, 0.25, 0.5)
        self.assertEqual(dl.combined_transform(text, factors, 0.25, 0.5),
                         dl.scale_devices(scaled, factors))
        self.assertNotEqual(text, scaled)

    def test_invalid_factors_fail_closed(self):
        for bad in (0, -1, float("nan"), float("inf"), True, "0.5"):
            for factors, fc, fr in (({"M$1": bad}, 1, 1), ({}, bad, 1), ({}, 1, bad)):
                with self.subTest(bad=bad, factors=factors, fc=fc, fr=fr):
                    with self.assertRaises(ValueError):
                        dl.combined_transform(SYN, factors, fc, fr)

    def test_cap_checked_before_any_submission(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pa, "run_stage") as submit:
            with patch.object(dl, "COMBINED_REQUEST_CAP", 322):
                with self.assertRaisesRegex(ValueError, "323.*cap 322"):
                    dl.main(["combined-run", str(Path(tmp) / "study")])
            submit.assert_not_called()

    def test_control_refusal_stops_before_grid(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pa, "run_stage", return_value=1) as submit:
            root = Path(tmp) / "study"
            self.assertEqual(dl.main(["combined-run", str(root)]), 1)
            self.assertEqual(submit.call_count, 1)
            self.assertEqual([v["id"] for v in submit.call_args.args[2]], ["ctrl", "sch"])
            self.assertEqual(submit.call_args.args[4], "batch")
            with self.assertRaises(FileExistsError):
                dl.main(["combined-run", str(root)])
            self.assertEqual(submit.call_count, 1)

    def test_conditional_followups(self):
        # Exercise the dispatch decisions using real report shapes and
        # synthetic delays. These values are never campaign evidence.
        two = pa.budget_points("two")
        ref = next((dl.HERE / "artifacts/design-levers").glob("*/stage.json")).parent
        control = {v: pa._budget_values(ref / v, two) for v in ("ctrl", "sch")}
        for winner, expected in (("primary", ["controls", "primary", "remaining-five"]),
                                 ("larger-pair", ["controls", "primary", "larger-pair", "remaining-five"]),
                                 (None, ["controls", "primary", "larger-pair"])):
            stages = []

            def measure(root, stage, text, plan, points, jobs):
                stages.append(stage)
                if stage == "controls":
                    return control
                if stage == "remaining-five":
                    self.assertEqual(len(points), 5)
                    self.assertEqual(len(plan), 1)
                results = {}
                for v in plan:
                    passes = v is plan[0] and stage in (winner, "remaining-five")
                    row = dict(control["ctrl"][two[0]], td_od50_ns=1.4 if passes else 1.6)
                    results[v["id"]] = dict.fromkeys(points, row)
                return results

            with self.subTest(winner=winner), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(dl, "combined_stage", side_effect=measure), \
                    patch.object(dl, "kickback_stage", return_value="record") as kickback:
                root = Path(tmp) / "run"
                self.assertEqual(dl.main(["combined-run", str(root)]), 0)
                summary = json.loads((root / "timing.json").read_text())
                self.assertEqual(stages, expected)
                self.assertEqual(len(summary["seven_corner_passes"]), int(bool(winner)))
                self.assertEqual(kickback.call_count, 2 if winner else 0)
                if winner:
                    self.assertEqual([c.args[1]["id"] for c in kickback.call_args_list],
                                     ["ctrl", *summary["two_corner_passes"]])


class CombinedReportValidation(unittest.TestCase):
    """Replay the DR-0007 reports through the combined study's report reader."""

    archive = dl.HERE / "artifacts/design-levers/20261017-192854-fa963e7"
    text = pa.load_extracted()
    points = pa.budget_points("two")

    def replay(self, variant, tag, change, stage="primary"):
        def restore(directory, *args, **kwargs):
            dest = directory / variant["id"]
            shutil.copytree(self.archive / variant["id"], dest)
            path = dest / f"{tag}.report.json"
            report = json.loads(path.read_text())
            change(report)
            path.write_text(json.dumps(report))
            return 0

        with tempfile.TemporaryDirectory() as tmp, patch.object(pa, "run_stage", restore):
            return dl.combined_stage(Path(tmp), stage, self.text, [variant], self.points, 1)

    def test_control_and_candidate_require_a_sane_low_to_high_decision(self):
        ctrl = dl.controls(self.text)[0]
        pair = next(v for v in dl.lever_variants(self.text) if v["id"] == "pair-x1.5")
        tag = f"ladder-{pa.pid(self.points[0])}"
        for field, bad, diagnostic in (("da_first", 1.0, "dout_od50_first"),
                                       ("da_end", 0.0, "dout_od50_end"),
                                       ("td_a", 0.5e-12, "td_od50_ns"),
                                       ("td_a", 26e-9, "td_od50_ns")):
            def change(report):
                measurements = {m["name"]: m for m in report["corners"][0]["measurements"]}
                if variant is pair:
                    measurements["td_a"]["value"] = 1.4e-9
                measurements[field]["value"] = bad

            for stage, variant in (("controls", ctrl), ("primary", pair)):
                with self.subTest(stage=stage, field=field, bad=bad):
                    with self.assertRaisesRegex(ValueError, f"{stage}/{variant['id']}/{tag}.*{diagnostic}"):
                        self.replay(variant, tag, change, stage)

    def test_bench_bounds_are_inclusive_and_controls_can_exceed_the_design_target(self):
        ctrl = dl.controls(self.text)[0]
        for delay in (1e-12, 1.5e-9, 25e-9):
            def change(report):
                measures = {m["name"]: m for m in report["corners"][0]["measurements"]}
                for field, value in (("td_a", delay), ("da_first", 0.1), ("da_end", 0.9)):
                    measures[field]["value"] = value

            with self.subTest(delay=delay):
                pt = self.points[0]
                row = self.replay(ctrl, f"ladder-{pa.pid(pt)}", change)["ctrl"][pt]
                self.assertEqual(pa._corner_cell(row, None, {})["meets_1p5ns"], delay <= 1.5e-9)

    def test_every_requested_supply_is_checked(self):
        tag = f"ladder-{pa.pid(self.points[0])}"
        for variant in dl.controls(self.text):
            for supplies in ({"vsup": 2.97, "vsupa": 3.63}, {"vsup": 2.97}):
                with self.subTest(variant=variant["id"], supplies=supplies):
                    with self.assertRaisesRegex(ValueError, f"{variant['id']}/{tag}.*vsupa"):
                        self.replay(variant, tag, lambda r: r["corners"][0].update(supply_v=supplies))

    def test_failed_execution_or_required_measurement_rejects_numeric_values(self):
        ctrl = dl.controls(self.text)[0]
        p, t, v = self.points[0]
        for tag, names in ((pa._probe_tag(t, v), ("t_flip",)),
                           (f"ladder-{pa.pid((p, t, v))}", ("td_a", "da_first", "da_end"))):
            for field in ("report", "corner", *names):
                def change(report):
                    corner = report["corners"][-1]
                    if field == "report":
                        report["status"] = "error"
                    elif field == "corner":
                        corner["status"] = "error"
                    else:
                        next(m for m in corner["measurements"] if m["name"] == field)["status"] = "error"

                with self.subTest(tag=tag, field=field):
                    with self.assertRaisesRegex(ValueError, f"ctrl/{tag}.*{field}.*error"):
                        self.replay(ctrl, tag, change)

    def test_failed_offset_probe_stops_before_ladder_dispatch(self):
        ctrl = dl.controls(self.text)[0]
        _, t, v = self.points[0]
        tag = pa._probe_tag(t, v)
        path = self.archive / "ctrl" / f"{tag}.report.json"
        for change, diagnostic in (({"status": "error"}, "t_flip status 'error'"),
                                   ({"value": 0.0}, "probe span"),
                                   ({"value": pa.pm.PROBE_TRAMP}, "probe span"),
                                   ({"value": 1.1 * pa.pm.PROBE_TRAMP}, "probe span")):
            report = json.loads(path.read_text())
            report["corners"][-1]["measurements"][0].update(change)

            def submit_probe(vdir, job, *args):
                self.assertEqual(job, tag, "invalid probe dispatched a dependent ladder")
                return {"ok": True, "report": report}

            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(pa.pm, "_klt_identity", return_value={}), \
                    patch.object(pa, "submit", side_effect=submit_probe) as submit:
                root = Path(tmp)
                with self.assertRaisesRegex(ValueError, "controls: fleet reports incomplete"):
                    dl.combined_stage(root, "controls", self.text, [ctrl], self.points, 1)
                submit.assert_called_once()
                log = json.loads((root / "controls" / "run-log.json").read_text())
                self.assertIn(diagnostic, log["job_errors"][f"ctrl/{tag}"])

    def test_archived_candidate_with_clamped_probe_cannot_qualify(self):
        pair = next(v for v in dl.lever_variants(self.text) if v["id"] == "pair-x1.5")
        _, t, v = self.points[0]
        tag = pa._probe_tag(t, v)

        def clamp(report):
            report["corners"][-1]["measurements"][0]["value"] = pa.pm.PROBE_TRAMP

        with self.assertRaisesRegex(ValueError, f"primary/pair-x1.5/{tag}.*probe span"):
            self.replay(pair, tag, clamp)

    def test_wrong_decision_at_a_followup_corner_withholds_seven_corner_pass(self):
        pair = next(v for v in dl.lever_variants(self.text) if v["id"] == "pair-x1.5")
        bad_point = ("ss", 125.0, 3.63)

        def submit(vdir, tag, deck, request, *args):
            grid = request["corners"]
            processes = [p["name"] for p in grid["process"]]
            points = {(p, grid["temperature_c"][0], grid["supply_v"]["vsup"][0]) for p in processes}
            probe = tag.startswith("probe-")
            source = "probe" if probe else f"ladder-{processes[0]}"
            side = "schematic" if vdir.name == "sch" else "extracted"
            archive = dl.HERE / "artifacts/measure" / side / f"{source}.report.json"
            template = json.loads(archive.read_text())
            template["corners"] = [c for c in template["corners"] if pa.pm._point_key(c) in points]
            if not probe and vdir.name == pair["id"]:
                corner, = template["corners"]
                measurements = {m["name"]: m for m in corner["measurements"]}
                measurements["td_a"]["value"] = 1.4e-9
                if pa.pm._point_key(corner) == bad_point:
                    measurements["da_end"]["value"] = 0.0
            template["environment"]["netlist_sha256"] = pa.sha(deck)
            (vdir / f"{tag}.request.json").write_text(json.dumps(request))
            (vdir / f"{tag}.report.json").write_text(json.dumps(template))
            return {"ok": True, "report": template}

        with tempfile.TemporaryDirectory() as tmp, patch.object(pa, "submit", submit), \
                patch.object(pa.pm, "_klt_identity", return_value={}), \
                patch.object(dl, "combined_grid", return_value=[pair]), patch.object(dl, "kickback_stage") as kick:
            root = Path(tmp) / "study"
            self.assertEqual(dl.main(["combined-run", str(root)]), 1)
            result = json.loads((root / "timing.json").read_text())
            self.assertTrue(result["controls_valid"])
            self.assertEqual(result["two_corner_passes"], [pair["id"]])
            self.assertNotIn("seven_corner_passes", result)
            self.assertIn(f"remaining-five/{pair['id']}/ladder-{pa.pid(bad_point)}", result["validity_failure"])
            self.assertIn("dout_od50_end", result["validity_failure"])
            kick.assert_not_called()


class KickbackReportValidation(unittest.TestCase):
    """Generate both request phases and replace fleet dispatch with finite test values."""

    @staticmethod
    def passing_report(request, entry, toolchain):
        t, = request["corners"]["temperature_c"]
        corners = []
        values = {"t_flip": 3.6e-5, "ad_pos": 0.012, "da_end": 1, "db_end": 1, "dc_end": 1}
        for proc in request["corners"]["process"]:
            p = proc["name"]
            measures = [{"name": m["name"], "value": values.get(m["name"], 0.001), "status": "pass"}
                        for m in request["measurements"]]
            corners.append({"corner_id": f"{p}/novdd/{t:g}C", "process": p, "temperature_c": t,
                            "supply_v": {}, "status": "pass", "measurements": measures})
        return {
            "status": "pass", "corners": corners,
            "environment": {"netlist_sha256": entry["netlist_sha256"], "remote": {"job_id": "test-job"},
                            "engine": "ngspice", "engine_version": str(toolchain["ngspice_min_major"])},
            "provenance": {"pdk": {"name": toolchain["pdk_variant"],
                                   "version": "open_pdks " + toolchain["open_pdks"]}},
        }

    def test_report_and_ingredient_status_gate_each_phase(self):
        variant = dl.controls(pa.load_extracted())[0]
        for phase, field in (("probe", "report"), ("probe", "corner"), ("probe", "t_flip"),
                             ("main", "report"), ("main", "corner"), ("main", "ad_pos"),
                             ("main", "dc_end"), (None, None)):
            def dispatch(work, names, **kwargs):
                bundle = dl.kr.load_bundle(work, "comparator-kickback")
                for name in names:
                    entry = bundle["requests"][name]
                    request = json.loads((work / entry["request"]).read_text())
                    report = self.passing_report(request, entry, bundle["toolchain"])
                    corner = next((c for c in report["corners"] if c["process"] == "tt"), None)
                    if entry["leg"] == phase and corner:
                        if field == "report":
                            report["status"] = "error"
                        elif field == "corner":
                            corner["status"] = "error"
                        else:
                            next(m for m in corner["measurements"] if m["name"] == field)["status"] = "error"
                    (work / f"report-{name}.json").write_text(json.dumps(report))

            with self.subTest(phase=phase, field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                pdk = root / "gf180mcuD"
                models = pdk / "libs.tech/ngspice"
                models.mkdir(parents=True)
                (models / "sm141064.ngspice").touch()
                (models / "design.ngspice").touch()
                with patch.dict(os.environ, GF180_PDK_PATH=str(pdk)), \
                        patch.object(dl.kr, "dispatch", side_effect=dispatch) as submit:
                    if phase:
                        with self.assertRaisesRegex(ValueError, f"{phase}.*{field}.*error"):
                            dl.kickback_stage(root, variant)
                    else:
                        result = dl.kickback_stage(root, variant)
                        self.assertEqual(set(result["corners"]), set(pa.CORNER_IDS.values()))
                        for corner in result["corners"].values():
                            self.assertAlmostEqual(corner["kick_1k_peak_mv"], 12.0)
                            self.assertAlmostEqual(corner["dut_vos_v"], -0.004)
                self.assertEqual(submit.call_count, 1 if phase == "probe" else 2)
                if phase == "probe":
                    work = root / "kickback" / variant["id"]
                    self.assertFalse((work / dl.kr.mk.PROBE_RESULTS_NAME).exists())
                    self.assertEqual(list(work.glob("request-main-*.json")), [])


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
