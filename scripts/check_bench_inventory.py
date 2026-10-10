#!/usr/bin/env python3
"""Every sim/comparator-<slug> bench dir must be run by sim/characterize.sh
(CAMPAIGNS) or listed below with a reason it is not (issue #216). Stdlib only."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Benches deliberately NOT run by characterize.sh, with the reason.
NOT_RUN_BY_CHARACTERIZE = {
    "comparator-offset-tran": "fleet-only; not wired into run_corners.py "
        "(reproduce via sim/tools/klt_record.py, see sim/README.md)",
    "comparator-offset-cm-window": "supplemental, unscored feasibility stage; "
        "fleet path refused (nested sweep), no record",
    "comparator-offset-cm-index": "supplemental, unscored monotonic-index "
        "variant of the cm-window bench (issue #218); fleet-only via "
        "sim/tools/mk_klt_request.py, see its README for coverage status",
    "comparator-offset-tran-extracted-feasibility": "bounded feasibility "
        "probe, not a campaign; fleet-only, mints_record: false, no record",
}


def campaigns(text):
    m = re.search(r"^CAMPAIGNS=\(\s*(.*?)\)", text, re.S | re.M)
    if not m:
        sys.exit("cannot find CAMPAIGNS=( ... ) in sim/characterize.sh")
    body = re.sub(r"#.*", "", m.group(1))
    return set(body.split())


def main(root=ROOT):
    sim = Path(root) / "sim"
    run = campaigns((sim / "characterize.sh").read_text())
    benches = {p.name for p in sim.glob("comparator-*") if p.is_dir()}
    rc = 0
    for b in sorted(benches - run - set(NOT_RUN_BY_CHARACTERIZE)):
        print(f"UNLISTED bench: sim/{b} is neither in characterize.sh CAMPAIGNS "
              f"nor in NOT_RUN_BY_CHARACTERIZE in {Path(__file__).name}")
        rc = 1
    for b in sorted((run | set(NOT_RUN_BY_CHARACTERIZE)) - benches):
        print(f"STALE entry: {b} has no sim/{b} directory")
        rc = 1
    for b in sorted(run & set(NOT_RUN_BY_CHARACTERIZE)):
        print(f"CONFLICT: {b} is both a campaign and in the not-run list")
        rc = 1
    if rc == 0:
        print(f"ok: {len(run)} campaigns + {len(NOT_RUN_BY_CHARACTERIZE)} "
              f"documented non-campaign benches cover all {len(benches)} bench dirs")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ROOT))
