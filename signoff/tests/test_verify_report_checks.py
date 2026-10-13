#!/usr/bin/env python3
"""PDK-free, klt-free regressions for verify-report.py's comparison checks.

Covers grade_drift, verify_vendored_doc, verify_yield_pin and verify_pins with
in-memory dicts and synthetic tmp-dir trees (module globals REPO_ROOT,
PINNED_ARTIFACTS and YIELD_SAMPLES_PATH are patched per test). Committed
evidence is never read or written.

    python3 signoff/tests/test_verify_report_checks.py
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VERIFY = _load("verify_report_checks_under_test", REPO_ROOT / "signoff" / "verify-report.py")
DOC = VERIFY.VENDORED_DOC_PATH


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _report() -> dict:
    return {
        "schema_version": 1, "block": "b", "kind": "k", "tier": "T0",
        "t1_item_count": 2, "t1_met_count": 1, "source_doc": DOC,
        "items": [
            {"tier": "T1", "id": 1, "title": "one", "status": "met", "reason": "ok"},
            {"tier": "T1", "id": 2, "title": "two", "status": "unmet", "reason": "no"},
        ],
    }


class GradeDrift(unittest.TestCase):
    def test_identical_is_clean(self) -> None:
        self.assertEqual(VERIFY.grade_drift(_report(), _report()), [])

    def test_each_block_field_drift_is_named(self) -> None:
        for field in VERIFY.BLOCK_LEVEL_FIELDS:
            fresh = _report()
            fresh[field] = "changed"
            problems = VERIFY.grade_drift(fresh, _report())
            self.assertEqual(len(problems), 1, field)
            self.assertIn(repr(field), problems[0])

    def test_item_status_and_reason_flip(self) -> None:
        for field, val in (("status", "met"), ("reason", "other")):
            fresh = _report()
            fresh["items"][1][field] = val
            problems = VERIFY.grade_drift(fresh, _report())
            self.assertEqual(len(problems), 1, field)
            self.assertIn("('T1', 2)", problems[0])

    def test_item_on_one_side_only(self) -> None:
        fresh = _report()
        extra = fresh["items"].pop()
        self.assertIn("('T1', 2)", "".join(VERIFY.grade_drift(fresh, _report())))
        self.assertIn("('T1', 2)", "".join(VERIFY.grade_drift(_report(), fresh)))
        self.assertEqual(extra["id"], 2)


class VendoredDoc(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "signoff").mkdir()
        self.pin = "a" * 64
        (self.root / VERIFY.RULEBOOK_PIN.PIN_FILE).write_text(
            f"{self.pin}  {VERIFY.RULEBOOK_PIN.RULEBOOK}\n")

    def check(self, committed: dict, fresh: dict) -> list[str]:
        return VERIFY.verify_vendored_doc(committed, fresh, self.root)

    def test_matching_passes_with_and_without_hash(self) -> None:
        self.assertEqual(self.check(_report(), _report()), [])
        c, f = _report(), _report()
        c["source_doc_content_hash"] = "sha256:" + self.pin
        f["source_doc_content_hash"] = self.pin
        self.assertEqual(self.check(c, f), [])

    def test_committed_source_doc_mismatch(self) -> None:
        c = _report()
        c["source_doc"] = "docs/design-evidence-tiers.md"
        problems = self.check(c, _report())
        self.assertEqual(len(problems), 1)
        self.assertIn("committed report", problems[0])

    def test_fresh_source_doc_mismatch_or_missing(self) -> None:
        for value in ("/abs/other.md", None):
            f = _report()
            f["source_doc"] = value
            problems = self.check(_report(), f)
            self.assertEqual(len(problems), 1)
            self.assertIn("fresh grade", problems[0])

    def test_hash_mismatch_names_side(self) -> None:
        c, f = _report(), _report()
        c["source_doc_content_hash"] = "sha256:" + "b" * 64
        problems = self.check(c, f)
        self.assertEqual(len(problems), 1)
        self.assertIn("committed report", problems[0])
        f["source_doc_content_hash"] = "c" * 64
        problems = self.check(_report() | {"source_doc_content_hash": self.pin}, f)
        self.assertEqual(len(problems), 1)
        self.assertIn("fresh grade", problems[0])


class TreeCase(unittest.TestCase):
    """Synthetic repo tree with the module globals re-pointed at it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.samples_rel = "sim/yield/samples.json"
        self.gds = self._write("layout/a.gds", b"gds-bytes")
        self.ref = self._write("design/ref.spice", b"ref-bytes")
        self.samples = self._write(self.samples_rel, b"samples-bytes")
        self.env2 = self._envelope("layout/e2.json", {
            "provenance": {"input": {"content_hash": "sha256:" + _sha(b"gds-bytes")}}})
        self.env4 = self._envelope("layout/e4.json", {
            "provenance": {"input": {"content_hash": "sha256:" + "d" * 64}},
            "environment": {"reference_sha256": _sha(b"ref-bytes")}})
        self.env11 = self._envelope("layout/e11.json", {
            "provenance": {"input": {"content_hash": "sha256:" + _sha(b"gds-bytes")}}})
        self.env6 = self._envelope("sim/yield/y.json", {"samples": self.samples_rel})
        prov = ("provenance", "input", "content_hash")
        rows = {
            "2": (self.env2, self.gds, prov),
            "4": (self.env4, self.ref, ("environment", "reference_sha256")),
            "11": (self.env11, self.gds, prov),
        }
        for patcher in (
            mock.patch.object(VERIFY, "REPO_ROOT", self.root),
            mock.patch.object(VERIFY, "PINNED_ARTIFACTS", rows),
            mock.patch.object(VERIFY, "YIELD_SAMPLES_PATH", self.samples_rel),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _write(self, rel: str, data: bytes) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def _envelope(self, rel: str, body: dict) -> Path:
        return self._write(rel, json.dumps(body).encode())

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))


class YieldPin(TreeCase):
    def entry(self, **kw) -> dict:
        e = {"file": self.rel(self.env6), "content_hash": "sha256:" + _sha(b"samples-bytes")}
        return e | kw

    def test_matching_pin_passes(self) -> None:
        self.assertEqual(VERIFY.verify_yield_pin(self.entry()), [])
        self.assertEqual(
            VERIFY.verify_yield_pin(self.entry(content_hash=_sha(b"samples-bytes"))), [])

    def test_malformed_entries(self) -> None:
        for bad in (None, "x", [], {"file": "f"}, {"content_hash": "h"}):
            problems = VERIFY.verify_yield_pin(bad)
            self.assertEqual(len(problems), 1, bad)
            self.assertIn("content_hash pin", problems[0])

    def test_wrong_samples_path(self) -> None:
        self._envelope(self.rel(self.env6), {"samples": "sim/other.json"})
        problems = VERIFY.verify_yield_pin(self.entry())
        self.assertEqual(len(problems), 1)
        self.assertIn("names samples document", problems[0])

    def test_hash_mismatch(self) -> None:
        problems = VERIFY.verify_yield_pin(self.entry(content_hash="sha256:" + "0" * 64))
        self.assertEqual(len(problems), 1)
        self.assertIn("manifest pin", problems[0])
        self.samples.write_bytes(b"edited")
        self.assertEqual(len(VERIFY.verify_yield_pin(self.entry())), 1)


class Pins(TreeCase):
    def manifest(self) -> dict:
        e4 = {"file": self.rel(self.env4), "content_hash": "sha256:" + "d" * 64}
        e2 = {"file": self.rel(self.env2), "content_hash": _sha(b"gds-bytes")}
        e11 = {"file": self.rel(self.env11), "content_hash": "sha256:" + _sha(b"gds-bytes")}
        return {"evidence": {
            "2": e2, "4": e4, "11": [e11, e4],
            "6": {"file": self.rel(self.env6),
                  "content_hash": "sha256:" + _sha(b"samples-bytes")},
        }}

    def test_consistent_manifest_passes(self) -> None:
        self.assertEqual(VERIFY.verify_pins(self.manifest()), [])

    def test_manifest_pin_differs_from_envelope_input(self) -> None:
        m = self.manifest()
        m["evidence"]["2"]["content_hash"] = "e" * 64
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("item 2 citation", problems[0])
        self.assertIn("does not match", problems[0])

    def test_artifact_changed_since_envelope(self) -> None:
        self.ref.write_bytes(b"edited")
        problems = VERIFY.verify_pins(self.manifest())
        self.assertEqual(len(problems), 1)
        self.assertIn("item 4 citation", problems[0])
        self.assertIn("currently hashes", problems[0])

    def test_missing_envelope_hash_reports_absent(self) -> None:
        self._envelope(self.rel(self.env2), {})
        problems = VERIFY.verify_pins(self.manifest())
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("absent" in p for p in problems))
        self.assertTrue(any("no hash" in p for p in problems))

    def test_removed_citation_fails(self) -> None:
        m = self.manifest()
        del m["evidence"]["2"]
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("removed", problems[0])

    def test_citation_without_pinned_row_fails(self) -> None:
        m = self.manifest()
        m["evidence"]["9"] = {"file": "x", "content_hash": "y"}
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("no PINNED_ARTIFACTS row", problems[0])

    def test_entry_without_content_hash_fails(self) -> None:
        m = self.manifest()
        del m["evidence"]["2"]["content_hash"]
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("content_hash pin", problems[0])

    def test_item11_must_cite_item4_verbatim(self) -> None:
        m = self.manifest()
        m["evidence"]["11"] = [m["evidence"]["11"][0], {"file": "other"}]
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("item 4's", problems[0])

    def test_item11_without_erc_part_fails(self) -> None:
        m = self.manifest()
        m["evidence"]["11"] = [copy.deepcopy(m["evidence"]["4"])]
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("item 11 citation", problems[0])

    def test_yield_item_routes_to_yield_check(self) -> None:
        m = self.manifest()
        m["evidence"]["6"]["content_hash"] = "0" * 64
        problems = VERIFY.verify_pins(m)
        self.assertEqual(len(problems), 1)
        self.assertIn("item 6 citation", problems[0])


if __name__ == "__main__":
    unittest.main()
