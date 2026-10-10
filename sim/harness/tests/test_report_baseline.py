"""#262: post-layout delta baseline must be a comparable committed schematic
record. PDK-free; git tracking is mocked, records are temp fixtures."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import dut as dut_mod  # noqa: E402
from harness import report  # noqa: E402

TB_PROV = {"manifest_sha256": "m", "netlist_sha256": "n"}
CTX = {"dut_provenance": "extracted", "schematic_baseline_id": "base"}


def _write(d: Path, rid, *, dut="base", dirty=False, tb=TB_PROV, nominal=1.0,
           mean=1.1, extra_point=False, prov="schematic"):
    (d / "records").mkdir(parents=True, exist_ok=True)
    pts = [{"status": "ok", "corner": "tt", "temp_c": 27.0, "vdd": 3.3,
            "measurements": {"x": nominal}}]
    if extra_point:
        pts.append({"status": "ok", "corner": "ss", "temp_c": 27.0, "vdd": 3.3,
                    "measurements": {"x": nominal}})
    ctx = {"record_id": rid, "dut_provenance": prov, "dut_id": dut}
    if dirty is not None:
        ctx["dirty"] = dirty
    (d / "records" / f"{rid}.json").write_text(json.dumps({
        "context": ctx, "testbench": tb, "points": pts,
        "summary": {"x": {"mean": mean}}}))


def _tb(d: Path, prov=TB_PROV):
    return types.SimpleNamespace(
        experiment=d.name, experiment_dir=d, nominal_supply_v=3.3,
        measure={"x": "x"}, provenance=lambda: dict(prov))


def _results(grid_extra=False):
    def r(c):
        return types.SimpleNamespace(
            status="ok",
            point=types.SimpleNamespace(corner=types.SimpleNamespace(name=c),
                                        temp_c=27.0, vdd=3.3),
            measurements={"x": 2.0})
    res = [r("tt")] + ([r("ss")] if grid_extra else [])
    summ = {"x": report.MeasurementSummary(
        name="x", values={"a": 2.0}, minimum=2.0, maximum=2.0, mean=2.2)}
    return res, summ


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.d = Path(self._td.name) / "bench"
        self.committed = mock.patch.object(report, "_is_committed", return_value=True)
        self.committed.start()
        self.addCleanup(self.committed.stop)

    def _lines(self, ctx=CTX, grid_extra=False):
        res, summ = _results(grid_extra)
        return "\n".join(report._postlayout_delta_lines(_tb(self.d), res, summ, ctx))

    def test_valid_baseline_chosen_over_newer_incompatible(self):
        _write(self.d, "20260101-000000-a")
        _write(self.d, "20260102-000000-b", dut="experiment")       # newer, other DUT
        _write(self.d, "20260103-000000-c", dirty=True)             # dirty
        text = self._lines()
        self.assertIn("20260101-000000-a", text)
        self.assertNotIn("20260103", text.split("Baseline basis")[0])
        self.assertIn("declared baseline DUT", text)

    def test_uncommitted_record_not_selected(self):
        _write(self.d, "20260101-000000-a")
        with mock.patch.object(report, "_is_committed", return_value=False):
            text = self._lines()
        self.assertIn("UNAVAILABLE", text)
        self.assertIn("not committed", text)

    def test_unrecorded_cleanliness_not_selected(self):
        _write(self.d, "20260101-000000-a", dirty=None)
        self.assertIn("UNAVAILABLE", self._lines())

    def test_only_dirty_or_other_dut_is_unavailable_and_named(self):
        _write(self.d, "20260102-000000-b", dut="experiment")
        _write(self.d, "20260103-000000-c", dirty=True)
        text = self._lines()
        self.assertIn("UNAVAILABLE", text)
        self.assertIn("different DUT", text)
        self.assertIn("dirty", text)
        self.assertNotIn("Δ nominal", text)

    def test_methodology_mismatch_rejected(self):
        _write(self.d, "20260101-000000-a", tb={"manifest_sha256": "other",
                                                "netlist_sha256": "n"})
        text = self._lines()
        self.assertIn("UNAVAILABLE", text)
        self.assertIn("manifest_sha256 differs", text)

    def test_legacy_record_without_testbench_provenance_disclosed(self):
        _write(self.d, "20260101-000000-a", tb={})
        self.assertIn("legacy provenance", self._lines())

    def test_no_declared_baseline_identity_is_unavailable(self):
        _write(self.d, "20260101-000000-a")
        text = self._lines({"dut_provenance": "extracted"})
        self.assertIn("UNAVAILABLE", text)
        self.assertIn("no schematic baseline identity", text)

    def test_corner_set_mismatch_omits_mean_delta(self):
        _write(self.d, "20260101-000000-a", mean=1.1)
        text = self._lines(grid_extra=True)
        self.assertIn("OMITTED", text)
        self.assertIn("corner sets differ", text)
        row = [ln for ln in text.splitlines() if ln.startswith("  | `x`")][0]
        self.assertIn("+100%", row)           # nominal delta still reported
        self.assertNotIn("1.1 ", row)         # no mean numbers

    def test_matching_grid_reports_mean_delta(self):
        _write(self.d, "20260101-000000-a", mean=1.1)
        row = [ln for ln in self._lines().splitlines() if ln.startswith("  | `x`")][0]
        self.assertIn("+100%", row)
        self.assertIn("1.1", row)

    def test_explicit_pin_is_reproducible_and_still_validated(self):
        _write(self.d, "20260101-000000-a", nominal=1.0)
        _write(self.d, "20260102-000000-b", nominal=1.5)
        pinned = dict(CTX, schematic_baseline_record="20260101-000000-a")
        text = self._lines(pinned)
        self.assertIn("20260101-000000-a", text)
        self.assertIn("pinned", text)
        _write(self.d, "20260103-000000-d", dirty=True)
        bad = dict(CTX, schematic_baseline_record="20260103-000000-d")
        self.assertIn("UNAVAILABLE", self._lines(bad))

    def test_existing_records_not_modified(self):
        _write(self.d, "20260101-000000-a")
        p = self.d / "records" / "20260101-000000-a.json"
        before = p.read_bytes()
        self._lines()
        self.assertEqual(before, p.read_bytes())


class DutBaselineTests(unittest.TestCase):
    def test_provenance_record_carries_baseline_only_when_declared(self):
        base = dict(netlist=Path(__file__), dut_id="x", provenance="extracted",
                    description="")
        with mock.patch.object(dut_mod.Dut, "netlist_sha256", "h"), \
             mock.patch.object(dut_mod, "REPO_ROOT", Path(__file__).parent):
            self.assertNotIn("schematic_baseline_id",
                             dut_mod.Dut(**base).provenance_record())
            rec = dut_mod.Dut(**base, schematic_baseline="b").provenance_record()
            self.assertEqual(rec["schematic_baseline_id"], "b")


if __name__ == "__main__":
    unittest.main()
