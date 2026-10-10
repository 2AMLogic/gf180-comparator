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


NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
           "twelve": 12}


def mentions(name, text):
    # Whole-name match: comparator-offset-tran must not match its longer
    # extracted-feasibility sibling.
    return re.search(re.escape(name) + r"(?![\w-])", text) is not None


def readme_drift(root, benches):
    """README-DRIFT lines: bench names missing from README.md / sim/README.md,
    or the spelled-out bench count in README.md differing from the dir count."""
    out = []
    docs = {}
    for rel in ("README.md", "sim/README.md"):
        f = Path(root) / rel
        docs[rel] = f.read_text() if f.is_file() else None
        if docs[rel] is None:
            out.append(f"README-DRIFT: {rel} not found")
    for rel, text in docs.items():
        if text is None:
            continue
        for b in sorted(benches):
            if not mentions(b, text):
                out.append(f"README-DRIFT: sim/{b} is not mentioned by full "
                           f"name in {rel}")
    text = docs["README.md"]
    if text is not None:
        m = re.search(r"sim/`?\s+holds\s+(\w+)\s+bench\s+directories", text)
        if not m:
            out.append("README-DRIFT: README.md has no 'holds <N> bench "
                       "directories' count statement")
        else:
            word = m.group(1).lower()
            n = NUMBERS.get(word, int(word) if word.isdigit() else None)
            if n != len(benches):
                out.append(f"README-DRIFT: README.md says {word} bench "
                           f"directories but sim/ has {len(benches)}")
    return out


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
    for line in readme_drift(root, benches):
        print(line)
        rc = 1
    if rc == 0:
        print(f"ok: {len(run)} campaigns + {len(NOT_RUN_BY_CHARACTERIZE)} "
              f"documented non-campaign benches cover all {len(benches)} bench dirs")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ROOT))
