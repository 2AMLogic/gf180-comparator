#!/usr/bin/env python3
"""PDK-free regressions for signoff/make_item5_envelope.py (issue #108).

The central case: every *measured* ratified target passes (kickback
included, via a synthetic fixture -- committed evidence is never touched),
but the ratified average-power row is still unscored because its clock rate
is TBD. Item 5 must NOT grade ``met`` on that envelope.

No PDK, xschem or ngspice is needed: fixtures are copies of the committed
records in a temporary root, and the wrapper module's ``REPO_ROOT`` is
pointed there. The grader test additionally needs the pinned
``klayout-tools==0.6.0`` ``klt`` (CI's signoff job installs it); it looks
for ``$KLT``, then a ``klt`` beside this interpreter, then ``klt`` on PATH,
and is skipped -- loudly, by name -- when none is found.

Run from the repo root:

    python3 signoff/tests/test_item5_envelope.py
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "signoff" / "make_item5_envelope.py"
TIERS_DOC = REPO_ROOT / "signoff" / "design-evidence-tiers.md"

#: sha256 of the revision-1 (#91) envelope as committed -- historical
#: evidence that must stay byte-for-byte.
HISTORICAL_R1_SHA256 = "8748dce2fd35883c0dc586b6a6de8f2396d2256ae1f8f9c417c95ef81ef9c95a"


def load_wrapper(root: Path):
    spec = importlib.util.spec_from_file_location(f"item5_{id(root)}", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.REPO_ROOT = root
    return mod


def find_klt() -> str | None:
    env = os.environ.get("KLT")
    if env:
        return env
    sibling = Path(sys.executable).parent / "klt"
    if sibling.is_file():
        return str(sibling)
    return shutil.which("klt")


def make_fixture(root: Path, *, kickback_mv: float | None) -> None:
    """Copy the netlist and the four cited records into ``root``.

    ``kickback_mv`` (when given) overwrites every corner's
    ``kick_1k_peak_mv`` -- the one row that misses today -- so the fixture
    exercises the all-measured-targets-pass case without new simulation.
    """
    wrapper = load_wrapper(REPO_ROOT)
    (root / "design").mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / wrapper.NETLIST, root / wrapper.NETLIST)
    for bench, rid in wrapper.RECORDS:
        src = REPO_ROOT / "sim" / bench / "records" / f"{rid}.json"
        dst = root / "sim" / bench / "records" / f"{rid}.json"
        dst.parent.mkdir(parents=True)
        if bench == "comparator-kickback" and kickback_mv is not None:
            rec = json.loads(src.read_text())
            for p in rec["points"]:
                p["measurements"]["kick_1k_peak_mv"] = kickback_mv
            dst.write_text(json.dumps(rec, indent=2) + "\n")
        else:
            shutil.copyfile(src, dst)
    # The both-node kickback record revision 4 scores the kickback row on (#204).
    ksrc = REPO_ROOT / "sim" / wrapper.KICKBACK_BENCH / "records" / f"{wrapper.KICKBACK_BOTH_RECORD_ID}.json"
    kdst = root / "sim" / wrapper.KICKBACK_BENCH / "records" / ksrc.name
    if kickback_mv is not None:
        krec = json.loads(ksrc.read_text())
        for d in krec["derived"].values():
            d["kick_1k_peak_mv"] = kickback_mv
        kdst.write_text(json.dumps(krec, indent=2) + "\n")
    else:
        shutil.copyfile(ksrc, kdst)
    # The whole-comparator record revision 3 scores the offset row on (#200).
    tsrc = REPO_ROOT / "sim" / wrapper.OFFSET_TRAN_BENCH / "records" / f"{wrapper.OFFSET_TRAN_RECORD_ID}.json"
    tdst = root / "sim" / wrapper.OFFSET_TRAN_BENCH / "records" / tsrc.name
    tdst.parent.mkdir(parents=True)
    shutil.copyfile(tsrc, tdst)


def run_main(mod, *argv: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod.main(list(argv))
    return rc, out.getvalue() + err.getvalue()


class _FixtureCase(unittest.TestCase):
    kickback_mv: float | None = None

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fixture(self.root, kickback_mv=self.kickback_mv)
        self.mod = load_wrapper(self.root)
        self.env = self.mod.build_envelope()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def power_row(self) -> dict:
        rows = [r for r in self.env["spec_rows"] if r["name"] == self.mod.AVG_POWER_ROW]
        self.assertEqual(len(rows), 1)
        return rows[0]


class AllMeasuredTargetsPass(_FixtureCase):
    """Every measured target passes; average power is still unscored."""

    kickback_mv = 1.0  # inside the 5 mV target and 2 mV stretch

    def test_measured_rows_all_pass(self) -> None:
        self.assertEqual(self.env["failed"], 0)
        self.assertTrue(all(m["status"] == "pass" for m in self.env["measurements"]))
        self.assertEqual(self.env["eligibility"]["numerical"], "pass")

    def test_aggregate_is_not_passing(self) -> None:
        self.assertEqual(self.env["status"], "pass_partial")
        self.assertNotEqual(self.env["status"], "pass")
        self.assertEqual(self.env["eligibility"]["coverage"], "incomplete")
        self.assertFalse(self.env["eligibility"]["eligible"])
        self.assertEqual(self.env["passed"], 0)
        self.assertEqual(self.env["passed_partial"], 45)
        self.assertTrue(all(c["status"] == "pass_partial" for c in self.env["corners"]))

    def test_static_power_kept_per_corner_and_marked_partial(self) -> None:
        for c in self.env["corners"]:
            static = [m for m in c["measurements"] if m["name"] == self.mod.STATIC_POWER]
            self.assertEqual(len(static), 1, c["corner_id"])
            self.assertEqual(static[0]["partial_of"], self.mod.AVG_POWER_ROW)
            self.assertGreater(static[0]["value"], 0.0)
            self.assertEqual(c["unscored_rows"], [self.mod.AVG_POWER_ROW])
        names = {m["name"] for c in self.env["corners"] for m in c["measurements"]}
        self.assertNotIn("supply_power_uw", names)  # no row poses as average power
        self.assertNotIn(self.mod.AVG_POWER_ROW, names)

    def test_power_row_incomplete_not_failed(self) -> None:
        row = self.power_row()
        self.assertEqual(row["coverage"], "incomplete")
        self.assertIsNone(row["corners_within_target"])  # unknown, not a fake 0
        self.assertEqual(row["partial_evidence"]["measurement"], self.mod.STATIC_POWER)
        self.assertEqual(row["partial_evidence"]["corners_within_target"], 45)

    def test_coverage_block_records_skipped_row(self) -> None:
        cov = self.env["coverage"]
        self.assertTrue(cov["known"])
        self.assertFalse(cov["nothing_checked"])
        self.assertEqual(len(cov["skipped"]), 45)
        self.assertEqual({s["reason"] for s in cov["skipped"]}, {self.mod.AVG_POWER_SKIP_REASON})
        self.assertEqual(len(cov["checked"]), 45 * len(self.mod.MEASURED))
        self.assertEqual(cov["spec_rows_incomplete"], [self.mod.AVG_POWER_ROW])

    def test_pinned_grader_grades_item5_unmet(self) -> None:
        klt = find_klt()
        if klt is None:
            self.skipTest("pinned grader `klt` (klayout-tools==0.6.0) not found; set $KLT")
        rc, _ = run_main(self.mod)
        self.assertEqual(rc, 0)
        out = self.mod.output_path()
        manifest = {
            "block": "item5-fixture",
            "kind": "analog",
            "evidence": {
                "5": {
                    "file": out.relative_to(self.root).as_posix(),
                    "content_hash": self.env["provenance"]["input"]["content_hash"],
                }
            },
        }
        mpath = self.root / "signoff" / "block-manifest.json"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, indent=1) + "\n")
        proc = subprocess.run(
            [klt, "signoff", "--manifest", str(mpath), "--tiers-doc", str(TIERS_DOC), "--format", "json"],
            cwd=self.root, capture_output=True, text=True, check=False,
        )
        self.assertIn(proc.returncode, (0, 3), proc.stderr)
        report = json.loads(proc.stdout)
        item = [i for i in report["items"] if i["tier"] == "T1" and str(i["id"]) == "5"]
        self.assertEqual(len(item), 1)
        # The row itself, not the exit code (other unmet items also exit 3).
        self.assertEqual(item[0]["status"], "unmet", item[0])
        self.assertEqual(item[0]["reason"], "partial_coverage", item[0])


class KickbackMissStillDisclosesCoverage(_FixtureCase):
    """The committed state: kickback misses; the coverage gap is still stated."""

    kickback_mv = None  # records as committed

    def test_numerical_failure_takes_precedence(self) -> None:
        self.assertEqual(self.env["status"], "fail")
        self.assertEqual(self.env["eligibility"]["numerical"], "fail")
        self.assertEqual(self.env["eligibility"]["coverage"], "incomplete")
        self.assertFalse(self.env["eligibility"]["eligible"])
        self.assertEqual(self.env["failed"], 44)

    def test_bounds_and_clock_rate_untouched(self) -> None:
        row = self.power_row()
        self.assertEqual(row["target_max"], 1000.0)
        self.assertEqual(row["stretch_max"], 500.0)
        self.assertIsNone(row["clock_rate"])
        static = [m for m in self.env["measurements"] if m["name"] == self.mod.STATIC_POWER][0]
        self.assertEqual(static["limits"], {"max": 1000.0})

    def test_matches_committed_successor(self) -> None:
        committed = load_wrapper(REPO_ROOT).output_path()
        self.assertEqual(committed.read_text(), self.mod.envelope_text())


class GenerationContract(_FixtureCase):
    kickback_mv = None

    def test_write_repeat_check_and_refuse_overwrite(self) -> None:
        out = self.mod.output_path()
        self.assertTrue(out.name.endswith(f"-r{self.mod.SCORING_REVISION}.json"))
        self.assertNotEqual(out, self.mod.predecessor_path())
        rc, msg = run_main(self.mod, "--check")
        self.assertEqual(rc, 1, msg)  # not yet written
        rc, msg = run_main(self.mod)
        self.assertEqual(rc, 0, msg)
        first = out.read_bytes()
        rc, msg = run_main(self.mod)
        self.assertEqual((rc, "unchanged" in msg), (0, True), msg)
        self.assertEqual(out.read_bytes(), first)
        rc, msg = run_main(self.mod, "--check")
        self.assertEqual(rc, 0, msg)
        out.write_text(out.read_text().replace('"status": "fail"', '"status": "pass"', 1))
        tampered = out.read_bytes()
        rc, msg = run_main(self.mod, "--check")
        self.assertEqual(rc, 1, msg)
        rc, msg = run_main(self.mod)
        self.assertEqual(rc, 1, msg)
        self.assertIn("append-only", msg)
        self.assertEqual(out.read_bytes(), tampered)  # never overwritten

    def test_predecessor_never_written(self) -> None:
        run_main(self.mod)
        self.assertFalse(self.mod.predecessor_path().exists())


class InvalidSourceRefusal(unittest.TestCase):
    """Issue #126: validation is explicit, so it holds under ``python -O``.

    Each case mutates a temporary copy of the records, runs the copied
    wrapper as a subprocess (so REPO_ROOT is the temp tree) in ordinary and
    optimized modes, and requires exit 1, the offending bench/corner/field in
    stderr, and that no envelope file exists afterwards.
    """

    MODES = (
        ("plain", [], {}),
        ("-O", ["-O"], {}),
        ("-OO", ["-OO"], {}),
        ("PYTHONOPTIMIZE=1", [], {"PYTHONOPTIMIZE": "1"}),
    )
    OFF = "comparator-offset-mc"
    NOISE = "comparator-preamp-noise"
    REGEN = "comparator-regeneration"
    KICK = "comparator-kickback"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fixture(self.root, kickback_mv=None)
        (self.root / "signoff").mkdir()
        shutil.copyfile(SCRIPT, self.root / "signoff" / "make_item5_envelope.py")
        self.wrapper = load_wrapper(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def rec_path(self, bench: str) -> Path:
        rid = dict(self.wrapper.RECORDS)[bench]
        return self.root / "sim" / bench / "records" / f"{rid}.json"

    def mutate(self, bench: str, fn) -> None:
        p = self.rec_path(bench)
        rec = json.loads(p.read_text())
        fn(rec)
        p.write_text(json.dumps(rec, indent=2) + "\n")

    def run_wrapper(self, mode_args, extra_env, *argv):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONOPTIMIZE"}
        env.update(extra_env)
        return subprocess.run(
            [sys.executable, *mode_args, str(self.root / "signoff" / "make_item5_envelope.py"), *argv],
            capture_output=True, text=True, cwd=self.root, env=env,
        )

    def assert_refused(self, *needles: str) -> None:
        out = self.wrapper.output_path()
        for label, mode_args, extra in self.MODES:
            for argv in ((), ("--check",)):
                with self.subTest(mode=label, argv=argv):
                    proc = self.run_wrapper(mode_args, extra, *argv)
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    self.assertNotIn("Traceback", proc.stderr)
                    for n in needles:
                        self.assertIn(n, proc.stderr)
                    self.assertFalse(out.exists(), "invalid input must not write evidence")

    def test_valid_fixture_accepted_in_every_mode(self) -> None:
        for label, mode_args, extra in self.MODES:
            with self.subTest(mode=label):
                proc = self.run_wrapper(mode_args, extra)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.wrapper.output_path().unlink()

    def test_valid_envelope_byte_identical_to_committed(self) -> None:
        proc = self.run_wrapper(["-O"], {})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            self.wrapper.output_path().read_bytes(),
            load_wrapper(REPO_ROOT).output_path().read_bytes(),
        )

    def test_stale_hash_in_one_record(self) -> None:
        self.mutate(self.NOISE, lambda r: r["context"].update(dut_netlist_sha256="0" * 64))
        self.assert_refused(self.NOISE, "dut_netlist_sha256")

    def test_all_records_stale_vs_current_netlist(self) -> None:
        for b, _ in self.wrapper.RECORDS:
            self.mutate(b, lambda r: r["context"].update(dut_netlist_sha256="1" * 64))
        self.assert_refused("current", "design/comparator.spice")

    def test_netlist_changed_since_records(self) -> None:
        nl = self.root / self.wrapper.NETLIST
        nl.write_text(nl.read_text() + "* edited\n")
        self.assert_refused("dut_netlist_sha256", "stale")

    def test_failed_point_status(self) -> None:
        self.mutate(self.REGEN, lambda r: r["points"][7].update(status="error"))
        cid = json.loads(self.rec_path(self.REGEN).read_text())["points"][7]["corner_id"]
        self.assert_refused(f"{self.REGEN}/{cid}", "status")

    def test_omitted_corner(self) -> None:
        self.mutate(self.KICK, lambda r: r["points"].pop(10))
        self.assert_refused(self.KICK, "omitted corner")

    def test_duplicate_corner_keeps_count_at_45(self) -> None:
        def dup(r):
            r["points"][5] = dict(r["points"][4])
        self.mutate(self.OFF, dup)
        self.assert_refused(self.OFF, "duplicate corner_id", "omitted corner")

    def test_corner_outside_committed_matrix(self) -> None:
        self.mutate(self.OFF, lambda r: r["points"][0].update(corner_id="tt_85c_3.30v"))
        self.assert_refused(self.OFF, "tt_85c_3.30v")

    def test_inconsistent_pvt_coordinate(self) -> None:
        self.mutate(self.NOISE, lambda r: r["points"][3].update(vdd=3.0))
        self.assert_refused(self.NOISE, "field vdd")

    def test_inconsistent_temperature_and_process(self) -> None:
        self.mutate(self.KICK, lambda r: r["points"][0].update(temp_c=27.0, corner="ff"))
        self.assert_refused(self.KICK, "field temp_c", "field corner")

    def test_corner_order_disagreement(self) -> None:
        self.mutate(self.REGEN, lambda r: r["points"].reverse())
        self.assert_refused(self.REGEN, "order")

    def test_non_finite_measurement(self) -> None:
        # json.dumps writes a bare NaN token, which json.loads accepts.
        self.mutate(self.KICK, lambda r: r["points"][9]["measurements"].update(kick_1k_peak_mv=float("nan")))
        self.assertIn("NaN", self.rec_path(self.KICK).read_text())
        self.assert_refused(self.KICK, "kick_1k_peak_mv", "finite")

    def test_infinite_and_missing_measurement(self) -> None:
        def f(r):
            r["points"][2]["measurements"]["i_static_ua"] = float("inf")
            del r["points"][3]["measurements"]["td_od50_ns"]
        self.mutate(self.REGEN, f)
        self.assert_refused("i_static_ua", "td_od50_ns")

    def test_existing_envelope_not_modified_on_invalid_input(self) -> None:
        out = self.wrapper.output_path()
        self.assertEqual(self.run_wrapper([], {}).returncode, 0)
        before = out.read_bytes()
        self.mutate(self.NOISE, lambda r: r["points"][0].update(status="error"))
        for label, mode_args, extra in self.MODES:
            with self.subTest(mode=label):
                self.assertEqual(self.run_wrapper(mode_args, extra).returncode, 1)
                self.assertEqual(out.read_bytes(), before)


class WholeComparatorOffsetScoring(unittest.TestCase):
    """Issue #200: the offset row is scored on the full-grid whole-comparator
    record only with complete supported coverage and valid provenance; every
    degraded case becomes incomplete coverage, never a passing claim."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fixture(self.root, kickback_mv=1.0)  # every OTHER measured row passes
        self.mod = load_wrapper(self.root)
        self.tran = self.root / "sim" / self.mod.OFFSET_TRAN_BENCH / "records" / f"{self.mod.OFFSET_TRAN_RECORD_ID}.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def mutate(self, fn) -> None:
        rec = json.loads(self.tran.read_text())
        fn(rec)
        self.tran.write_text(json.dumps(rec, indent=2) + "\n")

    def offset_row(self, env) -> dict:
        return [r for r in env["spec_rows"] if r["name"] == self.mod.OFFSET_ROW][0]

    def assert_degraded(self, needle: str) -> dict:
        env = self.mod.build_envelope()  # must not raise
        row = self.offset_row(env)
        self.assertEqual(row["coverage"], "incomplete", row)
        self.assertEqual(row["coverage_reason"], self.mod.OFFSET_TRAN_SKIP_REASON)
        self.assertIn(needle, " ".join(row["problems"]))
        self.assertIsNone(row["corners_within_target"])
        self.assertNotEqual(env["status"], "pass")
        self.assertEqual(env["status"], "pass_partial")  # only coverage is missing
        self.assertFalse(env["eligibility"]["eligible"])
        self.assertIn(self.mod.OFFSET_ROW, env["eligibility"]["incomplete_rows"])
        reasons = {s["reason"] for s in env["coverage"]["skipped"]}
        self.assertIn(self.mod.OFFSET_TRAN_SKIP_REASON, reasons)
        self.assertTrue(all(self.mod.OFFSET_ROW in c["unscored_rows"] for c in env["corners"]))
        # Falls back to the preamp-only value, labelled as such (never as whole-comparator).
        self.assertTrue(all(
            m["scope"] == "preamp_only" for c in env["corners"] for m in c["measurements"]
            if m["name"] == self.mod.OFFSET_ROW))
        return env

    def test_full_grid_scored_with_disclosure(self) -> None:
        env = self.mod.build_envelope()
        row = self.offset_row(env)
        self.assertEqual((row["coverage"], row["scope"]), ("complete", "whole_comparator"))
        self.assertEqual(row["corners_total"], 45)
        self.assertEqual(row["draws_per_corner"], 200)
        self.assertEqual((row["target_max"], row["stretch_max"]), (15.0, 8.0))
        self.assertEqual(row["evidence_bench"], "comparator-offset-tran")
        self.assertEqual(row["corners_within_target"], 45)
        self.assertEqual(row["binding_corner"], "ff_125c_3.63v")
        self.assertIn("NOT simulated", row["composition"])
        self.assertEqual(row["preamp_only_diagnostic"]["evidence_bench"], "comparator-offset-mc")
        for c in env["corners"]:
            m = [x for x in c["measurements"] if x["name"] == self.mod.OFFSET_ROW][0]
            self.assertEqual(m["scope"], "whole_comparator")
            self.assertGreater(m["value"], m["simulated"]["vos_3sig_tran_mv"])  # derived term adds
            self.assertGreater(m["derived_not_simulated"]["load_r_1sigma_conservative_mv"], 0)
            self.assertEqual(m["simulated"]["n_samples"], 200)
            self.assertNotEqual(m["value"], m["diagnostic_preamp_only_3sigma_mv"])
        # Only the unrelated average-power row stays unscored.
        self.assertEqual(env["eligibility"]["incomplete_rows"], [self.mod.AVG_POWER_ROW])
        self.assertEqual(env["status"], "pass_partial")

    def test_source_record_pinned(self) -> None:
        env = self.mod.build_envelope()
        paths = [s["path"] for s in env["source_records"]]
        self.assertIn(self.tran.relative_to(self.root).as_posix(), paths)

    def test_missing_record_is_incomplete(self) -> None:
        self.tran.unlink()
        self.assert_degraded("no comparator-offset-tran record")

    def test_omitted_corner(self) -> None:
        self.mutate(lambda r: r["derived"].pop("sf_125c_3.63v"))
        self.assert_degraded("omitted corner")

    def test_missing_draws(self) -> None:
        self.mutate(lambda r: r["derived"]["tt_27c_3.30v"].update(n_samples=199))
        self.assert_degraded("tt_27c_3.30v: n_samples 199")

    def test_saturation_named_problem(self) -> None:
        def f(r):
            r["complete"], r["outcome"] = False, "incomplete"
            r["problems"] = ["TRIP_OUT_OF_RANGE: fs_-40c_2.97v/mc3 flipped in cycle 70 (level 68) outside 1..63"]
        self.mutate(f)
        self.assert_degraded("not complete")
        self.assert_degraded("TRIP_OUT_OF_RANGE")

    def test_non_finite_derivation(self) -> None:
        self.mutate(lambda r: r["derived"]["ss_125c_2.97v"].update(vos_3sig_total_cons_mv=float("nan")))
        self.assert_degraded("not a finite number")

    def test_dirty_or_uncitable_source(self) -> None:
        def f(r):
            r["citable"], r["dirty"] = False, True
            r["source_bundle"]["origin_dirty_paths"] = ["sim/tools"]
        self.mutate(f)
        self.assert_degraded("source provenance not valid")

    def test_stale_dut(self) -> None:
        self.mutate(lambda r: r["dut"].update(dut_netlist_sha256="0" * 64))
        self.assert_degraded("dut_netlist_sha256")

    def test_relaxed_bound_rejected(self) -> None:
        self.mutate(lambda r: r["spec_row"].update(target_max=20.0))
        self.assert_degraded("unchanged 15 / 8 mV bounds")

    def test_unrelated_failure_still_fails(self) -> None:
        # A degraded offset claim must not mask a measured miss elsewhere.
        kp = self.root / "sim/comparator-kickback/records" / f"{self.mod.KICKBACK_BOTH_RECORD_ID}.json"
        krec = json.loads(kp.read_text())
        for d in krec["derived"].values():
            d["kick_1k_peak_mv"] = 9.0
        kp.write_text(json.dumps(krec))
        self.tran.unlink()
        self.assertEqual(self.mod.build_envelope()["status"], "fail")


class BothNodeKickbackScoring(unittest.TestCase):
    """Issue #204: the kickback row is scored on the both-node record only if
    it validates; every degraded case falls back to the positive-node-only
    record with an explicit partial-node-coverage disclosure."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fixture(self.root, kickback_mv=None)
        self.mod = load_wrapper(self.root)
        self.rec = self.root / "sim" / self.mod.KICKBACK_BENCH / "records" / f"{self.mod.KICKBACK_BOTH_RECORD_ID}.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def mutate(self, fn) -> None:
        rec = json.loads(self.rec.read_text())
        fn(rec)
        self.rec.write_text(json.dumps(rec, indent=2) + "\n")

    def kick_row(self, env) -> dict:
        return [r for r in env["spec_rows"] if r["name"] == self.mod.KICKBACK_ROW][0]

    def kick_values(self, env) -> dict:
        return {c["corner_id"]: [m for m in c["measurements"] if m["name"] == self.mod.KICKBACK_ROW][0]
                for c in env["corners"]}

    def assert_fallback(self, needle: str) -> None:
        env = self.mod.build_envelope()  # must not raise
        row = self.kick_row(env)
        self.assertEqual(row["input_node_coverage"], "positive_node_only")
        self.assertTrue(row["partial_node_coverage"])
        self.assertEqual(row["fallback_reason"], self.mod.KICKBACK_FALLBACK_REASON)
        self.assertEqual(row["record_id"], dict(self.mod.RECORDS)["comparator-kickback"])
        self.assertIn(needle, " ".join(row["both_node_problems"]))
        self.assertTrue(env["kickback_source"]["partial_node_coverage"])
        self.assertTrue(all(m["partial_node_coverage"] for m in self.kick_values(env).values()))
        # Fallback values are the older record's, verbatim.
        old = json.loads((self.root / "sim/comparator-kickback/records"
                          / f"{dict(self.mod.RECORDS)['comparator-kickback']}.json").read_text())
        want = {p["corner_id"]: p["measurements"]["kick_1k_peak_mv"] for p in old["points"]}
        self.assertEqual({c: m["value"] for c, m in self.kick_values(env).items()}, want)
        # Ratified bounds and counts are unaffected.
        self.assertEqual((row["target_max"], row["stretch_max"]), (5.0, 2.0))
        self.assertEqual((row["corners_within_target"], row["corners_within_stretch"]), (1, 0))

    def test_both_node_record_used_when_valid(self) -> None:
        env = self.mod.build_envelope()
        row = self.kick_row(env)
        self.assertEqual(row["input_node_coverage"], "both")
        self.assertNotIn("partial_node_coverage", row)
        self.assertEqual(row["record_id"], self.mod.KICKBACK_BOTH_RECORD_ID)
        self.assertEqual((row["target_max"], row["stretch_max"]), (5.0, 2.0))
        self.assertEqual((row["corners_within_target"], row["corners_within_stretch"]), (1, 0))
        self.assertEqual(env["failed"], 44)
        rec = json.loads(self.rec.read_text())
        for cid, m in self.kick_values(env).items():
            self.assertEqual(m["value"], rec["derived"][cid]["kick_1k_peak_mv"])
        self.assertIn(f"{self.mod.KICKBACK_BOTH_RECORD_ID}.json", " ".join(s["path"] for s in env["source_records"]))

    def test_revision_suffix_and_name(self) -> None:
        self.assertEqual(self.mod.SCORING_REVISION, 4)
        out = self.mod.output_path()
        self.assertTrue(out.name.endswith("-r4.json"))
        self.assertIn(self.mod.KICKBACK_BOTH_RECORD_ID, out.name)
        self.assertEqual(self.mod.build_envelope()["scoring_revision"], 4)

    def test_older_envelopes_remain_committed(self) -> None:
        real = load_wrapper(REPO_ROOT)
        self.assertTrue(real.predecessor_path().is_file())
        self.assertTrue(real.supersedes_path().is_file())
        self.assertTrue(real.supersedes_path().name.endswith("-r3.json"))

    def test_shuffled_corner_keys_still_valid(self) -> None:
        self.mutate(lambda r: r.update(derived=dict(reversed(list(r["derived"].items())))))
        self.assertEqual(self.mod.validate_kickback_both(json.loads(self.rec.read_text())), [])

    def test_missing_record(self) -> None:
        self.rec.unlink()
        self.assert_fallback("no comparator-kickback record")

    def test_unparseable_record(self) -> None:
        self.rec.write_text("{not json")
        self.assert_fallback("not an object")

    def test_not_citable(self) -> None:
        self.mutate(lambda r: r.update(citable=False, not_citable_reasons=["dirty"]))
        self.assert_fallback("source provenance not valid")

    def test_partial_coverage(self) -> None:
        self.mutate(lambda r: r.update(input_node_coverage="positive"))
        self.assert_fallback("input_node_coverage")

    def test_omitted_corner(self) -> None:
        self.mutate(lambda r: r["derived"].pop("sf_125c_3.63v"))
        self.assert_fallback("omitted corner")

    def test_non_finite_value(self) -> None:
        self.mutate(lambda r: r["derived"]["tt_27c_3.30v"].update(kick_1k_peak_mv=float("nan")))
        self.assert_fallback("not a finite number")

    def test_stale_dut(self) -> None:
        self.mutate(lambda r: r["dut"].update(dut_netlist_sha256="0" * 64))
        self.assert_fallback("dut_netlist_sha256")

    def test_relaxed_bound_rejected(self) -> None:
        self.mutate(lambda r: r["spec_row"].update(target_max=10.0))
        self.assert_fallback("unchanged 5 / 2 mV bounds")

    def test_wrong_point_count(self) -> None:
        self.mutate(lambda r: r.update(expected_points=44))
        self.assert_fallback("expected_points")


class HistoricalEvidenceUnchanged(unittest.TestCase):
    def test_r1_envelope_bytes(self) -> None:
        r1 = load_wrapper(REPO_ROOT).predecessor_path()
        self.assertEqual(hashlib.sha256(r1.read_bytes()).hexdigest(), HISTORICAL_R1_SHA256)

    def test_r2_envelope_still_committed(self) -> None:
        self.assertTrue(load_wrapper(REPO_ROOT).supersedes_path().is_file())

    def test_source_records_match_successor_pins(self) -> None:
        wrapper = load_wrapper(REPO_ROOT)
        env = json.loads(wrapper.output_path().read_text())
        for src in env["source_records"]:
            data = (REPO_ROOT / src["path"]).read_bytes()
            self.assertEqual("sha256:" + hashlib.sha256(data).hexdigest(), src["content_hash"], src["path"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
