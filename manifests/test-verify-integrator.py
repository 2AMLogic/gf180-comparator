#!/usr/bin/env python3
"""Regression matrix for ``manifests/verify-integrator.py``.

Runs the committed verifier inside scratch sandboxes (temp copies of the
verifier plus doctored ``integrator.json`` / ``signoff-report.json``
pairs) and asserts the exit code for every case the consistency contract
names -- including the malformed-report case the review of PR #93 added:
a report whose ``tier`` key is missing entirely must FAIL, not pass as an
implicit ``null``. Against the pre-fix verifier (which read the tier with
``.get()``) that case exits 0, so this matrix fails there -- it is the
committed, CI-run form of the test-first claim for this guard.

Also asserts the real committed pair (``manifests/integrator.json`` vs
``signoff/signoff-report.json``) passes.

Run from anywhere inside the repository:

    python3 manifests/test-verify-integrator.py

CI runs this command (a step in ``.github/workflows/signoff.yml``).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFIER = REPO_ROOT / "manifests" / "verify-integrator.py"
INTEGRATOR = REPO_ROOT / "manifests" / "integrator.json"
REPORT = REPO_ROOT / "signoff" / "signoff-report.json"


def run_verifier(sandbox: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(sandbox / "manifests" / "verify-integrator.py")],
        capture_output=True,
        text=True,
    )


def make_sandbox(root: Path, mutate) -> Path:
    """Copy the verifier and both committed JSON files into a scratch
    sandbox, apply ``mutate(manifest_dict, report_dict)``, write back."""
    sandbox = Path(tempfile.mkdtemp(prefix="integrator-verify-test-", dir=root))
    (sandbox / "manifests").mkdir()
    (sandbox / "signoff").mkdir()
    shutil.copy2(VERIFIER, sandbox / "manifests" / "verify-integrator.py")
    manifest = json.loads(INTEGRATOR.read_text())
    report = json.loads(REPORT.read_text())
    mutate(manifest, report)
    (sandbox / "manifests" / "integrator.json").write_text(json.dumps(manifest))
    (sandbox / "signoff" / "signoff-report.json").write_text(json.dumps(report))
    return sandbox


def set_rung(value):
    def mutate(manifest, report):
        manifest["maturity"]["rung"] = value
    return mutate


def set_rung_and_tier(rung, tier):
    def mutate(manifest, report):
        manifest["maturity"]["rung"] = rung
        report["tier"] = tier
    return mutate


def drop_tier_key(manifest, report):
    report.pop("tier", None)


def drop_rung_key(manifest, report):
    manifest["maturity"].pop("rung", None)


def repoint_verdict(manifest, report):
    manifest["maturity"]["verdict_of_record"] = "signoff/elsewhere.json"


#: (name, mutate, expected) -- expected is the verifier's exit status.
CASES = [
    ("issue's bug: advertise T1 while report tier is null", set_rung("T1"), 1),
    ("understate: rung null while report grades T1", set_rung_and_tier(None, "T1"), 1),
    (
        "prose rung value",
        set_rung("T1 (design-evidence tiers, graded)"),
        1,
    ),
    ("supported but differing tiers (T1 vs T2)", set_rung_and_tier("T1", "T2"), 1),
    (
        "malformed report: tier key missing entirely (PR #93)",
        drop_tier_key,
        1,
    ),
    ("malformed manifest: rung key missing", drop_rung_key, 1),
    ("verdict pointer repointed elsewhere", repoint_verdict, 1),
    ("matching null passes", set_rung(None), 0),
    ("matching T1 passes", set_rung_and_tier("T1", "T1"), 0),
    ("matching T4 passes", set_rung_and_tier("T4", "T4"), 0),
]


def main() -> None:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="integrator-verify-suite-") as tmp:
        root = Path(tmp)
        for name, mutate, expected in CASES:
            sandbox = make_sandbox(root, mutate)
            result = run_verifier(sandbox)
            ok = result.returncode == expected
            print(
                f"{'ok  ' if ok else 'FAIL'} {name}: "
                f"exit {result.returncode} (expected {expected})"
            )
            if not ok:
                detail = (result.stderr or result.stdout).strip().splitlines()
                failures.append(
                    f"{name}: exit {result.returncode}, expected {expected}"
                    + (f" -- {detail[0][:120]}" if detail else "")
                )
            shutil.rmtree(sandbox)

    # The committed pair itself must pass.
    committed = subprocess.run(
        [sys.executable, str(VERIFIER)], capture_output=True, text=True
    )
    ok = committed.returncode == 0
    print(
        f"{'ok  ' if ok else 'FAIL'} committed integrator.json/report pair: "
        f"exit {committed.returncode} (expected 0)"
    )
    if not ok:
        failures.append(
            "committed pair fails the verifier: "
            + (committed.stderr or committed.stdout).strip()[:200]
        )

    if failures:
        print(f"\n{len(failures)} case(s) failed:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)
    print(f"\nall {len(CASES) + 1} cases as expected")


if __name__ == "__main__":
    main()
