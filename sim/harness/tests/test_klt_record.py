"""PDK-free tests for the evidence-minting path (issue #142).

``sim/tools/klt_record.py`` turns raw per-leg ``klt sim`` values into the
derived quantities scored against the ratified bounds, and ``mk_klt_request.py``
builds the requests it consumes. Every record they mint is append-only, so a
silent arithmetic slip (population vs sample sigma, a sign flip in
``voa = -dv0/gain``) cannot be corrected later, only superseded. These tests
use synthetic inputs and the committed ``tb.json`` files only: no ``klt``, no
ngspice, no PDK, no network, and ``subprocess.Popen`` is mocked.
"""

from __future__ import annotations

import io
import json
import math
import os
import statistics
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SIM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SIM / "tools"))

import klt_record as kr  # noqa: E402
import mk_klt_request as mk  # noqa: E402
from harness import testbench as htb  # noqa: E402


def _report(*corners: tuple[str, str, dict]) -> dict:
    """(corner_id, status, {name: value}) -> a minimal klt sim report."""
    return {"corners": [
        {"corner_id": cid, "status": st,
         "measurements": [{"name": k, "value": v} for k, v in m.items()]}
        for cid, st, m in corners
    ]}


class CornerIdCollect(unittest.TestCase):
    def test_corner_id_plain_and_mc(self):
        self.assertEqual(kr.corner_id("tt/27C", 3.3), ("tt_27c_3.30v", ""))
        self.assertEqual(kr.corner_id("ss/-40C/mc7", 2.97), ("ss_-40c_2.97v", "mc7"))
        self.assertEqual(kr.corner_id("ff/125C", 3.63)[0], "ff_125c_3.63v")

    def test_collect_round_trip(self):
        rep = _report(("tt/27C/mc0", "pass", {"dv0": 1.0, "dv1": 2.0}),
                      ("tt/27C/mc1", "pass", {"dv0": 3.0, "dv1": None}))
        out, bad = kr.collect(rep, 3.3)
        self.assertEqual(bad, [])
        self.assertEqual(out, {"tt_27c_3.30v": {"mc0": {"dv0": 1.0, "dv1": 2.0},
                                                "mc1": {"dv0": 3.0}}})  # None dropped

    def test_collect_failed_leg_is_bad_not_data(self):
        rep = _report(("tt/27C", "pass", {"a": 1.0}), ("ss/125C", "error", {"a": 9.0}))
        out, bad = kr.collect(rep, 3.3)
        self.assertEqual(list(out), ["tt_27c_3.30v"])
        self.assertEqual(bad, [("ss/125C", "error")])

    def test_failed_leg_surfaces_in_problems(self):
        rep = _report(("tt/27C", "pass", {"onoise_total": 1e-3, "inoise_total": 1e-5, "av_dc": 10.0}),
                      ("ss/125C", "timeout", {}))
        leg = kr.collect(rep, 3.3)
        _, problems = kr.derive("comparator-preamp-noise", None, {"noise": leg, "ac": leg})
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("ss/125C -> timeout" in p for p in problems))


class DeriveOffsetMc(unittest.TestCase):
    CID = "tt_27c_3.30v"

    def _derive(self, draws):
        smp = {f"mc{i}": {"dv0": a, "dv1": b} for i, (a, b) in enumerate(draws)}
        return kr.derive("comparator-offset-mc", None, {"main": ({self.CID: smp}, [])})

    def test_population_sigma_3sigma_mean_and_gain(self):
        # gain = (dv1-dv0)/2mV per draw; voa = -dv0/gain.
        draws = [(-2e-3, 8e-3), (1e-3, 11e-3), (3e-3, 9e-3), (-1e-3, 5e-3)]
        res, problems = self._derive(draws)
        self.assertEqual(problems, [])
        gains = [(b - a) / 2e-3 for a, b in draws]
        voa = [-a / g for (a, _), g in zip(draws, gains)]
        d = res[self.CID]
        self.assertEqual(d["n_samples"], 4)
        self.assertAlmostEqual(d["sig_vos_mv"], statistics.pstdev(voa) * 1e3, places=12)
        self.assertAlmostEqual(d["vos_3sig_mv"], 3 * d["sig_vos_mv"], places=12)
        self.assertAlmostEqual(d["mean_vos_uv"], statistics.fmean(voa) * 1e6, places=9)
        self.assertAlmostEqual(d["av_mean"], statistics.fmean(gains), places=9)
        self.assertAlmostEqual(
            d["av_sigma_pct"], statistics.pstdev(gains) / statistics.fmean(gains) * 100, places=9)
        # Population, not sample: the two differ by sqrt(n/(n-1)) for n = 4.
        self.assertNotAlmostEqual(d["sig_vos_mv"], statistics.stdev(voa) * 1e3, places=6)
        self.assertAlmostEqual(
            d["sig_vos_mv"] * math.sqrt(4 / 3), statistics.stdev(voa) * 1e3, places=9)

    def test_known_two_point_sigma_and_sign(self):
        # Gain 10 for both draws; dv0 = -+1 mV -> voa = +-0.1 mV, pop sigma = 0.1 mV.
        res, _ = self._derive([(-1e-3, 19e-3), (1e-3, 21e-3)])
        d = res[self.CID]
        self.assertAlmostEqual(d["sig_vos_mv"], 0.1, places=9)
        self.assertAlmostEqual(d["vos_3sig_mv"], 0.3, places=9)
        self.assertAlmostEqual(d["mean_vos_uv"], 0.0, places=9)
        self.assertAlmostEqual(d["av_mean"], 10.0, places=9)
        self.assertAlmostEqual(d["av_sigma_pct"], 0.0, places=9)
        # Sign of voa = -dv0/gain: a single positive dv0 gives a negative offset.
        res, _ = self._derive([(1e-3, 21e-3)])
        self.assertAlmostEqual(res[self.CID]["mean_vos_uv"], -100.0, places=9)

    def test_only_corners_present_in_every_leg(self):
        smp = {"mc0": {"dv0": 0.0, "dv1": 2e-3}}
        res, _ = kr.derive("comparator-offset-mc", None,
                           {"main": ({"a": smp, "b": smp}, [])})
        self.assertEqual(sorted(res), ["a", "b"])


class DeriveOtherBenches(unittest.TestCase):
    def test_noise_referral(self):
        legs = {"noise": ({"c": {"": {"onoise_total": 2e-3, "inoise_total": 5e-6}}}, []),
                "ac": ({"c": {"": {"av_dc": 4.0}}}, [])}
        res, problems = kr.derive("comparator-preamp-noise", None, legs)
        self.assertEqual(problems, [])
        d = res["c"]
        self.assertAlmostEqual(d["vn_in_uv"], 2e-3 / 4.0 * 1e6)  # onoise / av_dc
        self.assertAlmostEqual(d["onoise_uv"], 2e3)
        self.assertAlmostEqual(d["inoise_band_uv"], 5.0)
        self.assertEqual(d["av_dc"], 4.0)

    def test_measure_eval_with_math_env_and_caret(self):
        tb = types.SimpleNamespace(measure={
            "td_ns": "td_a*1e9", "tau": "(td_c-td_b)/ln(10)", "p": "x^2 + sqrt(4)",
            "i_ua": "abs(i_stat)*1e6"})
        raw = {"c": {"": {"td_a": 1.2e-9, "td_b": 1.0, "td_c": 11.0, "x": 3.0, "i_stat": -2e-6}}}
        res, _ = kr.derive("comparator-regeneration", tb, {"main": (raw, [])})
        d = res["c"]
        self.assertAlmostEqual(d["td_ns"], 1.2)
        self.assertAlmostEqual(d["tau"], 10 / math.log(10))
        self.assertAlmostEqual(d["p"], 11.0)  # ^ -> **
        self.assertAlmostEqual(d["i_ua"], 2.0)

    def test_eval_is_sandboxed(self):
        tb = types.SimpleNamespace(measure={"bad": "__import__('os')"})
        with self.assertRaises(NameError):
            kr.derive("comparator-kickback", tb, {"main": ({"c": {"": {}}}, [])})

    def test_committed_tb_measure_evaluates(self):
        # The committed regeneration/kickback tb.json expressions evaluate on
        # synthetic ingredients (catches an expression/ingredient rename).
        for bench in ("comparator-regeneration", "comparator-kickback"):
            tb = htb.load(SIM / bench)
            names = set()
            for expr in tb.measure.values():
                names |= {t for t in __import__("re").findall(r"[A-Za-z_]\w*", expr)
                          if t not in kr.MATH}
            raw = {"c": {"": {n: 2.0 + i for i, n in enumerate(sorted(names))}}}  # distinct: no x/0
            res, _ = kr.derive(bench, tb, {"main": (raw, [])})
            self.assertEqual(set(res["c"]), set(tb.measure), bench)

    def test_power_uw(self):
        self.assertAlmostEqual(
            kr.power_uw("comparator-regeneration", "tt_27c_3.30v", {"i_static_ua": 100.0}), 330.0)
        self.assertIsNone(kr.power_uw("comparator-kickback", "tt_27c_3.30v", {"i_static_ua": 1.0}))


class DispatchGuard(unittest.TestCase):
    def _run(self, backend):
        env = {k: v for k, v in os.environ.items() if k != "KLT_SIM_BACKEND"}
        if backend is not None:
            env["KLT_SIM_BACKEND"] = backend
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(kr.subprocess, "Popen") as popen:
            try:
                kr.dispatch(Path(td), ["main-v3.30"])
            except SystemExit as e:
                return popen, e
            return popen, None

    def test_refuses_unset_local_and_other(self):
        for backend in (None, "", "local", "BATCH"):
            popen, exc = self._run(backend)
            self.assertIsNotNone(exc, backend)
            self.assertIn("refusing", str(exc.code))
            popen.assert_not_called()

    def test_batch_and_remote_submit(self):
        for backend in ("batch", "remote"):
            with tempfile.TemporaryDirectory() as td:
                work = Path(td)

                def fake(cmd, stdout, stderr):
                    stdout.write("{}")  # Popen truncated the report; klt wrote JSON
                    stdout.flush()
                    pr = mock.Mock()
                    pr.wait.return_value = 0
                    return pr

                env = dict(os.environ, KLT_SIM_BACKEND=backend)
                with mock.patch.dict(os.environ, env, clear=True), \
                        mock.patch.object(kr.subprocess, "Popen", side_effect=fake) as popen, \
                        redirect_stdout(io.StringIO()):
                    kr.dispatch(work, ["main-v3.30"])
                popen.assert_called_once()
                self.assertEqual(popen.call_args.args[0][:2], ["klt", "sim"])


class MkKltRequest(unittest.TestCase):
    def _mk(self, bench, *extra):
        with tempfile.TemporaryDirectory() as td:
            design = Path(td) / "design.ngspice"
            design.write_text("* fake PDK design include\n")
            fake_pdk = types.SimpleNamespace(design_include=design)
            argv = ["mk_klt_request.py", bench, str(Path(td) / "out"), *extra]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(mk.hpdk, "find_pdk", return_value=fake_pdk), \
                    redirect_stdout(io.StringIO()):
                rc = mk.main()
            out = Path(td) / "out"
            reqs = {p.name: json.loads(p.read_text()) for p in out.glob("request-*.json")}
            bodies = {p.name: p.read_text() for p in out.glob("body-*.spice")}
            return rc, reqs, bodies

    def test_offset_mc_seed_and_n_plumbed(self):
        tb = htb.load(SIM / "comparator-offset-mc")
        rc, reqs, bodies = self._mk("comparator-offset-mc", "--mc-n", "7")
        self.assertEqual(rc, 0)
        # One request (and body) per supply point, leg `main`.
        self.assertEqual(len(reqs), 3)
        self.assertEqual(len(bodies), 3)
        self.assertEqual(sorted(reqs), [f"request-main-v{v}.json" for v in ("2.97", "3.30", "3.63")])
        for req in reqs.values():
            self.assertEqual(req["monte_carlo"], {"n": 7, "seed": mk.OFFSET_MC_SEED, "vary": "mismatch"})
            self.assertEqual(req["analysis"], {"kind": "dc", "args": "vd 0 2m 2m"})
            self.assertEqual([m["name"] for m in req["measurements"]], ["dv0", "dv1"])
            self.assertEqual(req["engine"], "ngspice")
            self.assertEqual(req["corners"]["temperature_c"], [float(t) for t in tb.temperatures_c])
            self.assertEqual([c["name"] for c in req["corners"]["process"]],
                             [c.name for c in mk.hc.resolve_corners(list(tb.corners))])
        self.assertIn(".param vdd_val=3.3", bodies["body-v3.30.spice"])
        self.assertIn(".param vdd_val=2.97", bodies["body-v2.97.spice"])

    def test_mc_n_default(self):
        _, reqs, _ = self._mk("comparator-offset-mc")
        self.assertEqual(next(iter(reqs.values()))["monte_carlo"]["n"], mk.OFFSET_MC_N)

    def test_tran_bench_reads_tb_json(self):
        tb = htb.load(SIM / "comparator-regeneration")
        _, reqs, _ = self._mk("comparator-regeneration")
        self.assertEqual(len(reqs), 3)
        kind, args = tb.analyses[0].split(None, 1)
        for req in reqs.values():
            self.assertNotIn("monte_carlo", req)
            self.assertEqual(req["analysis"], {"kind": kind, "args": args})
            self.assertEqual(len(req["measurements"]), len(tb.analyses) - 1)
            self.assertTrue(all(m["spice"].startswith(".meas tran ") for m in req["measurements"]))

    def test_noise_bench_refused(self):
        with self.assertRaises(SystemExit):
            self._mk("comparator-preamp-noise")


def _req(procs=("tt", "ss"), temps=(27.0, 125.0), mc=None, meas=("dv0", "dv1")):
    r = {"corners": {"process": [{"name": p} for p in procs], "temperature_c": list(temps)},
         "measurements": [{"name": m} for m in meas]}
    if mc:
        r["monte_carlo"] = mc
    return r


MC2 = {"n": 2, "seed": 5, "vary": "mismatch"}


def _full_mc_report(req, vdd=3.3, mc=MC2, vals=None):
    vals = vals or {"dv0": 1e-3, "dv1": 21e-3}
    units = [(f"{p['name']}/{t:g}C/mc{i}", "pass", dict(vals))
             for p in req["corners"]["process"] for t in req["corners"]["temperature_c"]
             for i in range(mc["n"])]
    rep = _report(*units)
    rep["environment"] = {"monte_carlo": dict(mc)}
    return rep


class CoverageValidation(unittest.TestCase):
    def _check(self, rep, req=None, vdd=3.3):
        return kr.collect_checked(rep, req or _req(mc=MC2), vdd)

    def _codes(self, issues):
        return sorted({i.split(": ")[0].split()[-1] if ": " in i else i for i in issues})

    def test_complete_campaign_clean(self):
        req = _req(mc=MC2)
        out, bad, issues = self._check(_full_mc_report(req), req)
        self.assertEqual((bad, issues), ([], []))
        self.assertEqual(len(out), 4)
        self.assertEqual(sorted(out["tt_27c_3.30v"]), ["mc0", "mc1"])

    def test_complete_campaign_numerics_preserved(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=MC2)
        rep = _report(("tt/27C/mc0", "pass", {"dv0": -1e-3, "dv1": 19e-3}),
                      ("tt/27C/mc1", "pass", {"dv0": 1e-3, "dv1": 21e-3}))
        rep["environment"] = {"monte_carlo": MC2}
        out, _, issues = kr.collect_checked(rep, req, 3.3)
        self.assertEqual(issues, [])
        res, problems = kr.derive("comparator-offset-mc", None, {"main": (out, [])})
        self.assertEqual(problems, [])
        self.assertAlmostEqual(res["tt_27c_3.30v"]["sig_vos_mv"], 0.1, places=9)
        self.assertEqual(res["tt_27c_3.30v"]["n_samples"], 2)

    def test_duplicate_rejected_not_overwritten(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=MC2)
        rep = _report(("tt/27C/mc0", "pass", {"dv0": 1.0, "dv1": 2.0}),
                      ("tt/27C/mc0", "pass", {"dv0": 9.0, "dv1": 9.0}),
                      ("tt/27C/mc1", "pass", {"dv0": 1.0, "dv1": 2.0}))
        rep["environment"] = {"monte_carlo": MC2}
        out, _, issues = self._check(rep, req)
        self.assertTrue(any(i.startswith("DUPLICATE_UNIT") and "tt/27C/mc0" in i for i in issues))
        self.assertEqual(out["tt_27c_3.30v"]["mc0"]["dv0"], 1.0)  # first kept

    def test_missing_mc_draw_named(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=MC2)
        rep = _report(("tt/27C/mc0", "pass", {"dv0": 1.0, "dv1": 2.0}))
        rep["environment"] = {"monte_carlo": MC2}
        _, _, issues = self._check(rep, req)
        self.assertEqual(issues, ["MISSING_UNIT: tt_27c_3.30v/mc1 has no result"])

    def test_missing_corner_named(self):
        req = _req(mc=None)
        rep = _report(*[(f"{p}/{t:g}C", "pass", {"dv0": 1.0, "dv1": 2.0})
                        for p, t in (("tt", 27), ("tt", 125), ("ss", 27))])
        _, _, issues = self._check(rep, req)
        self.assertEqual(issues, ["MISSING_UNIT: ss_125c_3.30v has no result"])

    def test_unexpected_corner_and_sample(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=MC2)
        rep = _report(("tt/27C/mc0", "pass", {"dv0": 1.0, "dv1": 2.0}),
                      ("tt/27C/mc1", "pass", {"dv0": 1.0, "dv1": 2.0}),
                      ("tt/27C/mc2", "pass", {"dv0": 1.0, "dv1": 2.0}),
                      ("fs/85C/mc0", "pass", {"dv0": 1.0, "dv1": 2.0}))
        rep["environment"] = {"monte_carlo": MC2}
        _, _, issues = self._check(rep, req)
        self.assertEqual(sorted(i.split(" ")[1] for i in issues), ["fs/85C/mc0", "tt/27C/mc2"])
        self.assertTrue(all(i.startswith("UNEXPECTED_UNIT") for i in issues))

    def test_inconsistent_mc_declaration(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=MC2)
        rep = _full_mc_report(req, mc=MC2)
        rep["environment"]["monte_carlo"] = {"n": 2, "seed": 6, "vary": "mismatch"}
        _, _, issues = self._check(rep, req)
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0].startswith("MC_DECLARATION_MISMATCH: seed"))
        rep["environment"] = {}
        _, _, issues = self._check(rep, req)
        self.assertTrue(issues[0].startswith("MC_DECLARATION_MISMATCH"))

    def test_nonfinite_ingredient_named_and_excluded(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=None)
        for bad in (float("nan"), float("inf"), None):
            rep = _report(("tt/27C", "pass", {"dv0": bad, "dv1": 2.0}))
            out, _, issues = self._check(rep, req)
            self.assertEqual(len(issues), 1, issues)
            self.assertTrue(issues[0].startswith("NONFINITE_INGREDIENT: tt/27C dv0"))
            self.assertEqual(out, {})

    def test_failed_unit_is_failed_not_missing(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=None)
        _, bad, issues = self._check(_report(("tt/27C", "error", {})), req)
        self.assertEqual(bad, [("tt/27C", "error")])
        self.assertEqual(issues, ["FAILED_UNIT: tt/27C -> error"])

    def test_zero_gain_named_by_unit(self):
        smp = {"mc0": {"dv0": 1.0, "dv1": 1.0}, "mc1": {"dv0": 1.0, "dv1": 3.0}}
        res, problems = kr.derive("comparator-offset-mc", None, {"main": ({"c": smp}, [])})
        self.assertEqual(res, {})
        self.assertEqual(problems, ["ZERO_GAIN: c/mc0 gain = 0"])

    def test_zero_av_dc_noise(self):
        leg = ({"c": {"": {"onoise_total": 1.0, "inoise_total": 1.0, "av_dc": 0.0}}}, [])
        res, problems = kr.derive("comparator-preamp-noise", None, {"noise": leg, "ac": leg})
        self.assertEqual(res, {})
        self.assertTrue(problems[0].startswith("ZERO_GAIN: c"))

    def test_missing_ac_noise_leg_corner_reported(self):
        n = {"": {"onoise_total": 1e-3, "inoise_total": 1e-5, "av_dc": 10.0}}
        res, problems = kr.derive("comparator-preamp-noise", None,
                                  {"noise": ({"a": n, "b": n}, []), "ac": ({"a": n}, [])})
        self.assertEqual(sorted(res), ["a"])
        self.assertEqual(problems, ["MISSING_LEG_CORNER: leg ac has no result for b"])

    def test_expected_units_from_request(self):
        u = kr.expected_units(_req(mc=MC2), 2.97)
        self.assertEqual(len(u), 4)
        self.assertEqual(u["ss_125c_2.97v"], {"mc0", "mc1"})
        self.assertEqual(kr.expected_units(_req(), 3.3)["tt_27c_3.30v"], {""})


class MainCoverageGate(unittest.TestCase):
    """End-to-end ingestion of a --from-report dir (no klt, no ngspice)."""

    BENCH = "comparator-offset-mc"

    def _run(self, drop=0, empty=False, dup=False):
        tb = htb.load(SIM / self.BENCH)
        vdds = kr.hc.supply_points(tb.nominal_supply_v, tb.supply_tolerance)
        procs = [c.name for c in kr.hc.resolve_corners(list(tb.corners))]
        temps = [float(t) for t in tb.temperatures_c]
        mc = {"n": 3, "seed": 1, "vary": "mismatch"}
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            (work / "design.ngspice").write_text("*\n")
            for v in vdds:
                req = _req(procs=procs, temps=temps, mc=mc)
                rep = _full_mc_report(req, v, mc, {"dv0": 1e-3, "dv1": 21e-3})
                if empty:
                    rep["corners"] = []
                if drop:
                    rep["corners"] = rep["corners"][:-drop]
                if dup:
                    rep["corners"].append(dict(rep["corners"][0]))
                (work / f"body-v{v:.2f}.spice").write_text("*\n")
                (work / f"request-main-v{v:.2f}.json").write_text(json.dumps(req))
                (work / f"report-main-v{v:.2f}.json").write_text(json.dumps(rep))
            argv = ["klt_record.py", self.BENCH, "--from-report", str(work)]
            written = []
            err = io.StringIO()
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(kr, "REPO", Path(td)), \
                    mock.patch.object(kr, "SIM", Path(td) / "sim"), \
                    mock.patch.object(kr, "git_state", return_value=("abc1234", False)), \
                    mock.patch.object(kr.subprocess, "check_output", return_value="klt 0\n"), \
                    mock.patch.object(kr.hdut, "load", return_value=types.SimpleNamespace(
                        netlist=work / "design.ngspice", dut_id="x", provenance="p",
                        netlist_sha256="0" * 64, provenance_record=lambda: {})), \
                    mock.patch.object(htb, "load", return_value=tb), \
                    redirect_stdout(io.StringIO()), mock.patch.object(sys, "stderr", err):
                (Path(td) / "sim" / self.BENCH).mkdir(parents=True)
                try:
                    rc = kr.main()
                except SystemExit as e:
                    rc = e.code
                recs = list((Path(td) / "sim" / self.BENCH / "records").glob("*.json"))
                rec = json.loads(recs[0].read_text()) if recs else None
        return rc, rec, err.getvalue()

    def test_complete(self):
        rc, rec, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertTrue(rec["complete"])
        self.assertEqual(rec["points"], rec["expected_points"])

    def test_partial_inspectable_but_nonzero_and_flagged(self):
        rc, rec, _ = self._run(drop=1)
        self.assertEqual(rc, 1)
        self.assertFalse(rec["complete"])
        self.assertEqual(rec["outcome"], "incomplete")
        self.assertTrue(any(p.startswith("main-v3.63: MISSING_UNIT") for p in rec["problems"]))

    def test_duplicate_makes_incomplete(self):
        rc, rec, _ = self._run(dup=True)
        self.assertEqual(rc, 1)
        self.assertTrue(any("DUPLICATE_UNIT" in p for p in rec["problems"]))

    def test_empty_fails_cleanly(self):
        rc, rec, err = self._run(empty=True)
        self.assertIsInstance(rc, str)
        self.assertIn("EMPTY_RESULT", rc)
        self.assertIsNone(rec)


if __name__ == "__main__":
    unittest.main()
