#!/usr/bin/env python3
"""Write the `klt sim`-shaped corner-matrix envelope for T1 item 5 (issue #91).

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
* ``status`` is *derived*, never asserted: ``pass`` only if every corner meets
  every ratified target bound, else ``fail``. Kickback misses its target at
  44/45 corners, so the derived status is ``fail`` and item 5 stays unmet --
  with evidence now, rather than ``no_evidence``. No bound is relaxed.
* Stretch bounds are carried per row in ``spec_rows`` (counts of corners
  inside each), but only the target bound drives ``status``.
* The supply/power row is derived: ``i_static_ua`` x the corner's ``vdd``
  (average static power; the same derivation the characterization report uses).

Usage (from the repo root):

    python3 signoff/make_item5_envelope.py           # write (append-only)
    python3 signoff/make_item5_envelope.py --check   # exit 1 on drift

The output name embeds the four record ids; an existing different file is
never overwritten (a new record set mints a new file -- re-pin the manifest).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NETLIST = "design/comparator.spice"

# (bench, record id) -- the four records DR-0002 ratified and the
# characterization report scores.
RECORDS = [
    ("comparator-offset-mc", "20260910-124917-4805118"),
    ("comparator-preamp-noise", "20260910-125200-4805118"),
    ("comparator-regeneration", "20260910-125206-4805118"),
    ("comparator-kickback", "20260910-125341-4805118"),
]

# Ratified rows (DR-0002 Decision table; README.md target-spec table).
# (name, label, bench, unit, target max, stretch max)
ROWS = [
    ("offset_3sigma_mv", "Offset sigma (3-sigma input-referred)", "comparator-offset-mc", "mV", 15.0, 8.0),
    ("input_noise_uv_rms", "Input-referred noise", "comparator-preamp-noise", "uV", 1000.0, 600.0),
    ("decision_time_od50_ns", "Decision time (50 mV overdrive)", "comparator-regeneration", "ns", 1.5, 0.8),
    ("kickback_1k_peak_mv", "Kickback into 1 kOhm", "comparator-kickback", "mV", 5.0, 2.0),
    ("supply_power_uw", "Supply / power (avg static)", "comparator-regeneration", "uW", 1000.0, 500.0),
]


def _value(row: str, point: dict) -> float:
    m = point["measurements"]
    return {
        "offset_3sigma_mv": lambda: m["vos_3sig_mv"],
        "input_noise_uv_rms": lambda: m["vn_in_uv"],
        "decision_time_od50_ns": lambda: m["td_od50_ns"],
        "kickback_1k_peak_mv": lambda: m["kick_1k_peak_mv"],
        "supply_power_uw": lambda: m["i_static_ua"] * point["vdd"],
    }[row]()


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def output_path() -> Path:
    tag = "-".join(rid for _, rid in RECORDS)
    return REPO_ROOT / "sim" / "corner-matrix" / f"item5-corner-matrix-{tag}.json"


def build_envelope() -> dict:
    recs = {}
    sources = []
    for bench, rid in RECORDS:
        p = REPO_ROOT / "sim" / bench / "records" / f"{rid}.json"
        recs[bench] = json.loads(p.read_text())
        sources.append({"path": p.relative_to(REPO_ROOT).as_posix(), "content_hash": _sha(p)})

    ctxs = {b: r["context"] for b, r in recs.items()}
    nl_sha = {c["dut_netlist_sha256"] for c in ctxs.values()}
    assert len(nl_sha) == 1, f"records disagree on DUT netlist: {nl_sha}"
    assert nl_sha.pop() == _sha(REPO_ROOT / NETLIST).split(":")[1], "design netlist changed since records"
    ids = {b: [p["corner_id"] for p in r["points"]] for b, r in recs.items()}
    corner_ids = ids["comparator-offset-mc"]
    assert all(v == corner_ids for v in ids.values()) and len(corner_ids) == 45
    for r in recs.values():
        assert all(p["status"] == "ok" for p in r["points"])

    by_corner = {b: {p["corner_id"]: p for p in r["points"]} for b, r in recs.items()}
    corners = []
    for cid in corner_ids:
        base = by_corner["comparator-offset-mc"][cid]
        meas = []
        for name, _label, bench, unit, tgt, stretch in ROWS:
            v = _value(name, by_corner[bench][cid])
            meas.append({
                "name": name, "unit": unit, "value": v,
                "limits": {"max": tgt}, "margin": tgt - v,
                "status": "pass" if v <= tgt else "fail",
                "within_stretch": v <= stretch,
            })
        corners.append({
            "corner_id": cid, "process": base["corner"], "temp_c": base["temp_c"],
            "vdd": base["vdd"],
            "status": "pass" if all(m["status"] == "pass" for m in meas) else "fail",
            "measurements": meas,
        })

    rollup, spec_rows = [], []
    for name, label, bench, unit, tgt, stretch in ROWS:
        vals = [(c["corner_id"], m) for c in corners for m in c["measurements"] if m["name"] == name]
        wc_id, wc = min(vals, key=lambda t: t[1]["margin"])
        n_t = sum(1 for _, m in vals if m["status"] == "pass")
        n_s = sum(1 for _, m in vals if m["within_stretch"])
        status = "pass" if n_t == len(vals) else "fail"
        rollup.append({
            "name": name, "unit": unit, "limits": {"max": tgt}, "status": status,
            "worst_case": {"corner_id": wc_id, "value": wc["value"], "margin": wc["margin"]},
        })
        spec_rows.append({
            "name": name, "label": label, "unit": unit,
            "target_max": tgt, "stretch_max": stretch,
            "corners_total": len(vals), "corners_within_target": n_t,
            "corners_within_stretch": n_s,
            "min": min(m["value"] for _, m in vals), "max": wc["value"],
            "binding_corner": wc_id, "evidence_bench": bench,
        })

    passed = sum(1 for c in corners if c["status"] == "pass")
    failed = len(corners) - passed
    status = "pass" if failed == 0 else "fail"
    return {
        "schema_version": 1,
        "netlist": NETLIST,
        "status": status,
        "corner_count": len(corners),
        "passed": passed,
        "failed": failed,
        "errored": 0,
        "wrapper": (
            "NOT a `klt sim` run. Hand-wrapped by signoff/make_item5_envelope.py "
            "from committed sim/*/records/*.json (harness format; ngspice-46, "
            "gf180mcuD, 45-point full-factorial PVT), values copied verbatim, no "
            "re-simulation. status is derived from the DR-0002 ratified TARGET "
            "bounds at every corner; stretch is reported in spec_rows only. "
            "Supply/power = i_static_ua x vdd."
        ),
        "scored_against": "spec/decision-records/DR-0002-target-spec-ratification.md",
        "source_records": sources,
        "spec_rows": spec_rows,
        "metrics": {"corner_count": len(corners), "corners_passed": passed, "corners_failed": failed},
        "provenance": {"input": {"path": NETLIST, "role": "netlist", "content_hash": _sha(REPO_ROOT / NETLIST)}},
        "measurements": rollup,
        "corners": corners,
    }


def envelope_text() -> str:
    return json.dumps(build_envelope(), indent=2) + "\n"


def main() -> int:
    out = output_path()
    text = envelope_text()
    rel = out.relative_to(REPO_ROOT)
    if "--check" in sys.argv[1:]:
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
