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
from datetime import datetime
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


class DeriveOffsetTran(unittest.TestCase):
    """Whole-comparator transient-MC derivation (issue #157)."""

    CID = "tt_27c_3.30v"
    A = 20.0       # synthetic preamp gain
    VDROP = 1.2    # synthetic load drop, V

    def setUp(self):
        self.tb = htb.load(SIM / "comparator-offset-tran")
        P = self.tb.params
        self.t0, self.T = P["stair_t0_ns"] * 1e-9, P["stair_period_ns"] * 1e-9
        self.step = P["stair_step_mv"] * 1e-3
        self.v0 = P["stair_v0_mv"] * 1e-3

    def _draw(self, k, pre, phase_ns=1.0, cycle=None, dn_end=1.0):
        """One draw whose first 1-decision is staircase level k, preamp offset `pre`."""
        c = (k + int(self.tb.params["stair_lead_cycles"])) if cycle is None else cycle
        ve = -self.v0
        return {
            "t_trip": self.t0 + c * self.T + phase_ns * 1e-9,
            "dn_start": 0.0, "dn_end": dn_end,
            "dd_start": self.A * (self.v0 - pre), "dd_end": self.A * (ve - pre),
            "ap_start": 3.3 - self.VDROP,
        }

    def _derive(self, draws):
        smp = {f"mc{i}": d for i, d in enumerate(draws)}
        return kr.derive("comparator-offset-tran", self.tb, {"main": ({self.CID: smp}, [])})

    def test_trip_midpoint_preamp_offset_and_latch_difference(self):
        # level k=32 -> V = -5.04 + 0.16*32 = 0.08 mV; trip estimate = V - step/2 = 0.00 mV.
        # preamp offset 0.3 mV -> latch contribution = 0.0 - 0.3 = -0.3 mV.
        res, problems = self._derive([self._draw(32, 0.3e-3), self._draw(32, 0.3e-3)])
        self.assertEqual(problems, [])
        d = res[self.CID]
        self.assertAlmostEqual(d["mean_vos_tran_uv"], 0.0, places=6)
        self.assertAlmostEqual(d["mean_vos_pre_uv"], 300.0, places=6)
        self.assertAlmostEqual(d["mean_latch_uv"], -300.0, places=6)
        self.assertAlmostEqual(d["av_mean"], self.A, places=9)
        self.assertEqual(d["n_samples"], 2)

    def test_quantisation_variance_removed_in_quadrature(self):
        # Two adjacent levels: raw population sigma = step/2; the correction
        # subtracts step^2/12 from sigma^2.
        res, _ = self._derive([self._draw(30, 0.0), self._draw(31, 0.0)])
        d = res[self.CID]
        raw = self.step / 2
        self.assertAlmostEqual(d["sig_vos_tran_raw_mv"], raw * 1e3, places=9)
        want = math.sqrt(raw ** 2 - self.step ** 2 / 12) * 1e3
        self.assertAlmostEqual(d["sig_vos_tran_mv"], want, places=9)
        self.assertAlmostEqual(d["vos_3sig_tran_mv"], 3 * want, places=9)

    def test_rload_budget_scales_with_measured_drop_over_gain_and_adds_in_quadrature(self):
        res, _ = self._derive([self._draw(30, 0.0), self._draw(31, 0.0)])
        d = res[self.CID]
        P = self.tb.params
        rel = P["rmis_a_r_um"] / math.sqrt(P["rmis_w_um"] * P["rmis_l_um"])  # pair sigma(dR/R)
        self.assertAlmostEqual(d["vdrop_over_av_mv"], self.VDROP / self.A * 1e3, places=9)
        self.assertAlmostEqual(d["sig_rload_mv"], self.VDROP / self.A * rel * 1e3, places=9)
        self.assertAlmostEqual(d["sig_rload_cons_mv"], d["sig_rload_mv"] * P["rmis_conservative_factor"], places=9)
        self.assertAlmostEqual(d["sig_vos_total_mv"], math.hypot(d["sig_vos_tran_mv"], d["sig_rload_mv"]), places=9)
        self.assertAlmostEqual(
            d["vos_3sig_total_cons_mv"], 3 * math.hypot(d["sig_vos_tran_mv"], d["sig_rload_cons_mv"]), places=9)
        self.assertGreater(d["vos_3sig_total_cons_mv"], d["vos_3sig_total_mv"])

    def test_malformed_draws_are_named_problems_not_data(self):
        for draw, code in (
            (self._draw(0, 0.0), "TRIP_OUT_OF_RANGE"),                  # flipped at the lowest level
            (self._draw(10, 0.0, phase_ns=20.0), "LATE_FLIP"),          # crossed after the high phase
            (self._draw(10, 0.0, dn_end=0.2), "BAD_ENDPOINT_DECISION"),  # never settled high
        ):
            res, problems = self._derive([self._draw(10, 0.0), draw])
            self.assertEqual(res, {}, code)  # the whole PVT point is dropped
            self.assertTrue(any(p.startswith(code) for p in problems), (code, problems))

    def test_nonfinite_ingredient_is_named_problem_not_a_crash(self):
        nan = self._draw(10, 0.0)
        nan["t_trip"] = float("nan")
        res, problems = self._derive([self._draw(10, 0.0), nan])
        self.assertEqual(res, {})
        self.assertTrue(any(p.startswith("NONFINITE_INGREDIENT") for p in problems), problems)

    def test_committed_measure_names_and_scored_key(self):
        res, _ = self._derive([self._draw(30, 0.0), self._draw(31, 0.0)])
        self.assertEqual(set(res[self.CID]), set(self.tb.measure))
        self.assertIn(kr.SPEC["comparator-offset-tran"][1], self.tb.measure)
        self.assertEqual(kr.SPEC["comparator-offset-tran"][2:4], (15.0, 8.0))  # ratified bounds untouched


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

    def test_offset_tran_is_tran_monte_carlo_on_the_full_grid(self):
        tb = htb.load(SIM / "comparator-offset-tran")
        rc, reqs, bodies = self._mk("comparator-offset-tran", "--mc-n", "5")
        self.assertEqual(rc, 0)
        # Full 45-point grid (issue #200): 3 supply requests x 5 corners x 3 temps.
        self.assertEqual(sorted(reqs), [f"request-main-v{v}.json" for v in ("2.97", "3.30", "3.63")])
        req = reqs["request-main-v3.30.json"]
        for r in reqs.values():
            self.assertEqual(r["corners"], req["corners"])
        self.assertEqual(req["monte_carlo"], {"n": 5, "seed": mk.OFFSET_MC_SEED, "vary": "mismatch"})
        self.assertEqual(req["analysis"]["kind"], "tran")
        self.assertEqual([c["name"] for c in req["corners"]["process"]], ["tt", "ss", "ff", "fs", "sf"])
        self.assertEqual(req["corners"]["temperature_c"], [-40.0, 27.0, 125.0])
        self.assertEqual(len(req["measurements"]), len(tb.analyses) - 1)
        self.assertTrue(all(m["spice"].startswith(".meas tran ") for m in req["measurements"]))
        self.assertEqual(req["batch"]["capacity_wait_s"], mk.BATCH_CAPACITY_WAIT_S)
        # One OpenMP thread per unit (issue #157): the `.control` block sits
        # AFTER both includes so it precedes klt's own `.control ... tran`.
        lines = bodies["body-v3.30.spice"].splitlines()
        i = lines.index(".control")
        self.assertEqual(lines[i:i + 3], mk.SINGLE_THREAD_CONTROL)
        self.assertTrue(lines[i - 1].startswith(".include") and "tb_offset_tran" in lines[i - 1])

    def test_single_thread_pin_scoped_to_offset_tran(self):
        # Other benches' bodies (and so their existing records' bundles) are unchanged.
        for bench in ("comparator-offset-mc", "comparator-regeneration"):
            _, _, bodies = self._mk(bench, "--mc-n", "2")
            for body in bodies.values():
                self.assertNotIn(".control", body)
                self.assertNotIn("num_threads", body)

    def test_noise_bench_refused(self):
        with self.assertRaises(SystemExit):
            self._mk("comparator-preamp-noise")


# ---------------------------------------------------------------------------
# Source binding of replayed fleet evidence (issue #151). Fixtures: a request
# set generated by mk_klt_request.main() from the committed bench/DUT sources
# (fake PDK include, git state mocked), plus synthetic klt reports linked to
# it the way the executor links them (environment.netlist_sha256 and the
# include closure). No klt, no ngspice, no PDK; every record lands in a temp
# dir -- committed sim/ evidence is never touched.
# ---------------------------------------------------------------------------

BENCH = "comparator-kickback"
REPO = SIM.parent
ORIGIN = "a1b2c3d" + "0" * 33
INGEST = "1ngest0" + "f" * 33  # full SHA, the form klt_record.git_state returns


def _sha(path: Path) -> str:
    return mk.sha256_file(path)


def _generate(td: Path, *extra, dirty=(), bench=BENCH, repo=None, work="work") -> Path:
    """Request set + source bundle for `bench` in td/<work> (source A = the checkout).

    `repo` regenerates from a copied checkout (see _fake_checkout) instead."""
    design = td / "design.ngspice"
    design.write_text("* fake PDK design include\n")
    work = td / work
    argv = ["mk_klt_request.py", bench, str(work), *extra]
    if repo is not None:
        argv = [a.replace(str(REPO), str(repo)) for a in argv]
    with mock.patch.object(sys, "argv", argv), \
            mock.patch.object(mk.hpdk, "find_pdk", return_value=types.SimpleNamespace(design_include=design)), \
            mock.patch.object(mk, "git_state", return_value=(ORIGIN, list(dirty))), \
            redirect_stdout(io.StringIO()):
        if repo is None:
            assert mk.main() == 0
        else:
            with mock.patch.object(mk, "SIM", repo / "sim"), mock.patch.object(mk, "REPO", repo), \
                    mock.patch.object(mk.hdut, "DUT_CONFIG", repo / "sim/dut.json"), \
                    mock.patch.object(mk.hdut, "SIM_DIR", repo / "sim"):
                assert mk.main() == 0
    return work


def _bundle(work: Path) -> dict:
    return json.loads((work / mk.BUNDLE_NAME).read_text())


def _link_env(work: Path, b: dict, r: dict, closure=True, netlist_sha=True) -> dict:
    """The executor's report-to-input linkage for bundled request `r`."""
    env = {"engine_version": "46", "remote": {"job_id": f"job-{r['request']}"}}
    if netlist_sha:
        env["netlist_sha256"] = r["netlist_sha256"]
    if closure:
        env["netlist_closure"] = [{"sha256": h} for h in (
            r["netlist_sha256"], _sha(work / "design.ngspice"),
            b["dut"]["netlist_sha256"], b["testbench"]["netlist_sha256"])]
    return env


def _write_reports(work: Path, closure=True, netlist_sha=True) -> None:
    """Synthetic fleet reports linked to the bundle's bodies."""
    b = _bundle(work)
    tb = htb.load(work / b["testbench"]["staged_dir"])
    names = set()
    for expr in tb.measure.values():
        names |= {t for t in __import__("re").findall(r"[A-Za-z_]\w*", expr) if t not in kr.MATH}
    for n, r in b["requests"].items():
        req = json.loads((work / r["request"]).read_text())
        meas = [m["name"] for m in req["measurements"]]
        vals = {m: 2.0 + i for i, m in enumerate(sorted(set(meas) | names))}
        corners = [{"corner_id": f"{p['name']}/{t:g}C", "status": "pass",
                    "measurements": [{"name": m, "value": vals[m]} for m in vals]}
                   for p in req["corners"]["process"] for t in req["corners"]["temperature_c"]]
        env = _link_env(work, b, r, closure, netlist_sha)
        (work / f"report-{n}.json").write_text(json.dumps(
            {"corners": corners, "measurements": [{"name": m} for m in meas], "environment": env}))


def _committed_blob(commit, path):
    """git_blob stand-in: the originating commit holds today's checkout files."""
    p = REPO / path
    return p.read_bytes() if p.is_file() else None


def _ingest(td: Path, work: Path, *extra, blob=_committed_blob, ingest_dirty=False, repo=None, bench=BENCH,
            ingest_sha=INGEST):
    """-> (exit code or SystemExit message, record json or None, stdout)."""
    root = td / "evidence"
    (root / bench).mkdir(parents=True, exist_ok=True)
    argv = ["klt_record.py", bench, "--from-report", str(work), *extra]
    out = io.StringIO()
    with mock.patch.object(sys, "argv", argv), \
            mock.patch.object(kr, "SIM", root), \
            mock.patch.object(kr, "REPO", repo or REPO), \
            mock.patch.object(kr, "git_state", return_value=(ingest_sha, ingest_dirty)), \
            mock.patch.object(kr, "git_blob", side_effect=blob), \
            mock.patch.object(kr, "klt_version", return_value="klt 0.0"), \
            redirect_stdout(out):
        try:
            rc = kr.main()
        except SystemExit as e:
            rc = e.code
    recs = sorted((root / bench / "records").glob("*.json"))
    return rc, (json.loads(recs[-1].read_text()) if recs else None), out.getvalue()


def _fake_checkout(td: Path) -> Path:
    """A copy of the sources BENCH depends on, to be edited into source B."""
    root = td / "checkout"
    tbdir = f"sim/{BENCH}/testbench"
    for rel in ["design/comparator.spice", "sim/dut.json",
                "sim/dut/experiment_comparator_dr0004_cascode.spice"] + \
            [f"{tbdir}/{p.name}" for p in (REPO / tbdir).iterdir()]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes((REPO / rel).read_bytes())
    return root


class RequestSourceBundle(unittest.TestCase):
    def test_bundle_identifies_origin_and_hashes_staged_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            work = _generate(Path(td))
            b = _bundle(work)
            tb = htb.load(SIM / BENCH)
            self.assertEqual((b["schema"], b["version"]), (mk.BUNDLE_SCHEMA, mk.BUNDLE_VERSION))
            self.assertEqual(b["origin"], {"commit": ORIGIN, "dirty": False, "dirty_paths": [],
                                           "checked_paths": b["origin"]["checked_paths"]})
            self.assertEqual(b["dut"]["dut_id"], "comparator-dr0001")
            self.assertEqual(b["dut"]["netlist"], "design/comparator.spice")
            self.assertEqual(b["dut"]["params"], {"dut_ib": 1e-05, "dut_vcm": 1.65})
            self.assertEqual(b["testbench"]["netlist_sha256"], tb.netlist_sha256)
            self.assertEqual(b["testbench"]["manifest_sha256"], tb.manifest_sha256)
            for rel, h in b["staged"].items():
                self.assertEqual(_sha(work / rel), h, rel)
            for rel in ("design.ngspice", "sources/dut/comparator.spice", "sources/dut-binding.json",
                        f"sources/testbench/{tb.netlist.name}", "sources/testbench/tb.json"):
                self.assertIn(rel, b["staged"])
            self.assertEqual(len(b["requests"]), 3)

    def test_body_includes_staged_copies_not_checkout_paths(self):
        with tempfile.TemporaryDirectory() as td:
            work = _generate(Path(td))
            body = (work / "body-v3.30.spice").read_text()
            self.assertIn('.include "sources/dut/comparator.spice"', body)
            self.assertIn('.include "sources/testbench/tb_kickback.spice"', body)
            staged = _bundle(work)["staged"]
            self.assertEqual(mk.declared_source_shas(body),
                             {k: h for k, h in staged.items() if k.startswith("sources/")})
            self.assertNotIn(str(REPO), body)

    def test_selected_dut_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            b = _bundle(_generate(Path(td), "--dut", "comparator-dr0004-cascode-exp"))
            self.assertEqual(b["dut"]["selector"], "comparator-dr0004-cascode-exp")
            self.assertEqual(b["dut"]["key"], "comparator-dr0004-cascode-exp")
            self.assertEqual(b["dut"]["netlist"], "sim/dut/experiment_comparator_dr0004_cascode.spice")

    def test_dirty_coverage_names_experiment_and_binding_not_evidence(self):
        paths = mk.source_paths(BENCH, REPO / "sim/dut.json", REPO / "design/comparator.spice")
        for p in (f"sim/{BENCH}/testbench", "sim/dut.json", "design/comparator.spice", "sim/tools"):
            self.assertIn(p, paths)
        self.assertNotIn(f"sim/{BENCH}", paths)  # records/corners/snapshots are output
        self.assertTrue(all(not p.startswith(f"sim/{BENCH}/records") for p in paths))
        outside = mk.source_paths(BENCH, Path("/nonexistent/binding.json"), REPO / "design/comparator.spice")
        self.assertIn("/nonexistent/binding.json", outside)

    def test_git_state_dirty_detection(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                       GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL="/dev/null")

            def git(*a):
                kr.subprocess.check_call(["git", "-C", str(repo), *a], env=env,
                                         stdout=kr.subprocess.DEVNULL, stderr=kr.subprocess.DEVNULL)
            git("init", "-q")
            tbd = repo / "sim" / BENCH / "testbench"
            tbd.mkdir(parents=True)
            (tbd / "tb.json").write_text("{}")
            (repo / "sim" / "dut.json").write_text("{}")
            git("add", "-A")
            git("commit", "-qm", "x")
            paths = [f"sim/{BENCH}/testbench", "sim/dut.json"]
            with mock.patch.dict(os.environ, env):
                sha, dirty = mk.git_state(paths, repo=repo)
                self.assertEqual((len(sha), dirty), (40, []))
                (repo / "sim" / BENCH / "records").mkdir()
                (repo / "sim" / BENCH / "records" / "r.md").write_text("generated output")
                self.assertEqual(mk.git_state(paths, repo=repo)[1], [])  # evidence excluded
                (tbd / "tb.json").write_text('{"measure": {}}')           # manifest edit
                (tbd / "tb_new.spice").write_text("* untracked fragment")   # untracked
                (repo / "sim" / "dut.json").write_text('{"x": 1}')        # binding edit
                dirty = mk.git_state(paths, repo=repo)[1]
            self.assertEqual(sorted(dirty), sorted([f"sim/{BENCH}/testbench/tb.json",
                                                    f"sim/{BENCH}/testbench/tb_new.spice",
                                                    "sim/dut.json"]))


class ReplayIngest(unittest.TestCase):
    def test_verified_bundle_imports_with_origin_identity(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            rc, rec, _ = _ingest(td, work)
            self.assertEqual(rc, 0)
            b = _bundle(work)
            self.assertEqual(rec["commit"], ORIGIN[:7])
            self.assertTrue(rec["record_id"].endswith(ORIGIN[:7]))
            self.assertTrue(rec["citable"], rec["not_citable_reasons"])
            self.assertEqual(rec["source_bundle"]["origin_commit"], ORIGIN)
            self.assertEqual(rec["source_bundle"]["sha256"], _sha(work / mk.BUNDLE_NAME))
            self.assertEqual(rec["ingest"]["commit"], "1ngest0")  # existing short field unchanged
            self.assertEqual(rec["ingest"]["commit_full"], INGEST)
            self.assertEqual(rec["ingest"]["source_drift"], [])
            self.assertEqual(rec["dut"]["dut_netlist_sha256"], b["dut"]["netlist_sha256"])
            self.assertEqual(rec["testbench"]["netlist_sha256"], b["testbench"]["netlist_sha256"])
            self.assertEqual(rec["points"], 45)
            cdir = td / "evidence" / BENCH / "corners" / rec["record_id"]
            self.assertTrue((cdir / mk.BUNDLE_NAME).is_file())
            self.assertEqual(_sha(cdir / "sources/dut/comparator.spice"), b["dut"]["netlist_sha256"])
            md = (td / "evidence" / BENCH / "records" / f"{rec['record_id']}.md").read_text()
            self.assertIn("originating commit", md)
            self.assertNotIn("NOT CITABLE", md)

    def test_source_a_report_cannot_claim_source_b_after_clean_checkout_change(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)  # source A
            _write_reports(work)
            a = _bundle(work)
            b_repo = _fake_checkout(td)  # a later clean checkout: source B
            frag = b_repo / f"sim/{BENCH}/testbench/tb_kickback.spice"
            frag.write_text(frag.read_text() + "* source B edit\n")
            cfg = json.loads((b_repo / "sim/dut.json").read_text())
            cfg["duts"]["comparator-dr0001"]["params"]["dut_ib"] = 2e-05
            (b_repo / "sim/dut.json").write_text(json.dumps(cfg))
            rc, rec, out = _ingest(td, work, repo=b_repo)
            self.assertEqual(rc, 0)
            # The record names A -- the sources that produced the reports.
            self.assertEqual(rec["testbench"]["netlist_sha256"], a["testbench"]["netlist_sha256"])
            self.assertEqual(rec["dut"]["dut_params"], {"dut_ib": 1e-05, "dut_vcm": 1.65})
            self.assertNotIn(_sha(frag), json.dumps(rec))
            self.assertEqual(len(rec["ingest"]["source_drift"]), 2, rec["ingest"]["source_drift"])
            self.assertIn("source drift", out)

    def test_report_produced_from_other_sources_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            rep = json.loads((work / "report-main-v3.30.json").read_text())
            rep["environment"]["netlist_sha256"] = "b" * 64  # a body for source B
            (work / "report-main-v3.30.json").write_text(json.dumps(rep))
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("REPORT_SOURCE_MISMATCH"), rc)
            self.assertIsNone(rec)

    def test_report_closure_missing_bundled_fragment_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            tb_sha = _bundle(work)["testbench"]["netlist_sha256"]
            rep = json.loads((work / "report-main-v2.97.json").read_text())
            rep["environment"]["netlist_closure"] = [
                e for e in rep["environment"]["netlist_closure"] if e["sha256"] != tb_sha]
            (work / "report-main-v2.97.json").write_text(json.dumps(rep))
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("REPORT_SOURCE_MISMATCH"), rc)
            self.assertIn("testbench fragment", str(rc))
            self.assertIsNone(rec)

    def test_no_closure_report_from_source_a_not_citable_against_bundle_b(self):
        # Regression (Judge, PR #155): on the no-netlist_closure fallback the
        # body hash is the only link. Bundle B stages a DUT / fragment with the
        # SAME file names as A but different bytes; A's reports must not link.
        def dut(repo):
            with (repo / "design/comparator.spice").open("a") as f:
                f.write("* source B: same file name, different DUT bytes\n")

        def frag(repo):
            with (repo / f"sim/{BENCH}/testbench/tb_kickback.spice").open("a") as f:
                f.write("* source B: same file name, different fragment bytes\n")
        for name, edit in (("dut", dut), ("fragment", frag)):
            with self.subTest(name), tempfile.TemporaryDirectory() as td:
                td = Path(td)
                work_a = _generate(td, work="work-a")
                _write_reports(work_a, closure=False)
                repo_b = _fake_checkout(td)
                edit(repo_b)
                work_b = _generate(td, repo=repo_b, work="work-b")
                ba, bb = _bundle(work_a), _bundle(work_b)
                self.assertEqual(sorted(k for k in bb["staged"] if k.startswith("sources/")),
                                 sorted(k for k in ba["staged"] if k.startswith("sources/")))
                self.assertNotEqual(bb["staged"], ba["staged"])
                for n in bb["requests"]:
                    (work_b / f"report-{n}.json").write_bytes((work_a / f"report-{n}.json").read_bytes())
                rc, rec, _ = _ingest(td, work_b)
                self.assertTrue(str(rc).startswith("REPORT_SOURCE_MISMATCH"), rc)
                self.assertIsNone(rec)
                # Control: the same no-closure reports DO link to their own bundle A.
                rc, rec, _ = _ingest(td, work_a)
                self.assertEqual(rc, 0, rc)
                self.assertTrue(rec["citable"])
                self.assertEqual(len(rec["ingest"]["linkage_notes"]), 3)

    def test_body_must_declare_staged_source_shas(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            b = _bundle(work)
            body = work / "body-v3.30.spice"
            text = "\n".join(l for l in body.read_text().splitlines()
                             if not l.startswith(mk.SOURCE_SHA_PREFIX))
            body.write_text(text)
            # A consistent re-hash of the stripped body (bundle + report) must
            # still be refused: the body no longer binds the source content.
            h = _sha(body)
            b["staged"]["body-v3.30.spice"] = h
            for r in b["requests"].values():
                if r["netlist"] == "body-v3.30.spice":
                    r["netlist_sha256"] = h
            (work / mk.BUNDLE_NAME).write_text(json.dumps(b))
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("SOURCE_BUNDLE_INCONSISTENT"), rc)
            self.assertIn("source-sha256", str(rc))
            self.assertIsNone(rec)

    def test_unlinked_report_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work, netlist_sha=False)
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("REPORT_UNLINKED"), rc)
            self.assertIsNone(rec)

    def test_report_measurements_must_match_request(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            rep = json.loads((work / "report-main-v3.63.json").read_text())
            rep["measurements"] = rep["measurements"][1:]
            (work / "report-main-v3.63.json").write_text(json.dumps(rep))
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("REPORT_REQUEST_MISMATCH"), rc)
            self.assertIsNone(rec)

    def test_tampered_staged_source_or_request_refused_before_publishing(self):
        for rel in ("sources/dut/comparator.spice", "sources/testbench/tb.json",
                    "sources/testbench/tb_kickback.spice", "request-main-v3.30.json",
                    "body-v2.97.spice", "design.ngspice"):
            with self.subTest(rel=rel), tempfile.TemporaryDirectory() as td:
                td = Path(td)
                work = _generate(td)
                _write_reports(work)
                with (work / rel).open("a") as f:
                    f.write("\n" if rel.endswith(".json") else "* tampered\n")
                rc, rec, _ = _ingest(td, work)
                self.assertTrue(str(rc).startswith("STAGED_SOURCE_TAMPERED"), rc)
                self.assertIn(rel, str(rc))
                self.assertIsNone(rec)
                self.assertFalse((td / "evidence" / BENCH / "corners").exists())

    def test_missing_staged_source_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            (work / "sources/dut-binding.json").unlink()
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("STAGED_SOURCE_MISSING"), rc)
            self.assertIsNone(rec)

    def test_clean_claim_contradicted_for_staged_probe_fragment_refused(self):
        """Every staged testbench file (not just the .included fragment and
        tb.json) is checked against the claimed clean commit."""
        probe = "tb_vosprobe.spice"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            b = _bundle(work)
            self.assertIn(f"{b['testbench']['staged_dir']}/{probe}", b["staged"])

            def other(commit, path):
                data = _committed_blob(commit, path)
                return data + b"* differs at origin\n" if path.endswith(probe) else data
            rc, rec, _ = _ingest(td, work, blob=other)
            self.assertTrue(str(rc).startswith("SOURCE_COMMIT_MISMATCH"), rc)
            self.assertIsNone(rec)

    def test_probe_fragment_unreadable_at_commit_noncitable_not_refused(self):
        probe = "tb_vosprobe.spice"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            rc, rec, _ = _ingest(td, work, blob=lambda c, p: None if p.endswith(probe) else _committed_blob(c, p))
            self.assertEqual(rc, 0)
            self.assertFalse(rec["citable"])
            self.assertFalse(rec["reference"])

    def test_bundle_identity_edit_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            b = _bundle(work)
            b["dut"]["netlist_sha256"] = "c" * 64  # claim another DUT
            (work / mk.BUNDLE_NAME).write_text(json.dumps(b))
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("SOURCE_BUNDLE_INCONSISTENT"), rc)
            self.assertIsNone(rec)

    def test_clean_claim_contradicted_by_origin_commit_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)

            def other(commit, path):
                data = _committed_blob(commit, path)
                return data + b"* differs at origin\n" if path.endswith("tb_kickback.spice") else data
            rc, rec, _ = _ingest(td, work, blob=other)
            self.assertTrue(str(rc).startswith("SOURCE_COMMIT_MISMATCH"), rc)
            self.assertIsNone(rec)

    def test_unverifiable_origin_dirty_origin_or_dirty_tools_not_citable(self):
        cases = {"unverifiable": dict(blob=lambda c, p: None),
                 "tools": dict(ingest_dirty=True)}
        for name, kw in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as td:
                td = Path(td)
                work = _generate(td)
                _write_reports(work)
                rc, rec, out = _ingest(td, work, **kw)
                self.assertEqual(rc, 0)
                self.assertTrue(rec["complete"])  # complete grid: only citability fails
                self.assertFalse(rec["citable"])
                self.assertFalse(rec["reference"])
                self.assertIn("NOT CITABLE", out)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, dirty=[f"sim/{BENCH}/testbench/tb.json"])
            _write_reports(work)
            rc, rec, _ = _ingest(td, work)
            self.assertEqual(rc, 0)
            self.assertTrue(rec["dirty"])
            self.assertTrue(rec["complete"])
            self.assertFalse(rec["citable"])
            self.assertFalse(rec["reference"])
            md = (td / "evidence" / BENCH / "records" / f"{rec['record_id']}.md").read_text()
            self.assertIn("NOT CITABLE", md)
            self.assertIn(f"sim/{BENCH}/testbench/tb.json", md)

    def test_ingest_dut_selection_must_match_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            rc, rec, _ = _ingest(td, work, "--dut", "comparator-dr0004-cascode-exp")
            self.assertTrue(str(rc).startswith("DUT_SELECTION_MISMATCH"), rc)
            self.assertIsNone(rec)
            rc, rec, _ = _ingest(td, work, "--dut", "comparator-dr0001")
            self.assertEqual(rc, 0)

    def test_legacy_workdir_refused_or_noncitable_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td)
            _write_reports(work)
            (work / mk.BUNDLE_NAME).unlink()
            rc, rec, _ = _ingest(td, work)
            self.assertTrue(str(rc).startswith("LEGACY_WORKDIR_UNBOUND"), rc)
            self.assertIsNone(rec)
            rc, rec, out = _ingest(td, work, "--legacy-diagnostic")
            self.assertEqual(rc, 3)
            self.assertIsNone(rec)
            self.assertIn("NON-CITABLE", out)
            self.assertFalse((td / "evidence" / BENCH / "corners").exists())


class CheckoutDrift(unittest.TestCase):
    """Each source the bundle binds is detected when only it changes."""

    def _drift(self, edit, *gen):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            b = _bundle(_generate(td, *gen))
            repo = _fake_checkout(td)
            self.assertEqual(kr.checkout_drift(b, repo), [])
            edit(repo)
            return kr.checkout_drift(b, repo)

    @staticmethod
    def _edit_cfg(repo, fn):
        cfg = json.loads((repo / "sim/dut.json").read_text())
        fn(cfg)
        (repo / "sim/dut.json").write_text(json.dumps(cfg))

    def test_fragment(self):
        def edit(repo):
            with (repo / f"sim/{BENCH}/testbench/tb_kickback.spice").open("a") as f:
                f.write("* edit\n")
        d = self._drift(edit)
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0].startswith("testbench fragment"))

    def test_manifest(self):
        def edit(repo):
            p = repo / f"sim/{BENCH}/testbench/tb.json"
            m = json.loads(p.read_text())
            m["measure"]["kick_1k_peak_mv"] += "*1.0"
            p.write_text(json.dumps(m))
        d = self._drift(edit)
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0].startswith("testbench manifest"))

    def test_binding_params(self):
        d = self._drift(lambda r: self._edit_cfg(
            r, lambda c: c["duts"]["comparator-dr0001"]["params"].update(dut_vcm=1.5)))
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0].startswith("DUT binding entry"))

    def test_selected_dut(self):
        d = self._drift(lambda r: self._edit_cfg(
            r, lambda c: c.update(active="comparator-dr0004-cascode-exp")))
        self.assertTrue(d[0].startswith("selected DUT"), d)

    def test_dut_netlist(self):
        def edit(repo):
            with (repo / "design/comparator.spice").open("a") as f:
                f.write("* edit\n")
        d = self._drift(edit)
        self.assertEqual(d, ["DUT netlist `design/comparator.spice`"])

    def test_explicit_selection_ignores_active(self):
        d = self._drift(lambda r: self._edit_cfg(r, lambda c: c.update(active="comparator-dr0001-layout")),
                        "--dut", "comparator-dr0004-cascode-exp")
        self.assertEqual(d, [])


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
        self.assertNotIn("mc0", out.get("tt_27c_3.30v", {}))  # neither copy trusted
        self.assertFalse(any(i.startswith("MISSING_UNIT") for i in issues))

    def _one(self, *units):
        req = _req(procs=("tt",), temps=(27.0,), mc=None, meas=("x",))
        return kr.collect_checked(_report(*units), req, 3.3)

    def test_alias_duplicate_rejected_either_order(self):
        a, b = ("tt/27C", "pass", {"x": 1}), ("tt/27.0C", "pass", {"x": 99})
        for units in ((a, b), (b, a)):
            out, _, issues = self._one(*units)
            self.assertEqual(self._codes(issues), ["DUPLICATE_UNIT"], issues)
            self.assertEqual(out, {})

    def test_exact_duplicate_rejected(self):
        a = ("tt/27C", "pass", {"x": 1})
        out, _, issues = self._one(a, a)
        self.assertEqual(self._codes(issues), ["DUPLICATE_UNIT"], issues)
        self.assertEqual(out, {})
        out, _, issues = self._one(a, a, a)
        self.assertEqual(out, {})

    def test_repeated_ingredient_rejected(self):
        for ms in ([("x", 1), ("x", 99)], [("x", None), ("x", 5)], [("x", 5), ("x", None)]):
            rep = {"corners": [{"corner_id": "tt/27C", "status": "pass",
                                "measurements": [{"name": n, "value": v} for n, v in ms]}]}
            req = _req(procs=("tt",), temps=(27.0,), meas=("x",))
            out, _, issues = kr.collect_checked(rep, req, 3.3)
            self.assertEqual(self._codes(issues), ["DUPLICATE_INGREDIENT"], issues)
            self.assertEqual(out, {})

    def test_repeated_unrequired_name_tolerated(self):
        rep = {"corners": [{"corner_id": "tt/27C", "status": "pass", "measurements": [
            {"name": "x", "value": 1}, {"name": "y", "value": 1}, {"name": "y", "value": 2}]}]}
        out, _, issues = kr.collect_checked(rep, _req(procs=("tt",), temps=(27.0,), meas=("x",)), 3.3)
        self.assertEqual(issues, [])

    def test_distinct_mc_samples_not_duplicates(self):
        req = _req(procs=("tt",), temps=(27.0,), mc=MC2)
        out, _, issues = self._check(_full_mc_report(req), req)
        self.assertEqual(issues, [])
        self.assertEqual(sorted(out["tt_27c_3.30v"]), ["mc0", "mc1"])

    def test_malformed_corner_ids_named(self):
        for raw in ("tt", "tt/xC", "tt/nanC", "/27C", "", None, 5):
            out, _, issues = self._one((raw, "pass", {"x": 1}))
            self.assertIn("MALFORMED_CORNER_ID", self._codes(issues), (raw, issues))
            self.assertEqual(out, {})

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
        """A real (mk_klt_request-generated) bundled request set with n = 3
        draws, plus synthetic MC reports linked to it; ingestion therefore
        passes the #151 source checks and exercises the #152 coverage gate."""
        mc = {"n": 3, "seed": mk.OFFSET_MC_SEED, "vary": "mismatch"}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, "--mc-n", "3", bench=self.BENCH)
            b = _bundle(work)
            for n, r in b["requests"].items():
                req = json.loads((work / r["request"]).read_text())
                self.assertEqual(req["monte_carlo"], mc)
                rep = _full_mc_report(req, r["vdd"], mc, {"dv0": 1e-3, "dv1": 21e-3})
                if empty:
                    rep["corners"] = []
                if drop:
                    rep["corners"] = rep["corners"][:-drop]
                if dup:
                    rep["corners"].append(dict(rep["corners"][0]))
                rep["measurements"] = [{"name": x["name"]} for x in req["measurements"]]
                rep["environment"].update(_link_env(work, b, r))
                (work / f"report-{n}.json").write_text(json.dumps(rep))
            err = io.StringIO()
            with mock.patch.object(sys, "stderr", err):
                rc, rec, _ = _ingest(td, work, bench=self.BENCH)
        return rc, rec, err.getvalue()

    def test_expected_points_from_bundled_requests(self):
        rc, rec, _ = self._run()
        tb = htb.load(SIM / self.BENCH)
        n_proc = len(kr.hc.resolve_corners(list(tb.corners)))
        n_vdd = len(kr.hc.supply_points(tb.nominal_supply_v, tb.supply_tolerance))
        self.assertEqual(rec["expected_points"], n_proc * len(tb.temperatures_c) * n_vdd)

    def test_complete_and_citable_is_reference(self):
        rc, rec, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertTrue(rec["complete"] and rec["citable"])
        self.assertTrue(rec["reference"])

    def test_incomplete_is_never_reference(self):
        rc, rec, _ = self._run(drop=1)
        self.assertTrue(rec["citable"])
        self.assertFalse(rec["reference"])

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


class _FrozenClock:
    """`datetime` stand-in for klt_record: every record id gets the same stamp."""

    @staticmethod
    def now(tz=None):
        return datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=tz)


def _cm_index_work(td: Path, n: int = 2) -> Path:
    """A generated common-mode index request set with clean synthetic reports:
    every requested draw carries all 18 values, coordinates read back exactly."""
    work = _generate(td, "--mc-n", str(n), bench=mk.CM_INDEX_BENCH)
    b = _bundle(work)
    vals = []
    for i, (label, (vcmd, vd, _)) in enumerate(mk.CM_WINDOW_POINTS.items()):
        dv = 1e-4 * (i // 2 + 1) + (50e-3 if vd else 0.0)
        vals += [{"name": f"dv_{label}", "value": dv}, {"name": f"xcm_{label}", "value": vcmd},
                 {"name": f"xvd_{label}", "value": vd}]
    for name, r in b["requests"].items():
        req = json.loads((work / r["request"]).read_text())
        corners = [{"corner_id": f"{p['name']}/{t:g}C/mc{i}", "status": "pass",
                    "monte_carlo": {"sample_index": i},
                    "measurements": [dict(v, value=v["value"] * (1 + 0.1 * i)) if v["name"].startswith("dv_")
                                     else dict(v) for v in vals]}
                   for p in req["corners"]["process"] for t in req["corners"]["temperature_c"] for i in range(n)]
        env = _link_env(work, b, r)
        env["monte_carlo"] = dict(req["monte_carlo"])
        env["remote"] = {"runner_klt_version": "0.5.0", "runner_compatibility": "match"}
        (work / f"report-{name}.json").write_text(json.dumps(
            {"corners": corners, "measurements": [{"name": m["name"]} for m in req["measurements"]],
             "environment": env}))
    return work


class CmIndexReplay(unittest.TestCase):
    """Issue #254: a successful common-mode replay through `mint_cm_index`,
    sharing the archive/provenance helpers with the scored path."""

    def test_clean_replay_is_complete_unscored_reference(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _cm_index_work(td)
            rc, rec, _ = _ingest(td, work, bench=mk.CM_INDEX_BENCH)
            self.assertEqual(rc, 0)
            self.assertTrue(rec["complete"] and rec["citable"] and rec["reference"] and rec["full_coverage"])
            self.assertEqual((rec["scored"], rec["verdict"]), (False, "Unknown"))
            self.assertNotIn("spec_row", rec)
            self.assertEqual(rec["not_citable_reasons"], [])
            self.assertEqual(rec["points"], rec["expected_points"])
            exp = td / "evidence" / mk.CM_INDEX_BENCH
            cdir = exp / "corners" / rec["record_id"]
            b = _bundle(work)
            want = {mk.BUNDLE_NAME, "design.ngspice", mk.SOURCES_DIR} | \
                {f"body-v{r['vdd']:.2f}.spice" for r in b["requests"].values()} | \
                {f"{k}-{n}.json" for n in b["requests"] for k in ("request", "report")}
            self.assertEqual({p.name for p in cdir.iterdir()}, want)
            self.assertEqual(rec["source_bundle"]["sha256"], _sha(cdir / mk.BUNDLE_NAME))
            snap = (exp / "netlist-snapshots" / f"{rec['record_id']}.spice").read_text()
            self.assertIn("\n* ---- testbench fragment ----\n", snap)
            self.assertEqual(list(rec)[:9], ["record_id", "bench", "commit", "dirty", "citable",
                                             "not_citable_reasons", "dut", "testbench", "source_bundle"])
            self.assertEqual(list(rec)[9:12], ["executor", "monte_carlo", "ingest"])

    def test_dirty_tools_replay_is_not_citable(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rc, rec, _ = _ingest(td, _cm_index_work(td), bench=mk.CM_INDEX_BENCH, ingest_dirty=True)
            self.assertEqual(rc, 0)
            self.assertFalse(rec["citable"] or rec["reference"])
            self.assertEqual(rec["not_citable_reasons"],
                             ["derivation tooling (sim/tools, sim/harness) dirty at ingest commit 1ngest0"])


class ReproduceGuidance(unittest.TestCase):
    """Issue #272: both record writers share one bundle-derived formatter, so a
    non-default MC count / DUT selector survives into the Reproduce bullet."""

    DUT = "comparator-dr0004-cascode-exp"

    def _md(self, td, rec, bench):
        return (td / "evidence" / bench / "records" / f"{rec['record_id']}.md").read_text()

    def _line(self, md):
        return next(l for l in md.splitlines() if l.startswith("- **Reproduce**"))

    def test_common_mode_writer_preserves_n_and_custom_dut(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, "--mc-n", "3", "--dut", self.DUT, bench=mk.CM_INDEX_BENCH)
            self.assertEqual(_bundle(work)["parameters"]["mc_n"], 3)
            # reuse the synthetic reports of the default-DUT helper for N=3
            tmp = td / "other"
            tmp.mkdir()
            ref = _cm_index_work(tmp, n=3)
            for f in ref.glob("report-*.json"):
                req = json.loads((work / f.name.replace("report-", "request-")).read_text())
                rep = json.loads(f.read_text())
                rep["environment"] = _link_env(work, _bundle(work), _bundle(work)["requests"][f.stem[7:]])
                rep["environment"]["monte_carlo"] = dict(req["monte_carlo"])
                rep["environment"]["remote"] = {"runner_klt_version": "0.5.0", "runner_compatibility": "match"}
                (work / f.name).write_text(json.dumps(rep))
            rc, rec, _ = _ingest(td, work, bench=mk.CM_INDEX_BENCH)
            self.assertEqual(rc, 0)
            line = self._line(self._md(td, rec, mk.CM_INDEX_BENCH))
            self.assertIn("--mc-n 3", line)
            self.assertNotIn("200", line)
            self.assertIn(f"--dut {self.DUT}", line)
            self.assertIn(ORIGIN, line)
            self.assertIn(INGEST, line)
            self.assertIn("derivation tooling ran at the ingest commit", line)

    def test_scored_writer_preserves_custom_dut_and_both_commits(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, "--dut", self.DUT)
            _write_reports(work)
            rc, rec, _ = _ingest(td, work)
            self.assertEqual(rc, 0)
            line = self._line(self._md(td, rec, BENCH))
            self.assertIn(f"--dut {self.DUT}", line)
            self.assertIn(ORIGIN, line)
            self.assertIn(INGEST, line)
            self.assertIn("derivation tooling ran at the ingest commit", line)

    def test_same_commit_has_no_replay_split(self):
        """Origin and ingest at one commit (git_state mocked in production form,
        full SHA): both writers print it in full and omit the split note."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, "--dut", self.DUT)
            _write_reports(work)
            rc, rec, _ = _ingest(td, work, ingest_sha=ORIGIN)
            self.assertEqual(rc, 0)
            self.assertEqual(rec["ingest"]["commit"], ORIGIN[:7])
            self.assertEqual(rec["ingest"]["commit_full"], ORIGIN)
            line = self._line(self._md(td, rec, BENCH))
            self.assertIn(f"origin commit `{ORIGIN}`; ingested at commit `{ORIGIN}`", line)
            self.assertNotIn("derivation tooling ran", line)
            self.assertNotIn("check out the origin commit", line)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rc, rec, _ = _ingest(td, _cm_index_work(td), bench=mk.CM_INDEX_BENCH, ingest_sha=ORIGIN)
            self.assertEqual(rc, 0)
            line = self._line(self._md(td, rec, mk.CM_INDEX_BENCH))
            self.assertIn(f"ingested at commit `{ORIGIN}`", line)
            self.assertNotIn("derivation tooling ran", line)

    def test_formatter_legacy_short_ingest_sha(self):
        """A record dict without the full ingest SHA falls back to the short one,
        matched by prefix rather than always reported as a split."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, "--mc-n", "3", bench="comparator-offset-mc")
            b = _bundle(work)
            tb = htb.load(work / b["testbench"]["staged_dir"])
            line = kr.reproduce_line("comparator-offset-mc", b, {"rid": "RID", "ingest_sha": ORIGIN[:7]}, tb)
            self.assertNotIn("derivation tooling ran", line)
            line = kr.reproduce_line("comparator-offset-mc", b, {"rid": "RID", "ingest_sha": "1ngest0"}, tb)
            self.assertIn("derivation tooling ran", line)

    def test_formatter_preserves_n3_and_flags_nondefault_grid(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = _generate(td, "--mc-n", "3", bench="comparator-offset-mc")
            b = _bundle(work)
            tb = htb.load(work / b["testbench"]["staged_dir"])
            r = {"rid": "RID", "ingest_sha": ORIGIN[:7], "ingest_commit_full": ORIGIN}
            line = kr.reproduce_line("comparator-offset-mc", b, r, tb)
            self.assertIn("--mc-n 3", line)
            self.assertNotIn("--mc-n 200", line)
            self.assertNotIn("differs", line)
            self.assertNotIn("derivation tooling ran", line)  # same commit: no replay split
            b["parameters"]["temperatures_c"] = [27.0]
            line = kr.reproduce_line("comparator-offset-mc", b, r, tb)
            self.assertIn("differs from the CLI defaults", line)
            self.assertIn("corners/RID/request-*.json", line)
            self.assertIn(mk.BUNDLE_NAME, line)
            self.assertIn("design.ngspice", line)
            self.assertIn("--mc-n 3", line)


class ExistingRecordRefused(unittest.TestCase):
    """Both writers create the corner dir exclusively: an existing record id
    is refused, never overwritten (issue #254 keeps this for both paths)."""

    def _twice(self, bench, work_fn):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = work_fn(td)
            with mock.patch.object(kr, "datetime", _FrozenClock):
                rc, _rec, _ = _ingest(td, work, bench=bench)
                self.assertIn(rc, (0, 1))
                before = sorted(p.relative_to(td) for p in (td / "evidence").rglob("*"))
                with self.assertRaises(FileExistsError):
                    _ingest(td, work, bench=bench)
            self.assertEqual(sorted(p.relative_to(td) for p in (td / "evidence").rglob("*")), before)

    def test_scored_path(self):
        def work_fn(td):
            work = _generate(td)
            _write_reports(work)
            return work
        self._twice(BENCH, work_fn)

    def test_common_mode_path(self):
        self._twice(mk.CM_INDEX_BENCH, _cm_index_work)


class KickbackBothNodes(unittest.TestCase):
    """#160: the row-facing kickback peak covers BOTH 1 kohm input nodes."""

    RAW = {"ad_pos": 4e-3, "ad_neg": -3e-3, "adn_pos": 2e-3, "adn_neg": -2e-3}

    def _derive(self, raw):
        tb = htb.load(SIM / "comparator-kickback")
        names = set()
        for expr in tb.measure.values():
            names |= {t for t in __import__("re").findall(r"[A-Za-z_]\w*", expr) if t not in kr.MATH}
        full = {n: 2.0 + i for i, n in enumerate(sorted(names))}
        full.update(raw)
        return kr.derive("comparator-kickback", tb, {"main": ({"c": {"": full}}, [])})

    def test_aggregate_is_max_of_both_nodes(self):
        res, problems = self._derive(self.RAW)
        self.assertEqual(problems, [])
        d = res["c"]
        self.assertAlmostEqual(d["kick_1k_pnode_peak_mv"], 4.0)
        self.assertAlmostEqual(d["kick_1k_nnode_peak_mv"], 2.0)
        self.assertAlmostEqual(d["kick_1k_peak_mv"], 4.0)

    def test_negative_node_larger_sets_the_aggregate(self):
        raw = dict(self.RAW, adn_pos=1e-3, adn_neg=-7e-3)  # negative node worse than positive
        res, problems = self._derive(raw)
        self.assertEqual(problems, [])
        d = res["c"]
        self.assertAlmostEqual(d["kick_1k_nnode_peak_mv"], 7.0)
        self.assertGreater(d["kick_1k_nnode_peak_mv"], d["kick_1k_pnode_peak_mv"])
        self.assertAlmostEqual(d["kick_1k_peak_mv"], 7.0)  # cannot ignore the negative node
        self.assertEqual(kr.node_coverage(res), "both")
        self.assertIn("1/1 corners", kr.node_coverage_line(res))

    def test_positive_node_value_unchanged_vs_historical_definition(self):
        res, _ = self._derive(self.RAW)
        d = res["c"]
        self.assertAlmostEqual(d["kick_1k_pnode_peak_mv"], max(abs(self.RAW["ad_pos"]), abs(self.RAW["ad_neg"])) * 1e3)

    def test_negative_node_ingredients_are_requested_and_validated(self):
        tb = htb.load(SIM / "comparator-kickback")
        cards = "\n".join(tb.analyses)
        self.assertIn("meas tran adn_pos max v(adn)", cards)
        self.assertIn("meas tran adn_neg min v(adn)", cards)
        self.assertIn("v(ana)-v(asn)", tb.netlist.read_text())
        # missing / non-finite node measurement fails validation (no record cell)
        req = _req(meas=("ad_pos", "ad_neg", "adn_pos", "adn_neg"))
        for bad in (None, float("nan"), float("inf")):
            vals = {"ad_pos": 1e-3, "ad_neg": -1e-3, "adn_pos": 1e-3, "adn_neg": bad}
            rep = {"corners": [{"corner_id": "tt/27C", "status": "pass",
                                "measurements": [{"name": k, "value": v} for k, v in vals.items()]}]}
            req1 = dict(req, corners={"process": [{"name": "tt"}], "temperature_c": [27.0]})
            out, _bad, issues = kr.collect_checked(rep, req1, 3.3)
            self.assertEqual(out, {}, bad)
            self.assertTrue(any("adn_neg" in i for i in issues), (bad, issues))

    def test_legacy_positive_only_record_is_partial(self):
        legacy = {"c": {"kick_1k_peak_mv": 7.6, "kick_1k_pos_mv": 7.6}}
        self.assertEqual(kr.node_coverage(legacy), "positive-only")
        self.assertIn("PARTIAL", kr.node_coverage_line(legacy))


if __name__ == "__main__":
    unittest.main()


class DerivedValidation(unittest.TestCase):
    """#154: derived outputs are validated like the raw ingredients."""

    def _kick(self, raw_by_cid, measure):
        tb = types.SimpleNamespace(measure=measure)
        legs = {"main": ({cid: {"": v} for cid, v in raw_by_cid.items()}, [])}
        return kr.derive("comparator-kickback", tb, legs)

    def test_finite_inputs_unchanged(self):
        res, problems = self._kick({"c": {"a": 2.0, "b": 4.0}}, {"r": "a / b", "s": "sqrt(b)"})
        self.assertEqual(problems, [])
        self.assertEqual(res, {"c": {"r": 0.5, "s": 2.0}})

    def test_overflow_in_scaling_is_nonfinite_derived(self):
        leg = ({"c": {"": {"onoise_total": 1e305, "inoise_total": 1.0, "av_dc": 10.0}}}, [])
        res, problems = kr.derive("comparator-preamp-noise", None, {"noise": leg, "ac": leg})
        self.assertEqual(res, {})
        self.assertTrue(any(p.startswith("NONFINITE_DERIVED: c onoise_uv") for p in problems), problems)
        self.assertTrue(any("vn_in_uv" in p for p in problems))

    def test_overflow_exception_named_with_corner_and_measurement(self):
        res, problems = self._kick({"c": {"a": 1e308}}, {"big": "a ** 2"})
        self.assertEqual(res, {})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("DERIVE_ERROR: c big: OverflowError"), problems)

    def test_arithmetic_errors_do_not_hide_other_corners(self):
        res, problems = self._kick(
            {"bad1": {"a": 1.0, "b": 0.0}, "good": {"a": 1.0, "b": 2.0}, "bad2": {"a": -4.0, "b": 1.0}},
            {"ratio": "a / b", "root": "sqrt(a)"},
        )
        self.assertEqual(sorted(res), ["good"])
        text = "\n".join(problems)
        self.assertIn("DERIVE_ERROR: bad1 ratio: ZeroDivisionError", text)
        self.assertIn("DERIVE_ERROR: bad2 root: ValueError", text)

    def test_all_outputs_of_a_bad_corner_are_reported(self):
        _, problems = self._kick({"c": {"a": 1.0, "b": 0.0}}, {"x": "a / b", "y": "1 / b"})
        self.assertEqual(len(problems), 2)

    def test_offset_mc_overflow_and_zero_mean_gain(self):
        smp = {"mc0": {"dv0": 1e306, "dv1": -1e306}, "mc1": {"dv0": 0.0, "dv1": 1.0}}
        res, problems = kr.derive("comparator-offset-mc", None, {"main": ({"c": smp}, [])})
        self.assertEqual(res, {})
        self.assertTrue(problems and all(p.startswith(("NONFINITE_DERIVED: c", "DERIVE_ERROR: c")) for p in problems))
        # gains +g and -g: finite draws but mean gain is exactly 0
        smp = {"mc0": {"dv0": 0.0, "dv1": 1.0}, "mc1": {"dv0": 0.0, "dv1": -1.0}}
        res, problems = kr.derive("comparator-offset-mc", None, {"main": ({"c": smp}, [])})
        self.assertEqual(res, {})
        self.assertTrue(any(p.startswith("DERIVE_ERROR: c av_sigma_pct: ZeroDivisionError") for p in problems))

    def test_bad_corner_cannot_be_complete(self):
        # main() requires `not problems and len(derived) == expected`
        res, problems = self._kick({"c": {"a": 1.0, "b": 0.0}}, {"x": "a / b"})
        self.assertTrue(problems or len(res) < 1)
        self.assertEqual(len(res), 0)


# ---------------------------------------------------------------------------
# Consumer-window common-mode feasibility contract (issue #182). Synthetic
# CONTRACT VALIDATION only: every value below is a hand-chosen fixture, not
# simulation evidence, and nothing here can mint a record -- the bench is
# refused with UNSUPPORTED_EXECUTOR_CAPABILITY on the real paths.
# ---------------------------------------------------------------------------

CMW = mk.CM_WINDOW_BENCH

#: Two deliberately asymmetric draws, given as (gain, offset) per common mode
#: so every expected number below is hand-derivable:
#:   draw 0: dn (20, -50 uV)  mid (25, +40 uV)   up (16, +125 uV)
#:           -> dvos_dn = -90 uV, dvos_up = +85 uV
#:   draw 1: dn (10, +200 uV) mid (20, -100 uV)  up (40, -25 uV)
#:           -> dvos_dn = +300 uV, dvos_up = +75 uV
CMW_DRAWS = [
    {"dn": (20.0, -50e-6), "mid": (25.0, 40e-6), "up": (16.0, 125e-6)},
    {"dn": (10.0, 200e-6), "mid": (20.0, -100e-6), "up": (40.0, -25e-6)},
]


def _cmw_dv(draw: dict) -> dict:
    """(gain, offset) per common mode -> the six dv values (dv0 = -vos*gain)."""
    out = {}
    for p, (g, vos) in draw.items():
        out[f"{p}_0"] = -vos * g
        out[f"{p}_2m"] = -vos * g + g * mk.CM_WINDOW_VD_STEP_V
    return out


def _cmw_request(n: int = 2) -> dict:
    req = dict(mk.cm_window_leg(n))
    req["corners"] = {"process": [{"name": "tt", "sections": ["typical"]}], "temperature_c": [27.0]}
    req["batch"] = {"runner_version_check": "enforce"}
    return req


def _cmw_report(draws=CMW_DRAWS, runner="0.7.0", compat="match", seed=mk.OFFSET_MC_SEED) -> dict:
    """A synthetic report of the six-point request: one corners[] entry per
    draw, carrying all 18 named values and the draw's monte_carlo identity."""
    corners = []
    for i, draw in enumerate(draws):
        dv = _cmw_dv(draw)
        meas = []
        for label, (vcmd, vd, _) in mk.CM_WINDOW_POINTS.items():
            meas += [{"name": f"dv_{label}", "value": dv[label]},
                     {"name": f"xcm_{label}", "value": vcmd},
                     {"name": f"xvd_{label}", "value": vd}]
        corners.append({"corner_id": f"tt/27C/mc{i}", "status": "pass", "measurements": meas,
                        "monte_carlo": {"sample_index": i, "seed": 1000 + i}})
    return {"corners": corners, "environment": {
        "monte_carlo": {"n": len(draws), "seed": seed, "vary": "mismatch"},
        "remote": {"provider": "aws-batch-fleet", "runner_klt_version": runner,
                   "client_klt_version": runner, "runner_compatibility": compat}}}


def _cmw_codes(issues):
    return {i.split(":", 1)[0] for i in issues}


class CmWindowRequestContract(unittest.TestCase):
    def test_one_analysis_one_draw_set_all_points_index_the_same_solve(self):
        leg = mk.cm_window_leg(7)
        self.assertEqual(leg["analysis"], {"kind": "dc", "args": "vd 0 2m 2m vcmd -100m 100m 100m"})
        self.assertEqual(leg["monte_carlo"], {"n": 7, "seed": mk.OFFSET_MC_SEED, "vary": "mismatch"})
        ms = leg["measurements"]
        self.assertEqual(len(ms), 18)
        self.assertTrue(all(set(m) == {"name", "expr"} for m in ms))  # no `.meas` card at all
        # Each label reads dv and both coordinates at ONE index of the one solve.
        for label, (_, _, k) in mk.CM_WINDOW_POINTS.items():
            got = {m["name"]: m["expr"] for m in ms if m["name"].endswith("_" + label)}
            self.assertEqual(got, {f"dv_{label}": f"v(dd)[{k}]", f"xcm_{label}": f"v(cm)[{k}]-v(cmb)[{k}]",
                                   f"xvd_{label}": f"v(vd)[{k}]"})
        self.assertEqual(kr.check_cm_window_request(_cmw_request()), [])

    def test_point_map_matches_ngspice_nested_order(self):
        # `dc A a0 a1 da B b0 b1 db`: A is the inner (fast) source, so the
        # flattened index of (vcmd_j, vd_i) is 2*j + i.
        vds, vcmds = (0.0, 2e-3), (-0.1, 0.0, 0.1)
        flat = [(c, d) for c in vcmds for d in vds]
        for label, (vcmd, vd, k) in mk.CM_WINDOW_POINTS.items():
            self.assertEqual(flat[k], (vcmd, vd), label)
        self.assertEqual(sorted(k for _, _, k in mk.CM_WINDOW_POINTS.values()), list(range(6)))

    def test_bad_request_shapes_refused(self):
        def issues(edit):
            req = json.loads(json.dumps(_cmw_request()))
            edit(req)
            return kr.check_cm_window_request(req)
        self.assertTrue(issues(lambda r: r["analysis"].update(args="vd 0 2m 2m")))
        self.assertTrue(issues(lambda r: r.pop("monte_carlo")))
        self.assertTrue(issues(lambda r: r["batch"].update(runner_version_check="warn")))
        # A `.meas` card cannot name the outer coordinate.
        self.assertTrue(any("`.meas` card" in i for i in issues(lambda r: r["measurements"][0].update(
            spice=".meas dc dv_dn_0 find v(dd) at=0"))))
        # Swapped point mapping: dn's dv reads up's index.
        def swap(r):
            for m in r["measurements"]:
                if m["name"] == "dv_dn_0":
                    m["expr"] = "v(dd)[4]"
        self.assertTrue(any("dv_dn_0" in i for i in issues(swap)))
        self.assertTrue(issues(lambda r: r["measurements"].pop()))

    def test_capability_gap_by_runner_version(self):
        gap = mk.cm_window_capability_gap("0.5.0")
        self.assertIn("'spice'", gap)
        self.assertIn("expr", gap)
        self.assertIn("klt >= 0.7.0", gap)
        for ok in ("0.7.0", "0.7.0+g5e5b55992a7f", "klt 0.8.1"):
            self.assertIsNone(mk.cm_window_capability_gap(ok), ok)
        for bad in (None, "", "unknown", "0.6.9"):
            self.assertIsNotNone(mk.cm_window_capability_gap(bad), bad)
        # The observed fleet runner is the unsupported one: the real paths refuse.
        self.assertIsNotNone(mk.cm_window_capability_gap(mk.FLEET_RUNNER_KLT_OBSERVED))

    def test_mk_request_refused_before_anything_is_staged(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            with mock.patch.object(sys, "argv", ["mk_klt_request.py", CMW, str(out)]), \
                    mock.patch.object(mk.hpdk, "find_pdk") as pdk, \
                    self.assertRaises(SystemExit) as cm:
                mk.main()
            self.assertTrue(str(cm.exception.code).startswith("UNSUPPORTED_EXECUTOR_CAPABILITY: "))
            self.assertFalse(out.exists())
            pdk.assert_not_called()
        with self.assertRaises(SystemExit) as cm:
            mk.legs_for(CMW, None, 3)
        self.assertIn("UNSUPPORTED_EXECUTOR_CAPABILITY", str(cm.exception.code))

    def test_record_path_refused_and_nothing_minted(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rc, rec, _ = _ingest(td, td / "work", bench=CMW)
            self.assertIn("UNSUPPORTED_EXECUTOR_CAPABILITY", str(rc))
            self.assertIsNone(rec)
            self.assertFalse(any((td / "evidence" / CMW).iterdir()))
            # Even with a capable runner there is no minting path yet.
            with mock.patch.object(mk, "FLEET_RUNNER_KLT_OBSERVED", "0.7.0"):
                rc, rec, _ = _ingest(td, td / "work", bench=CMW)
            self.assertIn("full 45-point coverage pending", str(rc))
            self.assertIsNone(rec)

    def test_bench_is_separate_and_historical_bench_untouched(self):
        tb = htb.load(SIM / CMW)
        self.assertIn("  dc vd 0 2m 2m vcmd -100m 100m 100m", tb.analyses)
        old = htb.load(SIM / "comparator-offset-mc")
        self.assertIn("  dc vd 0 2m 2m vcmd -50m 50m 50m", old.analyses)
        self.assertNotEqual(tb.netlist, old.netlist)
        # The adapter's outputs are the manifest's measure names.
        res, _ = kr.derive_cm_window({"c": {f"mc{i}": _cmw_dv(d) for i, d in enumerate(CMW_DRAWS)}})
        self.assertEqual(set(res["c"]), set(tb.measure))
        self.assertNotIn(CMW, kr.SPEC)  # no ratified row, no score


class CmWindowDerivation(unittest.TestCase):
    CID = "tt_27c_3.30v"

    def _collect(self, rep, req=None):
        return kr.collect_cm_window(rep, req or _cmw_request(), 3.3)

    def test_hand_calculated_two_draw_fixture(self):
        samples, issues = self._collect(_cmw_report())
        self.assertEqual(issues, [])
        d0 = kr.derive_cm_window_draw(samples[self.CID]["mc0"])
        self.assertAlmostEqual(d0["av_dn"], 20.0, places=9)
        self.assertAlmostEqual(d0["av_mid"], 25.0, places=9)
        self.assertAlmostEqual(d0["av_up"], 16.0, places=9)
        self.assertAlmostEqual(d0["vos_mid"] * 1e6, 40.0, places=6)
        self.assertAlmostEqual(d0["dvos_dn"] * 1e6, -90.0, places=6)
        self.assertAlmostEqual(d0["dvos_up"] * 1e6, 85.0, places=6)
        d1 = kr.derive_cm_window_draw(samples[self.CID]["mc1"])
        self.assertAlmostEqual(d1["av_mid"], 20.0, places=9)
        self.assertAlmostEqual(d1["dvos_dn"] * 1e6, 300.0, places=6)
        self.assertAlmostEqual(d1["dvos_up"] * 1e6, 75.0, places=6)
        res, problems = kr.derive_cm_window(samples)
        self.assertEqual(problems, [])
        r = res[self.CID]
        self.assertEqual(r["n_samples"], 2)
        self.assertAlmostEqual(r["mean_vos_mid_uv"], -30.0, places=6)
        self.assertAlmostEqual(r["sig_vos_mid_mv"], 0.070, places=9)   # population: |40-(-100)|/2 uV
        self.assertAlmostEqual(r["mean_dvos_dn_uv"], 105.0, places=6)
        self.assertAlmostEqual(r["sig_dvos_dn_uv"], 195.0, places=6)
        self.assertAlmostEqual(r["mean_dvos_up_uv"], 80.0, places=6)
        self.assertAlmostEqual(r["sig_dvos_up_uv"], 5.0, places=6)
        self.assertAlmostEqual(r["av_dn_mean"], 15.0, places=9)
        self.assertAlmostEqual(r["av_mid_mean"], 22.5, places=9)
        self.assertAlmostEqual(r["av_up_mean"], 28.0, places=9)
        self.assertAlmostEqual(r["av_sigma_pct"], 2.5 / 22.5 * 100, places=9)
        # Population, not sample, sigma (n = 2: they differ by sqrt(2)).
        self.assertNotAlmostEqual(r["sig_dvos_dn_uv"], 195.0 * math.sqrt(2), places=3)

    def test_paired_delta_is_within_draw_not_across_populations(self):
        # The same marginal populations, re-paired across draws, give a
        # different delta sigma: the pairing is what is being measured.
        samples, _ = self._collect(_cmw_report())
        res, _ = kr.derive_cm_window(samples)
        crossed = [dict(CMW_DRAWS[0], mid=CMW_DRAWS[1]["mid"]), dict(CMW_DRAWS[1], mid=CMW_DRAWS[0]["mid"])]
        res_x, _ = kr.derive_cm_window(self._collect(_cmw_report(crossed))[0])
        self.assertAlmostEqual(res_x[self.CID]["sig_vos_mid_mv"], res[self.CID]["sig_vos_mid_mv"], places=12)
        self.assertNotAlmostEqual(res_x[self.CID]["sig_dvos_dn_uv"], res[self.CID]["sig_dvos_dn_uv"], places=3)

    def test_shuffled_order_is_correct_by_identity(self):
        import random
        rep = _cmw_report()
        rng = random.Random(182)
        rng.shuffle(rep["corners"])
        for c in rep["corners"]:
            rng.shuffle(c["measurements"])
        a, ia = self._collect(_cmw_report())
        b, ib = self._collect(rep)
        self.assertEqual((ia, ib), ([], []))
        self.assertEqual(a, b)
        self.assertEqual(kr.derive_cm_window(a), kr.derive_cm_window(b))

    def test_duplicate_missing_and_misidentified_samples(self):
        rep = _cmw_report()
        rep["corners"].append(json.loads(json.dumps(rep["corners"][0])))
        out, issues = self._collect(rep)
        self.assertIn("DUPLICATE_SAMPLE", _cmw_codes(issues))
        self.assertNotIn("mc0", out[self.CID])  # neither copy is trusted
        rep = _cmw_report()
        rep["corners"].pop()
        _, issues = self._collect(rep)
        self.assertIn("MISSING_SAMPLE: tt_27c_3.30v/mc1 has no result", issues)
        rep = _cmw_report()
        rep["corners"][1]["monte_carlo"]["sample_index"] = 0
        _, issues = self._collect(rep)
        self.assertIn("SAMPLE_IDENTITY_MISMATCH", _cmw_codes(issues))
        rep = _cmw_report()
        rep["corners"][1]["corner_id"] = "tt/27C/mc9"
        _, issues = self._collect(rep)
        self.assertTrue({"UNEXPECTED_SAMPLE", "MISSING_SAMPLE"} <= _cmw_codes(issues))
        rep = _cmw_report()
        rep["corners"][0]["status"] = "error"
        _, issues = self._collect(rep)
        self.assertIn("FAILED_SAMPLE", _cmw_codes(issues))

    def test_wrong_endpoint_labels_fail_on_coordinate_readback(self):
        # A writer that swaps the dn/up labels (values intact, labels wrong):
        # the read-back coordinates name the other endpoint.
        rep = _cmw_report()
        for m in rep["corners"][0]["measurements"]:
            n = m["name"]
            m["name"] = n.replace("_dn_", "_UP_").replace("_up_", "_dn_").replace("_UP_", "_up_")
        out, issues = self._collect(rep)
        self.assertIn("COORDINATE_MISMATCH", _cmw_codes(issues))
        self.assertNotIn("mc0", out.get(self.CID, {}))
        # vd swapped within one common mode is caught the same way.
        rep = _cmw_report()
        for m in rep["corners"][1]["measurements"]:
            if m["name"] in ("xvd_mid_0", "xvd_mid_2m"):
                m["value"] = 2e-3 if m["name"].endswith("_0") else 0.0
        _, issues = self._collect(rep)
        self.assertTrue(any(i.startswith("COORDINATE_MISMATCH: tt/27C/mc1 mid_0") for i in issues))

    def test_unknown_label_and_incomplete_sample(self):
        rep = _cmw_report()
        for m in rep["corners"][0]["measurements"]:
            if m["name"] == "dv_up_2m":
                m["name"] = "dv_hi_2m"
        _, issues = self._collect(rep)
        self.assertTrue({"UNEXPECTED_VALUE", "INCOMPLETE_SAMPLE"} <= _cmw_codes(issues))
        rep = _cmw_report()
        rep["corners"][1]["measurements"] = rep["corners"][1]["measurements"][:-1]
        out, issues = self._collect(rep)
        self.assertEqual(_cmw_codes(issues), {"INCOMPLETE_SAMPLE"})
        self.assertEqual(sorted(out[self.CID]), ["mc0"])
        rep = _cmw_report()
        rep["corners"][0]["measurements"].append({"name": "dv_mid_0", "value": 0.0})
        _, issues = self._collect(rep)
        self.assertIn("DUPLICATE_VALUE", _cmw_codes(issues))

    def test_six_values_split_across_two_samples_are_not_a_draw(self):
        # Half the points under mc0, half under mc1: neither is a complete
        # draw of one analysis, so neither contributes.
        rep = _cmw_report()
        a, b = rep["corners"]
        a["measurements"] = [m for m in a["measurements"] if "_up_" not in m["name"]]
        b["measurements"] = [m for m in b["measurements"] if "_up_" in m["name"]]
        out, issues = self._collect(rep)
        self.assertEqual(out, {})
        self.assertEqual(_cmw_codes(issues), {"INCOMPLETE_SAMPLE"})

    def test_nonfinite_values_refused(self):
        for bad in (float("nan"), float("inf"), None, "1e-3", True):
            rep = _cmw_report()
            rep["corners"][0]["measurements"][0]["value"] = bad
            out, issues = self._collect(rep)
            self.assertIn("NONFINITE_VALUE", _cmw_codes(issues), bad)
            self.assertNotIn("mc0", out[self.CID])

    def test_zero_negative_and_overflowing_gain_drop_the_point(self):
        for edit in ({"mid_2m": None}, {"up_2m": "neg"}):
            dv = [_cmw_dv(d) for d in CMW_DRAWS]
            if "mid_2m" in edit:
                dv[1]["mid_2m"] = dv[1]["mid_0"]                 # zero gain
            else:
                dv[0]["up_2m"] = dv[0]["up_0"] - 1e-3            # negative gain
            res, problems = kr.derive_cm_window({self.CID: {f"mc{i}": v for i, v in enumerate(dv)}})
            self.assertEqual(res, {})
            self.assertTrue(problems and all(p.startswith("INVALID_GAIN: tt_27c_3.30v/mc") for p in problems))
        dv = _cmw_dv(CMW_DRAWS[0])
        dv["dn_0"], dv["dn_2m"] = -1e308, 1e308                  # (dv1 - dv0) overflows
        with self.assertRaises(ValueError) as cm:
            kr.derive_cm_window_draw(dv)
        self.assertEqual(cm.exception.args[0], "INVALID_GAIN")

    def test_executor_without_expr_or_version_match_is_unsupported(self):
        for runner, compat in (("0.5.0", "mismatch"), ("0.7.0", "mismatch"), (None, "unknown")):
            _, issues = self._collect(_cmw_report(runner=runner, compat=compat))
            self.assertIn("UNSUPPORTED_EXECUTOR_CAPABILITY", _cmw_codes(issues), runner)
        rep = _cmw_report()
        del rep["environment"]["remote"]
        _, issues = self._collect(rep)
        self.assertIn("UNSUPPORTED_EXECUTOR_CAPABILITY", _cmw_codes(issues))
        rep = _cmw_report()
        rep["environment"]["remote"]["fleet"] = [{"runner_klt_version": "0.7.0", "runner_compatibility": "match"},
                                                 {"runner_klt_version": "0.5.0", "runner_compatibility": "mismatch"}]
        _, issues = self._collect(rep)
        self.assertIn("UNSUPPORTED_EXECUTOR_CAPABILITY", _cmw_codes(issues))  # every shard must qualify

    def test_mc_declaration_and_request_shape_checked_at_collection(self):
        _, issues = self._collect(_cmw_report(seed=1))
        self.assertIn("MC_DECLARATION_MISMATCH", _cmw_codes(issues))
        req = _cmw_request()
        req["batch"]["runner_version_check"] = "warn"
        _, issues = self._collect(_cmw_report(), req)
        self.assertIn("REQUEST_SHAPE_INVALID", _cmw_codes(issues))

    def test_separate_request_seed_equality_is_not_pairing(self):
        # Three requests, one per common mode, all seeded identically: the
        # seed reproduces a sequence of separately randomized decks, not one
        # instance. Refused regardless of how well the seeds line up.
        reps = [_cmw_report(), _cmw_report(), _cmw_report()]
        for r in reps:
            self.assertEqual(r["environment"]["monte_carlo"]["seed"], mk.OFFSET_MC_SEED)
        with self.assertRaises(SystemExit) as cm:
            kr.pair_cm_window_reports(reps)
        self.assertTrue(str(cm.exception.code).startswith("SEPARATE_REQUEST_PAIRING: 3 reports"))
        self.assertIn("same monte_carlo seed", str(cm.exception.code))
        with self.assertRaises(SystemExit):
            kr.pair_cm_window_reports([])
        self.assertIs(kr.pair_cm_window_reports(reps[:1]), reps[0])
