"""#362: a record's Reproduce line must echo the restricting flags the run
actually passed (--corners / --temps / --supply-tolerance), so a subset record
does not tell its reader to run the full grid; a full manifest-default run
keeps the flagless line byte-identical. PDK-free: drives render_record
directly with a synthetic testbench and context."""

from __future__ import annotations

import math
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import report  # noqa: E402

BENCH = "comparator-avg-power"
FULL_LINE = f"  python3 sim/run_corners.py {BENCH}"


def _tb():
    return types.SimpleNamespace(
        experiment=BENCH,
        claim=None,
        measure={"pd_avg_w": "avg power"},
        checks={},
        evidence={},
        netlist=types.SimpleNamespace(name="tb.spice"),
        netlist_sha256="n" * 64,
        manifest_sha256="m" * 64,
    )


def _results(n=1):
    def r(i, corner):
        return types.SimpleNamespace(
            status="ok",
            point=types.SimpleNamespace(
                corner=types.SimpleNamespace(name=corner),
                corner_id=f"{corner}_27_3v30",
                index=i,
                temp_c=27.0,
                vdd=3.3,
            ),
            measurements={"pd_avg_w": 2.0},
            warnings=[],
            message="",
        )
    return [r(i, c) for i, c in enumerate(["tt"] * n)]


def _summaries():
    return {"pd_avg_w": report.MeasurementSummary(
        name="pd_avg_w", values={"tt_27_3v30": 2.0},
        minimum=2.0, maximum=2.0, mean=2.0, at_min="tt_27_3v30",
        at_max="tt_27_3v30", spread=0.0)}


def _ctx(restricting=None, **extra):
    ctx = {
        "record_id": "r0001",
        "commit": "a" * 40,
        "dut_id": "comparator-dr0001",
        "dut_provenance": "schematic",
        "dut_netlist": "dut.spice",
        "dut_netlist_sha256": "d" * 64,
        "pdk": {"variant": "gf180mcuD", "open_pdks_version": "b" * 40,
                "discovered_via": "env"},
        "toolchain": {"observed": {"ngspice": "46.0", "python": "3.12"},
                      "drift": []},
    }
    if restricting is not None:
        ctx["restricting_args"] = restricting
    ctx.update(extra)
    return ctx


def _reproduce_lines(ctx):
    md = report.render_record(_tb(), _results(), _summaries(), ctx)
    lines = md.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln == "  ```"]
    # The Reproduce block is the only fenced block in the record.
    return lines[starts[0] + 1:starts[1]]


class ReproduceFlagsTests(unittest.TestCase):
    def test_restricted_grid_names_all_flags(self):
        lines = _reproduce_lines(_ctx({
            "corners": ["tt"], "temps": [27.0], "supply_tolerance": 0.0,
        }))
        self.assertEqual(lines, [
            FULL_LINE + " --corners tt --temps 27 --supply-tolerance 0",
        ])

    def test_full_grid_line_byte_identical(self):
        # Both shapes of "no restricting flag": the key absent entirely
        # (any pre-#362 context) and the key present but all-None (a run
        # that took everything from the manifest).
        self.assertEqual(_reproduce_lines(_ctx()), [FULL_LINE])
        self.assertEqual(_reproduce_lines(_ctx({
            "corners": None, "temps": None, "supply_tolerance": None,
        })), [FULL_LINE])

    def test_supply_tolerance_zero_is_kept(self):
        # 0 is falsy but is a real restriction (supply_points() collapses to
        # a single rail at tolerance <= 0) -- the flag must survive.
        lines = _reproduce_lines(_ctx({
            "corners": None, "temps": None, "supply_tolerance": 0.0,
        }))
        self.assertEqual(lines, [FULL_LINE + " --supply-tolerance 0"])

    def test_bare_flag_empty_list_grows_no_flag(self):
        # A bare --corners parses to [] and means "manifest default" -- no
        # flag may grow even though the list was literally passed.
        lines = _reproduce_lines(_ctx({
            "corners": [], "temps": None, "supply_tolerance": None,
        }))
        self.assertEqual(lines, [FULL_LINE])

    def test_corner_set_name_echoed_as_passed(self):
        # resolve_corners expands set names for the run; Reproduce echoes argv.
        lines = _reproduce_lines(_ctx({
            "corners": ["fast"], "temps": None, "supply_tolerance": None,
        }))
        self.assertEqual(lines, [FULL_LINE + " --corners fast"])
        self.assertNotIn("fs", lines[0])

    def test_multi_value_flags_space_separated(self):
        lines = _reproduce_lines(_ctx({
            "corners": ["tt", "ss"],
            "temps": [-40.0, 27.0, 125.0],
            "supply_tolerance": None,
        }))
        self.assertEqual(lines, [FULL_LINE + " --corners tt ss --temps -40 27 125"])

    def test_extracted_shape_flags_on_run_corners_line(self):
        lines = _reproduce_lines(_ctx(
            {"corners": ["tt"], "temps": [27.0], "supply_tolerance": 0.0},
            dut_provenance="extracted", dut_id="comparator-dr0001-layout",
        ))
        self.assertEqual(lines, [
            "  python3 layout/run_extract_sim.py",
            FULL_LINE + " --dut comparator-dr0001-layout"
            " --corners tt --temps 27 --supply-tolerance 0",
        ])

    def test_restricting_args_survive_strict_json_safe(self):
        ctx = _ctx({"corners": ["tt"], "temps": [27.0], "supply_tolerance": 0.05})
        omitted: list[str] = []
        safe = report._strict_json_safe(ctx, "", omitted)
        self.assertEqual(safe["restricting_args"],
                         {"corners": ["tt"], "temps": [27.0],
                          "supply_tolerance": 0.05})
        self.assertEqual(omitted, [])

    def test_nonfinite_tolerance_omitted_explicitly(self):
        ctx = _ctx({"corners": None, "temps": None, "supply_tolerance": math.nan})
        omitted: list[str] = []
        safe = report._strict_json_safe(ctx, "", omitted)
        self.assertIsNone(safe["restricting_args"]["supply_tolerance"])
        self.assertEqual(omitted, [".restricting_args.supply_tolerance"])


if __name__ == "__main__":
    unittest.main()
