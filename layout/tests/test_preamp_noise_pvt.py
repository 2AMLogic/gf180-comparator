#!/usr/bin/env python3
"""PDK-free, ngspice-free negative fixtures for layout/pex/preamp_noise_pvt.py (#209).

Synthetic bundles/requests/reports exercise the paired 45-point validator:
coverage, source identity, measured-gain referral and executor capability
failures must each yield an "incomplete" summary (never a complete verdict),
and a complete summary still excludes regenerative latch noise and promotes
nothing.

    python3 layout/tests/test_preamp_noise_pvt.py
"""

from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pex"))

import preamp_noise_probe as pnp  # noqa: E402
import preamp_noise_pvt as pvt  # noqa: E402

PROCESS = ["tt", "ff", "ss", "fs", "sf"]
TEMPS = [-40.0, 27.0, 125.0]
VDDS = [2.97, 3.3, 3.63]
PARAMS = {"dut_ib": 1e-05, "dut_vcm": 1.65}
SHA_S, SHA_X = "5" * 64, "e" * 64
NODES = {"schematic": ["xdut.aop", "xdut.aon"],
         "extracted": ["xdut.xlayout_dut.aop", "xdut.xlayout_dut.aon"]}
RUNNER_OK = {"provider": "aws-batch-fleet", "runner_klt_version": "0.7.0+gabc",
             "client_klt_version": "0.7.0+gabc", "runner_compatibility": "match"}


def make_grid(process=PROCESS, temps=TEMPS, vdds=VDDS):
    return {"process": list(process), "process_sections": {p: [p, "res_typical"] for p in process},
            "temperatures_c": list(temps), "supply_v": list(vdds)}


def body_sha(tag):
    return pvt.sha256_bytes(tag.encode())


def make_bundle(grid=None):
    g = grid or make_grid()
    reqs = {}
    for leg in pvt.LEGS:
        for v in g["supply_v"]:
            tag = f"{leg}-v{v:.2f}"
            reqs[tag] = {"leg": leg, "vdd": v, "request": f"request-{tag}.json",
                         "request_sha256": "0" * 64, "netlist": f"body-{tag}.spice",
                         "netlist_sha256": body_sha(tag)}
    return {
        "schema": pvt.BUNDLE_SCHEMA, "version": pvt.BUNDLE_VERSION,
        "nominal_only": len(g["process"]) == 1,
        "params": dict(PARAMS), "grid": g, "stimulus_sha256": pvt.stimulus_sha256(),
        "pinned_identity": {"schematic": SHA_S, "extracted": SHA_X, "params": dict(PARAMS)},
        "legs": {"schematic": {"dut_sha256": SHA_S, "staged_dut": "sources/schematic/c.spice",
                               "observation": NODES["schematic"], "c_route": "0"},
                 "extracted": {"dut_sha256": SHA_X, "staged_dut": "sources/extracted/c.cir",
                               "observation": NODES["extracted"], "c_route": "0"}},
        "requests": reqs,
        "staged": {"sources/schematic/c.spice": SHA_S, "sources/extracted/c.cir": SHA_X},
    }


def make_requests(bundle):
    g = bundle["grid"]
    proc = [{"name": p, "sections": g["process_sections"][p]} for p in g["process"]]
    return {t: pvt.build_request(r["netlist"], proc, g["temperatures_c"],
                                 tuple(bundle["legs"][r["leg"]]["observation"]))
            for t, r in bundle["requests"].items()}


def unit_values(av=18.0, onoise=1.8e-3, onoise_hf=None, inoise=3.3e-4, white=250e-9):
    onoise_hf = onoise * 0.995 if onoise_hf is None else onoise_hf
    w_on = white * math.sqrt(pvt.WHITE_BW_HZ)
    raw = {"op.vbias_mv": 900.0, "op.dc_p": 2.05, "op.dc_n": 2.05,
           "nfull.onoise": onoise, "nfull.inoise": inoise, "nhf.onoise": onoise_hf,
           "nwhite.onoise": w_on, "ac.av_dc": av}
    raw.update({"vn_in_uv": onoise / av * 1e6, "vn_in_hf_uv": onoise_hf / av * 1e6,
                "onoise_uv": onoise * 1e6, "onoise_hf_uv": onoise_hf * 1e6,
                "inoise_band_uv": inoise * 1e6, "white_nv_rthz": white * 1e9,
                "enbw_mhz": onoise ** 2 / white ** 2 / 1e6})
    return raw


def corner(proc, temp, values, status="pass"):
    return {"corner_id": f"{proc}/novdd/{temp:g}C", "status": status,
            "measurements": [{"name": k, "value": v} for k, v in values.items()]}


def make_reports(bundle, leg_scale=None, runner=RUNNER_OK):
    reps = {}
    for tag, r in bundle["requests"].items():
        s = (leg_scale or {}).get(r["leg"], 1.0)
        corners = []
        for i, p in enumerate(bundle["grid"]["process"]):
            for j, t in enumerate(bundle["grid"]["temperatures_c"]):
                corners.append(corner(p, t, unit_values(av=18.0 - i - j * 0.1,
                                                        onoise=1.8e-3 * s * (1 + 0.01 * i + 0.02 * j))))
        reps[tag] = {"environment": {"netlist_sha256": r["netlist_sha256"],
                                     "remote": dict(runner) if runner else None},
                     "corners": corners}
    return reps


def codes(summary):
    return {i.split(":", 1)[0].split()[-1] for i in summary["issues"]}


def has(summary, code):
    return any(code in i for i in summary["issues"])


class Complete(unittest.TestCase):
    def setUp(self):
        self.b = make_bundle()
        self.s = pvt.validate_campaign(self.b, make_requests(self.b),
                                       make_reports(self.b, {"extracted": 0.7}))

    def test_complete_verdict_full_coverage(self):
        self.assertEqual(self.s["issues"], [])
        self.assertEqual(self.s["verdict"], "complete")
        self.assertEqual(self.s["coverage"], {"schematic": "45/45", "extracted": "45/45"})
        self.assertEqual(len(self.s["per_corner"]), 45)

    def test_deltas_and_binding_corners_cite_sources(self):
        row = self.s["per_corner"]["tt_27c_3.30v"]
        self.assertAlmostEqual(row["delta_pct"]["vn_in_uv"], -30.0, places=6)
        self.assertEqual(row["sources"]["extracted"]["report"], "report-extracted-v3.30.json")
        self.assertEqual(row["sources"]["schematic"]["corner_id"], "tt/novdd/27C")
        for b in self.s["binding_corners"].values():
            self.assertIn(b["corner"], self.s["per_corner"])
            for leg in pvt.LEGS:
                self.assertEqual(b["sources"][leg]["netlist_sha256"],
                                 self.b["requests"][b["sources"][leg]["report"][7:-5]]["netlist_sha256"])
        self.assertEqual(self.s["binding_corners"]["min_extracted_av_dc"]["corner"], "sf_125c_2.97v")

    def test_reports_gain_noise_bandwidth_white(self):
        row = self.s["per_corner"]["ss_-40c_3.63v"]
        for leg in pvt.LEGS:
            self.assertEqual(set(row[leg]), set(pvt.QUANTITIES))

    def test_scope_excludes_latch_noise_no_promotion(self):
        sc = self.s["scope"]
        self.assertIn("regenerative", sc["excludes"])
        self.assertIs(sc["t1_promotion"], False)
        self.assertIsNone(sc["spec_row_verdict"])
        self.assertIn("10 fF", sc["schematic_allowance"])


class Coverage(unittest.TestCase):
    def setUp(self):
        self.b = make_bundle()
        self.req = make_requests(self.b)

    def run_(self, reps, b=None):
        return pvt.validate_campaign(b or self.b, self.req if b is None else make_requests(b), reps)

    def test_missing_corner(self):
        reps = make_reports(self.b)
        reps["extracted-v3.63"]["corners"].pop(0)
        s = self.run_(reps)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "MISSING_CORNER: extracted tt_-40c_3.63v"))
        self.assertEqual(s["coverage"]["extracted"], "44/45")
        self.assertEqual(s["binding_corners"], {})

    def test_missing_report(self):
        reps = make_reports(self.b)
        del reps["schematic-v2.97"]
        s = self.run_(reps)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "REPORT_MISSING"))
        self.assertTrue(has(s, "COVERAGE_INCOMPLETE: schematic has 30/45"))

    def test_duplicate_corner(self):
        reps = make_reports(self.b)
        reps["schematic-v3.30"]["corners"].append(copy.deepcopy(reps["schematic-v3.30"]["corners"][3]))
        s = self.run_(reps)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "DUPLICATE_CORNER"))

    def test_unexpected_corner(self):
        reps = make_reports(self.b)
        reps["extracted-v3.30"]["corners"].append(corner("res_ff", 27.0, unit_values()))
        s = self.run_(reps)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "UNEXPECTED_CORNER: extracted res_ff_27c_3.30v"))

    def test_failed_unit(self):
        reps = make_reports(self.b)
        reps["extracted-v2.97"]["corners"][5]["status"] = "error"
        s = self.run_(reps)
        self.assertTrue(has(s, "FAILED_UNIT"))
        self.assertFalse(has(s, "MISSING_CORNER"))  # reported once, not twice
        self.assertEqual(s["verdict"], "incomplete")

    def test_nominal_only_grid_never_complete(self):
        b = make_bundle(make_grid(["tt"], [27.0], [3.3]))
        s = self.run_(make_reports(b), b)
        self.assertEqual(s["coverage"]["extracted"], "1/1")
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "COVERAGE_INCOMPLETE: the bundle's grid has 1 corners"))

    def test_partial_grid_never_complete(self):
        b = make_bundle(make_grid(PROCESS, [27.0], VDDS))
        s = self.run_(make_reports(b), b)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "grid has 15 corners"))

    def test_nonpositive_or_nonfinite_values(self):
        for key, bad in (("ac.av_dc", 0.0), ("nfull.onoise", float("nan")),
                         ("nwhite.onoise", -1.0), ("vn_in_uv", float("inf"))):
            reps = make_reports(self.b)
            for m in reps["schematic-v3.30"]["corners"][0]["measurements"]:
                if m["name"] == key:
                    m["value"] = bad
            s = self.run_(reps)
            self.assertEqual(s["verdict"], "incomplete", key)
            self.assertTrue(has(s, "NONFINITE_OR_NONPOSITIVE"), key)


class SourceIdentity(unittest.TestCase):
    def setUp(self):
        self.b = make_bundle()
        self.req = make_requests(self.b)
        self.reps = make_reports(self.b)

    def test_report_from_other_body(self):
        self.reps["extracted-v3.30"]["environment"]["netlist_sha256"] = "f" * 64
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "REPORT_SOURCE_MISMATCH: extracted-v3.30"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_unlinked_report(self):
        del self.reps["schematic-v3.63"]["environment"]["netlist_sha256"]
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "REPORT_UNLINKED"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_dut_not_the_202_identity(self):
        self.b["legs"]["extracted"]["dut_sha256"] = "1" * 64
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "SOURCE_IDENTITY_MISMATCH: extracted DUT"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_staged_dut_not_declared(self):
        self.b["staged"]["sources/schematic/c.spice"] = "2" * 64
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "SOURCE_IDENTITY_MISMATCH: staged schematic"))

    def test_bias_differs(self):
        self.b["params"] = {"dut_ib": 2e-05, "dut_vcm": 1.65}
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "BIAS_MISMATCH"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_stimulus_differs(self):
        self.b["stimulus_sha256"] = "3" * 64
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "STIMULUS_MISMATCH"))

    def test_request_altered(self):
        self.req["extracted-v3.30"]["measurements"][0]["expr"] = "nfull.onoise/18.0*1e6"
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "REQUEST_MISMATCH: extracted-v3.30 measurements"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_request_grid_altered(self):
        self.req["schematic-v2.97"]["corners"]["temperature_c"] = [27.0]
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "REQUEST_MISMATCH: schematic-v2.97 corners"))

    def test_request_not_enforced(self):
        self.req["schematic-v3.30"]["batch"]["runner_version_check"] = "warn"
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "REQUEST_MISMATCH: schematic-v3.30 batch"))

    def test_leg_missing(self):
        for t in [t for t, r in self.b["requests"].items() if r["leg"] == "schematic"]:
            del self.b["requests"][t]
        s = pvt.validate_campaign(self.b, self.req, self.reps)
        self.assertTrue(has(s, "LEG_MISSING"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_staged_tamper_refused(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / "a.txt").write_text("x")
            b = {"schema": pvt.BUNDLE_SCHEMA, "version": pvt.BUNDLE_VERSION,
                 "staged": {"a.txt": pvt.sha256_bytes(b"y")}, "requests": {}}
            with self.assertRaises(pvt.Refusal) as cm:
                pvt.verify_staged(work, b)
            self.assertEqual(cm.exception.name, "STAGED_SOURCE_TAMPERED")
            b["staged"] = {"../a.txt": "0"}
            with self.assertRaises(pvt.Refusal) as cm:
                pvt.verify_staged(work, b)
            self.assertEqual(cm.exception.name, "SOURCE_BUNDLE_INCONSISTENT")


class GainReferral(unittest.TestCase):
    def setUp(self):
        self.b = make_bundle()
        self.req = make_requests(self.b)

    def mutate(self, tag, idx, **kv):
        reps = make_reports(self.b)
        for m in reps[tag]["corners"][idx]["measurements"]:
            if m["name"] in kv:
                m["value"] = kv[m["name"]]
        return pvt.validate_campaign(self.b, self.req, reps)

    def test_referral_to_another_gain(self):
        v = unit_values()
        s = self.mutate("extracted-v3.30", 0, vn_in_uv=v["nfull.onoise"] / 20.0 * 1e6)
        self.assertTrue(has(s, "GAIN_REFERRAL_MISMATCH: reported vn_in_uv"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_stale_hf_referral(self):
        s = self.mutate("schematic-v2.97", 2, vn_in_hf_uv=1.0)
        self.assertTrue(has(s, "GAIN_REFERRAL_MISMATCH: reported vn_in_hf_uv"))

    def test_enbw_not_from_white(self):
        s = self.mutate("schematic-v2.97", 2, enbw_mhz=25.0)
        self.assertTrue(has(s, "GAIN_REFERRAL_MISMATCH: reported enbw_mhz"))

    def test_gain_below_unity(self):
        reps = make_reports(self.b)
        reps["extracted-v3.63"]["corners"][4]["measurements"] = [
            {"name": k, "value": v} for k, v in unit_values(av=0.5).items()]
        s = pvt.validate_campaign(self.b, self.req, reps)
        self.assertTrue(has(s, "GAIN_BELOW_UNITY"))
        self.assertEqual(s["verdict"], "incomplete")

    def test_hf_band_exceeds_full(self):
        reps = make_reports(self.b)
        reps["extracted-v3.63"]["corners"][4]["measurements"] = [
            {"name": k, "value": v} for k, v in unit_values(onoise=1e-3, onoise_hf=2e-3).items()]
        s = pvt.validate_campaign(self.b, self.req, reps)
        self.assertTrue(has(s, "NOISE_BAND_INCONSISTENT"))

    def test_recomputed_quantities(self):
        q, issues = pvt.quantities(unit_values(av=20.0, onoise=2e-3, white=200e-9))
        self.assertEqual(issues, [])
        self.assertAlmostEqual(q["vn_in_uv"], 100.0)
        self.assertAlmostEqual(q["white_nv_rthz"], 200.0)
        self.assertAlmostEqual(q["enbw_mhz"], (2e-3 / 200e-9) ** 2 / 1e6)


class Executor(unittest.TestCase):
    def test_capability_gap(self):
        self.assertIsNone(pvt.executor_capability_gap("0.7.0+gabc"))
        self.assertIsNone(pvt.executor_capability_gap("0.7.0+gabc", "0.7.0+gabc"))
        for v in ("0.5.0", "0.6.9", None, "garbage"):
            gap = pvt.executor_capability_gap(v)
            self.assertIn("analysis_steps", gap)
            self.assertIn("expr", gap)
        self.assertIn("enforce", pvt.executor_capability_gap("0.7.0+g1", "0.7.0+g2"))

    def test_old_runner_never_complete(self):
        b = make_bundle()
        reps = make_reports(b, runner=dict(RUNNER_OK, runner_klt_version="0.5.0",
                                           runner_compatibility="mismatch"))
        s = pvt.validate_campaign(b, make_requests(b), reps)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "UNSUPPORTED_EXECUTOR_CAPABILITY"))

    def test_mismatched_runner_never_complete(self):
        b = make_bundle()
        reps = make_reports(b, runner=dict(RUNNER_OK, runner_compatibility="mismatch"))
        s = pvt.validate_campaign(b, make_requests(b), reps)
        self.assertTrue(has(s, "runner_compatibility 'mismatch'"))

    def test_local_reports_never_complete(self):
        b = make_bundle()
        s = pvt.validate_campaign(b, make_requests(b), make_reports(b, runner=None))
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "report names no fleet runner"))

    def test_preflight_refusal_envelope(self):
        env = {"schema_version": 1, "error": {"command": "sim", "code": "batch_runner_version_mismatch",
                                              "message": "the fleet runner runs klt 0.5.0"}}
        issues = pvt.check_executor(env)
        self.assertEqual(len(issues), 1)
        self.assertIn("batch_runner_version_mismatch", issues[0])
        b = make_bundle()
        reps = make_reports(b)
        reps["extracted-v3.30"] = env
        s = pvt.validate_campaign(b, make_requests(b), reps)
        self.assertEqual(s["verdict"], "incomplete")
        self.assertTrue(has(s, "MISSING_CORNER: extracted tt_27c_3.30v"))

    def test_runner_preflight_diagnostic_quoted(self):
        rep = {"environment": {"remote": dict(RUNNER_OK, runner_klt_version="0.5.0",
                                              runner_compatibility="mismatch")},
               "corners": [{"corner_id": "tt/novdd/27C", "status": "error", "diagnostics": [{
                   "code": "batch_job_failed", "runner_code": "batch_runner_version_mismatch",
                   "message": "the fleet runner runs klt 0.5.0 -- the request was not run"}]}]}
        issues = pvt.check_executor(rep)
        self.assertTrue(any("batch_runner_version_mismatch: the fleet runner runs klt 0.5.0" in i
                            for i in issues))
        self.assertTrue(any("needs `analysis_steps`" in i for i in issues))

    def test_campaign_refuses_before_staging(self):
        with tempfile.TemporaryDirectory() as d:
            probe = Path(d) / "probe.json"
            probe.write_text(json.dumps({"environment": {"remote": dict(
                RUNNER_OK, runner_klt_version="0.5.0")}}))
            out = Path(d) / "campaign"
            argv = ["preamp_noise_pvt.py", "campaign", str(out), "--probe-report", str(probe)]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(pvt, "write_request_set") as w, \
                    mock.patch.object(pvt, "run_klt") as r:
                with self.assertRaises(pvt.Refusal) as cm:
                    pvt.main()
            self.assertEqual(cm.exception.name, "UNSUPPORTED_EXECUTOR_CAPABILITY")
            w.assert_not_called()
            r.assert_not_called()
            self.assertFalse(out.exists())


class RequestShape(unittest.TestCase):
    def test_stimulus_is_202_deck_circuit(self):
        fake = SimpleNamespace(design_include="/p/d", model_lib="/p/m")
        deck = pnp.build_deck("t", "/dut", fake, [("hub", "a", "b")], "0", None, PARAMS)
        lines = pvt.stimulus_lines()
        self.assertTrue(all(line in deck for line in lines))
        self.assertIn("Xdut ap an clk ibn dout doutb vdd 0 comparator_dut", lines)
        self.assertIn("vclk clk 0 dc 0", lines)
        self.assertFalse(any(line.startswith("Cw") for line in lines))  # no 10 fF allowance

    def test_body_has_no_corner_or_analysis_cards(self):
        body = pvt.body_text("extracted", 2.97, PARAMS, "sources/x.cir", ["* source-sha256 ab x"])
        self.assertIn(".param vdd_val=2.97", body)
        self.assertIn(".param dut_ib=1e-05", body)
        for bad in (".lib", ".temp", "noise ", "Cwp"):
            self.assertNotIn(bad, body)

    def test_request_referral_and_enforce(self):
        req = pvt.build_request("b.spice", [{"name": "tt", "sections": ["typical"]}], TEMPS,
                                ("xdut.aop", "xdut.aon"))
        self.assertEqual(req["batch"]["runner_version_check"], "enforce")
        self.assertNotIn("analysis", req)
        steps = [s["name"] for s in req["analysis_steps"]]
        self.assertEqual(steps, ["op", "nfull", "nhf", "nwhite", "ac"])
        der = {m["name"]: m["expr"] for m in req["measurements"]}
        self.assertEqual(der["vn_in_uv"], "nfull.onoise/ac.av_dc*1e6")
        self.assertIn("v(xdut.aop,xdut.aon) vd dec 20 1 1e9", req["analysis_steps"][1]["analysis"]["args"])
        self.assertEqual(req["analysis_steps"][4]["measurements"][0]["expr"], "mag(v(xdut.aop)-v(xdut.aon))[0]")

    def test_expected_corners_45(self):
        self.assertEqual(len(pvt.expected_corners(make_grid())), 45)
        self.assertIn("ss_-40c_2.97v", pvt.expected_corners(make_grid()))


if __name__ == "__main__":
    unittest.main()
