"""PDK-free coverage for the reverse-polarity regeneration ladder (issue #158).

The regeneration bench times the SECOND strobe's decision so no delay depends
on the power-up state. Issue #158 adds a mirrored ladder (positive first,
negative second) timing the HIGH->LOW decision. What can go wrong without a
simulator, and is pinned here:

* the existing forward cards/expressions drift (they feed signoff's
  ``td_od50_ns`` and DR-0005's ``tau_ps``);
* a reverse card picks the wrong transition (``rise`` instead of ``fall``) or
  the wrong window (no ``td``, or a ``td`` that admits the power-up
  resolution or the first decision) -- checked both structurally against
  the fragment's own clock/stimulus timing and behaviourally on synthetic
  waveforms with a small ngspice-``meas``-semantics evaluator;
* a missing reverse ingredient being silently dropped instead of failing
  the PVT point;
* a slower reverse direction being hidden, or leaking into the scored row.

Actual SPICE edge semantics are validated by
``sim/tools/regen_reverse_control.py`` (single PVT point, positive and
negative control). Stdlib only: no PDK, ngspice or klt.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

from harness import testbench as htb  # noqa: E402

import klt_record as kr  # noqa: E402
import mk_klt_request as mk  # noqa: E402
import regen_reverse_control as ctl  # noqa: E402

BENCH_DIR = SIM / "comparator-regeneration" / "testbench"

#: The forward cards and expressions as they were before issue #158. They are
#: what every existing record, signoff's item-5 envelope (td_od50_ns) and
#: DR-0005 (tau_ps) were computed from; #158 must not touch them.
FORWARD_ANALYSES = [
    "tran 5p 60n",
    "meas tran vsup_v find v(vdd) at=25n",
    "meas tran td_a trig v(clkn) val=0.5 rise=2 targ v(dan) val=0.5 rise=1 td=35n",
    "meas tran td_b trig v(clkn) val=0.5 rise=2 targ v(dbn) val=0.5 rise=1 td=35n",
    "meas tran td_c trig v(clkn) val=0.5 rise=2 targ v(dcn) val=0.5 rise=1 td=35n",
    "meas tran da_first find v(dan) at=18n",
    "meas tran db_first find v(dbn) at=18n",
    "meas tran dc_first find v(dcn) at=18n",
    "meas tran da_end find v(dan) at=55n",
    "meas tran db_end find v(dbn) at=55n",
    "meas tran dc_end find v(dcn) at=55n",
    "meas tran i_stat avg i(vsupa) from=25n to=29n",
    "meas tran q_dec integ i(vsupa) from=39.9n to=48n",
]
FORWARD_MEASURE = {
    "td_od50_ns": "td_a*1e9",
    "td_od1_ns": "td_b*1e9",
    "td_od01_ns": "td_c*1e9",
    "tau_ps": "(td_c-td_b)/ln(10)*1e12",
    "td_od1_over_tau": "td_b/((td_c-td_b)/ln(10))",
    "resolve_decades": "td_b/((td_c-td_b)/ln(10))",
    "dout_od50_end": "da_end",
    "dout_od1_end": "db_end",
    "dout_od01_end": "dc_end",
    "dout_od50_first": "da_first",
    "dout_od1_first": "db_first",
    "dout_od01_first": "dc_first",
    "i_static_ua": "abs(i_stat)*1e6",
    "e_dec_fj": "abs(q_dec - i_stat*8.1e-9)*vsup_v*1e15",
}
#: reverse instance -> (ladder rung param, forward twin, timing card, node)
REVERSE = {
    "ra": ("dv_big", "a", "tdr_a", "dran"),
    "rb": ("dv_mid", "b", "tdr_b", "drbn"),
    "rc": ("dv_tiny", "c", "tdr_c", "drcn"),
}

SI = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}


def si(tok: str) -> float:
    tok = tok.strip().lower()
    if tok and tok[-1] in SI:
        return float(tok[:-1]) * SI[tok[-1]]
    return float(tok)


# --------------------------------------------------------------------------- #
# A minimal evaluator of ngspice `.meas tran ... trig/targ` and `find ... at=`
# --------------------------------------------------------------------------- #

def parse_card(card: str) -> dict:
    """`meas tran NAME trig v(X) val=V rise|fall=N [td=T] targ ...` -> dict."""
    p = card.split()
    assert p[0] == "meas" and p[1] == "tran", card
    out = {"name": p[2]}
    if p[3] == "find":
        out["find"] = re.fullmatch(r"v\((\w+)\)", p[4]).group(1)
        out["at"] = si(p[5].split("=")[1])
        return out
    assert p[3] == "trig" and "targ" in p, card
    k = p.index("targ")
    for side, toks in (("trig", p[4:k]), ("targ", p[k + 1:])):
        d = {"node": re.fullmatch(r"v\((\w+)\)", toks[0]).group(1), "td": 0.0}
        for t in toks[1:]:
            key, val = t.split("=")
            if key in ("rise", "fall", "cross"):
                d["edge"], d["n"] = key, int(val)
            elif key == "val":
                d["val"] = float(val)
            elif key == "td":
                d["td"] = si(val)
            else:
                raise AssertionError(f"unknown token {t!r} in {card!r}")
        out[side] = d
    return out


def crossing(wave: list[tuple[float, float]], val: float, edge: str, n: int, td: float):
    """Time of the n-th `edge` crossing of `val` at or after `td`, or None."""
    seen = 0
    for (t0, v0), (t1, v1) in zip(wave, wave[1:]):
        if t1 < td:
            continue
        up = v0 < val <= v1
        down = v0 > val >= v1
        if (edge == "rise" and up) or (edge == "fall" and down) or (edge == "cross" and (up or down)):
            tc = t0 + (val - v0) * (t1 - t0) / (v1 - v0)
            if tc < td:
                continue
            seen += 1
            if seen == n:
                return tc
    return None


def value_at(wave, t):
    for (t0, v0), (t1, v1) in zip(wave, wave[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1
    return None


def evaluate(card: str, waves: dict):
    c = parse_card(card)
    if "find" in c:
        return value_at(waves[c["find"]], c["at"])
    tr, tg = c["trig"], c["targ"]
    a = crossing(waves[tr["node"]], tr["val"], tr["edge"], tr["n"], tr["td"])
    b = crossing(waves[tg["node"]], tg["val"], tg["edge"], tg["n"], tg["td"])
    return None if a is None or b is None else b - a


N = 1e-9
#: The fragment's strobe, supply-normalized: rises at 10 n and 40 n.
CLKN = [(0, 0), (10 * N, 0), (10.1 * N, 1), (20.1 * N, 1), (20.2 * N, 0),
        (40 * N, 0), (40.1 * N, 1), (50.1 * N, 1), (50.2 * N, 0), (60 * N, 0)]


def reverse_out(decide_at: float | None, startup_fall: bool = True):
    """Supply-normalized output of a mirrored instance. Power-up: starts at
    the metastable 0.6 and resolves LOW within 2 ns (a legitimate falling
    0.5-crossing). First strobe: decides HIGH at ~10.6 n. Second strobe:
    falls through 0.5 at `decide_at` (None: never -- the negative control)."""
    w = [(0, 0.6 if startup_fall else 1.0), (2 * N, 0.0 if startup_fall else 1.0),
         (10.4 * N, 0.0 if startup_fall else 1.0), (10.8 * N, 1.0)]
    if decide_at is None:
        return w + [(60 * N, 1.0)]
    return w + [(decide_at - 0.1 * N, 1.0), (decide_at + 0.1 * N, 0.0), (60 * N, 0.0)]


class ForwardUnchanged(unittest.TestCase):
    def setUp(self):
        self.tb = htb.load(BENCH_DIR)

    def test_forward_cards_are_byte_identical_and_first(self):
        self.assertEqual(list(self.tb.analyses[:len(FORWARD_ANALYSES)]), FORWARD_ANALYSES)

    def test_forward_expressions_unchanged(self):
        for k, v in FORWARD_MEASURE.items():
            with self.subTest(k=k):
                self.assertEqual(self.tb.measure[k], v)

    def test_forward_checks_unchanged_in_kind(self):
        # The anchor's per-axis floors stay where the sabotage control needs them.
        c = self.tb.checks["td_od50_ns"]
        self.assertEqual((c["min"], c["max"]), (0.001, 25.0))
        self.assertEqual(c["min_spread_pct_by_axis"], {"process": 8.0, "temperature": 10.0})
        # No reverse quantity carries a per-axis floor (it is not an anchor).
        for name, spec in self.tb.checks.items():
            if "_rev_" in name or name.startswith("tau_rev"):
                self.assertNotIn("min_spread_pct_by_axis", spec, name)

    def test_signoff_still_reads_forward_td_od50(self):
        spec = importlib.util.spec_from_file_location(
            "_item5_for_test", REPO / "signoff" / "make_item5_envelope.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        point = {"measurements": {"td_od50_ns": 0.7, "td_od50_rev_ns": 9.9}, "vdd": 3.3}
        self.assertEqual(mod._value("decision_time_od50_ns", point), 0.7)
        # and the fleet scorer still scores the forward measure
        self.assertEqual(kr.SPEC["comparator-regeneration"][1], "td_od50_ns")


class ReverseStructure(unittest.TestCase):
    """The reverse cards against the fragment's own timing."""

    @classmethod
    def setUpClass(cls):
        cls.tb = htb.load(BENCH_DIR)
        cls.text = cls.tb.netlist.read_text()
        cls.cards = {line.split()[2]: line for line in cls.tb.analyses[1:]}

    def _param(self, name):
        return si(re.search(rf"^\.param {name}=(\S+)", self.text, re.M).group(1))

    def test_mirrored_stimulus(self):
        for inst, (rung, twin, _, _) in REVERSE.items():
            with self.subTest(inst=inst):
                self.assertEqual(self.text.count(ctl.reverse_pwl(inst, rung)), 1)
                fwd = (f"vs{twin}  s{twin} 0 pwl(0 {{dut_vos-{rung}}} {{t_flip}} "
                       f"{{dut_vos-{rung}}} {{t_flip+1n}} {{dut_vos+{rung}}})")
                self.assertEqual(self.text.count(fwd), 1, "forward twin changed")

    def test_reverse_node_is_supply_normalized_output_of_reverse_instance(self):
        for inst, (_, _, _, node) in REVERSE.items():
            with self.subTest(inst=inst):
                self.assertRegex(self.text, rf"(?m)^X{inst}\s+ap{inst} an{inst} clk ibn{inst} dout{inst} \S+ vdd 0 comparator_dut$")
                self.assertRegex(self.text, rf"(?m)^B\w+\s+{node}\s+0 v = 'v\(dout{inst}\)/v\(vdd\)'$")

    def test_reverse_cards_select_second_strobe_falling_edge(self):
        for inst, (_, twin, name, node) in REVERSE.items():
            with self.subTest(card=name):
                c = parse_card(self.cards[name])
                f = parse_card(self.cards[f"td_{twin}"])
                self.assertEqual(c["targ"]["node"], node)
                self.assertEqual((c["targ"]["edge"], c["targ"]["n"], c["targ"]["val"]), ("fall", 1, 0.5))
                # identical trigger and window to the forward twin
                self.assertEqual(c["trig"], f["trig"])
                self.assertEqual(c["targ"]["td"], f["targ"]["td"])
                self.assertEqual((f["targ"]["edge"]), "rise")

    def test_window_excludes_startup_and_first_decision(self):
        m = re.search(r"(?m)^vclk clk 0 pulse\(0 \{vdd_val\} (\S+) (\S+) (\S+) (\S+) (\S+)\)$", self.text)
        delay, tr, tf, pw, per = (si(x) for x in m.groups())
        first_end = delay + tr + pw + tf
        second = delay + per
        settle = self._param("t_flip") + 1e-9
        for name in ("tdr_a", "tdr_b", "tdr_c"):
            with self.subTest(card=name):
                c = parse_card(self.cards[name])
                td = c["targ"]["td"]
                self.assertGreater(td, max(first_end, settle))
                self.assertLess(td, second)
                self.assertEqual(c["trig"]["n"], 2)  # the SECOND strobe edge
                self.assertEqual(c["trig"]["td"], 0.0)

    def test_state_samples_bracket_the_two_decisions(self):
        m = re.search(r"(?m)^vclk clk 0 pulse\(0 \{vdd_val\} (\S+) (\S+) (\S+) (\S+) (\S+)\)$", self.text)
        delay, tr, tf, pw, per = (si(x) for x in m.groups())
        tran_end = si(self.tb.analyses[0].split()[2])
        for inst in ("a", "b", "c"):
            first = parse_card(self.cards[f"dr{inst}_first"])
            end = parse_card(self.cards[f"dr{inst}_end"])
            self.assertEqual(first["find"], REVERSE["r" + inst][3])
            self.assertEqual(end["find"], REVERSE["r" + inst][3])
            self.assertTrue(delay < first["at"] < delay + tr + pw)          # inside strobe 1
            self.assertTrue(delay + per + tr + pw < end["at"] <= tran_end)  # after strobe 2

    def test_reverse_measures_and_checks(self):
        m, c = self.tb.measure, self.tb.checks
        self.assertEqual(m["td_od50_rev_ns"], "tdr_a*1e9")
        self.assertEqual(m["tau_rev_ps"], "(tdr_c-tdr_b)/ln(10)*1e12")
        self.assertEqual(m["dtd_od1_rev_ps"], "(tdr_b-td_b)*1e12")
        for r in ("od50", "od1", "od01"):
            self.assertEqual(c[f"dout_{r}_rev_first"]["min"], 0.9)
            self.assertEqual(c[f"dout_{r}_rev_end"]["max"], 0.1)
        # same sanity envelopes as the forward direction
        self.assertEqual((c["td_od50_rev_ns"]["min"], c["td_od50_rev_ns"]["max"]), (0.001, 25.0))
        self.assertEqual((c["tau_rev_ps"]["min"], c["tau_rev_ps"]["max"]),
                         (c["tau_ps"]["min"], c["tau_ps"]["max"]))

    def test_fleet_request_carries_every_reverse_card(self):
        names = [m["name"] for m in mk.tran_meas_cards(self.tb)]
        for n in ("tdr_a", "tdr_b", "tdr_c", "dra_first", "drc_end"):
            self.assertIn(n, names)
        self.assertEqual(names[:len(FORWARD_ANALYSES) - 1],
                         [c.split()[2] for c in FORWARD_ANALYSES[1:]])

    def test_negative_control_rewrite_applies_once_per_rung(self):
        out = ctl.suppress_reverse_flip(self.text)
        for inst, (rung, *_rest) in REVERSE.items():
            self.assertEqual(out.count(ctl.reverse_pwl(inst, rung)), 0)
            self.assertEqual(out.count(ctl.reverse_pwl(inst, rung, flip=False)), 1)
        with self.assertRaises(ValueError):
            ctl.suppress_reverse_flip(out)  # nothing left to suppress: loud


class ReverseWindowBehaviour(unittest.TestCase):
    """Committed cards on synthetic waveforms: the window/edge choice matters."""

    @classmethod
    def setUpClass(cls):
        tb = htb.load(BENCH_DIR)
        cls.cards = {line.split()[2]: line for line in tb.analyses[1:]}

    def _waves(self, out):
        return {"clkn": CLKN, "dran": out}

    def test_committed_card_times_second_decision(self):
        got = evaluate(self.cards["tdr_a"], self._waves(reverse_out(40.75 * N)))
        self.assertAlmostEqual(got, 0.70 * N, delta=1e-15)

    def test_unwindowed_card_would_latch_onto_power_up(self):
        bad = self.cards["tdr_a"].replace(" td=35n", "")
        got = evaluate(bad, self._waves(reverse_out(40.75 * N)))
        self.assertLess(got, 0)  # the power-up fall, a negative "delay"

    def test_window_admitting_first_decision_is_wrong(self):
        # A window opening before the first strobe sees the first decision's
        # RISE, never the timed fall -- with `cross` it would mis-time.
        bad = self.cards["tdr_a"].replace("fall=1 td=35n", "cross=1 td=5n")
        got = evaluate(bad, self._waves(reverse_out(40.75 * N)))
        self.assertLess(got, 0)

    def test_wrong_transition_finds_nothing(self):
        bad = self.cards["tdr_a"].replace("fall=1", "rise=1")
        self.assertIsNone(evaluate(bad, self._waves(reverse_out(40.75 * N))))

    def test_prevented_second_decision_yields_no_measurement(self):
        w = self._waves(reverse_out(None))
        self.assertIsNone(evaluate(self.cards["tdr_a"], w))
        self.assertGreater(evaluate(self.cards["dra_end"], w), 0.1)   # check fails
        self.assertGreaterEqual(evaluate(self.cards["dra_first"], w), 0.9)

    def test_state_samples(self):
        w = self._waves(reverse_out(40.75 * N))
        self.assertGreaterEqual(evaluate(self.cards["dra_first"], w), 0.9)
        self.assertLessEqual(evaluate(self.cards["dra_end"], w), 0.1)


def _raw(td_a=0.70e-9, td_b=0.90e-9, td_c=1.05e-9, slow=0.0, missing=()):
    """One corner's raw ingredients; the reverse direction `slow` s slower."""
    r = {
        "vsup_v": 3.3, "td_a": td_a, "td_b": td_b, "td_c": td_c,
        "da_first": 0.0, "db_first": 0.0, "dc_first": 0.0,
        "da_end": 1.0, "db_end": 1.0, "dc_end": 1.0,
        "i_stat": -30e-6, "q_dec": -1e-12,
        "tdr_a": td_a + slow, "tdr_b": td_b + slow, "tdr_c": td_c + slow,
        "dra_first": 1.0, "drb_first": 1.0, "drc_first": 1.0,
        "dra_end": 0.0, "drb_end": 0.0, "drc_end": 0.0,
    }
    for k in missing:
        r.pop(k)
    return r


class FleetIngest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tb = htb.load(BENCH_DIR)
        cls.request = {"corners": {"process": [{"name": "tt"}, {"name": "ss"}],
                                   "temperature_c": [27.0]},
                       "measurements": mk.tran_meas_cards(cls.tb)}

    def _report(self, per_corner):
        return {"corners": [
            {"corner_id": cid, "status": "pass",
             "measurements": [{"name": k, "value": v} for k, v in m.items()]}
            for cid, m in per_corner.items()]}

    def test_missing_reverse_ingredient_fails_the_point(self):
        rep = self._report({"tt/27C": _raw(), "ss/27C": _raw(missing=("tdr_b",))})
        ok, _bad, issues = kr.collect_checked(rep, self.request, 3.3)
        self.assertIn("tt_27c_3.30v", ok)
        self.assertNotIn("ss_27c_3.30v", ok)
        self.assertTrue(any(i.startswith("NONFINITE_INGREDIENT") and "tdr_b" in i for i in issues), issues)

    def test_slower_reverse_is_visible_and_forward_untouched(self):
        rep = self._report({"tt/27C": _raw(), "ss/27C": _raw(td_a=1.2e-9, slow=0.5e-9)})
        ok, _bad, issues = kr.collect_checked(rep, self.request, 3.3)
        self.assertEqual(issues, [])
        derived, problems = kr.derive("comparator-regeneration", self.tb, {"main": (ok, [])})
        self.assertEqual(problems, [])
        ss = derived["ss_27c_3.30v"]
        self.assertAlmostEqual(ss["td_od50_ns"], 1.2, places=9)        # forward as before
        self.assertAlmostEqual(ss["td_od50_rev_ns"], 1.7, places=9)    # reverse slower
        self.assertAlmostEqual(ss["dtd_od50_rev_ps"], 500.0, places=6)
        self.assertAlmostEqual(ss["dtau_rev_ps"], 0.0, places=6)
        self.assertAlmostEqual(derived["tt_27c_3.30v"]["dtd_od1_rev_ps"], 0.0, places=6)

        s = kr.reverse_polarity_summary(derived)
        self.assertFalse(s["scored"])
        r50 = next(r for r in s["rungs"] if r["rung"] == "50 mV")
        self.assertEqual(r50["reverse_binding"]["corner"], "ss_27c_3.30v")
        self.assertAlmostEqual(r50["reverse_binding"]["ns"], 1.7, places=9)
        self.assertAlmostEqual(r50["forward_binding"]["ns"], 1.2, places=9)
        self.assertEqual(r50["slower_direction_at_binding"], "reverse")
        self.assertAlmostEqual(r50["delta_ps"]["max"], 500.0, places=6)
        self.assertEqual(r50["delta_ps"]["max_corner"], "ss_27c_3.30v")
        self.assertEqual(s["polarity_proof_failing_corners"], [])
        lines = "\n".join(kr.reverse_polarity_lines(s))
        self.assertIn("NOT SCORED", lines)
        self.assertIn("ss_27c_3.30v", lines)

    def test_polarity_proof_failure_is_named(self):
        bad = _raw()
        bad["drc_end"] = 1.0  # 0.1 mV mirrored instance never went LOW
        rep = self._report({"tt/27C": _raw(), "ss/27C": bad})
        ok, _b, _i = kr.collect_checked(rep, self.request, 3.3)
        derived, _p = kr.derive("comparator-regeneration", self.tb, {"main": (ok, [])})
        s = kr.reverse_polarity_summary(derived)
        self.assertEqual(s["polarity_proof_failing_corners"], ["ss_27c_3.30v"])

    def test_pre_158_derived_has_no_supplement(self):
        old = {"tt_27c_3.30v": {k: 1.0 for k in FORWARD_MEASURE}}
        self.assertIsNone(kr.reverse_polarity_summary(old))
        self.assertEqual(kr.reverse_polarity_lines(None), [])


if __name__ == "__main__":
    unittest.main()
