#!/usr/bin/env python3
"""Verify this block's committed ``klt signoff`` records against the live tree.

Four independent checks, all PDK-free (``klt signoff --manifest`` grades
committed JSON envelopes; it never runs DRC/LVS/sim gates, so this needs no
PDK, xschem, or ngspice):

1.  Run ``klt signoff --manifest signoff/block-manifest.json --tiers-doc
    signoff/design-evidence-tiers.md --format json``. Exit 0 = block graded
    T1; exit 3 = graded below T1 (data, not failure -- this block has unmet
    items by design until its sub-issues land); any other exit is a real
    error and fails here.
2.  Compare the fresh block-level fields plus per-item grades (id, title,
    status, reason) against the committed verdict of record,
    ``signoff/signoff-report.json``. Any drift fails: a manifest or evidence
    envelope that changed without re-grading and re-committing the report
    rots loudly instead of passing -- this is the anti-rot gate for the part
    the grader itself does not check.
3.  Re-hash the committed artifacts each citation pins and compare against
    the hashes recorded in the cited envelope AND in the manifest, so a
    citation whose artifact has since changed fails rather than rotting.
4.  Check the grader used the vendored 11-item rulebook: the fresh grade's
    ``source_doc`` must name ``signoff/design-evidence-tiers.md`` -- anything
    else (notably the released wheel's own bundled copy,
    ``docs/design-evidence-tiers.md``) means the grade did not run against
    the vendored rulebook. Grading without the ``--tiers-doc`` flag silently
    falls back to the 10-item checklist the released klt 0.5.0 bundles (item
    11 shipped after that release, klayout-tools#2025), which disagrees with
    the verdict of record on ``t1_item_count`` -- this check names that
    failure mode explicitly. (The pinned wheel predates the
    ``source_doc_content_hash`` field -- klayout-tools#2191 -- so it cannot
    hash the governing doc into the report; the vendored copy's own sha256 is
    recorded in signoff/README.md as the human-facing pin instead, and the
    check-2 drift comparison covers any rulebook change that alters the
    rendered item table.)

Run from anywhere inside the repository:

    python3 signoff/verify-report.py

CI runs exactly this command (``.github/workflows/signoff.yml``), after
installing the pinned grader (``klayout-tools==0.5.0``, the PyPI registry
wheel -- the same distribution ``signoff/regenerate.sh`` grades with; see
that script's header for why the distribution identity matters). Before
committing a refreshed report locally, run this too -- if the freshly graded
report is not what got committed, or an artifact drifted, it fails.

Refresh contract: every citation ``signoff/block-manifest.json`` makes must
have a row in PINNED_ARTIFACTS below. Adding a citation (e.g. the item-11
compound entry once issue #56's ``klt erc`` supply evidence lands) means
adding the pinned-artifact row here in the same change -- an unlisted
citation fails this verifier by name rather than passing unverified.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "signoff" / "block-manifest.json"
COMMITTED_REPORT = REPO_ROOT / "signoff" / "signoff-report.json"
TIERS_DOC = REPO_ROOT / "signoff" / "design-evidence-tiers.md"

# Per-citation pin re-verification (check 3). Keyed by T1 item id:
#   (evidence envelope the manifest entry cites, committed artifact whose
#    sha256 must equal the manifest pin AND the envelope's recorded
#    provenance.input.content_hash).
#
# Both citations today pin the same artifact: the committed GDS whose
# extraction (item 2) and DRC run (item 3) the two envelopes record.
#
# The artifact mapping lives here -- not in the envelopes -- because the
# committed layout envelopes record the path they were generated from, which
# does not resolve from any other checkout. That is also why these are
# exactly the citations block-manifest.json makes: adding a citation means
# adding a row here, and signoff/README.md's refresh contract says so.
PINNED_ARTIFACTS = {
    "2": (
        REPO_ROOT / "layout" / "lvs" / "comparator.extract.json",
        REPO_ROOT / "layout" / "comparator.gds",
    ),
    "3": (
        REPO_ROOT / "layout" / "drc" / "comparator.drc.json",
        REPO_ROOT / "layout" / "comparator.gds",
    ),
}

BLOCK_LEVEL_FIELDS = (
    "schema_version",
    "block",
    "kind",
    "tier",
    "t1_item_count",
    "t1_met_count",
    "source_doc",
)
# The doc path the grader records for a run against the vendored rulebook
# (relative, as regenerate.sh passes it). The pinned wheel predates
# klayout-tools#2191, so source_doc_content_hash does not exist in this
# wheel's report schema -- the source_doc naming plus the t1_item_count
# drift comparison are the machine checks.
VENDORED_DOC_PATH = "signoff/design-evidence-tiers.md"
ITEM_FIELDS = ("tier", "id", "title", "status", "reason")


def find_klt() -> str:
    """Prefer the klt installed alongside this script's interpreter (CI's
    venv layout), then any klt on PATH. Absent both, there is nothing to
    verify with -- fail with the install version CI pins."""
    beside_interpreter = Path(sys.executable).parent / "klt"
    if beside_interpreter.is_file():
        return str(beside_interpreter)
    on_path = shutil.which("klt")
    if on_path:
        return on_path
    sys.exit(
        "no klt binary found (looked next to "
        f"{sys.executable} and on PATH) -- install the pinned grader per "
        "signoff/README.md, e.g.\n"
        "  python -m pip install klayout-tools==0.5.0"
    )


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(problems: list[str]) -> None:
    for line in problems:
        print(f"FAIL: {line}", file=sys.stderr)
    sys.exit(f"{len(problems)} signoff verification problem(s) -- see above")


def fresh_signoff(manifest: Path) -> dict:
    """Run the grader against the vendored rulebook and return its report.
    Exit 0 (T1) and exit 3 (below T1, unmet items exist) are both valid
    outcomes; anything else -- or a non-JSON payload -- is an error.

    The --tiers-doc argument is the repo-relative path (the same literal
    signoff/regenerate.sh passes), run with cwd=REPO_ROOT, so the grader
    records the same ``source_doc`` the committed report carries; an absolute
    path here would drift that field against the verdict of record."""
    completed = subprocess.run(
        [
            find_klt(),
            "signoff",
            "--manifest",
            "signoff/block-manifest.json",
            "--tiers-doc",
            VENDORED_DOC_PATH,
            "--format",
            "json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode not in (0, 3):
        print(completed.stdout[-2000:], file=sys.stderr)
        print(completed.stderr[-2000:], file=sys.stderr)
        sys.exit(f"klt signoff exited {completed.returncode} (expected 0 or 3)")
    try:
        return json.loads(completed.stdout)
    except ValueError:
        sys.exit("klt signoff stdout did not parse as JSON")


def grade_drift(fresh: dict, committed: dict) -> list[str]:
    """Block-level + per-item comparison of the fresh grade against the
    committed verdict of record. Returns a list of drift descriptions."""
    problems = []
    for field in BLOCK_LEVEL_FIELDS:
        if fresh.get(field) != committed.get(field):
            problems.append(
                f"block-level field {field!r} drifted: committed report has "
                f"{committed.get(field)!r}, fresh grade has {fresh.get(field)!r} "
                "(re-grade and commit a fresh signoff/signoff-report.json via "
                "./signoff/regenerate.sh, or restore the evidence/manifest)"
            )
    fresh_rows = [
        tuple(item.get(field) for field in ITEM_FIELDS) for item in fresh.get("items", [])
    ]
    committed_rows = [
        tuple(item.get(field) for field in ITEM_FIELDS)
        for item in committed.get("items", [])
    ]
    if fresh_rows != committed_rows:
        fresh_by_key = {(t[0], t[1]): t for t in fresh_rows}
        committed_by_key = {(t[0], t[1]): t for t in committed_rows}
        for key in sorted(
            set(fresh_by_key) | set(committed_by_key),
            key=lambda k: (str(k[0]), -1 if k[1] is None else k[1]),
        ):
            if fresh_by_key.get(key) != committed_by_key.get(key):
                problems.append(
                    f"item {key} drifted: committed report has "
                    f"{committed_by_key.get(key)}, fresh grade has "
                    f"{fresh_by_key.get(key)}"
                )
    return problems


def verify_vendored_doc(committed: dict, fresh: dict) -> list[str]:
    """Check 4: both the committed report and the fresh grade must have been
    rendered from the vendored 11-item rulebook -- their ``source_doc`` must
    name VENDORED_DOC_PATH, not the wheel's own bundled copy
    (docs/design-evidence-tiers.md, the older 10-item checklist)."""
    problems = []
    committed_doc = committed.get("source_doc") or ""
    if committed_doc != VENDORED_DOC_PATH:
        problems.append(
            f"committed report records source_doc {committed_doc!r}, not the "
            f"vendored rulebook {VENDORED_DOC_PATH!r} -- re-grade with "
            "./signoff/regenerate.sh so the verdict of record is reproducible "
            "from the committed rulebook"
        )
    fresh_doc = fresh.get("source_doc") or ""
    if fresh_doc != VENDORED_DOC_PATH:
        problems.append(
            f"fresh grade ran against {fresh_doc!r}, not the vendored "
            f"{VENDORED_DOC_PATH!r} -- grade with --tiers-doc "
            "signoff/design-evidence-tiers.md (the released klt 0.5.0 bundles "
            "the older 10-item checklist and disagrees with the verdict of "
            "record on t1_item_count)"
        )
    return problems


def verify_pins(manifest: dict) -> list[str]:
    """Check 3: every pinned citation's manifest pin == the cited envelope's
    recorded input hash == the sha256 of the artifact's current bytes; every
    manifest citation must have a PINNED_ARTIFACTS row (refresh contract)."""
    problems = []
    evidence = manifest.get("evidence", {})
    for item in sorted(set(list(evidence.keys()) + list(PINNED_ARTIFACTS.keys())), key=str):
        label = f"item {item} citation"
        envelope_path, artifact_path = PINNED_ARTIFACTS.get(item, (None, None))
        entry = evidence.get(item)
        if entry is None:
            problems.append(
                f"{label} was removed (or renamed) -- signoff/README.md's "
                "refresh contract says a citation change means updating "
                "verify-report.py's PINNED_ARTIFACTS in the same change; "
                "either restore the citation or drop the stale row and "
                "re-grade via ./signoff/regenerate.sh"
            )
            continue
        if envelope_path is None:
            problems.append(
                f"{label} exists in block-manifest.json but has no "
                "PINNED_ARTIFACTS row here -- see signoff/README.md's "
                "refresh contract (a new citation needs the pin-verification "
                "row added in the same change)"
            )
            continue
        if not isinstance(entry, dict) or "content_hash" not in entry:
            problems.append(
                f"{label} is expected to carry a content_hash pin -- a "
                "manifest entry with no pinned hash cannot have its freshness "
                "verified at all, which is the one thing this file exists to "
                "check"
            )
            continue
        manifest_pin = entry["content_hash"].removeprefix("sha256:")
        envelope = json.loads(envelope_path.read_text())
        recorded = (
            (envelope.get("provenance") or {})
            .get("input", {})
            .get("content_hash", "")
        ).removeprefix("sha256:")
        actual = sha256_of(artifact_path)
        if manifest_pin != recorded:
            problems.append(
                f"{label}: manifest pin {manifest_pin[:16]}... does not match "
                f"the hash recorded in {envelope_path.name} "
                f"({recorded[:16] if recorded else 'absent'}...)"
            )
        if recorded != actual:
            problems.append(
                f"{label}: envelope {envelope_path.name} pins "
                f"{(recorded or 'no hash')[:16] if recorded else 'no hash'}... but "
                f"{artifact_path.name} currently hashes to {actual[:16]}... "
                f"({artifact_path.name} changed since the evidence was "
                "generated -- refresh the evidence, then re-pin and re-grade "
                "per signoff/README.md's refresh contract)"
            )
    return problems


def main() -> None:
    if not MANIFEST.is_file():
        sys.exit(f"missing {MANIFEST.relative_to(REPO_ROOT)}")
    if not COMMITTED_REPORT.is_file():
        sys.exit(
            "missing signoff/signoff-report.json (the committed verdict of "
            "record) -- generate it with ./signoff/regenerate.sh and commit "
            "it alongside the manifest"
        )
    if not TIERS_DOC.is_file():
        sys.exit(
            "missing signoff/design-evidence-tiers.md (the vendored 11-item "
            "rulebook the report is graded under)"
        )
    manifest = json.loads(MANIFEST.read_text())
    committed = json.loads(COMMITTED_REPORT.read_text())

    fresh = fresh_signoff(MANIFEST)

    problems: list[str] = []
    problems += grade_drift(fresh, committed)
    problems += verify_pins(manifest)
    problems += verify_vendored_doc(committed, fresh)
    if problems:
        fail(problems)

    t1_met = fresh["t1_met_count"]
    t1_total = fresh["t1_item_count"]
    tier = fresh["tier"] or f"below T1 ({t1_met}/{t1_total} T1 items met)"
    print("OK: fresh klt signoff grade == committed signoff/signoff-report.json")
    print("OK: every pinned citation's content_hash matches the current artifact bytes")
    print("OK: graded under the vendored 11-item rulebook (signoff/design-evidence-tiers.md)")
    print(
        f"OK: {t1_total} T1 items under {VENDORED_DOC_PATH} -> {tier}"
    )


if __name__ == "__main__":
    main()
