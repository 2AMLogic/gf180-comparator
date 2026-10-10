#!/usr/bin/env python3
"""PDK-free regressions for verify-report.py's wrapper --check step (#111).

Each case builds a temporary copy of just the files the two wrappers read
(netlist, the four cited item-5 records, the item-5 envelopes, the item-8
report and envelope, and the wrapper scripts), mutates the copy, and runs
``verify_wrappers(root)``. Committed evidence is never touched.

    python3 signoff/tests/test_verify_wrappers.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VERIFY = _load("verify_report_under_test", REPO_ROOT / "signoff" / "verify-report.py")
WRAP5 = _load("wrap5_under_test", REPO_ROOT / "signoff" / "make_item5_envelope.py")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_tree(root: Path) -> None:
    for rel in ("signoff/make_item5_envelope.py", "signoff/make_item8_envelope.py",
                WRAP5.NETLIST, "measurements/characterization-report.md",
                "measurements/characterization-report.item8.json"):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, dst)
    for bench, rid in WRAP5.RECORDS:
        rel = f"sim/{bench}/records/{rid}.json"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, root / rel)
    rel = f"sim/{WRAP5.OFFSET_TRAN_BENCH}/records/{WRAP5.OFFSET_TRAN_RECORD_ID}.json"  # #200
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / rel, root / rel)
    for rel in (WRAP5.output_path(), WRAP5.predecessor_path()):
        rel = rel.relative_to(REPO_ROOT)
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, root / rel)


class CommittedWrappers(unittest.TestCase):
    def test_committed_tree_passes(self) -> None:
        self.assertEqual(VERIFY.verify_wrappers(REPO_ROOT), [])


class FixtureDrift(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_tree(self.root)
        self.before = {p: _sha(p) for p in (REPO_ROOT / "sim").rglob("*.json")
                       if "records" in p.parts or "corner-matrix" in p.parts}

    def tearDown(self) -> None:
        self._tmp.cleanup()
        after = {p: _sha(p) for p in self.before}
        self.assertEqual(self.before, after)  # committed evidence untouched

    def test_fixture_copy_passes(self) -> None:
        self.assertEqual(VERIFY.verify_wrappers(self.root), [])

    def test_item5_source_record_drift_fails_with_netlist_unchanged(self) -> None:
        bench, rid = WRAP5.RECORDS[0]
        rec = self.root / f"sim/{bench}/records/{rid}.json"
        rec.write_text(rec.read_text() + "\n")
        problems = VERIFY.verify_wrappers(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("item 5 wrapper drift", problems[0])
        self.assertEqual(_sha(self.root / WRAP5.NETLIST), _sha(REPO_ROOT / WRAP5.NETLIST))

    def test_item5_envelope_value_edit_fails(self) -> None:
        env = self.root / WRAP5.output_path().relative_to(REPO_ROOT)
        env.write_text(env.read_text().replace('"status": "fail"', '"status": "pass"', 1))
        problems = VERIFY.verify_wrappers(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("item 5 wrapper drift", problems[0])

    def test_item8_report_drift_fails(self) -> None:
        rep = self.root / "measurements/characterization-report.md"
        rep.write_text(rep.read_text() + "\nedited\n")
        problems = VERIFY.verify_wrappers(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("item 8 wrapper drift", problems[0])

    def test_item8_envelope_edit_fails(self) -> None:
        env = self.root / "measurements/characterization-report.item8.json"
        data = json.loads(env.read_text())
        data["summary"] = "edited"
        env.write_text(json.dumps(data, indent=2) + "\n")
        problems = VERIFY.verify_wrappers(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("item 8 wrapper drift", problems[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
