#!/usr/bin/env python3
"""Fail if the klayout-tools grader pin differs between its sites (#128).

``signoff/regenerate.sh``'s ``KLT_VERSION`` is the single source. Every
``klayout-tools==X.Y.Z`` pin in the sites below must equal it, because a
drifted pin means CI grades with a different klt than the one that wrote
``signoff/signoff-report.json``. Stdlib-only, PDK-free, no klt needed.

    python3 signoff/check_klt_pin.py

Evidence files (signoff-report.json, sim/, layout artifacts) are historical
records and deliberately not checked.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE = "signoff/regenerate.sh"
# (relative path, must contain at least one pin)
SITES = [
    (".github/workflows/signoff.yml", True),
    ("signoff/verify-report.py", True),
    ("signoff/README.md", True),
    ("signoff/tests/test_item5_envelope.py", False),
]

# Lines mentioning these are about a different, non-grading klt (e.g. the
# `klt pex` flow documented in the README) and are not grader pins.
IGNORE_LINE = "klt pex"

SOURCE_RE = re.compile(r'^KLT_VERSION="([^"]+)"', re.M)
PIN_RE = re.compile(r"klayout-tools==([0-9][0-9A-Za-z.+!_-]*?)(?=[^0-9A-Za-z.+!_-]|\.?$|\.?\s)")


def check(root: Path) -> list[str]:
    """Return a list of human-readable mismatch messages (empty when in sync)."""
    errors: list[str] = []
    src = root / SOURCE
    try:
        m = SOURCE_RE.search(src.read_text())
    except OSError as exc:
        return [f"{SOURCE}: cannot read ({exc})"]
    if not m:
        return [f'{SOURCE}: no KLT_VERSION="..." assignment found']
    want = m.group(1)
    for rel, required in SITES:
        try:
            lines = (root / rel).read_text().splitlines()
        except OSError as exc:
            errors.append(f"{rel}: cannot read ({exc})")
            continue
        found = 0
        for n, line in enumerate(lines, 1):
            if IGNORE_LINE in line:
                continue
            for pm in PIN_RE.finditer(line):
                found += 1
                got = pm.group(1)
                if got != want:
                    errors.append(
                        f"{rel}:{n}: pins klayout-tools=={got} but {SOURCE} "
                        f"KLT_VERSION is {want}"
                    )
        if required and not found:
            errors.append(f"{rel}: no klayout-tools==X.Y.Z pin found (expected {want})")
    return errors


def main() -> int:
    errors = check(REPO_ROOT)
    if errors:
        print("klayout-tools pin drift -- these sites must move together:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("klayout-tools pin consistent across all sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
