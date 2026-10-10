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

Revision 3 (issue #200) scores the offset row on the whole-comparator
transient Monte Carlo (``sim/comparator-offset-tran/``, 45 PVT points x
N = 200) instead of the preamp-only DC bench -- but ONLY when that record has
complete supported coverage and valid, clean source provenance
(``validate_offset_tran``). Otherwise the offset row falls back to the
preamp-only DC value, is marked ``coverage: incomplete`` (reason
``OFFSET_TRAN_SKIP_REASON``) and the envelope cannot be better than
``pass_partial``; the problems are listed in the row. The preamp-only DC
result is always carried as a separate diagnostic. The scored whole-comparator
value is the record's ``vos_3sig_total_cons_mv``: simulated mismatch (latch
included) plus a DERIVED, hand-budgeted load-resistor term the PDK does not
model; both parts are disclosed per corner and in the row.

Revision 4 (issue #204) scores the kickback row on the both-node schematic
record (``sim/comparator-kickback/records/20261010-022609774981-bf851ec``,
klt-record format, ``input_node_coverage`` = ``both``) -- but ONLY when
``validate_kickback_both`` finds 45 points, citable, current schematic DUT,
unchanged 5 / 2 mV bounds, coverage ``both`` and finite values. Otherwise the
row falls back to the positive-node-only record, disclosed as partial node
coverage (``KICKBACK_FALLBACK_REASON``) in the row, per corner and in
``kickback_source``. Bounds are untouched; verdict counts are unchanged.
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
#: append-only guard in main(). Revision 2 = issue #108 (coverage split out). Revision 3 = issue #200
#: (offset scored on the full-grid whole-comparator record when valid).
#: Revision 4 = issue #204 (kickback scored on the both-node klt-record when valid).
SCORING_REVISION = 4

# (bench, record id) -- the four records DR-0002 ratified and the
# characterization report scores. The kickback entry is the positive-node-only
# record: revisions 1-3 scored on it, and revision 4 keeps it as the validated
# FALLBACK (``KICKBACK_FALLBACK_DISCLOSURE``) when the both-node record is bad.
RECORDS = [
    ("comparator-offset-mc", "20260910-124917-4805118"),
    ("comparator-preamp-noise", "20260910-125200-4805118"),
    ("comparator-regeneration", "20260910-125206-4805118"),
    ("comparator-kickback", "20260910-125341-4805118"),
]

#: The whole-comparator transient-offset record revision 3 scores the offset
#: row on (issue #200). It is validated separately from the four records
#: above (``validate_offset_tran``) and never raises: an invalid or absent
#: record degrades the offset row to incomplete coverage instead.
OFFSET_TRAN_BENCH = "comparator-offset-tran"
OFFSET_TRAN_RECORD_ID = "20261010-021500046481-d84e59d"
OFFSET_TRAN_N = 200
OFFSET_TRAN_SCORED = "vos_3sig_total_cons_mv"
OFFSET_TRAN_SKIP_REASON = "offset_whole_comparator_not_substantiated"
OFFSET_ROW = "offset_3sigma_mv"

#: The both-node schematic kickback record revision 4 scores the kickback row
#: on (issue #204). Validated by ``validate_kickback_both`` and never raises:
#: an invalid or absent record degrades the row to the positive-node-only
#: record with an explicit partial-node-coverage disclosure.
KICKBACK_BENCH = "comparator-kickback"
KICKBACK_BOTH_RECORD_ID = "20261010-022609774981-bf851ec"
KICKBACK_FIELD = "kick_1k_peak_mv"
KICKBACK_COVERAGE = "both"
KICKBACK_FALLBACK_REASON = "kickback_partial_node_coverage"
KICKBACK_ROW = "kickback_1k_peak_mv"

# Measured, fully-scored ratified rows (DR-0002 Decision table; README.md
# target-spec table). (name, label, bench, unit, target max, stretch max)
ROWS = [
    (OFFSET_ROW, "Offset sigma (3-sigma input-referred)", OFFSET_TRAN_BENCH, "mV", 15.0, 8.0),
    ("input_noise_uv_rms", "Input-referred noise", "comparator-preamp-noise", "uV", 1000.0, 600.0),
    ("decision_time_od50_ns", "Decision time (50 mV overdrive)", "comparator-regeneration", "ns", 1.5, 0.8),
    (KICKBACK_ROW, "Kickback into 1 kOhm", "comparator-kickback", "mV", 5.0, 2.0),
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
        # The whole-comparator record scores its conservative derived total;
        # the preamp-only DC record (fallback / diagnostic) its `vos_3sig_mv`.
        OFFSET_ROW: lambda: m[OFFSET_TRAN_SCORED] if OFFSET_TRAN_SCORED in m else m["vos_3sig_mv"],
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
    ids = [KICKBACK_BOTH_RECORD_ID if b == KICKBACK_BENCH else rid for b, rid in RECORDS]
    return "-".join(ids + [OFFSET_TRAN_RECORD_ID])


def _four_tag() -> str:
    return "-".join(rid for _, rid in RECORDS)


def output_path() -> Path:
    return REPO_ROOT / "sim" / "corner-matrix" / f"item5-corner-matrix-{_tag()}-r{SCORING_REVISION}.json"


def predecessor_path() -> Path:
    """The revision-1 (issue #91) envelope this one supersedes."""
    return REPO_ROOT / "sim" / "corner-matrix" / f"item5-corner-matrix-{_four_tag()}.json"


def supersedes_path() -> Path:
    """The revision-3 (issue #200) envelope this one supersedes."""
    return REPO_ROOT / "sim" / "corner-matrix" / f"item5-corner-matrix-{_four_tag()}-{OFFSET_TRAN_RECORD_ID}-r3.json"


#: Key under which the both-node kickback record rides in ``recs`` (its bench
#: name is already taken by the positive-node fallback record).
KICKBACK_BOTH_KEY = "comparator-kickback-both"


def load_records() -> tuple[dict, list]:
    recs = {}
    sources = []
    for bench, rid in RECORDS:
        p = REPO_ROOT / "sim" / bench / "records" / f"{rid}.json"
        recs[bench] = json.loads(p.read_text())
        sources.append({"path": p.relative_to(REPO_ROOT).as_posix(), "content_hash": _sha(p)})
    # The whole-comparator record is cited whenever present (even if it then
    # fails validation, so the envelope says which bytes it rejected).
    tp = REPO_ROOT / "sim" / OFFSET_TRAN_BENCH / "records" / f"{OFFSET_TRAN_RECORD_ID}.json"
    if tp.is_file():
        recs[OFFSET_TRAN_BENCH] = json.loads(tp.read_text())
        sources.append({"path": tp.relative_to(REPO_ROOT).as_posix(), "content_hash": _sha(tp)})
    # Likewise the both-node kickback record (issue #204).
    kp = REPO_ROOT / "sim" / KICKBACK_BENCH / "records" / f"{KICKBACK_BOTH_RECORD_ID}.json"
    if kp.is_file():
        try:
            recs[KICKBACK_BOTH_KEY] = json.loads(kp.read_text())
        except ValueError as e:  # unparseable: disclosed by the validator, never raised
            recs[KICKBACK_BOTH_KEY] = f"unparseable JSON: {e}"
        sources.append({"path": kp.relative_to(REPO_ROOT).as_posix(), "content_hash": _sha(kp)})
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
    # The whole-comparator and both-node records are validated separately.
    recs = {b: r for b, r in recs.items() if b not in (OFFSET_TRAN_BENCH, KICKBACK_BOTH_KEY)}
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


#: Derived fields of the whole-comparator record the wrapper consumes.
OFFSET_TRAN_FIELDS = (
    "n_samples", "vos_3sig_tran_mv", "vos_3sig_total_mv", OFFSET_TRAN_SCORED,
    "sig_vos_tran_mv", "mean_vos_tran_uv", "sig_vos_pre_mv", "sig_latch_mv",
    "mean_latch_uv", "sig_rload_mv", "sig_rload_cons_mv", "av_mean",
)


def validate_offset_tran(rec) -> list[str]:
    """Problems that stop ``rec`` backing a full-corner whole-comparator claim.

    Empty list = complete supported coverage AND valid, clean source
    provenance: the 45 committed PVT points, each with exactly
    ``OFFSET_TRAN_N`` valid draws, no named problem (saturation, missing trip,
    non-finite derivation), a citable clean-bundle record whose DUT is the
    current netlist and whose ratified bounds are untouched. Never raises."""
    errs: list[str] = []
    if not isinstance(rec, dict):
        return [f"{OFFSET_TRAN_BENCH}: record is not an object"]
    if rec.get("bench") != OFFSET_TRAN_BENCH:
        errs.append(f"bench {rec.get('bench')!r} != {OFFSET_TRAN_BENCH!r}")
    if rec.get("complete") is not True or rec.get("outcome") != "complete":
        errs.append(f"record is not complete (complete={rec.get('complete')!r}, outcome={rec.get('outcome')!r})")
    if rec.get("problems"):
        errs.append(f"record lists {len(rec['problems'])} named problem(s): {list(rec['problems'])[:3]}")
    if rec.get("expected_points") != len(EXPECTED_CORNER_IDS):
        errs.append(f"expected_points {rec.get('expected_points')!r} != {len(EXPECTED_CORNER_IDS)}")
    if rec.get("citable") is not True or rec.get("reference") is not True or rec.get("not_citable_reasons"):
        errs.append(
            f"source provenance not valid (citable={rec.get('citable')!r}, reference={rec.get('reference')!r}, "
            f"not_citable_reasons={rec.get('not_citable_reasons')!r})"
        )
    if rec.get("dirty") is not False:
        errs.append(f"record was minted from a dirty tree (dirty={rec.get('dirty')!r})")
    bundle = rec.get("source_bundle")
    if not (isinstance(bundle, dict) and isinstance(bundle.get("sha256"), str)
            and isinstance(bundle.get("origin_commit"), str) and bundle.get("origin_dirty_paths") == []):
        errs.append("source_bundle identity (sha256, origin_commit, clean origin_dirty_paths) missing or dirty")
    dut = rec.get("dut")
    current = _sha(REPO_ROOT / NETLIST).split(":")[1]
    if not (isinstance(dut, dict) and dut.get("dut_netlist_sha256") == current):
        errs.append(f"dut_netlist_sha256 != current {NETLIST} sha256 {current}")
    row = rec.get("spec_row")
    if not (isinstance(row, dict) and row.get("measure") == OFFSET_TRAN_SCORED
            and row.get("target_max") == 15.0 and row.get("stretch_max") == 8.0):
        errs.append("spec_row does not score the conservative total against the unchanged 15 / 8 mV bounds")
    derived = rec.get("derived")
    if not isinstance(derived, dict):
        return errs + ["'derived' missing or not an object"]
    missing = [c for c in EXPECTED_CORNER_IDS if c not in derived]
    extra = sorted(str(c) for c in derived if c not in EXPECTED_COORDS)
    if missing:
        errs.append(f"omitted corner(s) vs committed matrix: {missing}")
    if extra:
        errs.append(f"unexpected corner_id(s) outside committed matrix: {extra}")
    for cid in EXPECTED_CORNER_IDS:
        d = derived.get(cid)
        if not isinstance(d, dict):
            continue
        if d.get("n_samples") != OFFSET_TRAN_N:
            errs.append(f"{cid}: n_samples {d.get('n_samples')!r} != {OFFSET_TRAN_N} valid draws")
        for f in OFFSET_TRAN_FIELDS:
            if f not in d:
                errs.append(f"{cid}: measurement {f} missing")
            elif not _finite(d[f]):
                errs.append(f"{cid}: measurement {f} = {d[f]!r} is not a finite number")
    return errs


def select_offset_source(recs: dict) -> tuple[bool, list[str]]:
    """-> (use the whole-comparator record?, why not)."""
    if OFFSET_TRAN_BENCH not in recs:
        return False, [f"no {OFFSET_TRAN_BENCH} record {OFFSET_TRAN_RECORD_ID} is committed"]
    problems = validate_offset_tran(recs[OFFSET_TRAN_BENCH])
    return not problems, problems


def validate_kickback_both(rec) -> list[str]:
    """Problems that stop ``rec`` backing a both-node kickback claim.

    Empty list = the klt-record format, 45 committed PVT points, citable
    reference record on a clean tree, DUT = the current netlist, ratified
    5 / 2 mV bounds untouched, ``input_node_coverage`` = ``both`` and a finite
    ``kick_1k_peak_mv`` at every corner. Never raises."""
    if not isinstance(rec, dict):
        return [f"{KICKBACK_BENCH}: both-node record is not an object ({rec!r})"]
    errs: list[str] = []
    if rec.get("bench") != KICKBACK_BENCH:
        errs.append(f"bench {rec.get('bench')!r} != {KICKBACK_BENCH!r}")
    if rec.get("complete") is not True or rec.get("outcome") != "complete":
        errs.append(f"record is not complete (complete={rec.get('complete')!r}, outcome={rec.get('outcome')!r})")
    if rec.get("problems"):
        errs.append(f"record lists {len(rec['problems'])} named problem(s): {list(rec['problems'])[:3]}")
    if rec.get("expected_points") != len(EXPECTED_CORNER_IDS):
        errs.append(f"expected_points {rec.get('expected_points')!r} != {len(EXPECTED_CORNER_IDS)}")
    if rec.get("citable") is not True or rec.get("reference") is not True or rec.get("not_citable_reasons"):
        errs.append(
            f"source provenance not valid (citable={rec.get('citable')!r}, reference={rec.get('reference')!r}, "
            f"not_citable_reasons={rec.get('not_citable_reasons')!r})"
        )
    if rec.get("dirty") is not False:
        errs.append(f"record was minted from a dirty tree (dirty={rec.get('dirty')!r})")
    dut = rec.get("dut")
    current = _sha(REPO_ROOT / NETLIST).split(":")[1]
    if not (isinstance(dut, dict) and dut.get("dut_netlist_sha256") == current):
        errs.append(f"dut_netlist_sha256 != current {NETLIST} sha256 {current}")
    row = rec.get("spec_row")
    if not (isinstance(row, dict) and row.get("measure") == KICKBACK_FIELD
            and row.get("target_max") == 5.0 and row.get("stretch_max") == 2.0):
        errs.append("spec_row does not score kick_1k_peak_mv against the unchanged 5 / 2 mV bounds")
    if rec.get("input_node_coverage") != KICKBACK_COVERAGE:
        errs.append(f"input_node_coverage {rec.get('input_node_coverage')!r} != {KICKBACK_COVERAGE!r}")
    derived = rec.get("derived")
    if not isinstance(derived, dict):
        return errs + ["'derived' missing or not an object"]
    missing = [c for c in EXPECTED_CORNER_IDS if c not in derived]
    extra = sorted(str(c) for c in derived if c not in EXPECTED_COORDS)
    if missing:
        errs.append(f"omitted corner(s) vs committed matrix: {missing}")
    if extra:
        errs.append(f"unexpected corner_id(s) outside committed matrix: {extra}")
    for cid in EXPECTED_CORNER_IDS:
        d = derived.get(cid)
        if not isinstance(d, dict):
            if cid in derived:
                errs.append(f"{cid}: derived entry is not an object")
            continue
        if KICKBACK_FIELD not in d:
            errs.append(f"{cid}: measurement {KICKBACK_FIELD} missing")
        elif not _finite(d[KICKBACK_FIELD]):
            errs.append(f"{cid}: measurement {KICKBACK_FIELD} = {d[KICKBACK_FIELD]!r} is not a finite number")
    return errs


def select_kickback_source(recs: dict) -> tuple[bool, list[str]]:
    """-> (use the both-node record?, why not)."""
    if KICKBACK_BOTH_KEY not in recs:
        return False, [f"no {KICKBACK_BENCH} record {KICKBACK_BOTH_RECORD_ID} is committed"]
    problems = validate_kickback_both(recs[KICKBACK_BOTH_KEY])
    return not problems, problems


def _kickback_disclosure(use_both: bool, problems: list[str]) -> dict:
    if use_both:
        return {"input_node_coverage": KICKBACK_COVERAGE, "record_id": KICKBACK_BOTH_RECORD_ID}
    return {
        "input_node_coverage": "positive_node_only",
        "record_id": dict(RECORDS)[KICKBACK_BENCH],
        "partial_node_coverage": True,
        "fallback_reason": KICKBACK_FALLBACK_REASON,
        "both_node_problems": problems,
    }


def _offset_disclosure(use_whole: bool, by_corner: dict, cid: str) -> dict:
    """Per-corner disclosure on the offset measurement: what is simulated and
    what is a derived hand budget (whole-comparator), or that the value is
    preamp-only (fallback)."""
    if not use_whole:
        return {"scope": "preamp_only", "unscored_reason": OFFSET_TRAN_SKIP_REASON}
    m = by_corner[OFFSET_TRAN_BENCH][cid]["measurements"]
    return {
        "scope": "whole_comparator",
        "scored_quantity": OFFSET_TRAN_SCORED,
        "simulated": {
            "vos_3sig_tran_mv": m["vos_3sig_tran_mv"], "mean_offset_uv": m["mean_vos_tran_uv"],
            "latch_1sigma_mv": m["sig_latch_mv"], "preamp_1sigma_mv": m["sig_vos_pre_mv"],
            "n_samples": m["n_samples"],
        },
        "derived_not_simulated": {
            "load_r_1sigma_nominal_mv": m["sig_rload_mv"],
            "load_r_1sigma_conservative_mv": m["sig_rload_cons_mv"],
            "total_3sigma_cited_coefficient_mv": m["vos_3sig_total_mv"],
        },
        "diagnostic_preamp_only_3sigma_mv": by_corner["comparator-offset-mc"][cid]["measurements"]["vos_3sig_mv"],
    }


def _offset_row(row: dict, use_whole: bool, problems: list[str], by_corner: dict) -> dict:
    dc = by_corner["comparator-offset-mc"]
    dc_vals = {cid: p["measurements"]["vos_3sig_mv"] for cid, p in dc.items()}
    dc_diag = {
        "evidence_bench": "comparator-offset-mc",
        "scope": "preamp_only (analog partition; sees neither the latch nor the load-resistor mismatch)",
        "corners_within_target": sum(1 for v in dc_vals.values() if v <= row["target_max"]),
        "corners_within_stretch": sum(1 for v in dc_vals.values() if v <= row["stretch_max"]),
        "min": min(dc_vals.values()), "max": max(dc_vals.values()),
        "binding_corner": max(dc_vals, key=dc_vals.get),
    }
    if not use_whole:
        return {
            **row,
            "label": row["label"] + " -- PREAMP-ONLY evidence; whole-comparator claim not substantiated",
            "coverage": "incomplete",
            "coverage_reason": OFFSET_TRAN_SKIP_REASON,
            "problems": problems,
            "corners_within_target": None,
            "corners_within_stretch": None,
            "partial_evidence": {**dc_diag, "measurement": "vos_3sig_mv"},
        }
    tran = by_corner[OFFSET_TRAN_BENCH]
    ms = {cid: p["measurements"] for cid, p in tran.items()}

    def rng(f):
        v = {cid: m[f] for cid, m in ms.items()}
        lo, hi = min(v, key=v.get), max(v, key=v.get)
        return {"min": v[lo], "max": v[hi], "min_corner": lo, "max_corner": hi}

    return {
        **row,
        "scope": "whole_comparator",
        "scored_quantity": OFFSET_TRAN_SCORED,
        "draws_per_corner": OFFSET_TRAN_N,
        "composition": (
            "scored value = 3 * sqrt(simulated whole-comparator sigma^2 + derived load-resistor sigma^2), "
            "the load term at the CONSERVATIVE (3x) matching coefficient. The simulated part is a transient "
            "Monte Carlo (preamp + latch mismatch, PDK sw_stat_mismatch); the load-resistor term is a "
            "hand-derived budget because the PDK models no ppolyf_u_1k mismatch. It is NOT simulated samples."
        ),
        "simulated_3sigma_mv": rng("vos_3sig_tran_mv"),
        "derived_load_r_1sigma_conservative_mv": rng("sig_rload_cons_mv"),
        "latch_1sigma_mv": rng("sig_latch_mv"),
        "mean_offset_uv": rng("mean_vos_tran_uv"),
        "preamp_only_diagnostic": dc_diag,
    }


def build_envelope_from(recs: dict, sources: list) -> dict:
    validate_sources(recs)
    use_whole, whole_problems = select_offset_source(recs)
    use_both, kick_problems = select_kickback_source(recs)
    offset_bench = OFFSET_TRAN_BENCH if use_whole else "comparator-offset-mc"
    rows = [(n, lab, offset_bench if n == OFFSET_ROW else b, u, t, st) for n, lab, b, u, t, st in ROWS]
    measured = [(n, b, u, t, st) for n, _l, b, u, t, st in rows] + [MEASURED[-1]]
    corner_ids = list(EXPECTED_CORNER_IDS)
    by_corner = {
        b: {p["corner_id"]: p for p in r["points"]}
        for b, r in recs.items() if b not in (OFFSET_TRAN_BENCH, KICKBACK_BOTH_KEY)
    }
    if use_both:
        kdrv = recs[KICKBACK_BOTH_KEY]["derived"]
        by_corner[KICKBACK_BENCH] = {
            cid: {**by_corner[KICKBACK_BENCH][cid], "measurements": kdrv[cid]} for cid in corner_ids
        }
    if use_whole:
        drv = recs[OFFSET_TRAN_BENCH]["derived"]
        by_corner[OFFSET_TRAN_BENCH] = {
            cid: {"corner_id": cid, "corner": EXPECTED_COORDS[cid][0], "temp_c": EXPECTED_COORDS[cid][1],
                  "vdd": EXPECTED_COORDS[cid][2], "measurements": drv[cid]}
            for cid in corner_ids
        }
    corners = []
    checked, skipped = [], []
    for idx, cid in enumerate(corner_ids):
        base = by_corner["comparator-offset-mc"][cid]
        meas = []
        for name, bench, unit, tgt, stretch in measured:
            v = _value(name, by_corner[bench][cid])
            entry = {
                "name": name, "unit": unit, "value": v,
                "limits": {"max": tgt}, "margin": tgt - v,
                "status": "pass" if v <= tgt else "fail",
                "within_stretch": v <= stretch,
            }
            if name == OFFSET_ROW:
                entry.update(_offset_disclosure(use_whole, by_corner, cid))
            if name == KICKBACK_ROW:
                entry.update(_kickback_disclosure(use_both, kick_problems))
            if name == STATIC_POWER:
                entry["partial_of"] = AVG_POWER_ROW
            meas.append(entry)
            checked.append(work_id("measurement", idx, cid, name))
        skipped.append({"id": work_id("spec_row", idx, cid, AVG_POWER_ROW), "reason": AVG_POWER_SKIP_REASON})
        unscored = [AVG_POWER_ROW]
        if not use_whole:
            skipped.append({"id": work_id("spec_row", idx, cid, OFFSET_ROW), "reason": OFFSET_TRAN_SKIP_REASON})
            unscored.insert(0, OFFSET_ROW)
        numerically_ok = all(m["status"] == "pass" for m in meas)
        corners.append({
            "corner_id": cid, "process": base["corner"], "temp_c": base["temp_c"],
            "vdd": base["vdd"],
            # Failure precedes coverage; a numerically clean corner is still
            # only partial while its average-power row is unscored.
            "status": "fail" if not numerically_ok else "pass_partial",
            "unscored_rows": unscored,
            "measurements": meas,
        })

    rollup, spec_rows = [], []

    def _row_stats(name: str):
        vals = [(c["corner_id"], m) for c in corners for m in c["measurements"] if m["name"] == name]
        wc_id, wc = min(vals, key=lambda t: t[1]["margin"])
        n_t = sum(1 for _, m in vals if m["status"] == "pass")
        n_s = sum(1 for _, m in vals if m["within_stretch"])
        return vals, wc_id, wc, n_t, n_s

    for name, bench, unit, tgt, _stretch in measured:
        vals, wc_id, wc, n_t, _n_s = _row_stats(name)
        entry = {
            "name": name, "unit": unit, "limits": {"max": tgt},
            "status": "pass" if n_t == len(vals) else "fail",
            "worst_case": {"corner_id": wc_id, "value": wc["value"], "margin": wc["margin"]},
        }
        if name == STATIC_POWER:
            entry["partial_of"] = AVG_POWER_ROW
        rollup.append(entry)

    for name, label, bench, unit, tgt, stretch in rows:
        vals, wc_id, wc, n_t, n_s = _row_stats(name)
        row = {
            "name": name, "label": label, "unit": unit,
            "target_max": tgt, "stretch_max": stretch,
            "coverage": "complete",
            "corners_total": len(vals), "corners_within_target": n_t,
            "corners_within_stretch": n_s,
            "min": min(m["value"] for _, m in vals), "max": wc["value"],
            "binding_corner": wc_id, "evidence_bench": bench,
        }
        if name == OFFSET_ROW:
            row = _offset_row(row, use_whole, whole_problems, by_corner)
        if name == KICKBACK_ROW:
            row.update(_kickback_disclosure(use_both, kick_problems))
            if not use_both:
                row["label"] += " -- POSITIVE-NODE-ONLY evidence (partial node coverage)"
        spec_rows.append(row)
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
        "kickback_source": _kickback_disclosure(use_both, kick_problems),
        "supersedes": supersedes_path().relative_to(REPO_ROOT).as_posix(),
        "wrapper": (
            "NOT a `klt sim` run. Hand-wrapped by signoff/make_item5_envelope.py "
            "from committed sim/*/records/*.json (harness format; ngspice-46, "
            "gf180mcuD, 45-point full-factorial PVT), values copied verbatim, no "
            "re-simulation. The offset row is scored on the whole-comparator "
            "transient Monte Carlo record (simulated mismatch + a DERIVED, "
            "conservative load-resistor budget) when that record has complete, "
            "source-bound 45-point coverage, else it is marked incomplete; the "
            "preamp-only DC value is carried as a separate diagnostic. Measured rows are scored against the DR-0002 "
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
