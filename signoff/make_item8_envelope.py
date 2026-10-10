#!/usr/bin/env python3
"""Write the generic evidence envelope for T1 item 8 (issue #80).

T1 item 8 ("Characterization report") names no `klt` verb: its natural
evidence is the hand-written narrative report
``measurements/characterization-report.md``, so the ingestion path is the
opt-in **generic evidence envelope** (``"kind": "generic"`` --
klayout-tools#1152, the only T1 item that may cite one; every other item
renders ``wrong_kind`` on a generic citation). This script writes that
envelope: a minimal, hand-rolled JSON wrapper pinning the report's sha256 in
its ``provenance.input.content_hash`` -- the exact field ``klt signoff
--manifest``'s staleness gate compares against the manifest's pinned
``content_hash`` (a generic envelope with no ``provenance`` block can never
satisfy a pinned citation: it grades ``stale_evidence``, never a false
pass). Stdlib only, deterministic: same report bytes in, same envelope
bytes out.

``status`` semantics (the one judgement call, stated here so it is
auditable): the envelope asserts ``"pass"`` for **item 8's claim** -- that
one aggregated, current characterization record, scored against the ratified
DR-0002 table with every verdict citing its evidence record, exists and is
committed. It does **not** assert every spec row meets its target: the
report honestly scores two rows as misses (decision-time stretch at
``ss_125c_2.97v``; kickback target and stretch), and the envelope's
``summary`` names both, so the misses travel with the citation instead of
being laundered into a bare pass. ``signoff/README.md``'s item-8 section
records this reading.

Usage (from the repo root):

    python3 signoff/make_item8_envelope.py           # write the envelope
    python3 signoff/make_item8_envelope.py --check   # exit 1 if the
        committed envelope is not what this script would write (e.g. it was
        hand-edited, or the report changed without re-running this)

Refresh contract (see signoff/README.md): if the report changes, re-run this
script, re-pin the new sha256 in ``signoff/block-manifest.json``'s item-8
entry, and re-grade via ``./signoff/regenerate.sh`` -- in one change. An
unchanged report must reproduce the committed envelope byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = REPO_ROOT / "measurements" / "characterization-report.md"
ENVELOPE = REPO_ROOT / "measurements" / "characterization-report.item8.json"

SUMMARY = (
    "T1 item 8: aggregated narrative characterization report, scored against "
    "the DR-0002 target-spec table (ratified by the two-key PR #74), every "
    "verdict citing its committed sim/ evidence record. The pass asserts the "
    "record's existence, currency and evidence chain -- not all-rows-met: "
    "offset (whole comparator, 45/45) and noise meet both bounds; decision "
    "time misses the stretch at 16/45 schematic corners and, extracted, the "
    "target at 7/45; kickback misses target and stretch (schematic and "
    "extracted); average power is UNSCORED (clock rate TBD, #125; static "
    "power is diagnostic only). Misses stand as recorded, not absorbed."
)

# Repo-relative, exactly as the manifest cites it (the grader resolves
# file-backed evidence paths against the repo root it is invoked from).
SOURCE = "measurements/characterization-report.md"


def build_envelope() -> dict:
    digest = hashlib.sha256(REPORT.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "kind": "generic",
        "status": "pass",
        "summary": SUMMARY,
        "source": SOURCE,
        "provenance": {"input": {"content_hash": f"sha256:{digest}"}},
    }


def envelope_text() -> str:
    return json.dumps(build_envelope(), indent=2) + "\n"


def main() -> int:
    if not REPORT.is_file():
        print(f"FATAL: {REPORT.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 1
    text = envelope_text()
    digest = hashlib.sha256(REPORT.read_bytes()).hexdigest()
    if "--check" in sys.argv[1:]:
        if not ENVELOPE.is_file():
            print(
                f"FATAL: {ENVELOPE.relative_to(REPO_ROOT)} not found -- run "
                "python3 signoff/make_item8_envelope.py and commit it",
                file=sys.stderr,
            )
            return 1
        if ENVELOPE.read_text() != text:
            print(
                "FAIL: committed envelope is not what make_item8_envelope.py "
                "would write (hand-edited, or the report changed) -- re-run "
                "the script, re-pin block-manifest.json's item-8 "
                "content_hash, and re-grade via ./signoff/regenerate.sh",
                file=sys.stderr,
            )
            return 1
        print(f"OK: envelope matches the current report (sha256:{digest[:16]}...)")
        return 0
    ENVELOPE.write_text(text)
    print(f"wrote {ENVELOPE.relative_to(REPO_ROOT)} pinning {SOURCE} sha256:{digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
