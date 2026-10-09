#!/usr/bin/env python3
"""Write the `klt sim`-shaped corner-matrix envelope for T1 item 5 (issues #91, #108).

T1 item 5 ("Full corner verification vs a ratified spec") accepts exactly one
evidence kind for an analog block: a ``klt sim`` envelope (``measurements``
list + ``corner_count``; every other kind, generic included, renders
``wrong_kind``). The four committed experiment records under
``sim/comparator-*/records/`` are this repo's harness format, which the
grader does not read. This script **wraps those committed records, without
re-simulating anything**, into the ``klt sim`` response shape the grader's
classifier and kind-validator consume, scored against the DR-0002 ratified
**target** bounds at every one of the 45 PVT corners.

Honesty contract (read before trusting the envelope):

* It is NOT output of a ``klt sim`` run. ``wrapper`` says so in the envelope,
  and every number is copied verbatim from the cited records (pinned by
  sha256 in ``source_records``); nothing is re-measured.
* Numerical compliance and coverage are tracked SEPARATELY (issue #108).
  ``eligibility.numerical`` is ``pass`` only if every corner meets every
  measured ratified target bound. ``eligibility.coverage`` is ``complete``
  only if every ratified spec row was actually scored at every corner.
* The ratified supply/power row is *average* power for one decision per
  clock edge at a stated clock rate -- and that clock rate is still TBD
  (README.md target-spec table). Average power therefore cannot be scored.
  What the records do measure is static current; ``static_power_uw`` =
  ``i_static_ua`` x corner ``vdd`` is carried per corner, **explicitly
  partial** (``partial_of``), and scored against the same 1 mW target: since
  static power is a lower bound on average power, a static value over the
  bound would be a real failure, but a static pass does NOT score the row.
  The average-power row is recorded as skipped work in the envelope's
  ``coverage`` block (``klayout_tools.coverage`` v1 shape), with reason
  ``AVG_POWER_SKIP_REASON``. No clock rate is chosen and no bound is relaxed.
* ``status`` is *derived*, never asserted, using the grader's own common
  rollup rule (failure precedes coverage): ``fail`` if any measured target
  is missed; else ``pass_partial`` while any ratified row is unscored; ``pass``
  only when both hold. ``pass_partial`` is the ``sim`` kind's partial token in
  the pinned grader (klayout-tools 0.6.0 ``_PARTIAL_STATUS_BY_KIND``): item 5
  grades ``unmet`` with reason ``partial_coverage`` -- distinct from
  ``check_failed`` -- so closing the kickback miss alone cannot turn item 5
  ``met`` while average power is unscored.
* Stretch bounds are carried per row in ``spec_rows`` (counts of corners
  inside each), but only the target bound drives ``status``.

Usage (from the repo root):

    python3 signoff/make_item5_envelope.py           # write (append-only)
    python3 signoff/make_item5_envelope.py --check   # exit 1 on drift

The output name embeds the four record ids plus the scoring revision
(``-r<SCORING_REVISION>``); an existing different file is never overwritten
(a new record set or a new scoring revision mints a new file -- re-pin the
manifest and verify-report.py's PINNED_ARTIFACTS row). Revision 1 (no suffix,
issue #91) is historical evidence: it scored static power as if it were the
average-power row. It was written by this script as of commit 1cdd5cb and is
kept byte-for-byte; this revision does not regenerate it.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NETLIST = "design/comparator.spice"

#: Bumped whenever the scoring semantics change for the same record set, so
#: the successor envelope gets a new identity instead of colliding with the
#: append-only guard in main(). Revision 2 = issue #108 (coverage split out).
SCORING_REVISION = 2

# (bench, record id) -- the four records DR-0002 ratified and the
# characterization report scores.
RECORDS = [
    ("comparator-offset-mc", "20260910-124917-4805118"),
    ("comparator-preamp-noise", "20260910-125200-4805118"),
    ("comparator-regeneration", "20260910-125206-4805118"),
    ("comparator-kickback", "20260910-125341-4805118"),
]

# Measured, fully-scored ratified rows (DR-0002 Decision table; README.md
# target-spec table). (name, label, bench, unit, target max, stretch max)
ROWS = [
    ("offset_3sigma_mv", "Offset sigma (3-sigma input-referred)", "comparator-offset-mc", "mV", 15.0, 8.0),
    ("input_noise_uv_rms", "Input-referred noise", "comparator-preamp-noise", "uV", 1000.0, 600.0),
    ("decision_time_od50_ns", "Decision time (50 mV overdrive)", "comparator-regeneration", "ns", 1.5, 0.8),
    ("kickback_1k_peak_mv", "Kickback into 1 kOhm", "comparator-kickback", "mV", 5.0, 2.0),
]

# The ratified supply/power row: average power at a stated clock rate (TBD).
# Not measurable from the records; only its static component is.
AVG_POWER_ROW = "supply_avg_power_uw"
AVG_POWER_LABEL = (
    "Supply / power (average, one decision per clock edge at a stated "
    "clock rate -- rate TBD)"
)
AVG_POWER_TARGET_UW = 1000.0
AVG_POWER_STRETCH_UW = 500.0
AVG_POWER_SKIP_REASON = "average_power_clock_rate_tbd"

# Partial evidence for AVG_POWER_ROW: static power only.
STATIC_POWER = "static_power_uw"
STATIC_POWER_LABEL = (
    "Static power (i_static_ua x vdd) -- PARTIAL evidence for the "
    "average-power row; does not score it"
)
STATIC_POWER_BENCH = "comparator-regeneration"

# Every measurement carried per corner, in order:
# (name, bench, unit, target max, stretch max)
MEASURED = [(n, b, u, t, s) for n, _l, b, u, t, s in ROWS] + [
    (STATIC_POWER, STATIC_POWER_BENCH, "uW", AVG_POWER_TARGET_UW, AVG_POWER_STRETCH_UW),
]


def _value(row: str, point: dict) -> float:
    m = point["measurements"]
    return {
        "offset_3sigma_mv": lambda: m["vos_3sig_mv"],
        "input_noise_uv_rms": lambda: m["vn_in_uv"],
        "decision_time_od50_ns": lambda: m["td_od50_ns"],
        "kickback_1k_peak_mv": lambda: m["kick_1k_peak_mv"],
        STATIC_POWER: lambda: m["i_static_ua"] * point["vdd"],
    }[row]()


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def work_id(domain: str, *parts) -> str:
    """Same identity spelling as klayout_tools.coverage.work_id (0.6.0)."""
    return domain + ":" + json.dumps(parts, separators=(",", ":"), ensure_ascii=True)


def _tag() -> str:
    return "-".join(rid for _, rid in RECORDS)


def output_path() -> Path:
    return REPO_ROOT / "sim" / "corner-matrix" / f"item5-corner-matrix-{_tag()}-r{SCORING_REVISION}.json"


def predecessor_path() -> Path:
    """The revision-1 (issue #91) envelope this one supersedes."""
    return REPO_ROOT / "sim" / "corner-matrix" / f"item5-corner-matrix-{_tag()}.json"


def load_records() -> tuple[dict, list]:
    recs = {}
    sources = []
    for bench, rid in RECORDS:
        p = REPO_ROOT / "sim" / bench / "records" / f"{rid}.json"
        recs[bench] = json.loads(p.read_text())
        sources.append({"path": p.relative_to(REPO_ROOT).as_posix(), "content_hash": _sha(p)})
    return recs, sources


class SourceValidationError(ValueError):
    """The cited records are not a valid, current, complete 45-corner set.

    Raised (never ``assert``: assertions vanish under ``python -O`` /
    ``PYTHONOPTIMIZE``) before any envelope is built, so no evidence file can
    be created or modified from invalid input.
    """


#: The committed PVT matrix (sim/harness/corners.py: DEFAULT_TEMPERATURES_C,
#: nominal 3.3 V +/-10 %, processes tt/ff/ss/fs/sf; sim/README.md id
#: convention ``<process>_<temp>c_<supply>v``), in committed record order.
MATRIX_PROCESSES = ("tt", "ff", "ss", "fs", "sf")
MATRIX_TEMPS_C = (-40.0, 27.0, 125.0)
MATRIX_VDDS = (2.97, 3.30, 3.63)
EXPECTED_POINTS = [
    (f"{p}_{t:g}c_{v:.2f}v", p, t, v)
    for p in MATRIX_PROCESSES for t in MATRIX_TEMPS_C for v in MATRIX_VDDS
]
EXPECTED_CORNER_IDS = [cid for cid, *_ in EXPECTED_POINTS]
EXPECTED_COORDS = {cid: (p, t, v) for cid, p, t, v in EXPECTED_POINTS}

#: Per-bench measurement fields the wrapper consumes (see ``_value``).
CONSUMED_FIELDS = {
    "comparator-offset-mc": ("vos_3sig_mv",),
    "comparator-preamp-noise": ("vn_in_uv",),
    "comparator-regeneration": ("td_od50_ns", "i_static_ua"),
    "comparator-kickback": ("kick_1k_peak_mv",),
}


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _finite(x) -> bool:
    return _is_number(x) and math.isfinite(x)


def validate_sources(recs: dict) -> None:
    """Raise SourceValidationError (listing every problem) on any defect."""
    errs: list[str] = []
    want_benches = [b for b, _ in RECORDS]
    if sorted(recs) != sorted(want_benches):
        raise SourceValidationError(f"benches {sorted(recs)} != expected {sorted(want_benches)}")

    # DUT provenance: all records agree, and agree with the current netlist.
    current = _sha(REPO_ROOT / NETLIST).split(":")[1]
    hashes = {}
    for b in want_benches:
        ctx = recs[b].get("context") if isinstance(recs[b], dict) else None
        h = ctx.get("dut_netlist_sha256") if isinstance(ctx, dict) else None
        hashes[b] = h
        if not isinstance(h, str):
            errs.append(f"{b}: context.dut_netlist_sha256 missing or not a string")
        elif h != current:
            errs.append(
                f"{b}: context.dut_netlist_sha256 {h} != current {NETLIST} sha256 {current} "
                "(stale record or netlist changed since records)"
            )
    if len({h for h in hashes.values() if isinstance(h, str)}) > 1:
        errs.append(f"records disagree on DUT netlist: {hashes}")

    for b in want_benches:
        pts = recs[b].get("points") if isinstance(recs[b], dict) else None
        if not isinstance(pts, list):
            errs.append(f"{b}: 'points' missing or not a list")
            continue
        ids = [p.get("corner_id") if isinstance(p, dict) else None for p in pts]
        seen, dups = set(), set()
        for i in ids:
            (dups if i in seen else seen).add(i)
        if dups:
            errs.append(f"{b}: duplicate corner_id(s): {sorted(map(str, dups))}")
        missing = [c for c in EXPECTED_CORNER_IDS if c not in seen]
        extra = sorted(str(c) for c in seen if c not in EXPECTED_COORDS)
        if missing:
            errs.append(f"{b}: omitted corner(s) vs committed matrix: {missing}")
        if extra:
            errs.append(f"{b}: unexpected corner_id(s) outside committed matrix: {extra}")
        if len(pts) != len(EXPECTED_CORNER_IDS):
            errs.append(f"{b}: {len(pts)} points, expected {len(EXPECTED_CORNER_IDS)}")
        if not (missing or extra or dups) and ids != EXPECTED_CORNER_IDS:
            errs.append(f"{b}: corner order differs from committed matrix order")
        for p in pts:
            if not isinstance(p, dict):
                errs.append(f"{b}: point is not an object: {p!r}")
                continue
            cid = p.get("corner_id")
            if p.get("status") != "ok":
                errs.append(f"{b}/{cid}: status {p.get('status')!r} != 'ok'")
            if cid in EXPECTED_COORDS:
                ep, et, ev = EXPECTED_COORDS[cid]
                got = (p.get("corner"), p.get("temp_c"), p.get("vdd"))
                for field, g, e in zip(("corner", "temp_c", "vdd"), got, (ep, et, ev)):
                    if g != e or (field != "corner" and not _finite(g)):
                        errs.append(f"{b}/{cid}: field {field} = {g!r}, expected {e!r}")
            m = p.get("measurements")
            if not isinstance(m, dict):
                errs.append(f"{b}/{cid}: 'measurements' missing or not an object")
                continue
            for f in CONSUMED_FIELDS[b]:
                if f not in m:
                    errs.append(f"{b}/{cid}: measurement {f} missing")
                elif not _finite(m[f]):
                    errs.append(f"{b}/{cid}: measurement {f} = {m[f]!r} is not a finite number")
    if errs:
        raise SourceValidationError(
            "invalid source records (no envelope built or written):\n  - " + "\n  - ".join(errs)
        )


def build_envelope_from(recs: dict, sources: list) -> dict:
    validate_sources(recs)
    corner_ids = list(EXPECTED_CORNER_IDS)
    by_corner = {b: {p["corner_id"]: p for p in r["points"]} for b, r in recs.items()}
    corners = []
    checked, skipped = [], []
    for idx, cid in enumerate(corner_ids):
        base = by_corner["comparator-offset-mc"][cid]
        meas = []
        for name, bench, unit, tgt, stretch in MEASURED:
            v = _value(name, by_corner[bench][cid])
            entry = {
                "name": name, "unit": unit, "value": v,
                "limits": {"max": tgt}, "margin": tgt - v,
                "status": "pass" if v <= tgt else "fail",
                "within_stretch": v <= stretch,
            }
            if name == STATIC_POWER:
                entry["partial_of"] = AVG_POWER_ROW
            meas.append(entry)
            checked.append(work_id("measurement", idx, cid, name))
        skipped.append({"id": work_id("spec_row", idx, cid, AVG_POWER_ROW), "reason": AVG_POWER_SKIP_REASON})
        numerically_ok = all(m["status"] == "pass" for m in meas)
        corners.append({
            "corner_id": cid, "process": base["corner"], "temp_c": base["temp_c"],
            "vdd": base["vdd"],
            # Failure precedes coverage; a numerically clean corner is still
            # only partial while its average-power row is unscored.
            "status": "fail" if not numerically_ok else "pass_partial",
            "unscored_rows": [AVG_POWER_ROW],
            "measurements": meas,
        })

    rollup, spec_rows = [], []

    def _row_stats(name: str):
        vals = [(c["corner_id"], m) for c in corners for m in c["measurements"] if m["name"] == name]
        wc_id, wc = min(vals, key=lambda t: t[1]["margin"])
        n_t = sum(1 for _, m in vals if m["status"] == "pass")
        n_s = sum(1 for _, m in vals if m["within_stretch"])
        return vals, wc_id, wc, n_t, n_s

    for name, bench, unit, tgt, _stretch in MEASURED:
        vals, wc_id, wc, n_t, _n_s = _row_stats(name)
        entry = {
            "name": name, "unit": unit, "limits": {"max": tgt},
            "status": "pass" if n_t == len(vals) else "fail",
            "worst_case": {"corner_id": wc_id, "value": wc["value"], "margin": wc["margin"]},
        }
        if name == STATIC_POWER:
            entry["partial_of"] = AVG_POWER_ROW
        rollup.append(entry)

    for name, label, bench, unit, tgt, stretch in ROWS:
        vals, wc_id, wc, n_t, n_s = _row_stats(name)
        spec_rows.append({
            "name": name, "label": label, "unit": unit,
            "target_max": tgt, "stretch_max": stretch,
            "coverage": "complete",
            "corners_total": len(vals), "corners_within_target": n_t,
            "corners_within_stretch": n_s,
            "min": min(m["value"] for _, m in vals), "max": wc["value"],
            "binding_corner": wc_id, "evidence_bench": bench,
        })
    vals, wc_id, wc, n_t, n_s = _row_stats(STATIC_POWER)
    spec_rows.append({
        "name": AVG_POWER_ROW, "label": AVG_POWER_LABEL, "unit": "uW",
        "target_max": AVG_POWER_TARGET_UW, "stretch_max": AVG_POWER_STRETCH_UW,
        "coverage": "incomplete",
        "coverage_reason": AVG_POWER_SKIP_REASON,
        "clock_rate": None,
        "corners_total": len(vals),
        # Not scored: the row's own target/stretch counts are unknown, not 0.
        "corners_within_target": None,
        "corners_within_stretch": None,
        "unscored_component": (
            "per-decision switching energy x clock rate; the clock rate is TBD "
            "in the ratified row and choosing one needs a decision record "
            "(spec/README.md). The regeneration bench records e_dec_fj but "
            "deliberately attaches no check to it, so it is not combined here."
        ),
        "partial_evidence": {
            "measurement": STATIC_POWER, "label": STATIC_POWER_LABEL,
            "corners_within_target": n_t, "corners_within_stretch": n_s,
            "min": min(m["value"] for _, m in vals), "max": wc["value"],
            "binding_corner": wc_id, "evidence_bench": STATIC_POWER_BENCH,
        },
        "evidence_bench": STATIC_POWER_BENCH,
    })

    failed = sum(1 for c in corners if c["status"] == "fail")
    passed = sum(1 for c in corners if c["status"] == "pass")
    passed_partial = sum(1 for c in corners if c["status"] == "pass_partial")
    numerical = "pass" if failed == 0 and all(m["status"] == "pass" for m in rollup) else "fail"
    incomplete_rows = [r["name"] for r in spec_rows if r["coverage"] != "complete"]
    coverage_state = "complete" if not skipped else "incomplete"
    if numerical == "fail":
        status = "fail"
    elif skipped:
        status = "pass_partial"
    else:
        status = "pass"

    coverage = {
        "schema_version": 1,
        "known": True,
        "checked": sorted(checked),
        "skipped": sorted(skipped, key=lambda r: r["id"]),
        "inapplicable": [],
        "unknown": [],
        "nothing_checked": False,
        "nothing_checked_reasons": [],
        "spec_rows_incomplete": incomplete_rows,
    }
    eligibility = {
        "numerical": numerical,
        "coverage": coverage_state,
        "incomplete_rows": incomplete_rows,
        "eligible": numerical == "pass" and coverage_state == "complete",
        "note": (
            "Item 5 needs BOTH every measured target met AND every ratified "
            "row scored. coverage=incomplete is not a numerical failure: "
            "status is pass_partial (grader reason partial_coverage) when "
            "the measured targets all pass, fail (check_failed) when any "
            "misses."
        ),
    }
    return {
        "schema_version": 1,
        "netlist": NETLIST,
        "status": status,
        "corner_count": len(corners),
        "passed": passed,
        "passed_partial": passed_partial,
        "failed": failed,
        "errored": 0,
        "scoring_revision": SCORING_REVISION,
        "supersedes": predecessor_path().relative_to(REPO_ROOT).as_posix(),
        "wrapper": (
            "NOT a `klt sim` run. Hand-wrapped by signoff/make_item5_envelope.py "
            "from committed sim/*/records/*.json (harness format; ngspice-46, "
            "gf180mcuD, 45-point full-factorial PVT), values copied verbatim, no "
            "re-simulation. Measured rows are scored against the DR-0002 "
            "ratified TARGET bounds at every corner; stretch is reported in "
            "spec_rows only. The ratified average-power row is NOT scored (its "
            "clock rate is TBD): static_power_uw = i_static_ua x vdd is carried "
            "as explicitly partial evidence, and the row is recorded as skipped "
            "work in coverage, so status can be at best pass_partial."
        ),
        "scored_against": "spec/decision-records/DR-0002-target-spec-ratification.md",
        "source_records": sources,
        "eligibility": eligibility,
        "spec_rows": spec_rows,
        "metrics": {
            "corner_count": len(corners), "corners_passed": passed,
            "corners_passed_partial": passed_partial, "corners_failed": failed,
        },
        "provenance": {"input": {"path": NETLIST, "role": "netlist", "content_hash": _sha(REPO_ROOT / NETLIST)}},
        "coverage": coverage,
        "measurements": rollup,
        "corners": corners,
    }


def build_envelope() -> dict:
    return build_envelope_from(*load_records())


def envelope_text() -> str:
    return json.dumps(build_envelope(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = output_path()
    try:
        text = envelope_text()
    except SourceValidationError as e:
        # Raised before any write: invalid input never creates/modifies evidence.
        print(f"FATAL: {e}", file=sys.stderr)
        return 1
    rel = out.relative_to(REPO_ROOT)
    if "--check" in argv:
        if not out.is_file():
            print(f"FATAL: {rel} not found -- run python3 signoff/make_item5_envelope.py", file=sys.stderr)
            return 1
        if out.read_text() != text:
            print(f"FAIL: committed {rel} is not what make_item5_envelope.py would write", file=sys.stderr)
            return 1
        print(f"OK: {rel} matches the cited records ({_sha(out)[:23]}...)")
        return 0
    if out.exists():
        if out.read_text() == text:
            print(f"unchanged: {rel}")
            return 0
        print(f"FATAL: {rel} exists with different content; sim/ evidence is append-only", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {rel} {_sha(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
