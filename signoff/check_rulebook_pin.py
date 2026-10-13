#!/usr/bin/env python3
"""Fail unless the vendored signoff rulebook is byte-identical to its pin (#168).

``signoff/design-evidence-tiers.md`` is the verbatim rulebook every grade
here runs under (``--tiers-doc``). Its expected sha256 lives in exactly one
place, ``signoff/design-evidence-tiers.md.sha256`` (``sha256sum`` format, so
``sha256sum -c signoff/design-evidence-tiers.md.sha256`` agrees with this
script). Both ``signoff/verify-report.py`` and ``signoff/regenerate.sh`` call
this check before grading, so an edit to the rulebook -- including a
prose-only edit that leaves every graded item id, count, status and reason
unchanged, which the grade-drift comparison cannot see -- fails by name
instead of passing. A missing rulebook or pin file also fails: nothing falls
back to the grader's bundled copy.

Deliberate re-vendoring: copy the new rulebook in, review its diff, refresh
the pin (``sha256sum signoff/design-evidence-tiers.md >
signoff/design-evidence-tiers.md.sha256``), re-grade with
``./signoff/regenerate.sh``, and commit all three together.

Stdlib-only, PDK-free, no klt needed:

    python3 signoff/check_rulebook_pin.py
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RULEBOOK = "signoff/design-evidence-tiers.md"
PIN_FILE = "signoff/design-evidence-tiers.md.sha256"

_PIN_RE = re.compile(r"^([0-9a-f]{64}) [ *](\S+)$")

REVENDOR_HINT = (
    "if this rulebook change is a deliberate re-vendor, review the diff, "
    f"refresh the pin (sha256sum {RULEBOOK} > {PIN_FILE}), re-grade with "
    "./signoff/regenerate.sh and commit all three together; otherwise restore "
    f"{RULEBOOK} (signoff/README.md, \"The two pins\")"
)


def read_pin(root: Path = REPO_ROOT) -> tuple[str | None, list[str]]:
    """Return (expected sha256, problems) parsed from PIN_FILE under ``root``."""
    path = root / PIN_FILE
    try:
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    except OSError as exc:
        return None, [
            f"rulebook pin file {PIN_FILE} is missing or unreadable ({exc}) -- "
            "refusing to grade without the committed rulebook identity"
        ]
    if len(lines) != 1:
        return None, [
            f"rulebook pin file {PIN_FILE} must hold exactly one "
            f"'<sha256>  {RULEBOOK}' line, found {len(lines)}"
        ]
    m = _PIN_RE.match(lines[0].strip())
    if not m:
        return None, [
            f"rulebook pin file {PIN_FILE} is malformed: expected "
            f"'<64 lowercase hex>  {RULEBOOK}', got {lines[0].strip()!r}"
        ]
    if m.group(2) != RULEBOOK:
        return None, [
            f"rulebook pin file {PIN_FILE} pins {m.group(2)!r}, not the "
            f"vendored rulebook {RULEBOOK!r}"
        ]
    return m.group(1), []


def check(root: Path = REPO_ROOT) -> list[str]:
    """Return human-readable problems; empty when the rulebook matches its pin."""
    expected, problems = read_pin(root)
    if problems:
        return problems
    doc = root / RULEBOOK
    if not doc.is_file():
        return [
            f"vendored rulebook {RULEBOOK} is missing -- refusing to grade "
            "(no fallback to the grader's bundled rulebook)"
        ]
    actual = hashlib.sha256(doc.read_bytes()).hexdigest()
    if actual != expected:
        return [
            f"rulebook hash mismatch: {RULEBOOK} hashes to {actual} but "
            f"{PIN_FILE} pins {expected} -- {REVENDOR_HINT}"
        ]
    return []


def pinned_hash(root: Path = REPO_ROOT) -> str | None:
    """The pinned sha256 (no prefix), or None if the pin file is unusable."""
    return read_pin(root)[0]


def main() -> int:
    problems = check(REPO_ROOT)
    if problems:
        for p in problems:
            print(f"FAIL: {p}", file=sys.stderr)
        return 1
    print(f"OK: {RULEBOOK} matches its pin in {PIN_FILE} ({pinned_hash()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
