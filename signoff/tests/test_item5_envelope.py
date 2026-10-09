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


class HistoricalEvidenceUnchanged(unittest.TestCase):
    def test_r1_envelope_bytes(self) -> None:
        r1 = load_wrapper(REPO_ROOT).predecessor_path()
        self.assertEqual(hashlib.sha256(r1.read_bytes()).hexdigest(), HISTORICAL_R1_SHA256)

    def test_source_records_match_successor_pins(self) -> None:
        wrapper = load_wrapper(REPO_ROOT)
        env = json.loads(wrapper.output_path().read_text())
        for src in env["source_records"]:
            data = (REPO_ROOT / src["path"]).read_bytes()
            self.assertEqual("sha256:" + hashlib.sha256(data).hexdigest(), src["content_hash"], src["path"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
