#!/usr/bin/env python3
"""Regenerate `layout/pex/comparator.pex.json` -- this block's `klt pex`
report, the only evidence kind T1 item 7 (Post-layout verification) accepts
(issue #81).

    python3 layout/pex/run_pex.py

Runs the released `klayout-tools==0.7.0` wheel's `klt pex` (`uvx --isolated`, never
the host `klt` -- the first release carrying `--measure-command`; the repo's
grading pin stays 0.6.0, see signoff/README.md) with the same extraction
flags `layout/run_extract_sim.py` and `layout/run_lvs.py` use, and with
`layout/pex/pex_measure.py` as the per-side measure command. That command
submits every PVT grid to the batch fleet as `klt sim` requests; see its
docstring for the bench re-expression and the grading rules.

Outputs:
  layout/pex/comparator.pex.json        the `klt pex` report (committed, cited)
  layout/pex/artifacts/measure/<side>/  each side's `klt sim` requests and
                                        reports + summary.json (committed);
                                        the generated .spice decks are scratch
  layout/pex/comparator.extracted-rc.spice  the extraction (scratch)

`klt pex` exits 3 when a delta row FAILED (a spec bound was missed) and 4
when one ERRORED; both still write a complete report, which is data, not a
script failure. Exit 1/2 (a malformed run) fails this script.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

KLT_PEX_VERSION = "0.7.0"
INTERFACE_PINS = ("vinp", "vinn", "clk", "ibias", "dout", "doutb", "vdd", "vss")
REPORT = os.path.join(HERE, "comparator.pex.json")


def main() -> int:
    rel = lambda p: os.path.relpath(p, REPO_ROOT)  # noqa: E731
    # `--isolated`: without it uvx reuses an installed tool whose local
    # version (e.g. a `0.7.0+g<sha>` git snapshot) satisfies `==0.7.0` under
    # PEP 440 -- not the released wheel. The identity check below enforces it.
    klt = ["uvx", "--isolated", "--from", f"klayout-tools=={KLT_PEX_VERSION}", "klt"]

    version = json.loads(subprocess.run(
        [*klt, "version", "--format", "json"], capture_output=True, text=True,
        check=True, cwd=REPO_ROOT).stdout)
    if version.get("git_tag") != f"v{KLT_PEX_VERSION}" or version.get("is_release") is not True:
        sys.exit(f"klt pex must be the released {KLT_PEX_VERSION} wheel, got {version}")

    cmd = [
        *klt, "pex", "layout/comparator.gds",
        "--deck", "gf180mcu",
        "--top", "COMPARATOR",
        "--pins", ",".join(INTERFACE_PINS),
        "--measure-command", f"python3 {rel(os.path.join(HERE, 'pex_measure.py'))}",
        "--reference-netlist", "design/comparator.spice",
        # One side = one offset-probe grid plus five ladder grids on the
        # batch fleet, Spot provisioning included.
        "--measure-timeout-s", "21600",
        "-o", rel(os.path.join(HERE, "comparator.extracted-rc.spice")),
        "--outdir", rel(os.path.join(HERE, "artifacts")),
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    sys.stderr.write(proc.stderr)
    if proc.returncode not in (0, 3, 4):
        sys.exit(f"klt pex exited {proc.returncode}")
    report = json.loads(proc.stdout)
    with open(REPORT, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {rel(REPORT)}: status={report['status']} "
          f"passed={report.get('passed')} failed={report.get('failed')} "
          f"errored={report.get('errored')} (klt pex exit {proc.returncode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
