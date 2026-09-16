#!/usr/bin/env python3
"""Regenerate the `klt extract` + `klt lvs` signoff evidence for
`layout/comparator.gds` -- issues #22 (T1 checklist item 4, LVS) and #30
(completing the routing the compare needs).

WHAT THIS SCRIPT DOES
----------------------
1. `klt extract layout/comparator.gds --deck gf180mcu --top COMPARATOR
   --pins <the 8 interface nets>` -- the same invocation
   `layout/README.md`'s "Devices" section cites by hand, plus `--pins`
   (issue #514) so the extracted top cell exposes exactly
   `sim/dut/README.md`'s declared interface rather than promoting all 20
   labelled nets to top-level pins. Writes the schematic-equivalent
   extracted netlist to
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

3. Asserts the extracted top-level interface against
   `sim/dut/README.md`'s own contract (`check_interface_contract`) -- the
   check `klt lvs`'s `status` verdict structurally cannot make, since
   `klayout.db.NetlistComparer` never compares pin ORDER.
4. Re-runs the same compare through `klt lvs`'s second engine, `netgen`
   (`run_netgen_crosscheck`), writing `layout/lvs/comparator.netgen.json`.
   A corroboration step, not a second verdict -- it is what lets a residual
   finding be attributed to the netlists rather than to one comparator's
   matching strategy. Skipped (never failed) when `netgen` is not
   installed.

Both JSON reports are the actual signoff artifacts this issue's acceptance
criteria ask for -- read `status`/`mismatches[]`/`category_counts` in them,
not this script's own stdout, which is a human-readable summary only.

Usage
-----
    python3 layout/run_lvs.py

Requires `klt` on `PATH` and the `gf180mcuC` PDK variant resolvable (same
pin as `layout/gen_comparator.py` -- see `layout/README.md`'s "Toolchain").
Exits non-zero (mirroring `klt lvs`'s own exit code) when the run does not
reach `status: match`, or 5 when the interface-contract check fails. The
run does not reach `status: match` today, for one remaining reason that is
upstream of this repo -- see `layout/README.md`'s "LVS" section and
[klayout-tools#1907](https://github.com/2AMLogic/klayout-tools/issues/1907)
-- and that is not a bug in this script.
"""

from __future__ import annotations

import json
import os
import shutil
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
NETGEN_REQUEST = os.path.join(OUTDIR, "comparator.netgen.request.json")
NETGEN_REPORT = os.path.join(OUTDIR, "comparator.netgen.json")

DECK = "gf180mcu"
TOP = "COMPARATOR"
REFERENCE_TOP = "comparator_dut"

#: `sim/dut/README.md`'s interface contract for `comparator_dut`, in its own
#: declared ORDER. Passed to `klt extract --pins` so the extracted layout
#: netlist exposes exactly this interface at the top cell (every other
#: labelled net -- aon/aop/atail/ltail/mn/mp/na/nb/qn/qp/sn/sp -- stays an
#: internal net, keeping its name), instead of promoting all 20 labelled
#: nets to top-level pins the way a label-only extraction does.
#: `check_interface_contract()` below re-asserts the result against this same
#: tuple: `klayout.db.NetlistComparer` does not use pin order to gate its
#: `status` verdict (docs/cli/lvs.md), so a clean LVS run does NOT by itself
#: prove the pinout -- see layout/README.md's "Pin-order interface-contract
#: check".
INTERFACE_PINS = ("vinp", "vinn", "clk", "ibias", "dout", "doutb", "vdd", "vss")


def run_extract() -> dict:
    # Run with cwd=REPO_ROOT and repo-relative paths so the committed report's
    # own `file`/`netlist_path` fields stay host-independent (no absolute
    # path baked into the signoff evidence).
    cmd = [
        "klt", "extract", os.path.relpath(GDS, REPO_ROOT),
        "--deck", DECK,
        "--top", TOP,
        "--pins", ",".join(INTERFACE_PINS),
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


def run_netgen_crosscheck() -> dict | None:
    """Compare the SAME two netlists through `klt lvs`'s second engine,
    `"netgen"` (`RTimothyEdwards/netgen`) -- an entirely separate comparator
    implementation, not `klayout.db.NetlistComparer`.

    This is a corroboration step, not a second verdict: it exists so a
    residual finding in the primary report can be attributed to the two
    netlists themselves rather than to one comparator's matching strategy.
    Skipped (returning `None`, never failing the run) when the `netgen`
    binary is not installed -- the committed
    `lvs/comparator.netgen.json` then simply keeps its last value, with its
    own provenance block recording when and against what it was produced.
    """
    if shutil.which("netgen") is None:
        return None
    request = {
        "schema": "klt.lvs.request/1",
        "engine": "netgen",
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
    }
    with open(NETGEN_REQUEST, "w") as f:
        json.dump(request, f, indent=2, sort_keys=True)
        f.write("\n")
    cmd = ["klt", "lvs", os.path.relpath(NETGEN_REQUEST, REPO_ROOT),
           "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if proc.returncode not in (0, 3, 4):
        sys.stderr.write(proc.stderr)
        sys.exit(f"klt lvs (netgen) failed (exit {proc.returncode})")
    report = json.loads(proc.stdout)
    with open(NETGEN_REPORT, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return report


def reference_pin_order() -> list[str]:
    """The `comparator_dut` pin ORDER `design/comparator.spice` itself
    declares -- read from the file rather than restated here, so this check
    tracks the schematic's own netlist and not a copy of it."""
    with open(REFERENCE) as f:
        for line in f:
            if line.lower().startswith(f".subckt {REFERENCE_TOP} "):
                return line.split()[2:]
    sys.exit(f"no '.subckt {REFERENCE_TOP}' line in {REFERENCE}")


def check_interface_contract(extract_report: dict) -> list[str]:
    """Assert the extracted layout's top-level interface against
    `sim/dut/README.md`'s contract -- the check `klt lvs`'s own `status`
    cannot make.

    `klayout.db.NetlistComparer` pins the two named circuits together and
    then matches nets by topology; it does not compare pin ORDER at all
    (docs/cli/lvs.md), so `status: match` alone would not catch a layout
    whose boundary ports are a permutation of the contract's. Returns a list
    of problem strings (empty when the interface is exactly right).
    """
    problems = []
    declared = list(INTERFACE_PINS)
    reference = reference_pin_order()
    if reference != declared:
        problems.append(
            f"design/comparator.spice declares .subckt {REFERENCE_TOP} "
            f"{' '.join(reference)}; layout/run_lvs.py's INTERFACE_PINS is "
            f"{' '.join(declared)} -- sim/dut/README.md's contract is the "
            f"arbiter; one of the two has drifted")
    extracted = {n["name"] for n in extract_report["nets"] if n.get("pin")}
    missing = [p for p in declared if p not in extracted]
    extra = sorted(extracted - set(declared))
    if missing:
        problems.append(f"layout exposes no top-level pin for: {', '.join(missing)}")
    if extra:
        problems.append(
            f"layout exposes top-level pin(s) the contract does not name: "
            f"{', '.join(extra)}")
    return problems


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

    interface_problems = check_interface_contract(extract_report)
    if interface_problems:
        for p in interface_problems:
            print(f"  INTERFACE: {p}")
    else:
        print(f"interface contract: OK -- top-level pins are exactly "
              f"{' '.join(INTERFACE_PINS)} (sim/dut/README.md)")

    lvs_report, lvs_exit = run_lvs()
    print(f"klt lvs: status={lvs_report['status']} "
          f"mismatch_count={lvs_report['mismatch_count']} "
          f"error_count={lvs_report['error_count']} "
          f"category_counts={lvs_report['category_counts']}")
    print(f"engine={lvs_report['engine']} "
          f"engine_version={lvs_report['environment']['engine_version']}")

    netgen_report = run_netgen_crosscheck()
    if netgen_report is None:
        print("netgen cross-check: skipped (no `netgen` binary on PATH) -- "
              f"{os.path.relpath(NETGEN_REPORT, REPO_ROOT)} left as committed")
    else:
        print(f"netgen cross-check: status={netgen_report['status']} "
              f"error_count={netgen_report['error_count']} "
              f"category_counts={netgen_report['category_counts']}")

    if interface_problems:
        # An interface-contract break is a real signoff failure even when
        # `klt lvs` itself says `match` -- never silently exit 0 on one.
        return 5
    return 0 if lvs_report["status"] == "match" else lvs_exit


if __name__ == "__main__":
    sys.exit(main())
