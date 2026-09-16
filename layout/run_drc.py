#!/usr/bin/env python3
"""Regenerate the `klt drc` signoff evidence for `layout/comparator.gds` --
issue #20 (T1 checklist item 3, DRC).

WHAT THIS SCRIPT DOES
----------------------
`klt drc layout/comparator.gds --deck gf180mcu --top COMPARATOR --format
json` -- the gf180mcu deck `klt pdk find`/`klt deck hash` resolves for the
installed PDK/klt build, run against the committed GDS exactly as
`layout/gen_comparator.py`'s own pipeline leaves it (that script's last
step, `route_nets.py`, draws every net's metal and re-runs `klt drc` inline;
this script is the standalone re-run that writes the committed artifact --
see `layout/README.md`'s "DRC signoff" section). Writes the structured JSON
report to `layout/drc/comparator.drc.json` (committed evidence; the
`layout/lvs/` directory's own sibling, same convention).

Usage
-----
    python3 layout/run_drc.py

Requires `klt` on `PATH` and the `gf180mcuC` PDK variant resolvable (same
pin as `layout/gen_comparator.py` -- see `layout/README.md`'s "Toolchain").
Exits non-zero (mirroring `klt drc`'s own exit code) when the run is not
`status: clean` -- this is a real failure for this script (unlike
`layout/run_lvs.py`'s LVS run, DRC clean is exactly what issue #20 commits
to maintaining going forward).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(HERE, "drc")
GDS = os.path.join(HERE, "comparator.gds")

DECK = "gf180mcu"
TOP = "COMPARATOR"
REPORT = os.path.join(OUTDIR, "comparator.drc.json")


def run_drc() -> tuple[dict, int]:
    cmd = [
        "klt", "drc", os.path.relpath(GDS, REPO_ROOT),
        "--deck", DECK,
        "--top", TOP,
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    # klt drc exits 0 (clean) or 3 (violations) with the JSON payload still
    # on stdout for both -- only exit 1/2 mean no payload was produced.
    if proc.returncode not in (0, 3):
        sys.stderr.write(proc.stderr)
        sys.exit(f"klt drc failed (exit {proc.returncode})")
    report = json.loads(proc.stdout)
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return report, proc.returncode


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    report, exit_code = run_drc()
    print(f"klt drc: status={report['status']} "
          f"violation_count={report.get('violation_count')} "
          f"rule_counts={report.get('rule_counts')}")
    print(f"deck={report['provenance']['deck']['name']} "
          f"content_hash={report['provenance']['deck']['content_hash']} "
          f"klt_version={report['provenance']['klt_version']}")
    return 0 if report["status"] == "clean" else exit_code


if __name__ == "__main__":
    sys.exit(main())
