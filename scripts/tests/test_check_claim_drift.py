#!/usr/bin/env python3
"""PDK-free fixture tests for scripts/check_claim_drift.py (#245). Builds temp
trees; never touches the real docs or records.

    python3 scripts/tests/test_check_claim_drift.py
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location(
    "ccd", REPO / "scripts" / "check_claim_drift.py")
CCD = importlib.util.module_from_spec(_s)
_s.loader.exec_module(CCD)

B = "comparator-demo"
OLD, NEW = "20260101-000000-aaaaaaa", "20260201-000000-bbbbbbb"
DUT = {"dut_id": "d1", "dut_netlist_sha256": "ab"}


def rec(root, rid, peak, dut=DUT, md=True):
    d = Path(root) / "sim" / B / "records"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}.json").write_text(json.dumps({
        "dut": dut,
        "derived": {"tt": {"m": peak}, "ff": {"m": peak + 1.0}}}))
    if md:
        (d / f"{rid}.md").write_text("# record\n")


def build(root, readme=None, cited=OLD, newer=None, newer_dut=DUT,
          literal="3.146 mV worst ff", registry=None, md=True):
    root = Path(root)
    rec(root, OLD, 2.146, md=md)
    if newer:
        rec(root, newer, 9.0, dut=newer_dut)
    cite = f"sim/{B}/records/{cited}.md"
    (root / "README.md").write_text(
        readme if readme is not None else f"Result 3.146 mV worst ff ({cite}).\n")
    (root / "spec").mkdir()
    (root / "spec" / "evidence-ledger.md").write_text("ledger\n")
    (root / "spec" / "consumers.md").write_text("consumers\n")
    claim = {"id": "c1", "doc": "README.md", "literal": literal,
             "record": f"sim/{B}/records/{OLD}.json",
             "pointer": "/derived/*/m", "agg": "max", "decimals": 3,
             "corner": "ff"}
    (root / "spec" / "claim-registry.json").write_text(json.dumps(
        registry if registry is not None else {"claims": [claim]}))


def run(root):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = CCD.main(root)
    return rc, buf.getvalue()


class ClaimDrift(unittest.TestCase):
    def tree(self, **kw):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        build(t.name, **kw)
        return t.name

    def test_passes(self):
        rc, out = run(self.tree(literal="3.146 mV worst ff"))
        self.assertEqual(rc, 0, out)

    def test_missing_record_fails(self):
        rc, out = run(self.tree(cited="20250101-000000-ccccccc"))
        self.assertEqual(rc, 1)
        self.assertIn("missing or untracked", out)

    def test_missing_twin_fails(self):
        rc, out = run(self.tree(md=False))
        self.assertEqual(rc, 1)
        self.assertIn("missing or untracked", out)

    def test_stale_unlabelled_fails_and_names_newer(self):
        rc, out = run(self.tree(newer=NEW))
        self.assertEqual(rc, 1)
        self.assertIn(NEW, out)
        self.assertIn("without a historical marker", out)

    def test_stale_labelled_passes(self):
        rc, out = run(self.tree(
            newer=NEW, readme=f"Earlier run: 3.146 mV worst ff "
            f"(sim/{B}/records/{OLD}.md).\n"))
        self.assertEqual(rc, 0, out)

    def test_other_dut_is_not_a_successor(self):
        rc, out = run(self.tree(newer=NEW, newer_dut={"dut_id": "d2",
                                                       "dut_netlist_sha256": "cd"}))
        self.assertEqual(rc, 0, out)

    def test_numeric_mismatch_fails(self):
        rc, out = run(self.tree(readme=f"Result 3.147 mV worst ff "
                                 f"(sim/{B}/records/{OLD}.md).\n",
                                literal="3.147 mV worst ff"))
        self.assertEqual(rc, 1)
        self.assertIn("3.146", out)

    def test_wrong_corner_fails(self):
        t = self.tree()
        p = Path(t) / "spec" / "claim-registry.json"
        reg = json.loads(p.read_text())
        reg["claims"][0]["corner"] = "tt"
        p.write_text(json.dumps(reg))
        rc, out = run(t)
        self.assertEqual(rc, 1)

    def test_literal_absent_fails(self):
        rc, out = run(self.tree(literal="not in the doc"))
        self.assertEqual(rc, 1)
        self.assertIn("not found", out)

    def test_bad_registry_fails_closed(self):
        rc, _ = run(self.tree(registry={"claims": [{"id": "x"}]}))
        self.assertEqual(rc, 1)
        rc, _ = run(self.tree(registry={}))
        self.assertEqual(rc, 1)

    def test_waiver_and_unused_waiver(self):
        w = {"doc": "README.md", "cited": OLD, "newer": [NEW], "issue": "#1"}
        reg = {"claims": [], "known_drift": [w]}
        rc, out = run(self.tree(newer=NEW, registry=reg))
        self.assertEqual(rc, 0, out)
        rc, out = run(self.tree(registry=reg))  # no newer record: unused
        self.assertEqual(rc, 1)
        self.assertIn("unused known_drift", out)

    def test_real_tree_passes(self):
        rc, out = run(REPO)
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
