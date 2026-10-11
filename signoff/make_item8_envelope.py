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

Evidence chain (issue #275): before emitting ``pass`` the script validates
``measurements/characterization-report.sources.json`` -- the report must be
non-empty, contain each required section heading, cite each section's
declared records by id and keep average power explicitly UNSCORED; each
registered record must exist, match its pinned sha256 and declared scope
(bench, DUT provenance, point count, clean tree). The envelope's numeric
summary is derived from those records, so a changed record cannot leave a
stale summary. This is not an all-targets-met gate: disclosed misses pass.
On failure it prints named ``evidence-chain:`` diagnostics and writes nothing.

Usage (from the repo root):

    python3 signoff/make_item8_envelope.py           # write the envelope
    python3 signoff/make_item8_envelope.py --check   # exit 1 if the
        committed envelope is not what this script would write (e.g. it was
        hand-edited, or the report changed without re-running this)

Refresh contract (see signoff/README.md): if the report changes, re-run this
script (and re-pin changed records in the sources manifest), re-pin the new sha256 in ``signoff/block-manifest.json``'s item-8
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

SOURCES = REPO_ROOT / "measurements" / "characterization-report.sources.json"

# Repo-relative, exactly as the manifest cites it (the grader resolves
# file-backed evidence paths against the repo root it is invoked from).
SOURCE = "measurements/characterization-report.md"

# Ratified DR-0002 bounds the numeric summary is derived against:
# summary_key -> (where, field, target_max, stretch_max, unit).
# ``derived`` = per-corner dict under rec["derived"]; ``points`` = list of
# rec["points"][i]["measurements"]. A test pins these to make_item5_envelope.ROWS.
SCORED = {
    "offset": ("derived", "vos_3sig_total_cons_mv", 15.0, 8.0),
    "noise": ("points", "vn_in_uv", 1000.0, 600.0),
    "decision_schematic": ("points", "td_od50_ns", 1.5, 0.8),
    "decision_extracted": ("points", "td_od50_ns", 1.5, 0.8),
    "kickback_schematic_both": ("derived", "kick_1k_peak_mv", 5.0, 2.0),
    "kickback_schematic_pnode": ("points", "kick_1k_peak_mv", 5.0, 2.0),
    "kickback_extracted": ("points", "kick_1k_peak_mv", 5.0, 2.0),
}
EXPECTED_POINTS = 45


class EvidenceChainError(Exception):
    """The characterization evidence chain is incomplete or inconsistent."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sections(text: str) -> dict[str, str]:
    """heading line -> body up to the next heading of any level."""
    out: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        if line.startswith("#"):
            cur = line.rstrip()
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(line)
    return {h: "\n".join(b) for h, b in out.items()}


def _record_values(rec: dict, key: str) -> list[float] | str:
    where, field, *_ = SCORED[key]
    vals: list[float] = []
    if where == "derived":
        d = rec.get("derived")
        if not isinstance(d, dict):
            return "'derived' missing"
        items = list(d.values())
    else:
        pts = rec.get("points")
        if not isinstance(pts, list):
            return "'points' missing"
        items = []
        for pt in pts:
            if not (isinstance(pt, dict) and pt.get("status") == "ok"
                    and isinstance(pt.get("measurements"), dict)):
                return "a point is not status 'ok' with measurements"
            items.append(pt["measurements"])
    for it in items:
        v = it.get(field) if isinstance(it, dict) else None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) == float("inf"):
            return f"field {field} missing or non-finite at a point"
        vals.append(float(v))
    return vals


def validate_chain(root: Path = REPO_ROOT) -> tuple[dict, dict[str, tuple[int, int, int]]]:
    """Validate the report against the source manifest and its records.

    Returns (manifest, counts) where counts maps summary_key ->
    (n_points, within_target, within_stretch). Raises EvidenceChainError
    listing every problem (named, prefixed ``evidence-chain:``)."""
    problems: list[str] = []
    mpath = root / "measurements" / "characterization-report.sources.json"
    if not mpath.is_file():
        raise EvidenceChainError([f"source manifest {mpath.relative_to(root)} not found"])
    try:
        man = json.loads(mpath.read_text())
        assert isinstance(man, dict) and man.get("schema_version") == 1
        records = {r["id"]: r for r in man["records"]}
        sections = man["sections"]
        assert isinstance(sections, list) and sections
    except (ValueError, AssertionError, KeyError, TypeError) as e:
        raise EvidenceChainError([f"source manifest malformed: {e!r}"])
    report = root / man.get("report", "")
    if man.get("report") != SOURCE or not report.is_file():
        raise EvidenceChainError([f"manifest report {man.get('report')!r} is not {SOURCE} or is missing"])
    text = report.read_text()
    if not text.strip():
        raise EvidenceChainError(["report is empty"])
    body = _sections(text)

    # 1. Required sections exist, cite their declared records, carry required text.
    for sec in sections:
        sid, head = sec.get("id"), sec.get("heading")
        if head not in body:
            problems.append(f"required section {sid!r} ({head!r}) is absent from the report")
            continue
        for rid in sec.get("cites", []):
            if rid not in records:
                problems.append(f"section {sid!r} declares record {rid} not in the manifest registry")
            elif rid not in body[head]:
                problems.append(f"section {sid!r} does not cite required record {rid}")
        for needle in man.get("required_text", {}).get(sid, []):
            if needle not in body[head]:
                problems.append(f"section {sid!r} lacks required text {needle!r}")

    # 2. Every registered record exists, is unchanged and has the declared scope.
    counts: dict[str, tuple[int, int, int]] = {}
    cited = {rid for sec in sections for rid in sec.get("cites", [])}
    for rid, ent in records.items():
        if rid not in cited:
            problems.append(f"record {rid} is registered but required by no section")
        path = root / ent.get("path", "")
        if not path.is_file():
            problems.append(f"record {rid}: {ent.get('path')} is missing")
            continue
        if _sha_file(path) != ent.get("sha256"):
            problems.append(f"record {rid}: sha256 differs from the manifest pin (record changed)")
            continue
        try:
            rec = json.loads(path.read_text())
        except ValueError:
            problems.append(f"record {rid}: not valid JSON")
            continue
        ctx = rec.get("context") if isinstance(rec.get("context"), dict) else {}
        dut = rec.get("dut") if isinstance(rec.get("dut"), dict) else {}
        prov = ctx.get("dut_provenance") or dut.get("dut_provenance")
        bench = rec.get("bench") or path.parent.parent.name
        npts = len(rec["points"]) if isinstance(rec.get("points"), list) else rec.get("points")
        dirty = rec.get("dirty") if "dirty" in rec else ctx.get("dirty")
        for what, got, want in (("record_id", rec.get("record_id"), rid),
                                ("bench", bench, ent.get("bench")),
                                ("dut_provenance", prov, ent.get("dut_provenance")),
                                ("points", npts, ent.get("points")),
                                ("dirty", dirty, False)):
            if got != want:
                problems.append(f"record {rid}: scope {what} is {got!r}, expected {want!r}")
        key = ent.get("summary_key")
        if key is None:
            continue
        if key not in SCORED:
            problems.append(f"record {rid}: unknown summary_key {key!r}")
            continue
        vals = _record_values(rec, key)
        if isinstance(vals, str):
            problems.append(f"record {rid}: {vals}")
        elif len(vals) != EXPECTED_POINTS:
            problems.append(f"record {rid}: {len(vals)} scored points, expected {EXPECTED_POINTS}")
        else:
            _, _, tmax, smax = SCORED[key]
            counts[key] = (len(vals), sum(v <= tmax for v in vals), sum(v <= smax for v in vals))
    for key in SCORED:
        if key not in counts and not any(p.startswith("record ") for p in problems):
            problems.append(f"no record registered for summary_key {key!r}")
    if problems:
        raise EvidenceChainError(problems)
    return man, counts


def build_summary(counts: dict[str, tuple[int, int, int]]) -> str:
    def f(key: str) -> str:
        n, t, s = counts[key]
        return f"target {t}/{n}, stretch {s}/{n}"

    return (
        "T1 item 8: aggregated narrative characterization report, scored against "
        "the DR-0002 target-spec table (ratified by the two-key PR #74), every "
        "verdict citing its committed sim/ evidence record. The pass asserts the "
        "record's existence, currency and evidence chain (validated against "
        "measurements/characterization-report.sources.json: required sections, "
        "pinned records and scope) -- not all-rows-met. Rows within bounds, "
        "derived from the pinned records: "
        f"offset (whole comparator, schematic) {f('offset')}; "
        f"noise {f('noise')}; "
        f"decision time schematic {f('decision_schematic')}, "
        f"extracted {f('decision_extracted')}; "
        f"kickback schematic both-node {f('kickback_schematic_both')} "
        f"(positive-node record {f('kickback_schematic_pnode')}), "
        f"extracted {f('kickback_extracted')}; "
        "average power is UNSCORED (clock rate TBD, #125; static "
        "power is diagnostic only). Misses stand as recorded, not absorbed."
    )


def build_envelope(root: Path = REPO_ROOT) -> dict:
    _, counts = validate_chain(root)
    digest = hashlib.sha256((root / "measurements" / "characterization-report.md").read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "kind": "generic",
        "status": "pass",
        "summary": build_summary(counts),
        "source": SOURCE,
        "provenance": {"input": {"content_hash": f"sha256:{digest}"}},
    }


def envelope_text(root: Path = REPO_ROOT) -> str:
    return json.dumps(build_envelope(root), indent=2) + "\n"


def main() -> int:
    if not REPORT.is_file():
        print(f"FATAL: {REPORT.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 1
    try:
        text = envelope_text()
    except EvidenceChainError as e:
        for p in e.problems:
            print(f"FAIL evidence-chain: {p}", file=sys.stderr)
        print("FAIL: item-8 evidence chain invalid; nothing written", file=sys.stderr)
        return 1
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
