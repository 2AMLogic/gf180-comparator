"""PDK-free tests for the avg-power sensitivity overrides (issue #452).

DR-0006's feasibility item 4 needs records at a NON-nominal condition: 0 and
100 fF loads, 1 and 50 mV overdrive, a 32 MHz clock, each on a declared
corner subset. The nominal ``tb.json`` is never edited (append-only, and the
two-PDK-twin rule); instead ``mk_klt_request.py`` overrides the params at
request-build time and re-renders every period-coupled ``.meas`` literal from
the effective schedule, and ``klt_record.py`` rescales the period-coupled
check bounds / window expressions at ingest and stamps the record
SENSITIVITY-ONLY.

These tests pin the mechanism's two invariants:

1. **Nominal is byte-unchanged.** The renderer fed the committed nominal
   params must reproduce ``tb.json``'s ``analyses`` byte for byte, a request
   set generated with an override numerically equal to nominal must be
   byte-identical to one generated with no flags at all, and the request
   JSON/bodies of a no-flag generation are unchanged in shape (the
   ``AvgPowerFleetPath`` tests pin the rest).
2. **A t_per override rescales everything that depends on the period.** The
   window, its half split, every per-cycle decision read, the quiescent
   probe, the reset-search anchor and the transient stop; the input sign
   change stays inside the reset phase (setup scales with the period); and
   the µW expressions carry the window scale their ``1e12`` factor needs at
   a non-1 µs window, so ``p_avg_uw`` stays VDD*Q_win/(N*T).

Stdlib only. No PDK, no ngspice, no klt; git state is irrelevant (the
bench's own sources stay clean).
"""

from __future__ import annotations

import dataclasses
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SIM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

from harness import testbench as htb  # noqa: E402
import klt_record as kr  # noqa: E402
import mk_klt_request as mk  # noqa: E402

BENCH = mk.AVG_POWER_BENCH
NOMINAL_T_PER = 6.25e-08
TWO_X_RATE_T_PER = 3.125e-08  # 32 MHz, DR-0006 "Alternatives considered"


class RenderIdentity(unittest.TestCase):
    """The renderer reproduces the committed schedule; overrides rescale it."""

    def setUp(self):
        self.tb = htb.load(SIM / BENCH)

    def test_nominal_render_is_byte_identical_to_the_manifest(self):
        self.assertEqual(mk.render_avg_power_cards(self.tb.params),
                         list(self.tb.analyses))

    def test_schedule_without_t_per_keeps_manifest_cards_verbatim(self):
        # A v_od/c_load-only sensitivity changes no schedule byte: the cards
        # are tb.analyses themselves, not a re-render that happens to match.
        _eff, cards, _scale, applied = mk.avg_power_schedule(
            self.tb, {"v_od": 0.001})
        self.assertEqual(list(applied), ["v_od"])
        self.assertEqual(cards, list(self.tb.analyses))

    def test_rendered_schedule_is_refused_if_nominal_drifts(self):
        # The guard: a scaled schedule may only ship from a renderer that
        # just proved it reproduces the committed nominal cards.
        drifted = dataclasses.replace(self.tb, analyses=tuple(
            list(self.tb.analyses[:-1]) + ["meas tran t_rst when v(irst)=i_rst_thr fall=LAST td=1478.9n"]))
        with self.assertRaises(SystemExit) as ctx:
            mk.avg_power_schedule(drifted, {"t_per": TWO_X_RATE_T_PER})
        self.assertIn("NOMINAL_RENDER_DRIFT", str(ctx.exception))

    def test_32mhz_schedule_scales_every_period_coupled_time(self):
        eff, cards, scale, applied = mk.avg_power_schedule(
            self.tb, {"t_per": TWO_X_RATE_T_PER})
        self.assertEqual(sorted(applied), ["t_per"])
        self.assertEqual(scale, 2.0)
        by_name = {}
        for card in cards:
            parts = card.split()
            if parts[0] == "meas":
                by_name.setdefault(parts[2], []).append(card)
        # window [t_rise0+8*T, t_rise0+24*T] = [260n, 760n]; halves at 510n
        self.assertEqual(cards[0], "tran 10p 760n")
        self.assertEqual(by_name["vsup_v"][0], "meas tran vsup_v find v(vdda) at=260n")
        self.assertEqual(by_name["q_win"][0],
                         "meas tran q_win integ i(vsupa) from=260n to=760n")
        self.assertEqual(by_name["q_h1"][0],
                         "meas tran q_h1 integ i(vsupa) from=260n to=510n")
        self.assertEqual(by_name["q_h2"][0],
                         "meas tran q_h2 integ i(vsupa) from=510n to=760n")
        # per-cycle reads: 250 ps before each falling edge
        self.assertEqual(by_name["d08"][0], "meas tran d08 find v(dn) at=275.375n")
        self.assertEqual(by_name["d23"][0], "meas tran d23 find v(dn) at=744.125n")
        self.assertEqual(by_name["db08"][0], "meas tran db08 find v(dbn) at=275.375n")
        self.assertEqual(by_name["db23"][0], "meas tran db23 find v(dbn) at=744.125n")
        # quiescent probe: same 3 ns width, ending one edge before the close
        self.assertEqual(by_name["i_q"][0],
                         "meas tran i_q avg i(vsupa) from=757n to=759.9n")
        # the clock-plumbing edge indices are counts, not times: unchanged
        self.assertEqual(by_name["t_elo"][0], "meas tran t_elo when v(clkn)=0.5 rise=9")
        self.assertEqual(by_name["t_ehi"][0], "meas tran t_ehi when v(clkn)=0.5 rise=24")

    def test_32mhz_reads_and_flips_stay_inside_their_phases(self):
        # Every decision read sits inside its cycle's evaluate phase, and
        # every input sign change begins after the preceding falling edge
        # and completes t_setup before the next rising edge -- the deck's
        # own timing argument, at the period-scaled setup.
        eff = dict(self.tb.params)
        eff.update(mk.avg_power_effective_params(self.tb.params,
                                                 {"t_per": TWO_X_RATE_T_PER})[0])
        tr, tp, th, te = eff["t_rise0"], eff["t_per"], eff["t_hi"], eff["t_edge"]
        self.assertEqual(th, tp / 2)
        self.assertEqual(eff["f_clk"], 32e6)
        self.assertEqual(eff["t_setup"], 1e-08)  # 20 ns scaled by 31.25/62.5
        for k in range(8, 24):
            rising, falling = tr + k * tp, tr + k * tp + th
            read = falling - 250e-12
            self.assertGreater(read, rising)
            self.assertLess(read, falling)
        for m in range(12):  # flips at t_rise0 + (2m+1)*tp - t_setup - t_edge
            begin = tr + (2 * m + 1) * tp - eff["t_setup"] - te
            done = begin + te
            prev_falling = tr + 2 * m * tp + th
            next_rising = tr + (2 * m + 1) * tp
            self.assertGreater(begin, prev_falling)      # inside the reset phase
            self.assertAlmostEqual(done, next_rising - eff["t_setup"])  # settled


class EffectiveParams(unittest.TestCase):
    def setUp(self):
        self.params = htb.load(SIM / BENCH).params

    def test_nominal_values_are_not_overrides(self):
        _eff, scale, applied = mk.avg_power_effective_params(
            self.params, {"v_od": 0.01, "c_load": 2e-14, "t_per": NOMINAL_T_PER})
        self.assertEqual(applied, {})
        self.assertEqual(scale, 1.0)

    def test_unknown_and_invalid_values_are_refused(self):
        for bad in ({"v_bias": 1e-5}, {"v_od": 0.0}, {"v_od": -0.001},
                    {"c_load": -1e-14}, {"t_per": 0.0}, {"t_per": -1e-8}):
            with self.assertRaises(SystemExit):
                mk.avg_power_effective_params(self.params, bad)

    def test_v_od_and_c_load_substitute_directly(self):
        eff, _scale, applied = mk.avg_power_effective_params(
            self.params, {"v_od": 0.05, "c_load": 1e-13})
        self.assertEqual(applied, {"v_od": 0.05, "c_load": 1e-13})
        self.assertEqual(eff["v_od"], 0.05)
        self.assertEqual(eff["c_load"], 1e-13)
        self.assertEqual(eff["t_per"], NOMINAL_T_PER)  # untouched

    def test_uw_scale_tracks_the_window(self):
        # The manifest's p_avg_uw 1e12 factor bakes in the nominal 1.000 us
        # window; at 32 MHz the window is 500 ns and the scale is exactly 2.
        eff, scale, _applied = mk.avg_power_effective_params(
            self.params, {"t_per": TWO_X_RATE_T_PER})
        self.assertEqual(eff["t_per"] * eff["n_win"], 5e-07)
        self.assertEqual(scale, 2.0)


class ApplyAtIngest(unittest.TestCase):
    """What klt_record.py does to the loaded STAGED manifest at ingest."""

    def setUp(self):
        self.tb = htb.load(SIM / BENCH)

    @staticmethod
    def raw_32mhz():
        # Synthetic ingredients of a clean 32 MHz point: window charge such
        # that the TRUE average power is 150 uW over the 500 ns window, the
        # measured period exactly 31.25 ns, 16/16 correct decisions.
        q_win = -(150e-6 * 5e-07) / 3.3  # C
        raw = {"vsup_v": 3.3, "t_elo": 260.05e-9, "t_ehi": 728.8e-9,
               "q_win": q_win, "q_h1": q_win / 2, "q_h2": q_win / 2,
               "e_win": -q_win * 3.3, "q_clk": -7e-15, "i_q": -30e-6,
               "db08": 7.42e-10, "db23": 1.0}
        for i in range(8, 24):
            raw[f"d{i:02d}"] = 1.0 if i % 2 == 0 else 7.42e-10
        return raw

    def test_stamp_and_scaling(self):
        stamp = mk.apply_avg_power_overrides(self.tb, {"t_per": TWO_X_RATE_T_PER})
        self.assertTrue(stamp["sensitivity_only"])
        self.assertEqual(stamp["overrides"], {"t_per": TWO_X_RATE_T_PER})
        self.assertEqual(stamp["t_win_s"], 5e-07)
        self.assertEqual(stamp["uw_scale"], 2.0)
        # the period-plumbing check follows the effective period
        self.assertEqual(self.tb.checks["clk_period_ns"]["min"], 31.24)
        self.assertEqual(self.tb.checks["clk_period_ns"]["max"], 31.26)
        # the two window-baked uW expressions carry the scale
        self.assertEqual(self.tb.measure["p_avg_uw"], "(-q_win*vsup_v*1e12)*2.0")
        self.assertEqual(self.tb.measure["p_avg_vi_uw"], "(e_win*1e12)*2.0")
        # nothing else moved
        self.assertNotIn("scale", self.tb.measure["e_dec_fj"])

    def test_no_override_is_a_no_op(self):
        before_measure, before_checks = dict(self.tb.measure), dict(self.tb.checks)
        self.assertEqual(mk.apply_avg_power_overrides(self.tb, {}), {})
        self.assertEqual(self.tb.measure, before_measure)
        self.assertEqual(self.tb.checks, before_checks)

    def test_derive_reports_true_uw_at_the_effective_window(self):
        mk.apply_avg_power_overrides(self.tb, {"t_per": TWO_X_RATE_T_PER})
        res, problems = kr.derive(BENCH, self.tb,
                                  {"main": ({"tt_27c_3.30v": {"": self.raw_32mhz()}}, [])})
        self.assertEqual(problems, [])
        d = res["tt_27c_3.30v"]
        self.assertAlmostEqual(d["p_avg_uw"], 150.0, places=9)   # not 75.0
        self.assertAlmostEqual(d["p_avg_vi_uw"], 150.0, places=9)
        self.assertAlmostEqual(d["e_dec_fj"], 150e-6 * 5e-07 / 16 * 1e15, places=6)
        self.assertAlmostEqual(d["clk_period_ns"], 31.25, places=9)
        self.assertAlmostEqual(d["dec_cycles_correct"], 16.0, places=12)

    def test_unscaled_check_would_have_failed_the_corner(self):
        # The point of rescaling clk_period_ns: with the nominal 62.49/62.51
        # bounds a clean 32 MHz run measures 31.25 ns and every corner would
        # be GUARD_FAILED -- a plumbing artifact, not a circuit finding.
        tb = htb.load(SIM / BENCH)
        res, problems = kr.derive(BENCH, tb,
                                  {"main": ({"tt_27c_3.30v": {"": self.raw_32mhz()}}, [])})
        self.assertEqual(res, {})
        self.assertTrue(any("GUARD_FAILED: tt_27c_3.30v clk_period_ns" in p
                            for p in problems), problems)


class RequestGeneration(unittest.TestCase):
    """mk_klt_request.main() with the new flags, fake PDK, no dispatch."""

    def _mk(self, *extra, bench=BENCH):
        with tempfile.TemporaryDirectory() as td:
            design = Path(td) / "design.ngspice"
            design.write_text("* fake PDK design include\n")
            out = Path(td) / "out"
            argv = ["mk_klt_request.py", bench, str(out), *extra]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(mk.hpdk, "find_pdk",
                                      return_value=types.SimpleNamespace(design_include=design)), \
                    redirect_stdout(io.StringIO()):
                rc = mk.main()
            reqs = {p.name: p.read_text() for p in out.glob("request-*.json")}
            bodies = {p.name: p.read_text() for p in out.glob("body-*.spice")}
            bundle = json.loads((out / mk.BUNDLE_NAME).read_text()) \
                if (out / mk.BUNDLE_NAME).is_file() else None
            return rc, reqs, bodies, bundle

    def test_explicit_nominal_override_is_byte_identical_to_no_flags(self):
        _rc0, reqs0, bodies0, bundle0 = self._mk()
        _rc1, reqs1, bodies1, bundle1 = self._mk(
            "--v-od", "0.01", "--c-load", "2e-14", "--t-per", "6.25e-08")
        self.assertEqual(reqs0, reqs1)
        self.assertEqual(bodies0, bodies1)
        self.assertNotIn("overrides", bundle1["parameters"])
        self.assertEqual(bundle0["parameters"], bundle1["parameters"])

    def test_32mhz_request_carries_the_scaled_schedule(self):
        rc, reqs, bodies, bundle = self._mk("--t-per", "3.125e-08")
        self.assertEqual(rc, 0)
        req = json.loads(reqs["request-main-v3.30.json"])
        self.assertEqual(req["analysis"], {"kind": "tran", "args": "10p 760n"})
        spice = {m["name"]: m["spice"] for m in req["measurements"]}
        self.assertEqual(spice["q_win"], ".meas tran q_win integ i(vsupa) from=260n to=760n")
        self.assertEqual(spice["d08"], ".meas tran d08 find v(dn) at=275.375n")
        # the let/t_rst pair stays dropped (issue #372)
        self.assertNotIn("t_rst", spice)
        body = bodies["body-v3.30.spice"]
        for line in (".param t_per=3.125e-08", ".param t_hi=1.5625e-08",
                     ".param f_clk=32000000.0", ".param t_setup=1e-08"):
            self.assertIn(line, body)
        self.assertEqual(bundle["parameters"]["overrides"], {"t_per": 3.125e-08})

    def test_overload_override_bakes_only_that_param(self):
        _rc, reqs, bodies, bundle = self._mk("--v-od", "0.05")
        body = bodies["body-v3.30.spice"]
        self.assertIn(".param v_od=0.05", body)
        self.assertIn(".param t_per=6.25e-08", body)  # nominal schedule kept
        self.assertEqual(bundle["parameters"]["overrides"], {"v_od": 0.05})

    def test_corner_points_build_exactly_the_declared_set(self):
        rc, reqs, _bodies, bundle = self._mk(
            "--corner-points", "tt_27c_3.30v", "ff_125c_3.63v", "ss_125c_2.97v")
        self.assertEqual(rc, 0)
        # one request per supply point, exactly the declared points
        self.assertEqual(sorted(reqs), ["request-main-v2.97.json",
                                        "request-main-v3.30.json",
                                        "request-main-v3.63.json"])
        by_supply = {}
        for name, text in reqs.items():
            req = json.loads(text)
            points = {(p["name"], t) for p in req["corners"]["process"]
                      for t in req["corners"]["temperature_c"]}
            by_supply[name] = points
            self.assertEqual(len(points), 1)
        self.assertEqual(by_supply["request-main-v3.30.json"], {("tt", 27.0)})
        self.assertEqual(by_supply["request-main-v3.63.json"], {("ff", 125.0)})
        self.assertEqual(by_supply["request-main-v2.97.json"], {("ss", 125.0)})
        self.assertEqual(bundle["parameters"]["corner_points"],
                         ["tt_27c_3.30v", "ff_125c_3.63v", "ss_125c_2.97v"])
        self.assertNotIn("overrides", bundle["parameters"])

    def test_non_product_subset_is_refused(self):
        # tt and ff at 27/125C on ONE supply would run 4 corners to cover 2
        # declared points -- the product nobody asked for.
        with self.assertRaises(SystemExit) as ctx:
            self._mk("--corner-points", "tt_27c_3.30v", "ff_125c_3.30v")
        self.assertIn("not a process x temperature product", str(ctx.exception))

    def test_corner_points_reject_unknown_and_malformed_ids(self):
        for bad in (["tt_27c_3.30v", "typical_27c_3.30v"],
                    ["cap_ff_27c_3.30v"],
                    ["tt_27c_3.3v"],
                    ["tt_200c_3.30v"]):
            with self.assertRaises(SystemExit):
                self._mk("--corner-points", *bad)

    def test_flag_combinations_and_other_benches_are_refused(self):
        with self.assertRaises(SystemExit):
            self._mk("--corner-points", "tt_27c_3.30v", "--corners", "tt")
        with self.assertRaises(SystemExit):
            self._mk("--corner-points", "tt_27c_3.30v", "--temps", "27")
        with self.assertRaises(SystemExit):
            self._mk("--corner-points", "tt_27c_3.30v", "--supply-v", "3.3")
        with self.assertRaises(SystemExit):
            self._mk(bench="comparator-kickback", *("--v-od", "0.01"))
        with self.assertRaises(SystemExit):
            self._mk(bench="comparator-kickback", *("--corner-points", "tt_27c_3.30v"))


class RecorderSurfaces(unittest.TestCase):
    """klt_record.py's CLI gate and the Reproduce line's selection flags."""

    def test_override_flags_refused_for_other_benches(self):
        for extra in (["--v-od", "0.01"], ["--c-load", "1e-13"],
                      ["--t-per", "3.125e-08"], ["--corner-points", "tt_27c_3.30v"]):
            argv = ["klt_record.py", "comparator-kickback", *extra]
            with mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    kr.main()

    @staticmethod
    def _reproduce(parameters):
        b = {"origin": {"commit": "a" * 40}, "parameters": parameters,
             "dut": {"selector": None}}
        r = {"rid": "20261120-000000000000-abcdef0", "ingest_sha": "b" * 7,
             "ingest_commit_full": "b" * 40}
        tb = htb.load(SIM / BENCH)
        return kr.reproduce_line(BENCH, b, r, tb)

    def test_reproduce_line_carries_the_sensitivity_flags(self):
        line = self._reproduce({"overrides": {"t_per": 3.125e-08},
                                "corner_points": ["tt_27c_3.30v", "ff_125c_3.63v"]})
        self.assertIn("--t-per 3.125e-08", line)
        self.assertIn("--corner-points tt_27c_3.30v ff_125c_3.63v", line)

    def test_reproduce_line_of_a_nominal_bundle_carries_no_flags(self):
        self.assertNotIn("--t-per", self._reproduce({}))
        self.assertNotIn("--corner-points", self._reproduce({}))


class SensitivityIngest(unittest.TestCase):
    """End-to-end: generate an overridden, subset-restricted request set,
    link synthetic fleet reports to it, ingest, and read the minted record.

    The full main() path is exercised (bundle validation, staged-source
    verification, derive under the applied overrides, header stamping,
    Reproduce line) against a temp evidence tree -- the same fixture style
    test_klt_record.py uses, no PDK, no klt, nothing dispatched."""

    def _run(self, *mk_extra, ingest_extra=()):
        from sim.harness.tests import test_klt_record as tk
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = tk._generate(td, *mk_extra, bench=BENCH)
            b = tk._bundle(work)
            raw = ApplyAtIngest.raw_32mhz()
            for n, r in b["requests"].items():
                req = json.loads((work / r["request"]).read_text())
                meas = [m["name"] for m in req["measurements"]]
                corners = [{"corner_id": "tt/novdd/27C", "status": "pass",
                            "measurements": [{"name": m, "value": raw[m]} for m in meas]}]
                (work / f"report-{n}.json").write_text(json.dumps(
                    {"corners": corners, "measurements": [{"name": m} for m in meas],
                     "environment": tk._link_env(work, b, r), "provenance": tk._prov()}))
            rc, rec, out = tk._ingest(td, work, *ingest_extra, bench=BENCH)
            md = next((td / "evidence" / BENCH / "records").glob("*.md"), None)
            return rc, rec, out, (md.read_text() if md else "")

    def test_32mhz_subset_record_mints_stamped_and_true(self):
        rc, rec, _out, md = self._run(
            "--t-per", "3.125e-08", "--corner-points", "tt_27c_3.30v")
        self.assertEqual(rc, 0)
        self.assertTrue(rec["complete"])
        self.assertEqual(rec["points"], 1)
        self.assertEqual(rec["condition"]["sensitivity_only"], True)
        self.assertEqual(rec["condition"]["overrides"], {"t_per": 3.125e-08})
        self.assertEqual(rec["condition"]["uw_scale"], 2.0)
        self.assertEqual(rec["condition"]["corner_points"], ["tt_27c_3.30v"])
        d = rec["derived"]["tt_27c_3.30v"]
        self.assertAlmostEqual(d["p_avg_uw"], 150.0, places=9)  # true µW at 500 ns
        self.assertIn("SENSITIVITY-ONLY, NON-NOMINAL", md)
        self.assertIn("`t_per` = 3.125e-08", md)
        self.assertIn("corner subset: `tt_27c_3.30v`", md)
        self.assertIn("--t-per 3.125e-08", md)
        self.assertIn("--corner-points tt_27c_3.30v", md)
        self.assertIn("SUPPLEMENTAL AND UNSCORED", md)

    def test_ingest_flags_must_match_the_bundle(self):
        # A mis-pasted Reproduce command cannot mint under the wrong
        # condition: the bundle is the authority and a contradiction refuses.
        for bad in (("--t-per", "6.25e-08"), ("--v-od", "0.01")):
            rc, rec, _out, md = self._run(
                "--t-per", "3.125e-08", "--corner-points", "tt_27c_3.30v",
                ingest_extra=bad)
            self.assertNotEqual(rc, 0, bad)
            self.assertIsNone(rec)
            self.assertEqual(md, "")

    def test_bundleless_flags_do_not_create_a_sensitivity(self):
        # Flags on an ingest of a NOMINAL bundle are refused the same way --
        # they claim a condition the request set does not carry.
        rc, rec, _out, _md = self._run(ingest_extra=("--v-od", "0.05"))
        self.assertNotEqual(rc, 0)
        self.assertIsNone(rec)


if __name__ == "__main__":
    unittest.main()
