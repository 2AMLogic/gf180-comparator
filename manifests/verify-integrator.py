#!/usr/bin/env python3
"""Keep ``manifests/integrator.json``'s maturity rung consistent with the
committed signoff verdict of record.

The integrator view must not advertise a tier the graded report does not
support (issue #84: the manifest said ``"T1 (design-evidence tiers,
graded)"`` while ``signoff/signoff-report.json`` recorded ``tier: null``
with only part of the T1 checklist met). This verifier is the CI side of
that contract:

- ``maturity.rung`` must equal the report's ``tier``. JSON ``null`` on
  both sides passes (no tier graded), and any supported ladder value
  (``T1``-``T4``, per ``signoff/design-evidence-tiers.md``) passes when
  both sides carry it;
- any mismatch fails, in either direction -- advertising a tier the
  report does not record, or withholding one it does;
- a value outside ``null``/``T1``-``T4`` fails on either side, so a
  prose string like ``"T1 (design-evidence tiers, graded)"`` can never
  pose as a graded rung again;
- a report with no ``tier`` key at all fails as malformed -- an absent
  key must never be read as an explicit graded ``null``;
- ``maturity.verdict_of_record`` must name this repo's fixed verdict of
  record (``signoff/signoff-report.json``), so the manifest cannot dodge
  the comparison by pointing elsewhere.

Run from anywhere inside the repository:

    python3 manifests/verify-integrator.py

CI runs this command (a step in ``.github/workflows/signoff.yml``) on
every push/PR, alongside ``signoff/verify-report.py``. Unlike the
re-grading verifier it needs no ``klt`` install: it compares two
committed JSON files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATOR = REPO_ROOT / "manifests" / "integrator.json"
REPORT = REPO_ROOT / "signoff" / "signoff-report.json"

#: The one file this repo treats as the verdict of record (manifests/README.md
#: "Where the maturity rung lives"). The maturity pointer must name it.
VERDICT_OF_RECORD = "signoff/signoff-report.json"

#: The tier ladder from signoff/design-evidence-tiers.md. ``klt signoff``
#: records ``null`` until it awards a tier; beyond that only these values
#: are meaningful as a graded rung.
SUPPORTED_TIERS = ("T1", "T2", "T3", "T4")


def fail(problems: list[str]) -> None:
    for line in problems:
        print(f"FAIL: {line}", file=sys.stderr)
    sys.exit(f"{len(problems)} integrator manifest consistency problem(s) -- see above")


def describe(value: Any) -> str:
    return "null" if value is None else repr(value)


def main() -> None:
    if not INTEGRATOR.is_file():
        sys.exit(f"missing {INTEGRATOR.relative_to(REPO_ROOT)}")
    if not REPORT.is_file():
        sys.exit(
            "missing signoff/signoff-report.json (the committed verdict of "
            "record) -- generate it with ./signoff/regenerate.sh and commit "
            "it alongside the manifest"
        )
    integrator = json.loads(INTEGRATOR.read_text())
    report = json.loads(REPORT.read_text())

    maturity = integrator.get("maturity")
    if not isinstance(maturity, dict):
        sys.exit("manifests/integrator.json has no maturity object")

    problems: list[str] = []

    pointer = maturity.get("verdict_of_record")
    if pointer != VERDICT_OF_RECORD:
        problems.append(
            f"maturity.verdict_of_record is {pointer!r}, expected "
            f"{VERDICT_OF_RECORD!r} -- the rung comparison below is against "
            "this repo's fixed verdict of record; re-point it (or move the "
            "verdict of record deliberately and update this verifier in the "
            "same change)"
        )

    if "tier" not in report:
        # A missing key is a malformed report, not a graded null: reading it
        # with .get() would silently equate "tier absent" with "tier: null"
        # and let a report that no longer records a tier verdict pass (the
        # gap the review of PR #93 caught).
        problems.append(
            "signoff/signoff-report.json has no 'tier' key at all -- a "
            "malformed report cannot back any rung value; re-grade and "
            "commit a well-formed report via ./signoff/regenerate.sh"
        )
        tier = None
    else:
        tier = report["tier"]

    rung = maturity.get("rung", "")

    for side, value in (("maturity.rung", rung), ("report tier", tier)):
        if value is not None and value not in SUPPORTED_TIERS:
            problems.append(
                f"{side} is {describe(value)}, expected null or one of "
                f"{'/'.join(SUPPORTED_TIERS)} -- a graded rung is a ladder "
                "value from signoff/design-evidence-tiers.md, never prose"
            )

    if (
        (rung is None or rung in SUPPORTED_TIERS)
        and (tier is None or tier in SUPPORTED_TIERS)
        and rung != tier
    ):
        problems.append(
            f"maturity.rung is {describe(rung)} but the verdict of record "
            f"records tier {describe(tier)} -- the integrator view must "
            "mirror the committed grade exactly; re-grade via "
            "./signoff/regenerate.sh and refresh manifests/integrator.json's "
            "maturity.rung (and provenance) in the same change, or restore "
            "the report"
        )

    if problems:
        fail(problems)

    state = "null (no tier graded)" if rung is None else rung
    print("OK: manifests/integrator.json maturity.rung == signoff/signoff-report.json tier")
    print(f"OK: graded maturity rung is {state}; an operator award is a separate act (see manifests/README.md)")


if __name__ == "__main__":
    main()
