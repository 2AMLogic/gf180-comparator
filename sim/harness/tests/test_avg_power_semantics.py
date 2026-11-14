"""Pin the committed ``comparator-avg-power`` manifest to DR-0006 (issue #356).

``sim/comparator-avg-power/`` implements the average-power operating condition
proposed by
``spec/decision-records/DR-0006-average-power-operating-condition.md``. Two
things about that manifest cannot be checked by running it:

1. **An ngspice ``meas`` card takes literal times.** Every integration
   boundary, every per-cycle decision-read instant and the reset-completion
   search window are therefore hard-coded numbers in ``analyses``, while the
   clock they must agree with is built from ``params``. Nothing at run time
   compares the two: a window that silently covered 15.5 cycles, or a decision
   read that landed after the falling edge, would simulate cleanly and report a
   confident wrong number. These tests re-derive every literal from ``params``
   and DR-0006's definition and fail on any disagreement.

2. **The quantities are definitions, not measurements.** ``P_avg``,
   ``E_dec`` and the half-window settledness criterion are arithmetic DR-0006
   states exactly; the manifest's ``measure`` strings are an implementation of
   them. These tests evaluate those committed expressions on synthetic
   ``.meas`` values -- the way ``sim/tools/klt_record.py`` does, ``eval`` with
   no builtins and its own ``MATH`` table -- so the three equivalent forms
   DR-0006 gives (``VDD*Q/(N*T)``, ``E_dec/T``, ``E_dec*f_clk``) are checked to
   agree, and so the sign discipline (a negative window integral is invalid,
   never clamped with ``abs()``) is checked to be fail-closed rather than
   stated.

A third group asserts the bench stays **unscored**: no ceiling on power or
charge, no corner-sensitivity (``*_spread_pct*``) check, and the 1-of-45
bring-up-probe wording present in the manifest ``claim`` and the bench README.

Stdlib only. No PDK, no ngspice, no klt, and nothing here reads a record.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SIM))

from harness import testbench as htb  # noqa: E402

BENCH = SIM / "comparator-avg-power"
BENCH_DIR = BENCH / "testbench"
REPO = SIM.parent

#: DR-0006's proposed condition, transcribed from the record's own tables
#: rather than read out of the manifest -- that is the point of the test.
DR0006 = {
    "f_clk": 16e6,            # "16 MHz (period 62.5 ns)"
    "t_per": 62.5e-9,
    "duty": 0.5,              # "50 %: 31.25 ns evaluate, 31.25 ns reset"
    "t_edge": 100e-12,        # "100 ps rise/fall as in the existing deck"
    "t_rise0": 10e-9,         # "Cycle 0 begins with the rising edge at t = 10 ns"
    "n_warm": 8,              # "the first 8 cycles (500 ns) are discarded"
    "n_win": 16,              # "N = 16 whole clock cycles (1.000 us)"
    "v_od": 10e-3,            # "Vod = 10 mV above/below the DUT's own trip point"
    "c_load": 20e-15,         # "20 fF to vss, the same on both"
    "t_setup": 20e-9,         # ">= 20 ns before the next rising edge"
    "half_window_pct": 1.0,   # "must agree within 1 %"
}


def _klt_record_math() -> dict:
    spec = importlib.util.spec_from_file_location(
        "_klt_record_for_avg_power_test", SIM / "tools" / "klt_record.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.MATH)


def _seconds(token: str) -> float:
    """``'1478.85n'`` -> ``1.47885e-06``. Only the suffixes the deck uses."""
    token = token.strip()
    scale = {"n": 1e-9, "u": 1e-6, "p": 1e-12, "m": 1e-3}.get(token[-1:])
    return float(token[:-1]) * scale if scale else float(token)


class AvgPowerManifest(unittest.TestCase):
    """Shared load + the param/DR-0006 correspondence."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tb = htb.load(BENCH_DIR)
        cls.math = _klt_record_math()
        cls.params = dict(cls.tb.params)
        cls.analyses = list(cls.tb.analyses)
        cls.fragment = cls.tb.netlist.read_text()

    # ---- params are DR-0006's numbers ---------------------------------
    def test_params_are_the_record_s_numbers(self) -> None:
        for key in ("f_clk", "t_per", "t_edge", "t_rise0", "n_warm", "n_win",
                    "v_od", "c_load", "t_setup"):
            with self.subTest(param=key):
                self.assertIn(key, self.params)
                self.assertAlmostEqual(
                    float(self.params[key]), DR0006[key],
                    delta=abs(DR0006[key]) * 1e-12 or 1e-18,
                )

    def test_period_duty_and_rate_are_self_consistent(self) -> None:
        p = self.params
        self.assertAlmostEqual(float(p["t_per"]) * float(p["f_clk"]), 1.0, places=12)
        self.assertAlmostEqual(
            float(p["t_hi"]) / float(p["t_per"]), DR0006["duty"], places=12
        )

    # ---- harness contract --------------------------------------------
    def test_params_define_no_harness_owned_name(self) -> None:
        htb.check_reserved_params(self.params, "test")
        for name in htb.RESERVED_PARAMS:
            self.assertNotIn(name, self.params)
        # dut_vos is referenced but never defined: the harness owns it, and it
        # is only defined at all because an offset_probe is declared.
        self.assertIn("dut_vos", self.fragment)
        self.assertTrue(self.tb.offset_probe)
        self.assertEqual(self.tb.offset_probe["measure"]["dut_vos"], "vos_v")


class WindowGeometry(AvgPowerManifest):
    """The literal `.meas` times must be DR-0006's window, exactly."""

    def _integ(self, vector: str) -> tuple[float, float]:
        pattern = re.compile(
            rf"^meas tran \w+ integ {re.escape(vector)} from=(\S+) to=(\S+)$"
        )
        hits = [m for m in (pattern.match(a) for a in self.analyses) if m]
        self.assertTrue(hits, f"no integ card over {vector}")
        return hits

    def test_window_is_a_whole_and_even_number_of_cycles(self) -> None:
        p = self.params
        t_per, n_win = float(p["t_per"]), float(p["n_win"])
        t0 = float(p["t_rise0"]) + float(p["n_warm"]) * t_per
        t1 = t0 + n_win * t_per
        for m in self._integ("i(vsupa)"):
            frm, to = _seconds(m.group(1)), _seconds(m.group(2))
            cycles = (to - frm) / t_per
            with self.subTest(card=m.group(0)):
                # Every supply-charge integral spans a whole number of cycles.
                self.assertAlmostEqual(cycles, round(cycles), places=9)
                self.assertGreater(round(cycles), 0)
                # ... and each boundary is the START of a rising edge.
                for edge in (frm, to):
                    k = (edge - float(p["t_rise0"])) / t_per
                    self.assertAlmostEqual(k, round(k), places=9)
        # The widest card is the window itself: N = 16 whole cycles, even, so
        # it holds a whole number of the two-cycle input-polarity period.
        widest = max(self._integ("i(vsupa)"),
                     key=lambda m: _seconds(m.group(2)) - _seconds(m.group(1)))
        self.assertAlmostEqual(_seconds(widest.group(1)), t0, places=15)
        self.assertAlmostEqual(_seconds(widest.group(2)), t1, places=15)
        self.assertEqual(round(n_win), DR0006["n_win"])
        self.assertEqual(round(n_win) % 2, 0)
        self.assertAlmostEqual(n_win * t_per, 1.0e-6, places=15)

    def test_warm_up_is_discarded_before_the_window_opens(self) -> None:
        p = self.params
        t0 = float(p["t_rise0"]) + float(p["n_warm"]) * float(p["t_per"])
        self.assertEqual(round(float(p["n_warm"])), DR0006["n_warm"])
        self.assertAlmostEqual(t0, 510e-9, places=15)
        starts = {_seconds(m.group(1)) for m in self._integ("i(vsupa)")}
        # Nothing is integrated before warm-up ends.
        self.assertGreaterEqual(min(starts), t0 - 1e-18)

    def test_the_two_halves_are_equal_and_partition_the_window(self) -> None:
        cards = sorted(self._integ("i(vsupa)"),
                       key=lambda m: _seconds(m.group(2)) - _seconds(m.group(1)))
        self.assertEqual(len(cards), 3, "expected q_win plus two halves")
        h1, h2, win = cards
        a1, b1 = _seconds(h1.group(1)), _seconds(h1.group(2))
        a2, b2 = _seconds(h2.group(1)), _seconds(h2.group(2))
        aw, bw = _seconds(win.group(1)), _seconds(win.group(2))
        self.assertAlmostEqual(b1 - a1, b2 - a2, places=15)   # equal length
        self.assertAlmostEqual(b1, a2, places=15)             # contiguous
        self.assertAlmostEqual(a1, aw, places=15)             # cover the window
        self.assertAlmostEqual(b2, bw, places=15)
        half_cycles = (b1 - a1) / float(self.params["t_per"])
        self.assertAlmostEqual(half_cycles, float(self.params["n_win"]) / 2, places=9)
        self.assertEqual(round(half_cycles), 8)               # DR-0006's halves

    def test_the_vi_cross_check_integrates_the_same_interval(self) -> None:
        win = max(self._integ("i(vsupa)"),
                  key=lambda m: _seconds(m.group(2)) - _seconds(m.group(1)))
        pwr = self._integ("v(pwr)")
        self.assertEqual(len(pwr), 1)
        self.assertAlmostEqual(_seconds(pwr[0].group(1)),
                               _seconds(win.group(1)), places=15)
        self.assertAlmostEqual(_seconds(pwr[0].group(2)),
                               _seconds(win.group(2)), places=15)

    def test_transient_reaches_the_end_of_the_window_and_no_further(self) -> None:
        tran = [a for a in self.analyses if a.startswith("tran ")]
        self.assertEqual(len(tran), 1)
        _, _tstep, tstop = tran[0].split()
        win = max(self._integ("i(vsupa)"),
                  key=lambda m: _seconds(m.group(2)) - _seconds(m.group(1)))
        # The window's last instant must be simulated, or the integral would
        # silently stop early...
        self.assertAlmostEqual(_seconds(tstop), _seconds(win.group(2)), places=15)
        # ... and no further, because the reset-completion search below uses
        # `fall=LAST` and is bounded only by the end of the transient. One more
        # evaluate phase in the run would hand it the wrong excursion.

    def test_decision_reads_land_inside_each_window_cycle_evaluate_phase(self) -> None:
        p = self.params
        t_per, t_hi = float(p["t_per"]), float(p["t_hi"])
        t_rise0, t_edge = float(p["t_rise0"]), float(p["t_edge"])
        n_warm, n_win = round(float(p["n_warm"])), round(float(p["n_win"]))
        pattern = re.compile(r"^meas tran d(\d+) find v\(dn\) at=(\S+)$")
        reads = {int(m.group(1)): _seconds(m.group(2))
                 for m in (pattern.match(a) for a in self.analyses) if m}
        self.assertEqual(sorted(reads), list(range(n_warm, n_warm + n_win)),
                         "one decision read per window cycle, and no other")
        for k, t in sorted(reads.items()):
            rise = t_rise0 + k * t_per
            fall = rise + t_hi            # the falling edge starts here
            with self.subTest(cycle=k):
                # Read at the END of the evaluate phase: after the rising edge
                # has completed, and before the falling edge begins.
                self.assertGreater(t, rise + t_edge)
                self.assertLess(t, fall)
                # "the end" means close to it, not the middle of the phase.
                self.assertLess(fall - t, 0.05 * t_hi)

    def test_reset_search_is_confined_to_the_last_reset_phase(self) -> None:
        p = self.params
        t_per, t_hi = float(p["t_per"]), float(p["t_hi"])
        t_rise0, t_edge = float(p["t_rise0"]), float(p["t_edge"])
        last = round(float(p["n_warm"])) + round(float(p["n_win"])) - 1
        fall_done = t_rise0 + last * t_per + t_hi + t_edge
        next_rise = t_rise0 + (last + 1) * t_per
        when = [a for a in self.analyses if " when v(irst)=" in a]
        self.assertEqual(len(when), 1)
        self.assertIn("fall=LAST", when[0],
                      "the LAST excursion is the settling instant, not the first")
        td = _seconds(re.search(r"td=(\S+)", when[0]).group(1))
        self.assertGreaterEqual(td, fall_done - 1e-18)
        self.assertLess(td, next_rise)
        # The quiescent reference it is thresholded against sits at the very
        # end of the same reset phase, after any precharge transient.
        avg = [a for a in self.analyses
               if a.startswith("meas tran i_q avg i(vsupa)")]
        self.assertEqual(len(avg), 1)
        frm = _seconds(re.search(r"from=(\S+)", avg[0]).group(1))
        to = _seconds(re.search(r"to=(\S+)", avg[0]).group(1))
        self.assertGreater(frm, td)
        self.assertLessEqual(to, next_rise)
        # ... and the threshold is a multiple of THAT measurement, so no
        # corner-dependent absolute current enters the measure.
        lets = [a for a in self.analyses if a.startswith("let i_rst_thr")]
        self.assertEqual(len(lets), 1)
        self.assertIn("i_q", lets[0])
        self.assertRegex(lets[0], r"-1\.1\*i_q\*1e6")

    def test_clock_edge_plumbing_card_spans_the_window_cycles(self) -> None:
        p = self.params
        n_warm = round(float(p["n_warm"]))
        last = n_warm + round(float(p["n_win"])) - 1
        pattern = re.compile(r"^meas tran t_e(lo|hi) when v\(clkn\)=0\.5 rise=(\d+)$")
        got = {m.group(1): int(m.group(2))
               for m in (pattern.match(a) for a in self.analyses) if m}
        # Cycle 0's rising edge is the 1st 0.5 crossing, so cycle k's is k+1.
        self.assertEqual(got, {"lo": n_warm + 1, "hi": last + 1})
        span = got["hi"] - got["lo"]
        self.assertEqual(self.tb.measure["clk_period_ns"],
                         f"(t_ehi-t_elo)/{span}*1e9")
        env = self.tb.checks["clk_period_ns"]
        t_per_ns = float(p["t_per"]) * 1e9
        self.assertLess(env["min"], t_per_ns)
        self.assertGreater(env["max"], t_per_ns)
        # The envelope is edge resolution, not a loose window.
        self.assertLess(env["max"] - env["min"], 0.001 * t_per_ns)


class StimulusTiming(AvgPowerManifest):
    """DR-0006's input-timing clause, read off the committed pulse statement."""

    def _stimulus_pulse(self) -> list[str]:
        text = re.sub(r"\n\+\s*", " ", self.fragment)          # join continuations
        line = next(l for l in text.splitlines()
                    if l.lower().startswith("vs ") and "pulse(" in l.lower())
        body = line[line.index("(") + 1:line.rindex(")")]
        return body.split()

    def _eval_param(self, expr: str) -> float:
        expr = expr.strip().strip("{}")
        env = {k: float(v) for k, v in self.params.items()}
        env["dut_vos"] = 0.0                                    # schematic DUT
        return float(eval(expr, {"__builtins__": {}}, env))     # noqa: S307

    def test_overdrive_is_symmetric_about_the_dut_s_own_trip_point(self) -> None:
        v1, v2 = (self._eval_param(x) for x in self._stimulus_pulse()[:2])
        v_od = float(self.params["v_od"])
        # Even cycles see +v_od (v1 is the pulse's initial value), odd -v_od.
        self.assertAlmostEqual(v1, +v_od, places=15)
        self.assertAlmostEqual(v2, -v_od, places=15)
        self.assertAlmostEqual(v_od, DR0006["v_od"], places=15)
        # Referred to dut_vos, so an extracted DUT gets a true +/- v_od ladder.
        self.assertIn("dut_vos", self._stimulus_pulse()[0])
        self.assertIn("dut_vos", self._stimulus_pulse()[1])

    def test_polarity_period_is_two_clock_cycles(self) -> None:
        per = self._eval_param(self._stimulus_pulse()[6])
        self.assertAlmostEqual(per, 2 * float(self.params["t_per"]), places=15)

    def test_every_sign_change_lands_in_reset_and_leaves_the_setup_time(self) -> None:
        _, _, td, tr, tf, pw, per = self._stimulus_pulse()
        td, tr, tf, pw, per = (self._eval_param(x) for x in (td, tr, tf, pw, per))
        p = self.params
        t_per, t_hi = float(p["t_per"]), float(p["t_hi"])
        t_rise0, t_edge, t_setup = (float(p["t_rise0"]), float(p["t_edge"]),
                                    float(p["t_setup"]))
        self.assertAlmostEqual(tr, t_edge, places=15)
        self.assertAlmostEqual(tf, t_edge, places=15)
        # ngspice pulse: v1 until td, ramp to v2 over tr, hold pw, ramp back
        # over tf, hold v1 until td+per. Transitions therefore begin at
        # td + m*per and td + tr + pw + m*per.
        n_cycles = round(float(p["n_warm"])) + round(float(p["n_win"])) + 1
        transitions = []
        for m in range(0, n_cycles // 2 + 2):
            transitions.append((td + m * per, td + m * per + tr))
            transitions.append((td + tr + pw + m * per,
                                td + tr + pw + m * per + tf))
        checked = 0
        for begin, end in transitions:
            if end > t_rise0 + n_cycles * t_per:
                continue
            k = math.ceil((end - t_rise0) / t_per)              # next rising edge
            next_rise = t_rise0 + k * t_per
            prev_fall_done = next_rise - t_per + t_hi + t_edge
            with self.subTest(transition=round(begin * 1e9, 4)):
                # Completed at least t_setup before the next rising edge ...
                self.assertGreaterEqual(next_rise - end, t_setup - 1e-18)
                # ... and begun after the preceding falling edge finished, so
                # the change is inside the reset (clk-low) phase.
                self.assertGreaterEqual(begin, prev_fall_done - 1e-18)
            checked += 1
        self.assertGreater(checked, 2 * round(float(p["n_win"])) // 2)

    def test_both_outputs_carry_the_same_explicit_load(self) -> None:
        loads = re.findall(r"^c\w+\s+(\S+)\s+0\s+\{(\w+)\}\s*$",
                           self.fragment, re.M | re.I)
        self.assertEqual({n.lower() for n, _ in loads}, {"dout", "doutb"})
        self.assertEqual({p for _, p in loads}, {"c_load"})
        self.assertAlmostEqual(float(self.params["c_load"]),
                               DR0006["c_load"], places=18)

    def test_bias_is_drawn_from_the_rail_the_integral_is_taken_at(self) -> None:
        # DR-0006's accounting boundary: the bias reference current's charge
        # is counted, and "no separate ibias supply is permitted".
        self.assertRegex(self.fragment, r"(?mi)^vsupa\s+vdda\s+0\s+dc\s+\{vdd_val\}")
        self.assertRegex(self.fragment, r"(?mi)^iba\s+vdda\s+\w+\s+dc\s+\{dut_ib\}")
        supplies = re.findall(r"(?mi)^(v\w+)\s+\S+\s+\S+\s+dc\s", self.fragment)
        self.assertEqual([s.lower() for s in supplies].count("vsupa"), 1)
        # Exactly one DUT instance hangs on that rail.
        duts = re.findall(r"(?mi)^(x\w+)\s+.*\bcomparator_dut\b.*$", self.fragment)
        self.assertEqual(len(duts), 1)


class PowerDefinitions(AvgPowerManifest):
    """Evaluate the committed ``measure`` expressions, as klt_record does."""

    #: Synthetic `.meas` values: a delivered (negative-in-ngspice) window
    #: charge split into two nearly-equal halves, at a 3.30 V rail.
    @staticmethod
    def _synthetic(q_total_c: float, imbalance: float = 0.0,
                   vsup: float = 3.30) -> dict:
        q_win = -q_total_c
        q_h1 = q_win / 2 * (1 + imbalance)
        q_h2 = q_win - q_h1
        return {
            "q_win": q_win, "q_h1": q_h1, "q_h2": q_h2,
            "vsup_v": vsup,
            # The v*i form: VDD is constant within a corner, so the energy is
            # exactly VDD * Q.
            "e_win": vsup * q_total_c,
            "q_clk": -1.0e-14, "i_q": -28.5e-6,
            "t_rst": 1.480e-6,
            "t_elo": 510.05e-9, "t_ehi": 1447.55e-9,
        }

    def _eval(self, name: str, env: dict) -> float:
        expr = self.tb.measure[name].replace("^", "**")
        return eval(expr, {"__builtins__": {}}, dict(self.math, **env))  # noqa: S307

    def test_p_avg_is_vdd_q_over_n_t(self) -> None:
        p = self.params
        n_win, t_per = float(p["n_win"]), float(p["t_per"])
        for q in (2.85e-11, 4.39e-11, 1.0e-10):
            env = self._synthetic(q)
            with self.subTest(q=q):
                want_uw = env["vsup_v"] * q / (n_win * t_per) * 1e6
                self.assertAlmostEqual(self._eval("p_avg_uw", env), want_uw,
                                       delta=abs(want_uw) * 1e-12)

    def test_e_dec_and_the_three_equivalent_power_forms_agree(self) -> None:
        p = self.params
        n_win, t_per, f_clk = (float(p["n_win"]), float(p["t_per"]),
                               float(p["f_clk"]))
        for q in (2.85e-11, 4.39e-11):
            env = self._synthetic(q)
            e_dec_j = env["vsup_v"] * q / n_win
            with self.subTest(q=q):
                e_fj = self._eval("e_dec_fj", env)
                self.assertAlmostEqual(e_fj, e_dec_j * 1e15,
                                       delta=abs(e_dec_j) * 1e15 * 1e-12)
                p_uw = self._eval("p_avg_uw", env)
                # DR-0006: P_avg = VDD*Q/(N*T) = E_dec/T = E_dec*f_clk.
                self.assertAlmostEqual(p_uw, e_dec_j / t_per * 1e6,
                                       delta=abs(p_uw) * 1e-12)
                self.assertAlmostEqual(p_uw, e_dec_j * f_clk * 1e6,
                                       delta=abs(p_uw) * 1e-12)
                # ... and the independent v*i integration path agrees.
                self.assertAlmostEqual(self._eval("p_avg_vi_uw", env), p_uw,
                                       delta=abs(p_uw) * 1e-12)
                self.assertLess(self._eval("p_avg_form_delta_pct", env), 1e-9)

    def test_e_dec_divides_by_the_declared_cycle_count(self) -> None:
        # The expression hard-codes N because an ngspice `let` cannot read a
        # `.param`; this is the guard against params.n_win drifting past it.
        self.assertIn(f"/{round(float(self.params['n_win']))}*1e15",
                      self.tb.measure["e_dec_fj"])

    def test_charge_is_delivered_positive_with_no_abs_and_no_subtraction(self) -> None:
        for name in ("q_win_pc", "q_half1_pc", "q_half2_pc", "p_avg_uw",
                     "e_dec_fj"):
            expr = self.tb.measure[name]
            with self.subTest(measure=name):
                # DR-0006: "a negative window integral is invalid, not clamped
                # with abs()" -- and no hard-coded static-current subtraction,
                # unlike the regeneration bench's e_dec_fj.
                self.assertNotIn("abs(", expr)
                self.assertNotIn("i_stat", expr)
                self.assertTrue(expr.startswith("-q_"), expr)
        env = self._synthetic(4.39e-11)
        self.assertGreater(self._eval("q_win_pc", env), 0.0)
        self.assertAlmostEqual(self._eval("q_win_pc", env), 43.9, places=9)

    def test_a_negative_window_integral_is_rejected_not_coerced(self) -> None:
        # An integral with the wrong sign (the source absorbing, i.e. a broken
        # measurement) must come out negative and trip the validity floor,
        # rather than being turned into a plausible positive power.
        bad = self._synthetic(-4.39e-11)
        self.assertLess(self._eval("q_win_pc", bad), 0.0)
        self.assertLess(self._eval("p_avg_uw", bad), 0.0)
        floor = self.tb.checks["q_win_pc"]["min"]
        self.assertEqual(floor, 0.0)
        self.assertLess(self._eval("q_win_pc", bad), floor)
        # The floor is the only bound on the quantity: no ceiling.
        self.assertNotIn("max", self.tb.checks["q_win_pc"])

    def test_half_window_settledness_is_dr0006_s_criterion(self) -> None:
        env = self._synthetic(4.39e-11, imbalance=0.0)
        self.assertAlmostEqual(self._eval("q_half_mismatch_pct", env), 0.0,
                               places=9)
        # |difference| / mean, in percent -- and abs() appears on the
        # difference only, which is the one place DR-0006 permits it.
        expr = self.tb.measure["q_half_mismatch_pct"]
        self.assertEqual(expr.count("abs("), 1)
        self.assertTrue(expr.startswith("abs(q_h2-q_h1)"))
        for imbalance in (0.002, 0.01, 0.05, -0.03):
            env = self._synthetic(4.39e-11, imbalance=imbalance)
            with self.subTest(imbalance=imbalance):
                # halves are mean*(1+i) and mean*(1-i): |delta|/mean = 2|i|
                self.assertAlmostEqual(self._eval("q_half_mismatch_pct", env),
                                       abs(imbalance) * 200, places=9)
        self.assertEqual(self.tb.checks["q_half_mismatch_pct"]["max"],
                         DR0006["half_window_pct"])
        # The bound is a miss criterion, so a 0.6 % imbalance (1.2 % mismatch)
        # must fail it rather than pass as "close enough".
        env = self._synthetic(4.39e-11, imbalance=0.006)
        self.assertGreater(self._eval("q_half_mismatch_pct", env),
                           self.tb.checks["q_half_mismatch_pct"]["max"])

    def test_the_halves_partition_check_catches_a_mis_split_window(self) -> None:
        env = self._synthetic(4.39e-11)
        self.assertAlmostEqual(self._eval("q_split_delta_pct", env), 0.0,
                               places=12)
        # A half that does not belong to the window shows up here.
        env["q_h2"] = env["q_h2"] * 0.9
        self.assertGreater(self._eval("q_split_delta_pct", env),
                           self.tb.checks["q_split_delta_pct"]["max"])

    def test_reset_margin_is_time_left_in_the_reset_phase(self) -> None:
        p = self.params
        t1 = float(p["t_rise0"]) + (float(p["n_warm"]) + float(p["n_win"])) * float(p["t_per"])
        env = self._synthetic(4.39e-11)
        got = self._eval("reset_margin_ns", env)
        self.assertAlmostEqual(got, (t1 - env["t_rst"]) * 1e9, places=9)
        # Bounded above by the reset phase itself.
        self.assertLess(got, float(p["t_hi"]) * 1e9 + 1e-9)
        # Unchecked on purpose: DR-0006 proposes no bound on it.
        self.assertNotIn("reset_margin_ns", self.tb.checks)

    def test_clk_period_is_derived_from_the_measured_edges(self) -> None:
        env = self._synthetic(4.39e-11)
        got = self._eval("clk_period_ns", env)
        self.assertAlmostEqual(got, float(self.params["t_per"]) * 1e9, places=9)


class DecisionCorrectness(AvgPowerManifest):
    """The per-cycle rollup must be fail-closed, not merely informative."""

    def _cycles(self) -> list[int]:
        n_warm = round(float(self.params["n_warm"]))
        return list(range(n_warm, n_warm + round(float(self.params["n_win"]))))

    def _eval_dec(self, reads: dict) -> float:
        expr = self.tb.measure["dec_cycles_correct"].replace("^", "**")
        env = dict(self.math, **{f"d{k:02d}": v for k, v in reads.items()})
        return eval(expr, {"__builtins__": {}}, env)   # noqa: S307

    @staticmethod
    def _correct(cycles: list[int]) -> dict:
        return {k: (1.0 if k % 2 == 0 else 0.0) for k in cycles}

    def test_every_window_cycle_appears_in_the_rollup(self) -> None:
        expr = self.tb.measure["dec_cycles_correct"]
        for k in self._cycles():
            with self.subTest(cycle=k):
                self.assertIn(f"d{k:02d}", expr)
        self.assertEqual(len(re.findall(r"\bd\d\d\b", expr)),
                         2 * len(self._cycles()))

    def test_all_correct_counts_the_full_window(self) -> None:
        cycles = self._cycles()
        self.assertAlmostEqual(self._eval_dec(self._correct(cycles)),
                               len(cycles), places=9)
        self.assertEqual(self.tb.checks["dec_cycles_correct"]["min"],
                         float(len(cycles)))

    def test_one_wrong_decision_is_counted_and_fails_the_floor(self) -> None:
        cycles = self._cycles()
        floor = self.tb.checks["dec_cycles_correct"]["min"]
        for k in cycles:
            reads = self._correct(cycles)
            reads[k] = 1.0 - reads[k]              # that cycle decided the wrong way
            with self.subTest(wrong_cycle=k):
                got = self._eval_dec(reads)
                self.assertAlmostEqual(got, len(cycles) - 1, places=9)
                self.assertLess(got, floor)

    def test_alternating_polarity_is_what_is_expected_per_cycle(self) -> None:
        # The stimulus is +v_od on even cycles: a run that held one answer for
        # every cycle must score half the window, not all of it.
        cycles = self._cycles()
        self.assertAlmostEqual(self._eval_dec({k: 1.0 for k in cycles}),
                               len(cycles) / 2, places=9)
        self.assertAlmostEqual(self._eval_dec({k: 0.0 for k in cycles}),
                               len(cycles) / 2, places=9)

    def test_a_metastable_read_is_non_finite_rather_than_a_tie(self) -> None:
        cycles = self._cycles()
        reads = self._correct(cycles)
        reads[cycles[0]] = 0.5                     # exactly on the threshold
        with self.assertRaises(ZeroDivisionError):
            self._eval_dec(reads)
        # In ngspice the same term is inf/nan, which harness.runner's
        # parse_measurements rejects, so the point fails as missing rather
        # than scoring a tie. Pin that rejection here too.
        from harness import runner as hr
        self.assertEqual(hr.parse_measurements("m_dec_cycles_correct = inf\n"), {})

    def test_per_cycle_checks_cover_every_window_cycle_with_the_right_sense(self) -> None:
        for k in self._cycles():
            spec = self.tb.checks[f"dout_c{k:02d}"]
            with self.subTest(cycle=k):
                if k % 2 == 0:
                    self.assertEqual(spec.get("min"), 0.9)
                    self.assertNotIn("max", spec)
                else:
                    self.assertEqual(spec.get("max"), 0.1)
                    self.assertNotIn("min", spec)
        # The first post-warm-up cycle is the one DR-0006 names explicitly.
        first = self.tb.checks[f"dout_c{self._cycles()[0]:02d}"]["description"]
        self.assertIn("first post-warm-up cycle", first)

    def test_complementary_output_is_checked_too(self) -> None:
        cycles = self._cycles()
        self.assertEqual(self.tb.checks[f"doutb_c{cycles[0]:02d}"]["max"], 0.1)
        self.assertEqual(self.tb.checks[f"doutb_c{cycles[-1]:02d}"]["min"], 0.9)


class StaysUnscored(AvgPowerManifest):
    """AC2: no pass/fail bound against the supply / power row, anywhere."""

    POWERISH = ("p_avg_uw", "p_avg_vi_uw", "e_dec_fj")

    def test_no_ceiling_on_any_power_or_energy_quantity(self) -> None:
        for name in self.POWERISH:
            self.assertIn(name, self.tb.measure)
            with self.subTest(measure=name):
                self.assertNotIn(name, self.tb.checks,
                                 "a bound here would score the supply/power row")
        # No check in the manifest carries a ceiling expressed in the row's
        # units (<= 1 mW target / <= 500 uW stretch).
        for name, spec in self.tb.checks.items():
            with self.subTest(check=name):
                self.assertNotIn(name, self.POWERISH)
                if name == "q_win_pc":
                    self.assertNotIn("max", spec)

    def test_no_corner_sensitivity_check_exists(self) -> None:
        # A single-point run has no spread to measure, and a *_spread_pct*
        # floor is a calibration-bearing bound this bench must not carry.
        for name, spec in self.tb.checks.items():
            for key in ("min_spread_pct", "max_spread_pct",
                        "min_spread_pct_by_axis", "max_spread_pct_by_axis"):
                with self.subTest(check=name, key=key):
                    self.assertNotIn(key, spec)

    #: What a check's own description must say about its status. A
    #: description may instead be the repo's back-reference idiom ("the same
    #: at 1 mV overdrive." in sim/comparator-regeneration/testbench/tb.json),
    #: in which case it inherits the statement of the check it refers to --
    #: so the group it belongs to must still have a full description
    #: somewhere, which the next test asserts.
    STATUS_RE = (r"not a spec bound|not the (supply/power )?row|functional|"
                 r"plumbing|floor only|a proxy|not a specification|"
                 r"settledness|implementation")
    BACKREF_RE = r"^the same (for|at) "

    def test_every_check_description_says_it_is_not_a_spec_bound(self) -> None:
        for name, spec in self.tb.checks.items():
            with self.subTest(check=name):
                desc = spec.get("description", "").lower()
                self.assertTrue(desc, "every check must explain itself")
                if re.match(self.BACKREF_RE, desc):
                    continue
                self.assertRegex(desc, self.STATUS_RE)

    def test_every_back_referencing_check_has_a_full_sibling(self) -> None:
        """A terse "the same for ..." may not be the only description of a group."""
        groups: dict[str, list[str]] = {}
        for name, spec in self.tb.checks.items():
            desc = spec.get("description", "").lower()
            prefix = re.sub(r"_c\d\d$", "", name)
            groups.setdefault(prefix, []).append(
                "backref" if re.match(self.BACKREF_RE, desc) else "full")
        for prefix, kinds in groups.items():
            with self.subTest(group=prefix):
                self.assertIn("full", kinds,
                              f"{prefix}: every check here only back-references")

    def test_claim_states_the_unscored_one_of_45_bring_up_status(self) -> None:
        claim = self.tb.claim
        low = claim.lower()
        self.assertIn("unscored", low + self.tb.description.lower())
        self.assertIn("not ratified", low)
        self.assertIn("1-of-45", low)
        self.assertIn("bring-up", low)
        self.assertIn("probe", low)
        self.assertIn("tt_27c_3.30v", low)
        self.assertIn("average_power_clock_rate_tbd", low)

    def test_bench_readme_states_the_same_status(self) -> None:
        readme = (BENCH / "README.md").read_text()
        low = readme.lower()
        self.assertIn("unscored", low)
        self.assertIn("1 of 45", low)
        self.assertIn("bring-up", low)
        self.assertIn("dr-0006", low)
        self.assertIn("not ratified", low)

    def test_the_scoring_surfaces_this_bench_must_not_touch(self) -> None:
        # AC2 / the issue's out-of-scope list, asserted against the tree so a
        # later edit cannot quietly score the row through these files.
        envelope = (REPO / "signoff" / "make_item5_envelope.py").read_text()
        self.assertIn("average_power_clock_rate_tbd", envelope)
        self.assertNotIn("comparator-avg-power", envelope)
        characterize = (REPO / "sim" / "characterize.sh").read_text()
        self.assertNotIn("comparator-avg-power", characterize)
        registry = (REPO / "spec" / "claim-registry.json").read_text()
        self.assertNotIn("comparator-avg-power", registry)
        self.assertNotIn("supply_avg_power_uw", registry.split('"claims"')[0]
                         if '"claims"' in registry else "")


if __name__ == "__main__":
    unittest.main()
