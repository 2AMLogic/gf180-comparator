"""Layout-flow facts shared by `run_drc.py`, `run_lvs.py` and
`run_extract_sim.py`: paths, deck/top cell, the interface pin contract and the
single `klt extract` invocation. Defined once here so the scripts cannot drift.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GDS = os.path.join(HERE, "comparator.gds")

DECK = "gf180mcu"
TOP = "COMPARATOR"

#: `sim/dut/README.md`'s interface contract for `comparator_dut`, in its own
#: declared ORDER. Passed to `klt extract --pins` so the extracted layout
#: netlist exposes exactly this interface at the top cell (every other
#: labelled net stays an internal net, keeping its name), instead of promoting
#: all labelled nets to top-level pins. `run_lvs.check_interface_contract()`
#: re-asserts the result against this same tuple (a clean LVS run does not by
#: itself prove pin order); `sim/harness/dut.py` deliberately keeps an
#: independent textual copy as a drift check.
INTERFACE_PINS = ("vinp", "vinn", "clk", "ibias", "dout", "doutb", "vdd", "vss")


def run_extract(netlist: str, report_path: str, parasitics: bool = False) -> dict:
    """Run `klt extract` on `GDS`, write the netlist to `netlist` and the JSON
    report to `report_path`, and return the report.

    Runs with cwd=REPO_ROOT and repo-relative paths so the committed report's
    own `file`/`netlist_path` fields stay host-independent (no absolute path
    baked into the signoff evidence).
    """
    cmd = [
        "klt", "extract", os.path.relpath(GDS, REPO_ROOT),
        "--deck", DECK,
        "--top", TOP,
        "--pins", ",".join(INTERFACE_PINS),
    ]
    if parasitics:
        cmd.append("--parasitics")
    cmd += [
        "-o", os.path.relpath(netlist, REPO_ROOT),
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        what = "klt extract --parasitics" if parasitics else "klt extract"
        sys.exit(f"{what} failed (exit {proc.returncode})")
    report = json.loads(proc.stdout)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return report
