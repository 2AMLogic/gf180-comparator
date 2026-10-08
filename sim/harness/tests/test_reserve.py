"""Regression tests for #85: run reservation must never overwrite evidence."""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import report  # noqa: E402

NOW = datetime(2026, 10, 8, 12, 0, 0, 123456, tzinfo=timezone.utc)


class ReserveRunTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp = Path(self._tmp.name)
        p = mock.patch.object(report, "git_short_sha", return_value="abc1234")
        p.start()
        self.addCleanup(p.stop)

    def test_concurrent_reservation_distinct(self):
        got, barrier = [], threading.Barrier(16)

        def work():
            barrier.wait()
            got.append(report.reserve_run(self.exp, NOW))

        ts = [threading.Thread(target=work) for _ in range(16)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        ids = [r for r, _ in got]
        self.assertEqual(len(ids), 16)
        self.assertEqual(len(set(ids)), 16)
        for rid, d in got:
            self.assertTrue(d.is_dir())
            self.assertEqual(d, self.exp / "corners" / rid)

    def test_collision_leaves_existing_evidence_identical(self):
        base = report.record_id(NOW)
        files = {
            self.exp / "corners" / base / "c.log": b"log",
            self.exp / "records" / f"{base}.md": b"md",
            self.exp / "records" / f"{base}.json": b"{}",
            self.exp / "netlist-snapshots" / f"{base}.spice": b"sp",
        }
        for f, b in files.items():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b)
        rid, d = report.reserve_run(self.exp, NOW)
        self.assertNotEqual(rid, base)
        self.assertTrue(d.is_dir())
        for f, b in files.items():
            self.assertEqual(f.read_bytes(), b)

    def test_published_legacy_id_without_log_dir_is_skipped(self):
        base = report.record_id(NOW)
        (self.exp / "records").mkdir()
        (self.exp / "records" / f"{base}.md").write_text("x")
        rid, _ = report.reserve_run(self.exp, NOW)
        self.assertNotEqual(rid, base)

    def test_write_new_refuses_overwrite(self):
        p = self.exp / "a.md"
        p.write_text("orig")
        with self.assertRaises(FileExistsError):
            report._write_new(p, "new")
        self.assertEqual(p.read_text(), "orig")

    def test_ids_sort_chronologically_with_legacy(self):
        legacy = "20261008-115959-abc1234"
        legacy_same = "20261008-120000-abc1234"
        new = report.record_id(NOW)
        later = report.record_id(datetime(2026, 10, 8, 12, 0, 1, tzinfo=timezone.utc))
        self.assertTrue(legacy < legacy_same < new < later)


if __name__ == "__main__":
    unittest.main()
