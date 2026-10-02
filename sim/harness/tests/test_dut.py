"""Unit tests for the multi-entry DUT binding and its post-layout support.

Issue #23 (post-layout simulation) made ``sim/dut.json`` a multi-entry
document (``{"active": <id>, "duts": {...}}``) with a second,
``extracted``-provenance entry for the parasitic-extracted netlist. These
tests pin the load-time contract that change relies on:

* entry selection (active by default, ``select`` for ``--dut <id>``, a clear
  error naming what IS available otherwise),
* the provenance-conditional subckt requirement (a flat extraction defines
  only ``comparator_dut``; a schematic binding must still define all three),
* ``Dut.provides`` and the CLI's bench/DUT compatibility check that keeps
  the analog-partition benches off the flat binding,
* the record's post-layout delta section against a committed
  schematic-provenance counterpart.

Everything runs against temp files (an absolute ``netlist`` path in a
binding resolves as-is, which is what the fixtures exploit) -- no PDK,
ngspice, or repo-tree mutation involved.
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import dut as dut_mod  # noqa: E402
from harness import report as report_mod  # noqa: E402


SCHEMATIC_NETLIST = """* fixture: full two-level hierarchy
.subckt comparator_dut vinp vinn clk ibias dout doutb vdd vss
XA vinp vinn ibias aop aon vdd vss comparator_dut_analog
XL aop aon clk dout doutb vdd vss comparator_dut_latch
.ends
.subckt comparator_dut_analog vinp vinn ibias aop aon vdd vss
XM1 aop vinn atail vss nfet_03v3 L=2u W=30u
.ends
.subckt comparator_dut_latch inp inn clk dout doutb vdd vss
XM2 dout inn tail vss nfet_03v3 L=0.5u W=2u
.ends
"""

EXTRACTED_NETLIST = """* fixture: flat post-layout extraction
.SUBCKT COMPARATOR clk dout doutb ibias vdd vinn vinp vss
M$1 sp qp vss vss2 nfet_03v3 L=0.5U W=2U
.ENDS COMPARATOR
* ---- interface wrapper ----
.subckt comparator_dut vinp vinn clk ibias dout doutb vdd vss
Xlayout_dut vinp vinn clk ibias dout doutb vdd vss COMPARATOR
.ends
"""


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.schematic = self.root / "schematic.spice"
        self.schematic.write_text(SCHEMATIC_NETLIST)
        self.extracted = self.root / "extracted.spice"
        self.extracted.write_text(EXTRACTED_NETLIST)

    def binding(self, entry: dict, extra: dict | None = None) -> Path:
        doc = {"duts": {"the-dut": entry}, "active": "the-dut"}
        doc.update(extra or {})
        path = self.root / "binding.json"
        path.write_text(json.dumps(doc))
        return path


class MultiEntryLoadTest(_Fixture):
    def test_active_entry_loads_by_default(self):
        path = self.binding(
            {
                "netlist": str(self.schematic),
                "id": "the-dut",
                "provenance": "schematic",
            }
        )
        dut = dut_mod.load(path)
        self.assertEqual(dut.dut_id, "the-dut")
        self.assertEqual(dut.available_ids, ("the-dut",))

    def test_select_picks_the_named_entry(self):
        path = self.root / "binding.json"
        path.write_text(
            json.dumps(
                {
                    "active": "schem",
                    "duts": {
                        "schem": {
                            "netlist": str(self.schematic),
                            "id": "schem",
                            "provenance": "schematic",
                        },
                        "lay": {
                            "netlist": str(self.extracted),
                            "id": "lay",
                            "provenance": "extracted",
                        },
                    },
                }
            )
        )
        dut = dut_mod.load(path, select="lay")
        self.assertEqual(dut.dut_id, "lay")
        self.assertEqual(dut.provenance, "extracted")
        self.assertEqual(dut.available_ids, ("schem", "lay"))

    def test_unknown_selection_names_what_exists(self):
        path = self.binding(
            {
                "netlist": str(self.schematic),
                "id": "the-dut",
                "provenance": "schematic",
            }
        )
        with self.assertRaises(dut_mod.DutError) as ctx:
            dut_mod.load(path, select="nope")
        self.assertIn("the-dut", str(ctx.exception))

    def test_legacy_single_entry_document_still_loads(self):
        path = self.root / "legacy.json"
        path.write_text(
            json.dumps(
                {
                    "netlist": str(self.schematic),
                    "id": "legacy",
                    "provenance": "schematic",
                }
            )
        )
        dut = dut_mod.load(path)
        self.assertEqual(dut.dut_id, "legacy")
        self.assertEqual(dut.available_ids, ())

    def test_select_on_legacy_document_is_an_error(self):
        path = self.root / "legacy.json"
        path.write_text(
            json.dumps(
                {
                    "netlist": str(self.schematic),
                    "id": "legacy",
                    "provenance": "schematic",
                }
            )
        )
        with self.assertRaises(dut_mod.DutError):
            dut_mod.load(path, select="legacy")


class ProvenanceConditionalSubcktsTest(_Fixture):
    def test_extracted_binding_needs_only_comparator_dut(self):
        path = self.binding(
            {
                "netlist": str(self.extracted),
                "id": "the-dut",
                "provenance": "extracted",
            }
        )
        dut = dut_mod.load(path)
        self.assertTrue(dut.provides("comparator_dut"))
        self.assertFalse(dut.provides("comparator_dut_analog"))
        self.assertFalse(dut.provides("comparator_dut_latch"))

    def test_schematic_binding_still_needs_all_three(self):
        partial = self.root / "partial.spice"
        partial.write_text(
            "\n".join(
                line
                for line in SCHEMATIC_NETLIST.splitlines()
                if "comparator_dut_analog" not in line
            )
        )
        path = self.binding(
            {
                "netlist": str(partial),
                "id": "the-dut",
                "provenance": "schematic",
            }
        )
        with self.assertRaises(dut_mod.DutError) as ctx:
            dut_mod.load(path)
        self.assertIn("comparator_dut_analog", str(ctx.exception))

    def test_missing_extracted_netlist_points_at_the_generator(self):
        path = self.binding(
            {
                "netlist": str(self.root / "not-there.spice"),
                "id": "the-dut",
                "provenance": "extracted",
            }
        )
        with self.assertRaises(dut_mod.DutError) as ctx:
            dut_mod.load(path)
        self.assertIn("run_extract_sim.py", str(ctx.exception))


class CompatibilityCheckTest(_Fixture):
    def _dut(self):
        return dut_mod.load(
            self.binding(
                {
                    "netlist": str(self.extracted),
                    "id": "the-dut",
                    "provenance": "extracted",
                }
            )
        )

    def _tb(self, fragment: str):
        netlist = self.root / "tb.spice"
        netlist.write_text(fragment)
        return types.SimpleNamespace(
            experiment="fixture-bench", netlist=netlist
        )

    def test_analog_partition_bench_is_refused_on_extracted_dut(self):
        from harness.cli import _check_dut_compatibility

        tb = self._tb("* tb\nXA vinp vinn ibias aop aon vdd vss comparator_dut_analog\n")
        with self.assertRaises(dut_mod.DutError) as ctx:
            _check_dut_compatibility(self._dut(), tb)
        self.assertIn("comparator_dut_analog", str(ctx.exception))

    def test_whole_comparator_bench_passes_on_extracted_dut(self):
        from harness.cli import _check_dut_compatibility

        tb = self._tb("* tb\nXa vinp vinn clk ibias dout doutb vdd vss comparator_dut\n")
        _check_dut_compatibility(self._dut(), tb)  # must not raise

    def test_prefix_name_is_not_a_false_match(self):
        # `comparator_dut` as a WORD must not be matched inside
        # `comparator_dut_analog` -- the compatibility check would then
        # wrongly pass every analog bench on a binding that only looks
        # compatible.
        from harness.cli import _check_dut_compatibility

        with self.assertRaises(dut_mod.DutError):
            _check_dut_compatibility(
                self._dut(),
                self._tb("* tb\nXA v v i a a vdd vss comparator_dut_analog\n"),
            )


class PostlayoutDeltaTest(_Fixture):
    def _tb(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        netlist = directory / "tb.spice"
        netlist.write_text("* tb\n")
        return types.SimpleNamespace(
            experiment=directory.name,
            experiment_dir=directory,
            netlist=netlist,
            nominal_supply_v=3.3,
            measure={"td_od50_ns": "td_a*1e9"},
        )

    def _record(self, directory: Path, rid: str, provenance: str, nominal: float,
                mean: float) -> None:
        records = directory / "records"
        records.mkdir(parents=True, exist_ok=True)
        (records / f"{rid}.json").write_text(
            json.dumps(
                {
                    "context": {
                        "record_id": rid,
                        "dut_provenance": provenance,
                        "dut_id": "fixture-dut",
                    },
                    "points": [
                        {
                            "status": "ok",
                            "corner": "tt",
                            "temp_c": 27.0,
                            "vdd": 3.3,
                            "measurements": {"td_od50_ns": nominal},
                        }
                    ],
                    "summary": {"td_od50_ns": {"mean": mean}},
                }
            )
        )

    def _results(self, nominal: float):
        point = types.SimpleNamespace(
            corner=types.SimpleNamespace(name="tt"),
            temp_c=27.0,
            vdd=3.3,
        )
        result = types.SimpleNamespace(
            status="ok", point=point, measurements={"td_od50_ns": nominal}
        )
        summary = report_mod.MeasurementSummary(
            name="td_od50_ns",
            values={"tt_27c_3.30v": nominal},
            minimum=nominal,
            maximum=nominal,
            mean=nominal * 1.1,
        )
        return [result], {"td_od50_ns": summary}

    def test_delta_table_cites_counterpart_and_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "fixture-bench"
            self._record(directory, "20260101-000000-aaaaaaa", "schematic", 0.708, 0.748)
            # A later extracted record must not be picked as the counterpart.
            self._record(directory, "20260102-000000-bbbbbbb", "extracted", 0.9, 0.95)
            results, summaries = self._results(0.780)
            lines = report_mod._postlayout_delta_lines(
                self._tb(directory), results, summaries, {"dut_provenance": "extracted"}
            )
            text = "\n".join(lines)
            self.assertIn("20260101-000000-aaaaaaa", text)
            self.assertIn("0.708", text)
            self.assertIn("0.78", text)
            self.assertNotIn("20260102", text)
            self.assertIn("fixture-dut", text)

    def test_no_counterpart_record_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "fixture-bench"
            results, summaries = self._results(0.780)
            lines = report_mod._postlayout_delta_lines(
                self._tb(directory), results, summaries, {"dut_provenance": "extracted"}
            )
            self.assertTrue(any("NO schematic-provenance counterpart" in ln for ln in lines))


class ComposeDeckExtraParamsTest(_Fixture):
    """Issue #23: the per-point dut_vos param and the stamped measurement."""

    def _dut(self):
        return dut_mod.load(
            self.binding(
                {
                    "netlist": str(self.extracted),
                    "id": "the-dut",
                    "provenance": "extracted",
                }
            )
        )

    def test_extra_params_land_between_dut_and_tb_params(self):
        from harness.corners import CORNERS, PvtPoint
        from harness.runner import compose_deck
        from harness.testbench import Testbench

        netlist = self.root / "tb.spice"
        netlist.write_text("* tb\nXa v v c i d db vdd 0 comparator_dut\n")
        tb = Testbench(
            directory=self.root, name="fixture", netlist=netlist,
            measure={"td": "t*1e9"}, params={"dv": 1},
        )
        pdk = types.SimpleNamespace(
            variant="gf180mcuD", version="deadbeefdeadbeef",
            design_include=self.root / "design.ngspice",
            model_lib=self.root / "models.ngspice",
        )
        point = PvtPoint(corner=CORNERS["tt"], temp_c=27.0, vdd=3.3, index=0)
        deck = compose_deck(tb, pdk, self._dut(), point,
                            extra_params={"dut_vos": 8.1e-3})
        self.assertIn(".param dut_vos=0.0081", deck)
        self.assertLess(deck.index(".param dut_vos"), deck.index(".param dv=1"))

    def test_offset_probe_testbench_requires_dut_vos_measure(self):
        from harness.testbench import Testbench

        netlist = self.root / "tb.spice"
        netlist.write_text("* tb\n")
        probe = self.root / "tb_vosprobe.spice"
        probe.write_text("* probe\n")
        with self.assertRaises(ValueError):
            Testbench(
                directory=self.root, name="fixture", netlist=netlist,
                measure={"td": "t"},
                offset_probe={"netlist": "tb_vosprobe.spice",
                              "measure": {"wrong_name": "x"}},
            ).offset_probe_testbench()

    def test_probe_declaration_builds_its_own_testbench(self):
        from harness.testbench import Testbench

        netlist = self.root / "tb.spice"
        netlist.write_text("* tb\n")
        probe = self.root / "tb_vosprobe.spice"
        probe.write_text("* probe\n")
        probe_tb = Testbench(
            directory=self.root, name="fixture", netlist=netlist,
            measure={"td": "t"},
            offset_probe={
                "netlist": "tb_vosprobe.spice",
                "analyses": ["tran 1n 2n"],
                "measure": {"dut_vos": "vos_v"},
            },
        ).offset_probe_testbench()
        self.assertEqual(probe_tb.name, "fixture-vosprobe")
        self.assertEqual(probe_tb.netlist, probe)
        self.assertIn("dut_vos", probe_tb.measure)


if __name__ == "__main__":
    unittest.main()
