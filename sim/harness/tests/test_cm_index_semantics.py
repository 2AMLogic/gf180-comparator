"""Monotonic-index common-mode stimulus (issue #218): PDK-free semantics and
request/ingest contract tests.

The ngspice fixture drives the REAL stimulus block of
``tb_offset_cm_index.spice`` and the REAL ``.meas`` cards that
``mk_klt_request.cm_index_measurements`` puts in the fleet request, into a toy
DUT whose output is deliberately asymmetric in (common mode, differential
input). Expected values are computed here independently of the bench's index
table. The fixture is a semantics check, not design evidence. It needs a local
single-corner ``ngspice -b`` and is skipped when ngspice is absent.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SIM / "tools"))

import cm_tolerance_probe as tp  # noqa: E402
import klt_record as kr  # noqa: E402
import mk_klt_request as mk  # noqa: E402
from harness import testbench as htb  # noqa: E402

BENCH = SIM / "comparator-offset-cm-index"
FRAG = BENCH / "testbench" / "tb_offset_cm_index.spice"
DUT = BENCH / "fixtures" / "semantics_dut.spice"

#: Independent of mk.CM_WINDOW_POINTS: the (vcmd, vd) the bench documents per k.
EXPECT_COORD = [(-0.1, 0.0), (-0.1, 2e-3), (0.0, 0.0), (0.0, 2e-3), (0.1, 0.0), (0.1, 2e-3)]


def toy_dd(x: float, vd: float) -> float:
    return 100 * vd + 3 * x + 40 * x * x - 3 * x * vd


def _between(text: str, tag: str) -> list[str]:
    out, on = [], False
    for line in text.splitlines():
        if f"END {tag}" in line:
            on = False
        if on:
            out.append(line)
        if f"BEGIN {tag}" in line:
            on = True
    return out


def run_fixture() -> dict[str, float]:
    text = FRAG.read_text()
    deck = ["* semantics fixture", ".param dut_vcm=1.65", *_between(text, "stimulus"), DUT.read_text(),
            *_between(text, "probe"), f".dc {mk.CM_INDEX_DC_ARGS}",
            *(m["spice"] for m in mk.cm_index_measurements()),
            ".control", "set measureprec=12", "set numdgt=12", "run", ".endc", ".end"]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "fixture.cir"
        p.write_text("\n".join(deck) + "\n")
        r = subprocess.run(["ngspice", "-b", str(p)], capture_output=True, text=True, timeout=120)
    got = {}
    for m in re.finditer(r"^(\w+)\s+=\s+(\S+)", r.stdout, re.M):
        got[m.group(1).lower()] = float(m.group(2))
    return got


@unittest.skipUnless(shutil.which("ngspice"), "ngspice not installed")
class IndexSemanticsFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.got = run_fixture()

    def test_all_eighteen_lookups_present_and_finite(self):
        for m in mk.cm_index_measurements():
            self.assertIn(m["name"], self.got, m["name"])
            self.assertTrue(math.isfinite(self.got[m["name"]]))

    def test_each_label_reads_its_own_index_and_coordinates(self):
        for label, (_, _, k) in mk.CM_WINDOW_POINTS.items():
            x, vd = EXPECT_COORD[k]
            self.assertAlmostEqual(self.got[f"xcm_{label}"], x, delta=1e-9, msg=label)
            self.assertAlmostEqual(self.got[f"xvd_{label}"], vd, delta=1e-9, msg=label)
            self.assertAlmostEqual(self.got[f"dv_{label}"], toy_dd(x, vd), delta=1e-6, msg=label)

    def test_asymmetric_outputs_distinguish_every_point(self):
        vals = [round(self.got[f"dv_{lab}"], 6) for lab in mk.CM_WINDOW_POINTS]
        self.assertEqual(len(set(vals)), 6)
        # +100 mV and -100 mV common modes are not mirror images in this fixture.
        self.assertNotAlmostEqual(self.got["dv_dn_0"], -self.got["dv_up_0"], places=3)

    def test_labels_follow_documented_k(self):
        self.assertEqual([k for _, _, k in mk.CM_WINDOW_POINTS.values()], list(range(6)))
        self.assertEqual([(c, d) for c, d, _ in mk.CM_WINDOW_POINTS.values()], EXPECT_COORD)


class IndexRequest(unittest.TestCase):
    def test_one_dc_analysis_per_draw_with_raw_meas_cards(self):
        leg = mk.cm_index_leg(5)
        self.assertEqual(leg["analysis"], {"kind": "dc", "args": "vidx 0 5 1"})
        self.assertEqual(leg["monte_carlo"], {"n": 5, "seed": 20260909, "vary": "mismatch"})
        ms = leg["measurements"]
        self.assertEqual(len(ms), 18)
        self.assertTrue(all(set(m) == {"name", "spice"} for m in ms))  # runs on a 0.5.0 runner
        for label, (_, _, k) in mk.CM_WINDOW_POINTS.items():
            self.assertIn(f".meas dc dv_{label} find v(dd) at={k}", [m["spice"] for m in ms])
            self.assertIn(f".meas dc xcm_{label} find v(xcm) at={k}", [m["spice"] for m in ms])
            self.assertIn(f".meas dc xvd_{label} find v(vd) at={k}", [m["spice"] for m in ms])

    def test_legs_for_selects_it_explicitly_and_nested_stays_refused(self):
        tb = htb.load(BENCH)
        self.assertEqual(mk.legs_for(mk.CM_INDEX_BENCH, tb, 3)["main"], mk.cm_index_leg(3))
        with self.assertRaises(SystemExit):
            mk.legs_for(mk.CM_WINDOW_BENCH, tb, 3)

    def test_bench_manifest_loads_with_index_sweep(self):
        tb = htb.load(BENCH)
        self.assertIn("dc vidx 0 5 1", [a.strip() for a in tb.analyses])
        self.assertTrue(tb.netlist.name.endswith("cm_index.spice"))

    def test_request_check_rejects_swapped_mapping_and_wrong_analysis(self):
        req = {"analysis": {"kind": "dc", "args": mk.CM_INDEX_DC_ARGS}, **{k: v for k, v in mk.cm_index_leg(4).items() if k != "analysis"}}
        self.assertEqual(kr.check_cm_index_request(req), [])
        bad = json.loads(json.dumps(req))
        for m in bad["measurements"]:
            if m["name"] == "dv_dn_0":
                m["spice"] = ".meas dc dv_dn_0 find v(dd) at=4"
        self.assertTrue(any("dv_dn_0" in i for i in kr.check_cm_index_request(bad)))
        bad = json.loads(json.dumps(req))
        bad["analysis"]["args"] = "vd 0 2m 2m vcmd -100m 100m 100m"
        self.assertTrue(kr.check_cm_index_request(bad))
        bad = json.loads(json.dumps(req))
        bad["measurements"][0] = {"name": "dv_dn_0", "expr": "v(dd)[0]"}
        self.assertTrue(kr.check_cm_index_request(bad))


def _draw(dvs=(0.0001, 0.0501, 0.0002, 0.0502, 0.0003, 0.0503), **over) -> list[dict]:
    vals = {}
    for (label, (vcmd, vd, _)), dv in zip(mk.CM_WINDOW_POINTS.items(), dvs):
        vals.update({f"dv_{label}": dv, f"xcm_{label}": vcmd, f"xvd_{label}": vd})
    vals.update(over)
    return [{"name": k, "value": v} for k, v in vals.items()]


def _report(n=2, drop=None, extra=None, runner="0.5.0"):
    cs = []
    for i in range(n):
        cs.append({"corner_id": f"tt/27C/mc{i}", "status": "pass",
                   "monte_carlo": {"sample_index": i}, "measurements": _draw()})
    for fn in (drop, extra):
        if fn:
            fn(cs)
    return {"environment": {"monte_carlo": {"n": n, "seed": 20260909, "vary": "mismatch"},
                            "remote": {"runner_klt_version": runner, "runner_compatibility": "match"}},
            "corners": cs}


def _req(n=2):
    return {"analysis": {"kind": "dc", "args": mk.CM_INDEX_DC_ARGS}, **{k: v for k, v in mk.cm_index_leg(n).items() if k != "analysis"},
            "corners": {"process": [{"name": "tt", "sections": []}], "temperature_c": [27.0]}}


class IndexIngest(unittest.TestCase):
    def collect(self, rep, req=None):
        return kr.collect_cm_index(rep, req or _req(), 3.3)

    def test_clean_report_collects_and_derives(self):
        s, issues = self.collect(_report())
        self.assertEqual(issues, [])
        self.assertEqual(sorted(s["tt_27c_3.30v"]), ["mc0", "mc1"])
        res, problems = kr.derive_cm_window(s)
        self.assertEqual(problems, [])
        self.assertAlmostEqual(res["tt_27c_3.30v"]["av_mid_mean"], 25.0, places=6)

    def test_runner_0_5_0_is_accepted_but_executor_must_be_named(self):
        _, issues = self.collect(_report())
        self.assertEqual(issues, [])
        rep = _report()
        del rep["environment"]["remote"]
        _, issues = self.collect(rep)
        self.assertTrue(any(i.startswith("UNSUPPORTED_EXECUTOR_CAPABILITY") for i in issues))

    def test_swapped_coordinates_rejected(self):
        def swap(cs):
            m = {x["name"]: x for x in cs[0]["measurements"]}
            m["xcm_dn_0"]["value"], m["xcm_up_0"]["value"] = m["xcm_up_0"]["value"], m["xcm_dn_0"]["value"]
        s, issues = self.collect(_report(drop=swap))
        self.assertTrue(any(i.startswith("COORDINATE_MISMATCH") for i in issues))
        self.assertNotIn("mc0", s.get("tt_27c_3.30v", {}))

    def test_vd_coordinate_swapped_rejected(self):
        def swap(cs):
            for x in cs[1]["measurements"]:
                if x["name"] == "xvd_mid_2m":
                    x["value"] = 0.0
        _, issues = self.collect(_report(drop=swap))
        self.assertTrue(any(i.startswith("COORDINATE_MISMATCH") for i in issues))

    def test_duplicate_and_missing_draws(self):
        _, issues = self.collect(_report(extra=lambda cs: cs.append(dict(cs[0]))))
        self.assertTrue(any(i.startswith("DUPLICATE_SAMPLE") for i in issues))
        s, issues = self.collect(_report(drop=lambda cs: cs.pop()))
        self.assertTrue(any(i.startswith("MISSING_SAMPLE") for i in issues))
        self.assertNotIn("mc1", s["tt_27c_3.30v"])

    def test_nonfinite_and_missing_values(self):
        for bad in (float("nan"), float("inf"), None):
            def edit(cs, bad=bad):
                for x in cs[0]["measurements"]:
                    if x["name"] == "dv_up_2m":
                        x["value"] = bad
            _, issues = self.collect(_report(drop=edit))
            self.assertTrue(any(i.startswith("NONFINITE_VALUE") for i in issues), bad)
        _, issues = self.collect(_report(drop=lambda cs: cs[0]["measurements"].pop()))
        self.assertTrue(any(i.startswith("INCOMPLETE_SAMPLE") for i in issues))

    def test_invalid_gain_drops_point(self):
        for dvs in ((0.0, 0.0, 0.0, 0.05, 0.0, 0.05), (0.0, -0.05, 0.0, 0.05, 0.0, 0.05)):
            rep = _report()
            rep["corners"][0]["measurements"] = _draw(dvs)
            s, issues = self.collect(rep)
            self.assertEqual(issues, [])
            res, problems = kr.derive_cm_window(s)
            self.assertTrue(any(p.startswith("INVALID_GAIN") for p in problems))
            self.assertNotIn("tt_27c_3.30v", res)

    def test_wrong_sample_index_and_unexpected_draw(self):
        def edit(cs):
            cs[0]["monte_carlo"] = {"sample_index": 1}
        _, issues = self.collect(_report(drop=edit))
        self.assertTrue(any(i.startswith("SAMPLE_IDENTITY_MISMATCH") for i in issues))
        _, issues = self.collect(_report(n=3), _req(2))
        self.assertTrue(any(i.startswith("UNEXPECTED_SAMPLE") for i in issues))

    def test_equal_seeds_across_requests_are_not_pairing(self):
        with self.assertRaises(SystemExit) as cm:
            kr.pair_cm_window_reports([_report(), _report()])
        self.assertIn("SEPARATE_REQUEST_PAIRING", str(cm.exception))


class MintPath(unittest.TestCase):
    def test_mint_requires_source_bundle_not_pending_refusal(self):
        import argparse
        with tempfile.TemporaryDirectory() as d:
            a = argparse.Namespace(bench=mk.CM_INDEX_BENCH, work=None, from_report=d, mc_n=200,
                                   dut=None, label="")
            with self.assertRaises(SystemExit) as cm:
                kr.mint_cm_index(a)
        self.assertIn("LEGACY_WORKDIR_UNBOUND", str(cm.exception))
        self.assertNotIn("RECORD_PATH_PENDING", str(cm.exception))


# ---------------------------------------------------------------------------
# Solver-tolerance probe (issue #240). Synthetic, PDK-free, independent of the
# probe's own derivation: expected values below are hand-derived.
# ---------------------------------------------------------------------------

#: Base draw (V). Gain at every common mode is (dv_2m - dv_0)/2 mV = 25 V/V, so
#: Vos_dn = -4 uV, Vos_mid = -8 uV, Vos_up = -12 uV and both endpoint shifts are
#: +4 uV / -4 uV. Asymmetric in every pair on purpose.
BASE_DV = {"dn_0": 1e-4, "dn_2m": 5.01e-2, "mid_0": 2e-4, "mid_2m": 5.02e-2, "up_0": 3e-4, "up_2m": 5.03e-2}
TOL_BODY = "* body\n.param a=1\n{cards}\n.include \"x.spice\"\n"


def _body(profile):
    return TOL_BODY.format(cards="\n".join(mk.tolerance_option_lines(profile)))


def _unit(shift_up0=0.0, **meta_over):
    """4 paired draws; only mc0 carries `shift_up0` V added to dv_up_0."""
    samples, replay = {}, {}
    for i in range(4):
        dv = dict(BASE_DV)
        dv["mid_0"] += i * 1e-5  # distinct draws
        dv["mid_2m"] += i * 1e-5
        if i == 0:
            dv["up_0"] += shift_up0
        samples[f"mc{i}"] = dv
        replay[f"mc{i}"] = {"sample_index": i, "seed": 100 + i, "process_seed": 7, "mismatch_seed": 900 + i}
    meta = {"origin_commit": "c" * 40, "dut_id": "d", "dut_netlist_sha256": "a", "binding_entry_sha256": "b",
            "testbench_netlist_sha256": "t", "testbench_manifest_sha256": "m", "engine_version": "46",
            "runner_klt_version": "0.5.0", "body_without_tolerance_sha256": "same"}
    meta.update(meta_over)
    return {"samples": samples, "replay": replay, "meta": meta}


def _probe_data(shifts=(0.0, 3e-9, 3e-9), pvts=("tt_27c_3.30v", "ss_125c_2.97v"), mutate=None):
    """shifts[i] is the cumulative dv_up_0 shift of profile i relative to baseline."""
    data = {prof: {pvt: _unit(sh) for pvt in pvts} for prof, sh in zip(mk.TOLERANCE_PROFILE_ORDER, shifts)}
    if mutate:
        mutate(data)
    return data


class ToleranceProfiles(unittest.TestCase):
    def test_profiles_are_ordered_progressively_tighter(self):
        names = list(mk.TOLERANCE_PROFILES)
        self.assertEqual(names[0], "baseline")
        self.assertGreaterEqual(len(names), 3)
        for a, b in zip(names, names[1:]):
            for (ka, va), (kb, vb) in zip(mk.TOLERANCE_PROFILES[a], mk.TOLERANCE_PROFILES[b]):
                self.assertEqual(ka, kb)
                self.assertLess(vb, va)
        self.assertEqual(mk.tolerance_option_lines("baseline"),
                         [".options reltol=0.001", ".options abstol=1e-12", ".options vntol=1e-06"])
        with self.assertRaises(SystemExit):
            mk.tolerance_option_lines("nope")

    def test_default_manifest_has_no_tolerance_options(self):
        self.assertEqual(list(htb.load(BENCH).options), [])

    def test_body_check_accepts_exact_cards_only(self):
        for prof in mk.TOLERANCE_PROFILES:
            tp.check_tolerance_body(_body(prof), prof)
        good = _body("tight")
        other = good.replace("reltol=1e-05", "reltol=0.001")
        bad = {
            "missing": "* body\n.param a=1\n",
            "duplicated": good + ".options reltol=1e-05\n",
            "reordered": good.replace(".options reltol=1e-05\n.options abstol=1e-14", ".options abstol=1e-14\n.options reltol=1e-05"),
            "wrong value": other,
            "nan": good.replace("reltol=1e-05", "reltol=nan"),
            "inf": good.replace("vntol=1e-09", "vntol=inf"),
            "wrong profile": _body("tighter"),
        }
        for what, body in bad.items():
            with self.assertRaises(tp.ProbeRefused, msg=what) as cm:
                tp.check_tolerance_body(body, "tight")
            self.assertEqual(cm.exception.code, "TOLERANCE_NOT_APPLIED", what)

    def test_executor_deck_must_include_netlist_without_own_tolerance(self):
        ok = "* klt\n.options seed=1\n.include /var/tmp/job/inputs/netlist.cir\n.temp 27.0\n"
        tp.check_deck_no_override(ok, "tight")
        for deck in (ok + ".options reltol=1e-3\n", ok.replace(".include /var/tmp/job/inputs/netlist.cir\n", "")):
            with self.assertRaises(tp.ProbeRefused):
                tp.check_deck_no_override(deck, "tight")

    def test_unknown_profile_refused(self):
        with self.assertRaises(tp.ProbeRefused):
            tp.check_tolerance_body(_body("tight"), "tightest")


@unittest.skipUnless(shutil.which("ngspice"), "needs the PDK install via find_pdk")
class ToleranceGeneration(unittest.TestCase):
    def test_generated_bodies_and_bundles_carry_each_profile(self):
        try:
            from harness import pdk as hpdk
            hpdk.find_pdk()
        except Exception:
            self.skipTest("gf180mcu PDK not installed")
        with tempfile.TemporaryDirectory() as td:
            bodies = {}
            for prof in mk.TOLERANCE_PROFILES:
                out = Path(td) / prof
                subprocess.run([sys.executable, str(SIM / "tools" / "mk_klt_request.py"), mk.CM_INDEX_BENCH, str(out),
                                "--corners", "tt", "--temps", "27", "--supply-v", "3.30", "--mc-n", "2",
                                "--tolerance-profile", prof], check=True, capture_output=True)
                body = (out / "body-v3.30.spice").read_text()
                tp.check_tolerance_body(body, prof)
                bundle = json.loads((out / "source-bundle.json").read_text())
                self.assertEqual(bundle["parameters"]["tolerance_profile"]["name"], prof)
                self.assertEqual(bundle["parameters"]["tolerance_profile"]["cards"], mk.tolerance_option_lines(prof))
                bodies[prof] = body
            stripped = {tp._strip_tolerance(b).replace("\n\n", "\n") for b in bodies.values()}
            self.assertEqual(len(stripped), 1)
            out = Path(td) / "default"
            subprocess.run([sys.executable, str(SIM / "tools" / "mk_klt_request.py"), mk.CM_INDEX_BENCH, str(out),
                            "--corners", "tt", "--temps", "27", "--supply-v", "3.30", "--mc-n", "2"],
                           check=True, capture_output=True)
            self.assertNotIn("reltol", (out / "body-v3.30.spice").read_text())
            self.assertNotIn("tolerance_profile", json.loads((out / "source-bundle.json").read_text())["parameters"])


class ToleranceMath(unittest.TestCase):
    def test_hand_derived_deltas(self):
        res = tp.run_analysis(_probe_data(shifts=(0.0, 3e-9, 3e-9)))
        pt = res["analysis"]["baseline->tight"]["per_pvt"]["tt_27c_3.30v"]
        self.assertAlmostEqual(pt["dv_up_0"]["per_draw"]["mc0"], 3e-9, delta=1e-18)
        self.assertEqual(pt["dv_up_0"]["per_draw"]["mc1"], 0.0)
        self.assertAlmostEqual(pt["av_up"]["per_draw"]["mc0"], -1.5e-6, delta=1e-12)
        self.assertAlmostEqual(pt["dvos_up"]["per_draw"]["mc0"], -1.2072e-10, delta=2e-13)
        self.assertEqual(pt["dvos_dn"]["per_draw"]["mc0"], 0.0)
        self.assertEqual(pt["vos_mid"]["max_abs"], 0.0)
        self.assertEqual(pt["dv_dn_0"]["unit"], "V")
        self.assertEqual(pt["av_up"]["unit"], "V/V")
        # tight -> tighter did not move anything
        self.assertEqual(res["analysis"]["tight->tighter"]["max_abs_over_all"]["dvos_up"], 0.0)
        self.assertEqual(res["classification"], "stable")

    def test_sign_follows_later_minus_earlier(self):
        res = tp.run_analysis(_probe_data(shifts=(3e-9, 0.0, 0.0)))
        d = res["analysis"]["baseline->tight"]["per_pvt"]["tt_27c_3.30v"]
        self.assertAlmostEqual(d["dv_up_0"]["per_draw"]["mc0"], -3e-9, delta=1e-18)
        self.assertGreater(d["dvos_up"]["per_draw"]["mc0"], 0)

    def test_non_converged_fixture_cannot_pass(self):
        # last step moves dv_up_0 by 5 uV -> |d dvos_up| ~ 2e-7 V > T = 1e-7 V
        res = tp.run_analysis(_probe_data(shifts=(0.0, 3e-9, 3e-9 + 5e-6)))
        self.assertAlmostEqual(res["analysis"]["tight->tighter"]["max_abs_over_all"]["dvos_up"], 2.0e-7, delta=2e-9)
        self.assertEqual(res["classification"], "inconclusive")

    def test_tolerance_dominated_when_only_baseline_moves(self):
        res = tp.run_analysis(_probe_data(shifts=(0.0, 5e-6, 5e-6)))
        self.assertGreater(res["analysis"]["baseline->tighter"]["max_abs_over_all"]["dvos_up"], tp.CONVERGENCE_THRESHOLD_V)
        self.assertEqual(res["classification"], "tolerance-dominated")

    def test_identical_profiles_do_not_look_converged(self):
        res = tp.run_analysis(_probe_data(shifts=(0.0, 0.0, 0.0)))
        self.assertEqual(res["classification"], "inconclusive")
        self.assertIn("not evidenced", res["classification_reason"])

    def test_threshold_is_predeclared_constant(self):
        self.assertEqual(tp.CONVERGENCE_THRESHOLD_V, 1e-7)
        self.assertEqual(sorted(tp.CLASSES), ["inconclusive", "stable", "tolerance-dominated"])


class ToleranceGates(unittest.TestCase):
    def refused(self, code, **kw):
        with self.assertRaises(tp.ProbeRefused) as cm:
            tp.run_analysis(_probe_data(**kw))
        self.assertEqual(cm.exception.code, code)

    def test_missing_configurations(self):
        with self.assertRaises(tp.ProbeRefused) as cm:
            tp.run_analysis({k: v for k, v in _probe_data().items() if k != "tighter"})
        self.assertEqual(cm.exception.code, "MISSING_PROFILE")
        with self.assertRaises(tp.ProbeRefused):
            tp.run_analysis({k: v for k, v in _probe_data().items() if k != "tight"})
        self.refused("MISSING_PVT", pvts=("tt_27c_3.30v",))

    def test_pvt_set_must_match(self):
        self.refused("PVT_MISMATCH", mutate=lambda d: d["tight"].pop("ss_125c_2.97v"))

    def test_unpaired_draws(self):
        self.refused("UNPAIRED_DRAWS", mutate=lambda d: d["tight"]["tt_27c_3.30v"]["samples"].pop("mc3"))

        def reroll(d):
            d["tight"]["tt_27c_3.30v"]["replay"]["mc1"]["mismatch_seed"] = 12345
        self.refused("UNPAIRED_DRAWS", mutate=reroll)

    def test_equal_request_seed_alone_is_insufficient(self):
        def strip(d):
            for u in d["tighter"].values():
                for r in u["replay"].values():
                    r.pop("mismatch_seed")
        self.refused("REPLAY_IDENTITY_UNSUPPORTED", mutate=strip)

    def test_midpoint_not_reproduced_refuses_even_with_equal_seeds(self):
        def reroll_values(d):
            d["tight"]["tt_27c_3.30v"]["samples"]["mc2"]["mid_0"] += 5e-3  # a different realization
        self.refused("MIDPOINT_NOT_REPRODUCED", mutate=reroll_values)

    def test_coordinate_drift(self):
        self.refused("COORDINATE_DRIFT", mutate=lambda d: d["tight"]["tt_27c_3.30v"]["samples"]["mc0"].pop("up_2m"))

    def test_identity_drift(self):
        for key, val in (("dut_netlist_sha256", "zz"), ("engine_version", "45"), ("runner_klt_version", "0.7.0"),
                         ("testbench_manifest_sha256", "q"), ("origin_commit", "d" * 40)):
            self.refused("IDENTITY_MISMATCH", mutate=lambda d, k=key, v=val: d["tighter"]["tt_27c_3.30v"]["meta"].__setitem__(k, v))
        self.refused("DECK_DRIFT", mutate=lambda d: d["tight"]["tt_27c_3.30v"]["meta"].__setitem__("body_without_tolerance_sha256", "x"))

    def test_nonfinite_values(self):
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(tp.ProbeRefused):
                tp.run_analysis(_probe_data(mutate=lambda d, b=bad: d["tight"]["tt_27c_3.30v"]["samples"]["mc0"].__setitem__("up_0", b)))

    def test_invalid_gain(self):
        def flat(d):
            s = d["tight"]["tt_27c_3.30v"]["samples"]["mc0"]
            s["mid_2m"] = s["mid_0"]
        self.refused("INVALID_GAIN", mutate=flat)

    def test_too_few_draws(self):
        def trim(d):
            for p in d.values():
                for u in p.values():
                    for k in ("samples", "replay"):
                        for mc in ("mc2", "mc3"):
                            u[k].pop(mc)
        self.refused("TOO_FEW_DRAWS", mutate=trim)


class ToleranceSelection(unittest.TestCase):
    def test_hot_point_rule_on_synthetic_record(self):
        rec = {"derived": {
            "tt_27c_3.30v": {"sig_dvos_dn_uv": 9.0, "sig_dvos_up_uv": 9.0},  # cooler: ignored whatever its spread
            "ss_125c_2.97v": {"sig_dvos_dn_uv": 0.4, "sig_dvos_up_uv": 1.13},
            "tt_125c_3.30v": {"sig_dvos_dn_uv": 0.9, "sig_dvos_up_uv": 0.2},
            "ff_125c_3.63v": {"sig_dvos_dn_uv": 1.13, "sig_dvos_up_uv": 0.1}}}
        hot = tp.select_hot_point(rec)
        self.assertEqual(hot["key"], "ff_125c_3.63v")  # tie at 1.13 -> corner id order
        self.assertEqual((hot["process"], hot["temperature_c"], hot["supply_v"]), ("ff", 125.0, 3.63))
        self.assertEqual([p["key"] for p in tp.probe_points(rec)], ["tt_27c_3.30v", "ff_125c_3.63v"])
        with self.assertRaises(tp.ProbeRefused):
            tp.select_hot_point({"derived": {}})

    def test_committed_record_selects_ss_125c_2p97(self):
        rec = json.loads(next((BENCH / "records").glob("20261010-130605300890-d8e9253.json")).read_text())
        self.assertEqual(tp.select_hot_point(rec)["key"], "ss_125c_2.97v")


class ToleranceArtifact(unittest.TestCase):
    def test_refusal_artifact_has_no_numbers_and_is_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            plan = {"points": [{"key": "tt_27c_3.30v"}], "draws": 8, "hot_rule": "r"}
            root = Path(td) / "root"
            (root / "baseline").mkdir(parents=True)
            (root / "baseline" / "a.json").write_text("{}")
            e = tp.ProbeRefused("REPLAY_IDENTITY_UNSUPPORTED", "no seeds")
            rid = tp.write_artifact(root, plan, None, None, e, exp=exp)
            rec = json.loads((exp / "records" / f"{rid}.json").read_text())
            self.assertEqual(rec["outcome"], "refused")
            self.assertIsNone(rec["classification"])
            self.assertNotIn("analysis", rec)
            self.assertEqual(rec["verdict"], "Unknown")
            self.assertFalse(rec["scored"])
            self.assertTrue((exp / "probes" / rid / "baseline" / "a.json").is_file())

    def test_compared_artifact_records_threshold_and_classification(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            data = _probe_data()
            res = tp.run_analysis(data)
            root = Path(td) / "root"
            root.mkdir()
            rid = tp.write_artifact(root, {"points": [], "draws": 4, "hot_rule": "r"}, data, res, None, exp=exp)
            rec = json.loads((exp / "records" / f"{rid}.json").read_text())
            self.assertEqual(rec["classification"], "stable")
            self.assertEqual(rec["threshold_v"], 1e-7)
            self.assertIn("raw_dv_v", rec)
            self.assertIn("replay_identity", rec)
            self.assertEqual(rec["verdict"], "Unknown")


if __name__ == "__main__":
    unittest.main()
