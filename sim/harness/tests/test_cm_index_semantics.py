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


if __name__ == "__main__":
    unittest.main()
