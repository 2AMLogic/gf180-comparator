#!/usr/bin/env python3
"""Regenerate the `klt extract` + `klt lvs` signoff evidence for
`layout/comparator.gds` -- issue #22 (T1 checklist item 4, LVS).

WHAT THIS SCRIPT DOES
----------------------
1. `klt extract layout/comparator.gds --deck gf180mcu --top COMPARATOR` --
   the same invocation `layout/README.md`'s "Devices" section already cites
   by hand. Writes the schematic-equivalent extracted netlist to
   `layout/lvs/comparator.extracted.spice` (scratch, `.gitignore`'d -- same
   treatment `layout/comparator.spice` already gets, and for the same
   reason: `klt extract`'s own docs note that anonymous net numbering
   (`$N` labels) is not a stable contract across klayout versions/hosts, so
   the raw netlist text is not meaningful to diff or commit) and the
   structured JSON report to `layout/lvs/comparator.extract.json`
   (committed evidence).
2. `klt lvs` comparing that extracted netlist against the reference
   `design/comparator.spice`'s `comparator_dut` subcircuit -- the DUT
   `sim/dut.json` binds (`comparator-dr0001`, `provenance: schematic`) --
   per `sim/dut/README.md`'s interface contract
   (`vinp vinn clk ibias dout doutb vdd vss`). `reference.form` is
   `subckt-call` (the schematic flow's `XMB ... nfet_03v3 ...` simulation
   form, not the plain-element form `klt lvs` requires by default) and
   `options.flatten_reference` is `true`, since `design/comparator.spice`'s
   `comparator_dut` is a two-level hierarchy (it calls
   `comparator_dut_analog`/`comparator_dut_latch`) while `klt extract`'s
   layout-side output is always flat -- see `docs/cli/lvs.md`'s
   `options.flatten_reference` field for why an unflattened hierarchical
   reference cannot structurally match a flat layout netlist at all
   (a `topology` "circuit could not be matched to a counterpart" finding on
   every sub-circuit, not a real connectivity defect). Writes the structured
   JSON report to `layout/lvs/comparator.lvs.json` (committed evidence).

Both JSON reports are the actual signoff artifacts this issue's acceptance
criteria ask for -- read `status`/`mismatches[]`/`category_counts` in them,
not this script's own stdout, which is a human-readable summary only.

Usage
-----
    python3 layout/run_lvs.py

Requires `klt` on `PATH` and the `gf180mcuC` PDK variant resolvable (same
pin as `layout/gen_comparator.py` -- see `layout/README.md`'s "Toolchain").
Exits non-zero (mirroring `klt lvs`'s own exit code) when the run does not
reach `status: match` -- this is expected today, see `layout/README.md`'s
"LVS" section for why, and is not a bug in this script.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(HERE, "lvs")
GDS = os.path.join(HERE, "comparator.gds")
REFERENCE = os.path.join(REPO_ROOT, "design", "comparator.spice")

EXTRACT_NETLIST = os.path.join(OUTDIR, "comparator.extracted.spice")
EXTRACT_REPORT = os.path.join(OUTDIR, "comparator.extract.json")
LVS_REQUEST = os.path.join(OUTDIR, "comparator.lvs.request.json")
LVS_REPORT = os.path.join(OUTDIR, "comparator.lvs.json")

DECK = "gf180mcu"
TOP = "COMPARATOR"
REFERENCE_TOP = "comparator_dut"


def run_extract() -> dict:
    # Run with cwd=REPO_ROOT and repo-relative paths so the committed report's
    # own `file`/`netlist_path` fields stay host-independent (no absolute
    # path baked into the signoff evidence).
    cmd = [
        "klt", "extract", os.path.relpath(GDS, REPO_ROOT),
        "--deck", DECK,
        "--top", TOP,
        "-o", os.path.relpath(EXTRACT_NETLIST, REPO_ROOT),
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(f"klt extract failed (exit {proc.returncode})")
    report = json.loads(proc.stdout)
    with open(EXTRACT_REPORT, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return report


def run_lvs() -> tuple[dict, int]:
    # Relative paths resolve against the request FILE's own directory (see
    # docs/cli/lvs.md's `<request>` bullet) -- written relative rather than
    # absolute so the committed request document (and the `layout`/
    # `reference` fields the report echoes verbatim) stay host-independent.
    request = {
        "schema": "klt.lvs.request/1",
        "engine": "klayout",
        "layout": {
            "netlist": os.path.relpath(EXTRACT_NETLIST, OUTDIR),
            "top": TOP,
            "deck": DECK,
        },
        "reference": {
            "netlist": os.path.relpath(REFERENCE, OUTDIR),
            "top": REFERENCE_TOP,
            "form": "subckt-call",
            "deck": DECK,
        },
        "options": {
            # design/comparator.spice's comparator_dut is a two-level
            # hierarchy (XA/XL instances of comparator_dut_analog /
            # comparator_dut_latch); klt extract's layout-side output is
            # always flat. Without this, every sub-circuit reports an
            # unmatchable `topology` finding instead of the real
            # connectivity comparison -- see docs/cli/lvs.md's
            # `options.flatten_reference`.
            "flatten_reference": True,
        },
    }
    with open(LVS_REQUEST, "w") as f:
        json.dump(request, f, indent=2, sort_keys=True)
        f.write("\n")

    cmd = ["klt", "lvs", os.path.relpath(LVS_REQUEST, REPO_ROOT), "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    # klt lvs exits 0 (match), 3 (mismatch), or 4 (inconclusive) with the
    # JSON payload still on stdout for 0/3/4 -- only exit 1/2 mean no
    # payload was produced at all.
    if proc.returncode not in (0, 3, 4):
        sys.stderr.write(proc.stderr)
        sys.exit(f"klt lvs failed (exit {proc.returncode})")
    report = json.loads(proc.stdout)
    with open(LVS_REPORT, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return report, proc.returncode


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)

    extract_report = run_extract()
    print(f"klt extract: {extract_report['status']} -- "
          f"{extract_report['device_count']} devices "
          f"({extract_report['device_counts']}), "
          f"{extract_report['net_count']} nets, "
          f"{extract_report['pin_count']} pins")
    for w in extract_report.get("warnings", []):
        print(f"  warning: {w.splitlines()[0]}")

    lvs_report, lvs_exit = run_lvs()
    print(f"klt lvs: status={lvs_report['status']} "
          f"mismatch_count={lvs_report['mismatch_count']} "
          f"error_count={lvs_report['error_count']} "
          f"category_counts={lvs_report['category_counts']}")
    print(f"engine={lvs_report['engine']} "
          f"engine_version={lvs_report['environment']['engine_version']} "
          f"klayout_version={lvs_report['environment'].get('engine_version')}")

    return 0 if lvs_report["status"] == "match" else lvs_exit


if __name__ == "__main__":
    sys.exit(main())
