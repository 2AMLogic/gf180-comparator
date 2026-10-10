#!/usr/bin/env python3
"""Dispatch a bench's `klt sim` legs and mint an append-only evidence record.

    python3 sim/tools/klt_record.py BENCH [--work DIR] [--from-report DIR]
        [--dut ID|BINDING.json] [--label TEXT]

1. (unless --from-report) generates the requests with mk_klt_request.py and
   submits every leg with `klt sim`. The grid goes to the Spot fleet through
   KLT_SIM_BACKEND=batch; this script REFUSES to run a multi-unit grid on a
   local backend (shared dispatch worker: no hand-rolled ngspice grids).
2. computes each tb.json `measure` quantity from the raw per-leg values;
3. writes sim/<bench>/{records,corners,netlist-snapshots}/<record-id>.* --
   never overwriting an existing file (sim/ is append-only evidence).

The derived values are scored against the RATIFIED bounds (README.md target
table, DR-0002); nothing is relaxed. The record states pass/fail per row and
per corner.

Source identity (issue #151). A record is minted from the work dir's
`source-bundle.json` (written by mk_klt_request.py at request time), NEVER
from the checkout at ingest time: the DUT/testbench identity, the `measure`
expressions, the commit and the dirty state all come from the bundle. Before
anything is written under sim/, ingestion verifies, and refuses with a named
diagnostic on failure:

    LEGACY_WORKDIR_UNBOUND     no bundle (pre-#151 work dir): provenance
                               unknown. `--legacy-diagnostic` prints a
                               NON-CITABLE table instead; nothing is written.
    SOURCE_BUNDLE_UNSUPPORTED  unknown bundle schema/version
    BENCH_MISMATCH / DUT_SELECTION_MISMATCH
                               the bundle was generated for another bench /
                               DUT than the one named on the command line
    STAGED_SOURCE_MISSING / STAGED_SOURCE_TAMPERED
                               a staged request, body, PDK include copy or
                               source copy is gone or no longer matches
    SOURCE_BUNDLE_INCONSISTENT the bundle's own identity fields disagree
                               with the staged bytes / request set
    REPORT_UNLINKED            a report carries no netlist hash to link it
    REPORT_SOURCE_MISMATCH     a report's simulated netlist (or its include
                               closure) is not this bundle's body/DUT/fragment
    REPORT_REQUEST_MISMATCH    a report's measurements / Monte Carlo
                               declaration differ from the submitted request
    SOURCE_COMMIT_MISMATCH     the bundle claims a clean commit whose files
                               differ from the staged bytes

`comparator-offset-cm-window` (issue #182) is refused outright with
UNSUPPORTED_EXECUTOR_CAPABILITY: the fleet runner cannot address its nested
sweep's six points. `collect_cm_window` / `derive_cm_window` validate the
specified same-draw contract against synthetic reports only.

Differences between the bundle and today's checkout (fragment, manifest,
binding entry, selected DUT, DUT netlist) are reported as source drift; the
record still cites the bundle's (originating) sources, never today's.

A record is citable REFERENCE evidence (`"reference": true`) only when BOTH
gates pass: exact PVT/MC coverage of the bundled requests (#152, `complete`;
otherwise exit 1) and verified, clean source identity (#151, `citable`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))

from harness import corners as hc  # noqa: E402
from harness import dut as hdut  # noqa: E402
from harness import testbench as htb  # noqa: E402

sys.path.insert(0, str(HERE))
import mk_klt_request as mk  # noqa: E402

LEGS = {
    "comparator-kickback": ["main"],
    "comparator-regeneration": ["main"],
    "comparator-preamp-noise": ["noise", "ac"],
    "comparator-offset-mc": ["main"],
    "comparator-offset-tran": ["main"],
}

#: Ratified TARGET / STRETCH bounds (README.md table, DR-0002). Read-only.
#: key -> (label, derived measure name, target max, stretch max, unit)
SPEC = {
    "comparator-kickback": ("Kickback", "kick_1k_peak_mv", 5.0, 2.0, "mV"),
    "comparator-regeneration": ("Decision time @ 50 mV", "td_od50_ns", 1.5, 0.8, "ns"),
    "comparator-preamp-noise": ("Input-referred noise", "vn_in_uv", 1000.0, 600.0, "uV rms"),
    "comparator-offset-mc": ("Offset 3-sigma", "vos_3sig_mv", 15.0, 8.0, "mV"),
    # Scored on the CONSERVATIVE derived total (simulated whole-comparator
    # sigma + hand-budgeted load-R term at the conservative coefficient), so
    # the verdict is the pessimistic one; the cited-coefficient total and the
    # purely simulated value are reported alongside it (issue #157).
    "comparator-offset-tran": ("Offset 3-sigma (whole-comparator, incl. derived load-R budget)",
                               "vos_3sig_total_cons_mv", 15.0, 8.0, "mV"),
}
POWER_TARGET_UW = 1000.0  # <= 1 mW static, README.md supply/power row

MATH = {"abs": abs, "max": max, "min": min, "sqrt": math.sqrt, "ln": math.log, "log": math.log10}


def corner_id(raw: str, vdd: float) -> tuple[str, str]:
    """'tt/27C[/mcN]' + the request's supply -> ('tt_27c_3.30v', 'mcN' or '').

    The supply is not in klt's corner id: it is baked into each request's
    body netlist (one request per supply point, see mk_klt_request.py)."""
    parts = raw.split("/")
    proc = parts[0]
    temp = next(float(x.rstrip("C")) for x in parts[1:] if x.endswith("C"))
    sample = next((x for x in parts[1:] if x.startswith("mc")), "")
    return f"{proc}_{temp:g}c_{vdd:.2f}v", sample


def collect(report: dict, vdd: float) -> tuple[dict, list]:
    """report -> ({corner_id: {sample: {name: value}}}, bad statuses)."""
    out: dict = {}
    bad = []
    for c in report["corners"]:
        cid, sample = corner_id(c["corner_id"], vdd)
        if c["status"] != "pass":
            bad.append((c["corner_id"], c["status"]))
            continue
        out.setdefault(cid, {})[sample] = {
            m["name"]: m["value"] for m in c["measurements"] if m.get("value") is not None
        }
    return out, bad


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def expected_units(request: dict, vdd: float) -> dict[str, set[str]]:
    """Saved request -> {corner_id: expected sample ids} (the requested grid).

    Process x temperature from the request's `corners`, the supply from the
    body netlist it was minted for, and the draws from `monte_carlo.n`
    (sample ids `mc0`..`mc{n-1}`; a plain corner has the single id "")."""
    n = (request.get("monte_carlo") or {}).get("n")
    samples = {f"mc{i}" for i in range(n)} if isinstance(n, int) and n > 0 else {""}
    c = request["corners"]
    return {
        f"{p['name']}_{float(t):g}c_{vdd:.2f}v": set(samples)
        for p in c["process"]
        for t in c["temperature_c"]
    }


def collect_checked(report: dict, request: dict, vdd: float, tag: str = "") -> tuple[dict, list, list]:
    """report + its saved request -> (collected, bad statuses, coverage issues).

    Unlike `collect`, nothing is overwritten or silently dropped. Every issue is
    a string led by a named diagnostic code: DUPLICATE_UNIT, MISSING_UNIT,
    UNEXPECTED_UNIT, FAILED_UNIT, MC_DECLARATION_MISMATCH, NONFINITE_INGREDIENT."""
    pre = f"{tag}: " if tag else ""
    issues: list[str] = []
    want = expected_units(request, vdd)
    declared = request.get("monte_carlo")
    got_mc = (report.get("environment") or {}).get("monte_carlo")
    if (declared is None) != (not got_mc):
        issues.append(f"{pre}MC_DECLARATION_MISMATCH: request declares {declared!r}, report declares {got_mc!r}")
    elif declared:
        for k in ("n", "seed", "vary"):
            if k in declared and got_mc.get(k) != declared[k]:
                issues.append(f"{pre}MC_DECLARATION_MISMATCH: {k} requested {declared[k]!r}, report says {got_mc.get(k)!r}")
    ingredients = [m["name"] for m in request.get("measurements", []) if "name" in m]
    out: dict = {}
    bad: list = []
    seen: set = set()
    failed: set = set()
    for c in report["corners"]:
        raw = c["corner_id"]
        cid, sample = corner_id(raw, vdd)
        if raw in seen:
            issues.append(f"{pre}DUPLICATE_UNIT: {raw} appears more than once")
            continue
        seen.add(raw)
        if cid not in want or sample not in want[cid]:
            issues.append(f"{pre}UNEXPECTED_UNIT: {raw} is not in the requested grid")
            continue
        if c["status"] != "pass":
            bad.append((raw, c["status"]))
            failed.add((cid, sample))
            issues.append(f"{pre}FAILED_UNIT: {raw} -> {c['status']}")
            continue
        vals = {m["name"]: m["value"] for m in c["measurements"] if m.get("value") is not None}
        invalid = [name for name in ingredients if not _finite(vals.get(name))]
        for name in invalid:
            issues.append(f"{pre}NONFINITE_INGREDIENT: {raw} {name} = {vals.get(name)!r}")
        if invalid:
            failed.add((cid, sample))  # reported above; not also MISSING_UNIT
            continue
        out.setdefault(cid, {})[sample] = vals
    for cid, smp in want.items():
        for s in sorted(smp):
            if (cid, s) not in failed and s not in out.get(cid, {}):
                issues.append(f"{pre}MISSING_UNIT: {cid}{'/' + s if s else ''} has no result")
    return out, bad, issues


ARITH_ERRORS = (ArithmeticError, ValueError)  # ZeroDivision/Overflow are ArithmeticError


def _eval_outputs(cid: str, thunks: dict, problems: list) -> dict | None:
    """Evaluate each derived output of one corner/unit `cid`.

    Returns {name: value}, or None if any output raised an arithmetic error
    or came out non-finite (a named DERIVE_ERROR / NONFINITE_DERIVED problem
    per output is appended; every output is still tried so no diagnostic is
    lost). A corner with a bad output yields no result: it cannot count
    towards complete reference evidence."""
    out: dict = {}
    ok = True
    for name, thunk in thunks.items():
        try:
            v = thunk()
        except ARITH_ERRORS as e:
            problems.append(f"DERIVE_ERROR: {cid} {name}: {type(e).__name__}: {e}")
            ok = False
            continue
        if not _finite(v):
            problems.append(f"NONFINITE_DERIVED: {cid} {name} = {v!r}")
            ok = False
            continue
        out[name] = v
    return out if ok else None

#: Raw per-draw `.meas` ingredients of comparator-offset-tran (tb.json `analyses`).
TRAN_INGREDIENTS = ("t_trip", "dn_start", "dn_end", "dd_start", "dd_end", "ap_start")


def derive_offset_tran(tb, raw: dict, ids: list[str], problems: list[str]) -> dict:
    """Whole-comparator transient-MC statistics per PVT point (issue #157).

    Per draw (all quantities from ONE Monte-Carlo draw):
      cycle c   = floor((t_trip - t0)/T)           the clock period whose decision flipped
      level k   = c - lead                          index into the staircase
      V_trip    = v0 + k*step - step/2              midpoint of the one-step bracket
      A_v       = (dd_end - dd_start)/(v_end - v0)  preamp gain, end-of-reset samples
      V_os_pre  = v_end - dd_end/A_v                DC-equivalent preamp offset (same draw)
      V_lat     = V_trip - V_os_pre                 decision-stage contribution
    Population statistics over the draws are then fed to tb.json's `measure`
    expressions. The staircase quantises V_trip by a uniform +-step/2, so
    its variance step^2/12 is subtracted in quadrature (`q2`); the raw sigma
    is reported too. Any out-of-range or malformed draw is a named problem
    and its whole PVT point is dropped (never silently clipped)."""
    P = tb.params
    t0, period, high = P["stair_t0_ns"] * 1e-9, P["stair_period_ns"] * 1e-9, P["stair_clk_high_ns"] * 1e-9
    v0, step = P["stair_v0_mv"] * 1e-3, P["stair_step_mv"] * 1e-3
    levels, lead = int(P["stair_levels"]), int(P["stair_lead_cycles"])
    v_end = v0 + (levels - 1) * step
    pstd = statistics.pstdev
    res: dict = {}
    for cid in ids:
        vdd = float(cid.rsplit("_", 1)[1].rstrip("v"))
        trips, pres, lats, avs, vdrops = [], [], [], [], []
        bad = []
        for key, s in raw[cid].items():
            # collect_checked already drops non-finite ingredients; re-checked
            # here so a hand-built `raw` can never reach math.floor(nan).
            if not all(_finite(s.get(n)) for n in TRAN_INGREDIENTS):
                bad.append(f"NONFINITE_INGREDIENT: {cid}/{key} "
                           + ", ".join(f"{n}={s.get(n)!r}" for n in TRAN_INGREDIENTS))
                continue
            c = math.floor((s["t_trip"] - t0) / period)
            phase = (s["t_trip"] - t0) - c * period
            k = c - lead
            gain = (s["dd_end"] - s["dd_start"]) / (v_end - v0)
            err = None
            if s["dn_start"] > 0.1 or s["dn_end"] < 0.9:
                err = f"BAD_ENDPOINT_DECISION: {cid}/{key} dn_start={s['dn_start']:.3g} dn_end={s['dn_end']:.3g}"
            elif not 1 <= k <= levels - 1:
                err = f"TRIP_OUT_OF_RANGE: {cid}/{key} flipped in cycle {c} (level {k}) outside 1..{levels - 1}"
            elif phase > high + 1e-9:
                err = f"LATE_FLIP: {cid}/{key} output crossed {phase * 1e9:.2f} ns after the clock rise"
            elif gain <= 0:
                err = f"ZERO_GAIN: {cid}/{key} preamp gain = {gain!r}"
            if err:
                bad.append(err)
                continue
            trip = v0 + k * step - step / 2
            pre = v_end - s["dd_end"] / gain
            trips.append(trip)
            pres.append(pre)
            lats.append(trip - pre)
            avs.append(gain)
            vdrops.append((vdd - s["ap_start"]) / gain)
        if bad:
            problems += bad
            continue
        env = dict(MATH, **P)
        env.update({
            "n": len(trips), "q2": step * step / 12,
            "s_trip": pstd(trips), "m_trip": statistics.fmean(trips),
            "s_pre": pstd(pres), "m_pre": statistics.fmean(pres),
            "s_lat": pstd(lats), "m_lat": statistics.fmean(lats),
            "m_av": statistics.fmean(avs),
            "vdrop_over_av": statistics.fmean(vdrops),
        })
        d = _eval_outputs(cid, {
            name: (lambda expr=expr: eval(expr.replace("^", "**"), {"__builtins__": {}}, env))
            for name, expr in tb.measure.items()
        }, problems)
        if d is not None:
            res[cid] = d
    return res


# ---------------------------------------------------------------------------
# Consumer-window common-mode feasibility adapter (issue #182). PDK-free
# validation of the six-point same-draw contract specified by
# mk_klt_request.cm_window_leg. It mints nothing: `main` refuses the bench
# (UNSUPPORTED_EXECUTOR_CAPABILITY) until a fleet runner with
# `measurements[].expr` is established, and full 45-point coverage is pending.
# ---------------------------------------------------------------------------

CM_WINDOW_COMMON_MODES = ("dn", "mid", "up")
#: Coordinate read-back tolerance (V): the stimulus sources are ideal, so a
#: read-back off by more than this names a different sweep point.
CM_COORD_TOL_V = 1e-6


def check_cm_window_request(req: dict) -> list[str]:
    """REQUEST_SHAPE_INVALID issues; [] only for ONE dc analysis per draw whose
    18 values all index that one solve with the fixed label -> point mapping."""
    issues = []
    if req.get("analysis") != {"kind": "dc", "args": mk.CM_WINDOW_DC_ARGS}:
        issues.append(f"REQUEST_SHAPE_INVALID: analysis {req.get('analysis')!r} is not the one nested "
                      f"sweep `dc {mk.CM_WINDOW_DC_ARGS}`")
    mc = req.get("monte_carlo") or {}
    if mc.get("vary") != "mismatch" or not isinstance(mc.get("n"), int) or mc["n"] < 1:
        issues.append(f"REQUEST_SHAPE_INVALID: monte_carlo {req.get('monte_carlo')!r} is not a mismatch draw set")
    want = {m["name"]: m["expr"] for m in mk.cm_window_measurements()}
    got = req.get("measurements") or []
    names = [m.get("name") for m in got]
    if sorted(map(str, names)) != sorted(want):
        issues.append(f"REQUEST_SHAPE_INVALID: measurements {sorted(map(str, names))} != the six-point set")
    for m in got:
        if "spice" in m:
            issues.append(f"REQUEST_SHAPE_INVALID: {m.get('name')!r} is a `.meas` card; `at=` on the nested "
                          "sweep cannot select the outer common-mode coordinate")
        elif m.get("name") in want and m.get("expr") != want[m["name"]]:
            issues.append(f"REQUEST_SHAPE_INVALID: {m['name']!r} reads {m.get('expr')!r}, its point is "
                          f"{want[m['name']]!r}")
    if (req.get("batch") or {}).get("runner_version_check") != "enforce":
        issues.append("REQUEST_SHAPE_INVALID: batch.runner_version_check must be 'enforce' (an older runner "
                      "must refuse before simulating, not be detected afterwards)")
    return issues


def check_cm_index_request(req: dict) -> list[str]:
    """REQUEST_SHAPE_INVALID issues; [] only for ONE monotonic-index dc analysis
    per draw whose 18 raw `.meas dc ... at=<k>` cards are exactly the fixed
    label -> index mapping (issue #218). No `expr` entry is accepted."""
    issues = []
    if req.get("analysis") != {"kind": "dc", "args": mk.CM_INDEX_DC_ARGS}:
        issues.append(f"REQUEST_SHAPE_INVALID: analysis {req.get('analysis')!r} is not the one monotonic "
                      f"index sweep `dc {mk.CM_INDEX_DC_ARGS}`")
    mc = req.get("monte_carlo") or {}
    if mc.get("vary") != "mismatch" or not isinstance(mc.get("n"), int) or mc["n"] < 1:
        issues.append(f"REQUEST_SHAPE_INVALID: monte_carlo {req.get('monte_carlo')!r} is not a mismatch draw set")
    want = {m["name"]: m["spice"] for m in mk.cm_index_measurements()}
    got = req.get("measurements") or []
    names = [m.get("name") for m in got]
    if sorted(map(str, names)) != sorted(want):
        issues.append(f"REQUEST_SHAPE_INVALID: measurements {sorted(map(str, names))} != the six-point set")
    for m in got:
        if "expr" in m:
            issues.append(f"REQUEST_SHAPE_INVALID: {m.get('name')!r} is an `expr` entry; the index bench "
                          "uses raw `.meas` cards")
        elif m.get("name") in want and m.get("spice") != want[m["name"]]:
            issues.append(f"REQUEST_SHAPE_INVALID: {m['name']!r} reads {m.get('spice')!r}, its point is "
                          f"{want[m['name']]!r}")
    return issues


def check_cm_index_executor(report: dict) -> list[str]:
    """The report must name the fleet runner that produced it (executor
    identity). No `expr` capability is needed, so no version gate."""
    remote = (report.get("environment") or {}).get("remote")
    runners = (remote.get("fleet") or [remote]) if isinstance(remote, dict) else remote
    if not isinstance(runners, list) or not runners or not all(
            isinstance(r, dict) and r.get("runner_klt_version") for r in runners):
        return ["UNSUPPORTED_EXECUTOR_CAPABILITY: report names no fleet runner (environment.remote)"]
    return []


def collect_cm_index(report: dict, request: dict, vdd: float) -> tuple[dict, list[str]]:
    """Index-stimulus counterpart of `collect_cm_window`: same identity,
    coordinate read-back and finiteness checks over the 18 `.meas` values."""
    return collect_cm_window(report, request, vdd, index=True)


def check_cm_window_executor(report: dict) -> list[str]:
    """UNSUPPORTED_EXECUTOR_CAPABILITY unless every runner that produced the
    report is a version-matched klt with `expr` (environment.remote)."""
    remote = (report.get("environment") or {}).get("remote")
    runners = (remote.get("fleet") or [remote]) if isinstance(remote, dict) else remote
    if not isinstance(runners, list) or not runners:
        return ["UNSUPPORTED_EXECUTOR_CAPABILITY: report names no fleet runner (environment.remote)"]
    issues = []
    for r in runners:
        r = r if isinstance(r, dict) else {}
        gap = mk.cm_window_capability_gap(r.get("runner_klt_version"))
        if gap:
            issues.append(f"UNSUPPORTED_EXECUTOR_CAPABILITY: {gap}")
        elif r.get("runner_compatibility") != "match":
            issues.append(f"UNSUPPORTED_EXECUTOR_CAPABILITY: runner_compatibility "
                          f"{r.get('runner_compatibility')!r}, not 'match'")
    return issues


def pair_cm_window_reports(reports: list[dict]) -> dict:
    """The ONE report that may carry a supply point's draws.

    A draw's six points must come from one analysis of one instance. Values
    pooled from separate requests are refused even when their monte_carlo
    seeds are equal: a shared seed reproduces a sequence of separately
    randomized decks; it does not make two decks the same draw."""
    if len(reports) != 1:
        seeds = {json.dumps(((r.get("environment") or {}).get("monte_carlo") or {}).get("seed")) for r in reports}
        refuse("SEPARATE_REQUEST_PAIRING",
               f"{len(reports)} reports offered for one supply point"
               + (" (all with the same monte_carlo seed)" if len(seeds) == 1 and reports else "")
               + "; seed equality across requests is not draw identity")
    return reports[0]


def collect_cm_window(report: dict, request: dict, vdd: float, index: bool = False) -> tuple[dict, list[str]]:
    """-> ({corner_id: {mcN: {label: dv}}}, issues), keyed by identity, never
    by position. A sample contributes only when it carries every one of the
    18 named values, finite, with both coordinate read-backs matching its
    labels; anything else is a named issue and the sample is excluded."""
    issues = (check_cm_index_request(request) + check_cm_index_executor(report) if index
              else check_cm_window_request(request) + check_cm_window_executor(report))
    declared, got_mc = request.get("monte_carlo") or {}, (report.get("environment") or {}).get("monte_carlo") or {}
    for k in ("n", "seed", "vary"):
        if got_mc.get(k) != declared.get(k):
            issues.append(f"MC_DECLARATION_MISMATCH: {k} requested {declared.get(k)!r}, report says {got_mc.get(k)!r}")
    want = expected_units(request, vdd)
    names = {m["name"] for m in (mk.cm_index_measurements() if index else mk.cm_window_measurements())}
    out: dict = {}
    seen: set = set()
    for c in report.get("corners", []):
        raw = c.get("corner_id")
        cid, sample = corner_id(raw, vdd)
        if (cid, sample) in seen:
            issues.append(f"DUPLICATE_SAMPLE: {raw} appears more than once")
            out.get(cid, {}).pop(sample, None)  # neither copy is trusted
            continue
        seen.add((cid, sample))
        if not sample.startswith("mc") or cid not in want or sample not in want[cid]:
            issues.append(f"UNEXPECTED_SAMPLE: {raw} is not a requested draw")
            continue
        if (c.get("monte_carlo") or {}).get("sample_index") != int(sample[2:]):
            issues.append(f"SAMPLE_IDENTITY_MISMATCH: {raw} carries monte_carlo {c.get('monte_carlo')!r}")
            continue
        if c.get("status") != "pass":
            issues.append(f"FAILED_SAMPLE: {raw} -> {c.get('status')}")
            continue
        vals: dict = {}
        bad = []
        for m in c.get("measurements", []):
            if m.get("name") in vals:
                bad.append(f"DUPLICATE_VALUE: {raw} {m.get('name')}")
            vals[m.get("name")] = m.get("value")
        bad += [f"UNEXPECTED_VALUE: {raw} {n!r} is not a six-point label" for n in sorted(set(vals) - names, key=str)]
        bad += [f"INCOMPLETE_SAMPLE: {raw} has no {n}" for n in sorted(names - set(vals))]
        bad += [f"NONFINITE_VALUE: {raw} {n} = {vals[n]!r}" for n in sorted(names & set(vals)) if not _finite(vals[n])]
        if not bad:
            for label, (vcmd, vd, _) in mk.CM_WINDOW_POINTS.items():
                if abs(vals[f"xcm_{label}"] - vcmd) > CM_COORD_TOL_V or abs(vals[f"xvd_{label}"] - vd) > CM_COORD_TOL_V:
                    bad.append(f"COORDINATE_MISMATCH: {raw} {label} read back vcmd={vals[f'xcm_{label}']!r} "
                               f"vd={vals[f'xvd_{label}']!r}, labelled vcmd={vcmd!r} vd={vd!r}")
        if bad:
            issues += bad
            continue
        out.setdefault(cid, {})[sample] = {label: vals[f"dv_{label}"] for label in mk.CM_WINDOW_POINTS}
    for cid, smp in want.items():
        for s in sorted(smp):
            if (cid, s) not in seen:
                issues.append(f"MISSING_SAMPLE: {cid}/{s} has no result")
    return out, issues


def derive_cm_window_draw(dv: dict) -> dict:
    """ONE draw's six differential outputs -> per common mode p the gain
    A_p = (dv_p(2m) - dv_p(0))/0.002 and offset V_os,p = -dv_p(0)/A_p, plus
    the paired deltas V_os,dn - V_os,mid and V_os,up - V_os,mid of that same
    draw. Raises ValueError(code, detail) on a non-positive/non-finite gain."""
    d: dict = {}
    for p in CM_WINDOW_COMMON_MODES:
        v0, v1 = dv[f"{p}_0"], dv[f"{p}_2m"]
        gain = (v1 - v0) / mk.CM_WINDOW_VD_STEP_V
        if not _finite(gain) or gain <= 0:
            raise ValueError("INVALID_GAIN", f"{p} gain = {gain!r}")
        vos = -v0 / gain
        if not _finite(vos):
            raise ValueError("NONFINITE_DERIVED", f"{p} offset = {vos!r}")
        d[f"av_{p}"], d[f"vos_{p}"] = gain, vos
    d["dvos_dn"] = d["vos_dn"] - d["vos_mid"]
    d["dvos_up"] = d["vos_up"] - d["vos_mid"]
    return d


def derive_cm_window(samples: dict) -> tuple[dict, list[str]]:
    """Population statistics per PVT point, named as the bench's tb.json
    `measure` (population sigma, as everywhere in this tool). Any invalid
    draw drops its whole PVT point with a named problem."""
    pstd, mean = statistics.pstdev, statistics.fmean
    res: dict = {}
    problems: list[str] = []
    for cid in sorted(samples):
        draws, bad = [], []
        for key in sorted(samples[cid], key=lambda s: int(s[2:])):
            try:
                draws.append(derive_cm_window_draw(samples[cid][key]))
            except ValueError as e:
                bad.append(f"{e.args[0]}: {cid}/{key} {e.args[1]}")
        if bad or not draws:
            problems += bad or [f"EMPTY_POINT: {cid} has no draws"]
            continue
        col = {k: [d[k] for d in draws] for k in draws[0]}
        out = _eval_outputs(cid, {
            "n_samples": lambda: len(draws),
            "sig_vos_mid_mv": lambda: pstd(col["vos_mid"]) * 1e3,
            "mean_vos_mid_uv": lambda: mean(col["vos_mid"]) * 1e6,
            "mean_dvos_dn_uv": lambda: mean(col["dvos_dn"]) * 1e6,
            "sig_dvos_dn_uv": lambda: pstd(col["dvos_dn"]) * 1e6,
            "mean_dvos_up_uv": lambda: mean(col["dvos_up"]) * 1e6,
            "sig_dvos_up_uv": lambda: pstd(col["dvos_up"]) * 1e6,
            "av_dn_mean": lambda: mean(col["av_dn"]),
            "av_mid_mean": lambda: mean(col["av_mid"]),
            "av_up_mean": lambda: mean(col["av_up"]),
            "av_sigma_pct": lambda: pstd(col["av_mid"]) / mean(col["av_mid"]) * 100,
        }, problems)
        if out is not None:
            res[cid] = out
    return res, problems


def derive(bench: str, tb, legs: dict[str, dict]) -> tuple[dict, list]:
    """-> ({corner_id: {derived name: value}}, problems).

    Derived outputs are validated like the raw ingredients: an arithmetic
    failure or a non-finite result drops that corner with a named problem."""
    problems: list[str] = []
    for leg, (_, bad) in legs.items():
        problems += [f"leg {leg}: {cid} -> {st}" for cid, st in bad]
    every = set.union(*(set(v[0]) for v in legs.values())) if legs else set()
    ids = sorted(set.intersection(*(set(v[0]) for v in legs.values())) if legs else set())
    for leg, (c, _) in legs.items():
        for cid in sorted(every - set(c)):
            problems.append(f"MISSING_LEG_CORNER: leg {leg} has no result for {cid}")
    res: dict = {}
    if bench in ("comparator-kickback", "comparator-regeneration"):
        raw = legs["main"][0]
        for cid in ids:
            env = dict(MATH, **raw[cid][""])
            thunks = {
                name: (lambda expr=expr: eval(expr.replace("^", "**"), {"__builtins__": {}}, env))
                for name, expr in tb.measure.items()
            }
            d = _eval_outputs(cid, thunks, problems)
            if d is not None:
                res[cid] = d
        return res, problems
    if bench == "comparator-preamp-noise":
        for cid in ids:
            n, a = legs["noise"][0][cid][""], legs["ac"][0][cid][""]
            if not _finite(a.get("av_dc")) or a["av_dc"] == 0:
                problems.append(f"ZERO_GAIN: {cid} av_dc = {a.get('av_dc')!r}")
                continue
            d = _eval_outputs(cid, {
                "av_dc": lambda: a["av_dc"],
                "onoise_uv": lambda: n["onoise_total"] * 1e6,
                "vn_in_uv": lambda: n["onoise_total"] / a["av_dc"] * 1e6,
                "inoise_band_uv": lambda: n["inoise_total"] * 1e6,
            }, problems)
            if d is not None:
                res[cid] = d
        return res, problems
    if bench == "comparator-offset-tran":
        return derive_offset_tran(tb, legs["main"][0], ids, problems), problems
    # offset-mc: population statistics over the draws. Per draw, gain from the
    # 0 mV and +2 mV points of one dc sweep (same draw), voa = -dv0/gain --
    # the bench's `voa` at vcmd = 0.
    pstd = statistics.pstdev
    for cid in ids:
        smp = list(legs["main"][0][cid].values())
        try:
            ava = [(s["dv1"] - s["dv0"]) / 2e-3 for s in smp]
            if not all(_finite(g) for g in ava):
                problems.append(f"NONFINITE_DERIVED: {cid} per-draw gain")
                continue
            zero = [k for k, g in zip(legs["main"][0][cid], ava) if g == 0]
            if zero:
                problems += [f"ZERO_GAIN: {cid}/{k} gain = 0" for k in zero]
                continue
            voa = [-s["dv0"] / g for s, g in zip(smp, ava)]
            sig = pstd(voa)
            if not all(_finite(v) for v in voa):
                problems.append(f"NONFINITE_DERIVED: {cid} per-draw voa")
                continue
        except ARITH_ERRORS as e:
            problems.append(f"DERIVE_ERROR: {cid} per-draw gain/voa: {type(e).__name__}: {e}")
            continue
        d = _eval_outputs(cid, {
            "n_samples": lambda: len(smp),
            "sig_vos_mv": lambda: sig * 1e3,
            "vos_3sig_mv": lambda: 3 * sig * 1e3,
            "mean_vos_uv": lambda: statistics.fmean(voa) * 1e6,
            "av_mean": lambda: statistics.fmean(ava),
            "av_sigma_pct": lambda: pstd(ava) / statistics.fmean(ava) * 100,
        }, problems)
        if d is not None:
            res[cid] = d
    return res, problems


def node_coverage(derived: dict) -> str:
    """Kickback records: 'both' when every corner carries both input nodes' peaks.

    Records minted before issue #160 derived `kick_1k_peak_mv` from the
    positive node only; they have no `kick_1k_nnode_peak_mv` and are partial
    node coverage ('positive-only'). Anything in between is 'partial'."""
    has = [("kick_1k_nnode_peak_mv" in d and "kick_1k_pnode_peak_mv" in d) for d in derived.values()]
    if has and all(has):
        return "both"
    return "partial" if any(has) else "positive-only"


def node_coverage_line(derived: dict) -> str:
    cov = node_coverage(derived)
    if cov != "both":
        return ("`positive-only` -- PARTIAL node coverage: `kick_1k_peak_mv` here covers the positive "
                "input node alone; the negative node was not measured.")
    n_neg = sum(d["kick_1k_nnode_peak_mv"] > d["kick_1k_pnode_peak_mv"] for d in derived.values())
    return (f"`both` -- `kick_1k_peak_mv` is the maximum of the positive-node (`kick_1k_pnode_peak_mv`) and "
            f"negative-node (`kick_1k_nnode_peak_mv`) peaks; the negative node sets it at {n_neg}/{len(derived)} corners.")


def power_uw(bench: str, cid: str, d: dict) -> float | None:
    if bench != "comparator-regeneration":
        return None
    return d["i_static_ua"] * float(cid.rsplit("_", 1)[1].rstrip("v"))


def git_state() -> tuple[str, bool]:
    """INGEST-time checkout: (short commit, derivation tooling dirty?).

    Only the code that turns raw values into the record (sim/tools,
    sim/harness) matters here; the simulated sources' identity and dirty
    state come from the source bundle (see mk_klt_request.git_state)."""
    sha = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "--short=7", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=all", "--", "sim/tools", "sim/harness"], text=True).strip())
    return sha, dirty


def git_blob(commit: str, path: str) -> bytes | None:
    """`path` as committed at `commit`, or None if this clone cannot read it."""
    try:
        return subprocess.check_output(["git", "-C", str(REPO), "cat-file", "blob", f"{commit}:{path}"],
                                       stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, OSError):
        return None


def klt_version() -> str:
    return subprocess.check_output(["klt", "--version"], text=True).strip()


def refuse(code: str, msg: str):
    """Abort BEFORE anything is published, with a named diagnostic."""
    raise SystemExit(f"{code}: {msg}")


def _staged_path(work: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        refuse("SOURCE_BUNDLE_INCONSISTENT", f"staged path {rel!r} escapes the work dir")
    return work / p


def load_bundle(work: Path, bench: str) -> dict:
    """work dir -> its source bundle (refuses a legacy / foreign bundle)."""
    path = work / mk.BUNDLE_NAME
    if not path.is_file():
        refuse("LEGACY_WORKDIR_UNBOUND",
               f"{work} has no {mk.BUNDLE_NAME}: it predates source binding (issue #151), so the "
               "sources that produced its reports cannot be established and no reference record "
               "can be minted from it. Re-run from a clean commit, or pass --legacy-diagnostic "
               "for a NON-CITABLE printout (nothing is written).")
    try:
        b = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        refuse("SOURCE_BUNDLE_UNSUPPORTED", f"{path} is not valid JSON: {e}")
    if b.get("schema") != mk.BUNDLE_SCHEMA or b.get("version") != mk.BUNDLE_VERSION:
        refuse("SOURCE_BUNDLE_UNSUPPORTED",
               f"{path}: schema {b.get('schema')!r} version {b.get('version')!r}; this tool reads "
               f"{mk.BUNDLE_SCHEMA!r} version {mk.BUNDLE_VERSION}")
    if b.get("bench") != bench:
        refuse("BENCH_MISMATCH", f"{path} was generated for {b.get('bench')!r}, not {bench!r}")
    return b


def check_dut_selection(b: dict, dut_arg: str | None) -> None:
    """`--dut` at ingest, if given, must name the bundle's selection."""
    if dut_arg is None:
        return
    d = b["dut"]
    ok = dut_arg in (d.get("selector"), d.get("dut_id"), d.get("key"))
    if not ok and Path(dut_arg).is_file():
        p = Path(dut_arg).resolve()
        ok = (mk.repo_rel(p, REPO) or str(p)) == d.get("binding_config")
    if not ok:
        refuse("DUT_SELECTION_MISMATCH",
               f"--dut {dut_arg!r} but the work dir was generated for DUT {d.get('dut_id')!r} "
               f"(selector {d.get('selector')!r}); a report cannot be re-attributed to another DUT")


def verify_staged(work: Path, b: dict, names: dict) -> None:
    """Re-hash every staged input and cross-check the bundle's own fields."""
    staged = b.get("staged") or {}
    for rel, want in sorted(staged.items()):
        f = _staged_path(work, rel)
        if not f.is_file():
            refuse("STAGED_SOURCE_MISSING", f"{rel} is listed in the source bundle but absent")
        got = mk.sha256_file(f)
        if got != want:
            refuse("STAGED_SOURCE_TAMPERED",
                   f"{rel} sha256 {got[:16]} != {want[:16]} recorded at request generation")
    d, t = b["dut"], b["testbench"]
    expect = {
        d["staged_netlist"]: d["netlist_sha256"],
        f"{t['staged_dir']}/{t['netlist']}": t["netlist_sha256"],
        f"{t['staged_dir']}/{htb.MANIFEST_NAME}": t["manifest_sha256"],
    }
    for n, r in (b.get("requests") or {}).items():
        expect[r["request"]] = r["request_sha256"]
        expect[r["netlist"]] = r["netlist_sha256"]
    for rel, want in expect.items():
        if staged.get(rel) != want:
            refuse("SOURCE_BUNDLE_INCONSISTENT",
                   f"{rel}: bundle identity sha256 {str(want)[:16]} is not the staged sha256 "
                   f"{str(staged.get(rel))[:16]}")
    binding = json.loads(_staged_path(work, d["staged_binding"]).read_text())
    if (binding.get("key") != d.get("key") or mk.canonical_sha256(binding.get("entry")) != d["binding_entry_sha256"]):
        refuse("SOURCE_BUNDLE_INCONSISTENT", "staged DUT binding entry does not match the bundle's binding hash")
    if sorted(b.get("requests") or {}) != sorted(names):
        refuse("SOURCE_BUNDLE_INCONSISTENT",
               f"bundle requests {sorted(b.get('requests') or {})} != expected legs {sorted(names)}")
    sources = {rel: h for rel, h in staged.items() if rel.startswith(f"{mk.SOURCES_DIR}/")}
    for n, (leg, v) in names.items():
        r = b["requests"][n]
        req = json.loads((work / r["request"]).read_text())
        if req.get("netlist") != r["netlist"] or r.get("leg") != leg or abs(float(r.get("vdd")) - v) > 1e-9:
            refuse("SOURCE_BUNDLE_INCONSISTENT", f"request {n} does not name its bundled body netlist / leg / supply")
        # The body must declare every staged source's sha256: that is what
        # makes the body hash a report quotes bind the included CONTENT (a
        # report without a netlist_closure is linked through it alone).
        declared = mk.declared_source_shas((work / r["netlist"]).read_text())
        if declared != sources:
            diff = sorted(set(declared.items()) ^ set(sources.items()))
            refuse("SOURCE_BUNDLE_INCONSISTENT",
                   f"{r['netlist']} source-sha256 lines do not match the staged sources: {diff[:4]}")


def _report_netlist_sha(report: dict) -> str | None:
    env = report.get("environment") or {}
    if env.get("netlist_sha256"):
        return env["netlist_sha256"]
    h = ((report.get("provenance") or {}).get("input") or {}).get("content_hash") or ""
    return h.split(":", 1)[1] if h.startswith("sha256:") else None


def verify_reports(work: Path, b: dict, names: dict, reports: dict) -> list[str]:
    """Link each report to its submitted request/body -> informational notes."""
    notes = []
    for n in names:
        r, rep = b["requests"][n], reports[n]
        got = _report_netlist_sha(rep)
        if not got:
            refuse("REPORT_UNLINKED",
                   f"report-{n}.json carries no environment.netlist_sha256 / provenance.input "
                   "content hash; it cannot be tied to the submitted body netlist")
        if got != r["netlist_sha256"]:
            refuse("REPORT_SOURCE_MISMATCH",
                   f"report-{n}.json simulated netlist sha256 {got[:16]}, but the bundled "
                   f"{r['netlist']} is {r['netlist_sha256'][:16]}: the report was not produced "
                   "from this request set")
        env = rep.get("environment") or {}
        closure = env.get("netlist_closure")
        if isinstance(closure, list):
            shas = {e.get("sha256") for e in closure if isinstance(e, dict)}
            for what, h in (("DUT netlist", b["dut"]["netlist_sha256"]),
                            ("testbench fragment", b["testbench"]["netlist_sha256"])):
                if h not in shas:
                    refuse("REPORT_SOURCE_MISMATCH",
                           f"report-{n}.json include closure has no file with the bundled {what} "
                           f"sha256 {h[:16]}")
        else:
            notes.append(f"report-{n}.json has no netlist_closure; included sources are bound "
                         "through the body netlist hash, whose source-sha256 lines name every "
                         "staged source's content")
        req = json.loads((work / r["request"]).read_text())
        want_m = sorted(m["name"] for m in req.get("measurements", []))
        if isinstance(rep.get("measurements"), list):
            got_m = sorted(m.get("name") for m in rep["measurements"])
            if got_m != want_m:
                refuse("REPORT_REQUEST_MISMATCH",
                       f"report-{n}.json measures {got_m}, the submitted request {want_m}")
        mc_req, mc_rep = req.get("monte_carlo"), env.get("monte_carlo")
        if mc_req and mc_rep:
            for k in ("n", "seed", "vary"):
                if k in mc_req and k in mc_rep and mc_req[k] != mc_rep[k]:
                    refuse("REPORT_REQUEST_MISMATCH",
                           f"report-{n}.json monte_carlo {k} = {mc_rep[k]!r}, request {mc_req[k]!r}")
    return notes


def verify_origin_commit(b: dict) -> list[str]:
    """A bundle that claims a CLEAN commit: its staged bytes must be that
    commit's files. -> reasons the claim cannot be checked (non-citable);
    refuses outright on a contradiction."""
    o = b["origin"]
    if o.get("dirty"):
        return []
    d, t = b["dut"], b["testbench"]
    unverified = []
    checks = {d["netlist"]: d["netlist_sha256"],
              f"{t['dir']}/{t['netlist']}": t["netlist_sha256"],
              f"{t['dir']}/{htb.MANIFEST_NAME}": t["manifest_sha256"]}
    # stage_sources copies EVERY file in the testbench dir (e.g. the
    # tb_vosprobe.spice offset-probe fragments), and the bundle hashes each.
    # They are not .included by the body netlist, but a clean-commit claim
    # covers the whole staged testbench, so check them against the commit too.
    stdir = t["staged_dir"].rstrip("/") + "/"
    for rel, h in sorted((b.get("staged") or {}).items()):
        if rel.startswith(stdir):
            checks.setdefault(f"{t['dir']}/{rel[len(stdir):]}", h)
    for path, want in checks.items():
        data = git_blob(o["commit"], path)
        got = None if data is None else mk.sha256_bytes(data)
        if got is None:
            unverified.append(f"{path} @ {o['commit'][:7]} not readable from this clone")
        elif got != want:
            refuse("SOURCE_COMMIT_MISMATCH",
                   f"bundle claims clean commit {o['commit'][:7]}, but {path} there is "
                   f"{got[:16]}, staged {want[:16]}")
    blob = git_blob(o["commit"], d["binding_config"])
    if blob is None:
        unverified.append(f"{d['binding_config']} @ {o['commit'][:7]} not readable from this clone")
    else:
        doc = json.loads(blob)
        entry = doc["duts"].get(d["key"]) if "duts" in doc else doc
        if mk.canonical_sha256(entry) != d["binding_entry_sha256"]:
            refuse("SOURCE_COMMIT_MISMATCH",
                   f"bundle claims clean commit {o['commit'][:7]}, but its {d['binding_config']} "
                   f"entry {d['key']!r} differs from the staged binding")
    return unverified


def checkout_drift(b: dict, repo: Path | None = None) -> list[str]:
    """What in TODAY's checkout differs from the bundle's sources (named)."""
    repo = Path(repo or REPO)
    d, t = b["dut"], b["testbench"]
    drift = []

    def sha(p: Path) -> str | None:
        return mk.sha256_file(p) if p.is_file() else None

    if sha(repo / t["dir"] / t["netlist"]) != t["netlist_sha256"]:
        drift.append(f"testbench fragment `{t['dir']}/{t['netlist']}`")
    if sha(repo / t["dir"] / htb.MANIFEST_NAME) != t["manifest_sha256"]:
        drift.append(f"testbench manifest `{t['dir']}/{htb.MANIFEST_NAME}`")
    cfg = Path(d["binding_config"])
    cfg = cfg if cfg.is_absolute() else repo / cfg
    try:
        doc = json.loads(cfg.read_text())
        if "duts" in doc:
            key = d["selector"] if d.get("selector") and d["selector"] in doc["duts"] else doc.get("active")
            entry = doc["duts"].get(key)
        else:
            key, entry = None, doc
    except (OSError, ValueError, AttributeError) as e:
        return drift + [f"DUT binding `{d['binding_config']}` unreadable ({e})"]
    if key != d.get("key"):
        drift.append(f"selected DUT (`{d['binding_config']}` now selects {key!r}, generated for {d.get('key')!r})")
    if entry is None:
        return drift + [f"DUT binding entry {key!r} missing"]
    if mk.canonical_sha256(entry) != d["binding_entry_sha256"]:
        drift.append(f"DUT binding entry {key!r} (params/netlist/provenance)")
    net = (repo / "sim" / str(entry.get("netlist", ""))).resolve()
    if sha(net) != d["netlist_sha256"]:
        drift.append(f"DUT netlist `{mk.repo_rel(net, repo) or net}`")
    return drift


def dispatch(work: Path, names: list[str]) -> None:
    """Submit every request concurrently (each is a batch job on the fleet)."""
    backend = os.environ.get("KLT_SIM_BACKEND", "")
    if backend not in ("batch", "remote"):
        raise SystemExit(
            f"KLT_SIM_BACKEND={backend!r}: refusing to run a multi-unit grid on a "
            "local backend (shared dispatch worker). Export KLT_SIM_BACKEND=batch."
        )
    procs = {}
    for n in names:
        # The child inherits its own copy of each fd, so the parent closes its handles at once.
        with (work / f"report-{n}.json").open("w") as out, (work / f"stderr-{n}.txt").open("w") as err:
            procs[n] = subprocess.Popen(
                ["klt", "sim", "-o", str(work / f"out-{n}"), str(work / f"request-{n}.json"), "--format", "json"],
                stdout=out,
                stderr=err,
            )
    for n, pr in procs.items():
        rc = pr.wait()
        if not (work / f"report-{n}.json").read_text().strip():
            raise SystemExit(f"klt sim request {n} failed (rc={rc}):\n{(work / f'stderr-{n}.txt').read_text()}")
        print(f"request {n}: klt sim rc={rc}", flush=True)


def fmt(v) -> str:
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def _collect_checked_legs(bench: str, names: dict, reports: dict, requests: dict) -> tuple[dict, list, int]:
    """#152's coverage-checked collection over every leg/supply request.

    -> (legs for `derive`, coverage issues, expected PVT points). The expected
    count is derived from the requests' own grids (first leg only: the other
    legs of a bench are the same PVT points)."""
    legs_c: dict = {leg: ({}, []) for leg in LEGS[bench]}
    coverage: list[str] = []
    expected = 0
    for n, (leg, v) in names.items():
        ok, _bad, issues = collect_checked(reports[n], requests[n], v, tag=n)
        coverage += issues
        expected += len(expected_units(requests[n], v)) if leg == LEGS[bench][0] else 0
        for cid, smp in ok.items():
            legs_c[leg][0].setdefault(cid, {}).update(smp)
        # failed units are already named FAILED_UNIT in `coverage`
    mcs = {json.dumps(r.get("monte_carlo"), sort_keys=True) for r in requests.values()}
    if len(mcs) > 1:
        coverage.append(f"MC_DECLARATION_MISMATCH: requests disagree on monte_carlo: {sorted(mcs)}")
    return legs_c, coverage, expected


def legacy_diagnostic(bench: str, work: Path) -> int:
    """A pre-#151 work dir: print, never publish. Exit 3 (not a record)."""
    tb = htb.load(HERE.parent / bench)  # today's manifest: interpretation aid only
    vdds = hc.supply_points(tb.nominal_supply_v, tb.supply_tolerance)
    names = {f"{leg}-v{v:.2f}": (leg, v) for leg in LEGS[bench] for v in vdds}
    reports = {n: json.loads((work / f"report-{n}.json").read_text()) for n in names}
    requests = {n: json.loads((work / f"request-{n}.json").read_text()) for n in names}
    legs_c, coverage, expected = _collect_checked_legs(bench, names, reports, requests)
    derived, problems = derive(bench, tb, legs_c)
    problems = coverage + problems
    key = SPEC[bench][1]
    print(f"NON-CITABLE DIAGNOSTIC (LEGACY_WORKDIR_UNBOUND): {work} has no {mk.BUNDLE_NAME}; the DUT, "
          "testbench and commit that produced these reports are UNKNOWN. Derived with TODAY's "
          f"sim/{bench}/testbench/tb.json. Not reference evidence; nothing written under sim/.")
    for p in problems[:60]:
        print(f"  problem: {p}")
    for cid, d in derived.items():
        print(f"  {cid}  {key} = {fmt(d[key])}")
    print(f"  ({len(derived)} of {expected} requested PVT points derived)")
    return 3


def mint_cm_index(a) -> int:
    """Issue #218: append-only record for the monotonic-index common-mode
    bench. UNSCORED: no ratified bound exists, so there is no target/stretch
    verdict and the consumer's rejection verdict stays Unknown. Full coverage
    is claimed only when every requested PVT point is complete (`complete`)
    AND the source identity is citable; draws are joined by identity inside
    one report (`collect_cm_index`), never pooled across requests."""
    bench = a.bench
    work = Path(a.from_report or a.work or f"/tmp/klt-{bench}").resolve()
    if not a.from_report:
        work.mkdir(parents=True, exist_ok=True)
        subprocess.check_call([sys.executable, str(HERE / "mk_klt_request.py"), bench, str(work),
                               "--mc-n", str(a.mc_n)] + (["--dut", a.dut] if a.dut else []))
    b = load_bundle(work, bench)
    check_dut_selection(b, a.dut)
    d, t, origin = b["dut"], b["testbench"], b["origin"]
    tb = htb.load(_staged_path(work, t["staged_dir"]))
    vdds = hc.supply_points(tb.nominal_supply_v, tb.supply_tolerance)
    names = {f"main-v{v:.2f}": ("main", v) for v in vdds}
    verify_staged(work, b, names)
    if not a.from_report:
        dispatch(work, list(names))
    reports = {n: json.loads((work / f"report-{n}.json").read_text()) for n in names}
    link_notes = verify_reports(work, b, names, reports)
    unverified = verify_origin_commit(b)
    drift = checkout_drift(b)
    requests = {n: json.loads((work / b["requests"][n]["request"]).read_text()) for n in names}
    samples: dict = {}
    issues: list[str] = []
    expected = 0
    for n, (_, v) in names.items():
        pair_cm_window_reports([reports[n]])  # one report per supply point, by construction
        got, iss = collect_cm_index(reports[n], requests[n], v)
        issues += [f"{n}: {i}" for i in iss]
        expected += len(expected_units(requests[n], v))
        for cid, smp in got.items():
            samples.setdefault(cid, {}).update(smp)
    mcs = {json.dumps(r.get("monte_carlo"), sort_keys=True) for r in requests.values()}
    if len(mcs) > 1:
        issues.append(f"MC_DECLARATION_MISMATCH: requests disagree on monte_carlo: {sorted(mcs)}")
    derived, dprob = derive_cm_window(samples)
    problems = issues + dprob
    complete = not problems and len(derived) == expected
    if not derived:
        print("\n".join(["no complete PVT point: nothing derived, no record written"] + problems[:60]), file=sys.stderr)
        raise SystemExit(f"EMPTY_RESULT: {bench} produced no complete PVT point; refusing to publish a record")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    sha = origin["commit"][:7]
    ingest_sha, tools_dirty = git_state()
    citable = not origin["dirty"] and not unverified and not tools_dirty
    bundle_sha = mk.sha256_file(work / mk.BUNDLE_NAME)
    rid = f"{ts}-{sha}"
    exp = SIM / bench
    for sub in ("records", "corners", "netlist-snapshots"):
        (exp / sub).mkdir(exist_ok=True)
    cdir = exp / "corners" / rid
    cdir.mkdir()
    for f in [mk.BUNDLE_NAME, "design.ngspice"] + [f"body-v{v:.2f}.spice" for v in vdds] \
            + [f"request-{n}.json" for n in names] + [f"report-{n}.json" for n in names]:
        shutil.copy2(work / f, cdir / f)
    shutil.copytree(work / mk.SOURCES_DIR, cdir / mk.SOURCES_DIR)
    snap = exp / "netlist-snapshots" / f"{rid}.spice"
    snap.write_text(_staged_path(work, d["staged_netlist"]).read_text() + "\n* ---- testbench fragment ----\n" + tb.netlist.read_text())
    noncite = []
    if origin["dirty"]:
        noncite.append(f"sources uncommitted at request generation: {', '.join(origin['dirty_paths'])}")
    noncite += [f"origin unverifiable: {u}" for u in unverified]
    if tools_dirty:
        noncite.append(f"derivation tooling (sim/tools, sim/harness) dirty at ingest commit {ingest_sha}")
    reference = complete and citable
    full = reference
    rem = [r["environment"].get("remote") for r in reports.values()]
    ng = sorted({str(r["environment"].get("engine_version")) for r in reports.values()})
    mc = next(iter(reports.values()))["environment"].get("monte_carlo", {})
    draws = {cid: d_["n_samples"] for cid, d_ in derived.items()}
    cols = list(next(iter(derived.values())).keys())
    if reference:
        claim = ("COMPLETE: every requested PVT point returned every draw with verified coordinates; "
                 "FULL COVERAGE of the documented 1.55/1.65/1.75 V window, as schematic preamp DC characterization")
    elif not complete:
        claim = "NON-COMPLETE DIAGNOSTIC (full coverage NOT claimed; see INCOMPLETE / FAILED UNITS)" + ("; also NOT CITABLE, see Commit" if not citable else "")
    else:
        claim = "NOT-CITABLE DIAGNOSTIC (full coverage NOT claimed; source identity not citable, see Commit)"
    lines = [
        f"# Record {rid}", "",
        f"- **Record ID**: {rid}",
        f"- **Experiment**: `sim/{bench}/` (klt sim requests, one per supply point: {', '.join(names)})",
        f"- **Topology label**: {a.label or d['dut_id']}",
        f"- **Claim**: {claim}. UNSCORED: no ratified common-mode rejection bound exists; the consumer's rejection verdict stays **Unknown**. Schematic preamp DC only -- not whole-comparator transient, not extracted-layout.",
        f"- **DUT**: `{d['dut_id']}` -- **{d['provenance']}** -- `{d['netlist']}` (sha256 `{d['netlist_sha256']}`), binding `{d['binding_config']}` entry `{d['key']}` (sha256 `{d['binding_entry_sha256'][:16]}`), params {json.dumps(d['params'], sort_keys=True)}",
        f"- **Testbench**: `{t['dir']}/{t['netlist']}` (sha256 `{t['netlist_sha256']}`), manifest sha256 `{t['manifest_sha256'][:16]}`",
        f"- **Commit**: `{sha}` (originating commit, from the source bundle `corners/{rid}/{mk.BUNDLE_NAME}` sha256 `{bundle_sha[:16]}`)"
        + (f" -- **NOT CITABLE until re-minted from a clean commit**: {'; '.join(noncite)}" if noncite else ""),
        f"- **Ingested**: at commit `{ingest_sha}` by `sim/tools/klt_record.py`; report-to-request linkage verified",
        f"- **Source drift since generation**: {', '.join(drift) if drift else 'none'}",
        f"- **Executor**: `klt sim` ({klt_version()}), backend `{os.environ.get('KLT_SIM_BACKEND', '?')}`; remote/batch descriptor(s): `{json.dumps(rem)}`; ngspice engine_version(s) reported: {ng}",
        f"- **Coverage**: {len(derived)} of {expected} PVT points complete; draws per point min {min(draws.values())} / max {max(draws.values())} (requested {mc.get('n')}).",
        f"- **Monte Carlo**: seed {mc.get('seed')}, n = {mc.get('n')} draws requested per PVT point, vary = {mc.get('vary')}. One draw is one `corners[]` entry of one report (one analysis `dc {mk.CM_INDEX_DC_ARGS}` of one instance), joined by `monte_carlo.sample_index`; both coordinate read-backs checked within {CM_COORD_TOL_V:g} V. Seed equality across requests is not used as pairing.",
        "- **Definitions**: per draw, `A_p = (dv_p(2 mV) - dv_p(0))/2 mV`, `Vos_p = -dv_p(0)/A_p`; `dvos_dn/up` = endpoint minus midpoint offset change within the same draw (reported in uV). No rejection ratio is defined. Sigmas are population.",
    ]
    lines += [f"  - linkage note: {n}" for n in link_notes]
    if problems:
        lines += ["- **INCOMPLETE / FAILED UNITS**:"] + [f"  - {p}" for p in problems[:60]]
    lines += ["- **Result**:", "", "  | corner-id | " + " | ".join(f"`{n}`" for n in cols) + " |", "  |---|" + "---|" * len(cols)]
    for cid, dd in derived.items():
        lines.append(f"  | `{cid}` | " + " | ".join(fmt(dd[n]) for n in cols) + " |")
    lines += [
        "",
        f"- **Reproduce**: at commit `{sha}`: `KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py {bench}`",
        "",
    ]
    (exp / "records" / f"{rid}.md").write_text("\n".join(lines))
    (exp / "records" / f"{rid}.json").write_text(json.dumps({
        "record_id": rid, "bench": bench, "commit": sha, "dirty": bool(origin["dirty"]),
        "citable": citable, "not_citable_reasons": noncite,
        "dut": {
            "dut_id": d["dut_id"], "dut_provenance": d["provenance"], "dut_netlist": d["netlist"],
            "dut_netlist_sha256": d["netlist_sha256"], "dut_params": d["params"],
            "dut_selector": d.get("selector"), "dut_binding_config": d["binding_config"],
            "dut_binding_entry_sha256": d["binding_entry_sha256"],
        },
        "testbench": {"dir": t["dir"], "netlist": t["netlist"], "netlist_sha256": t["netlist_sha256"],
                      "manifest_sha256": t["manifest_sha256"]},
        "source_bundle": {"file": f"corners/{rid}/{mk.BUNDLE_NAME}", "sha256": bundle_sha,
                          "schema": b["schema"], "version": b["version"],
                          "origin_commit": origin["commit"], "origin_dirty_paths": origin["dirty_paths"]},
        "executor": {"remote": rem, "engine_versions": ng, "backend": os.environ.get("KLT_SIM_BACKEND", "?")},
        "monte_carlo": {"n": mc.get("n"), "seed": mc.get("seed"), "vary": mc.get("vary"), "draws_per_point": draws},
        "ingest": {"commit": ingest_sha, "tools_dirty": tools_dirty, "source_drift": drift,
                   "linkage_notes": link_notes},
        "scored": False, "verdict": "Unknown",
        "complete": complete, "outcome": "complete" if complete else "incomplete", "expected_points": expected,
        "full_coverage": full, "reference": reference, "points": len(derived), "problems": problems,
        "derived": derived,
    }, indent=1, allow_nan=False) + "\n")
    print(f"record {rid}: {len(derived)} of {expected} points, complete={complete}, citable={citable}"
          + ("" if citable else " -- NOT CITABLE: " + "; ".join(noncite)))
    if not complete:
        print(f"INCOMPLETE: {len(problems)} problem(s); non-complete diagnostic, full coverage not claimed", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", choices=sorted(LEGS) + [mk.CM_WINDOW_BENCH, mk.CM_INDEX_BENCH])
    ap.add_argument("--work", default=None, help="scratch dir for requests/reports")
    ap.add_argument("--from-report", default=None, help="ingest a finished work dir, skip dispatch")
    ap.add_argument("--mc-n", type=int, default=200)
    ap.add_argument("--dut", default=None, help="DUT binding id/path (e.g. a control netlist), as run_corners.py --dut")
    ap.add_argument("--label", default="", help="free-text topology label stamped in the record")
    ap.add_argument("--legacy-diagnostic", action="store_true",
                    help="for a --from-report dir with no source bundle: print a NON-CITABLE table, write nothing")
    a = ap.parse_args()

    if a.bench == mk.CM_INDEX_BENCH:
        return mint_cm_index(a)
    if a.bench == mk.CM_WINDOW_BENCH:
        # Issue #182: refused before any dispatch or ingest, so no evidence
        # record can be minted for it. Even with a capable runner there is no
        # record path yet: full 45-point consumer-window coverage is pending.
        refuse("UNSUPPORTED_EXECUTOR_CAPABILITY",
               mk.cm_window_capability_gap(mk.FLEET_RUNNER_KLT_OBSERVED)
               or f"{a.bench} has no record-minting path yet (full 45-point coverage pending, issue #182)")
    work = Path(a.from_report or a.work or f"/tmp/klt-{a.bench}").resolve()
    if not a.from_report:
        work.mkdir(parents=True, exist_ok=True)
        subprocess.check_call([sys.executable, str(HERE / "mk_klt_request.py"), a.bench, str(work), "--mc-n", str(a.mc_n)] + (["--dut", a.dut] if a.dut else []))
    elif a.legacy_diagnostic and not (work / mk.BUNDLE_NAME).is_file():
        return legacy_diagnostic(a.bench, work)

    # Every identity below comes from the source bundle written at request
    # time -- not from today's checkout (issue #151).
    b = load_bundle(work, a.bench)
    check_dut_selection(b, a.dut)
    d, t, origin = b["dut"], b["testbench"], b["origin"]
    tb = htb.load(_staged_path(work, t["staged_dir"]))  # originating manifest + `measure`
    vdds = hc.supply_points(tb.nominal_supply_v, tb.supply_tolerance)
    names = {f"{leg}-v{v:.2f}": (leg, v) for leg in LEGS[a.bench] for v in vdds}
    verify_staged(work, b, names)
    if not a.from_report:
        dispatch(work, list(names))

    reports = {n: json.loads((work / f"report-{n}.json").read_text()) for n in names}
    link_notes = verify_reports(work, b, names, reports)
    unverified = verify_origin_commit(b)
    drift = checkout_drift(b)
    # The requests are the bundled (hash-verified) ones; the expected grid
    # comes from them, never from a hard-coded count (#152).
    requests = {n: json.loads((work / b["requests"][n]["request"]).read_text()) for n in names}
    legs_c, coverage, expected = _collect_checked_legs(a.bench, names, reports, requests)
    derived, problems = derive(a.bench, tb, legs_c)
    problems = coverage + problems
    complete = not coverage and not problems and len(derived) == expected
    if not derived:
        print("\n".join(["no scorable corner: nothing derived, no record written"] + problems[:60]), file=sys.stderr)
        raise SystemExit(f"EMPTY_RESULT: {a.bench} produced no complete PVT point; refusing to publish a record")

    label, key, tgt, stretch, unit = SPEC[a.bench]
    vals = {cid: dd[key] for cid, dd in derived.items()}
    worst_cid = max(vals, key=vals.get)
    best_cid = min(vals, key=vals.get)
    n_t = sum(v <= tgt for v in vals.values())
    n_s = sum(v <= stretch for v in vals.values())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    sha = origin["commit"][:7]
    ingest_sha, tools_dirty = git_state()
    citable = not origin["dirty"] and not unverified and not tools_dirty
    bundle_sha = mk.sha256_file(work / mk.BUNDLE_NAME)
    rid = f"{ts}-{sha}"
    exp = SIM / a.bench
    for sub in ("records", "corners", "netlist-snapshots"):
        (exp / sub).mkdir(exist_ok=True)
    cdir = exp / "corners" / rid
    cdir.mkdir()  # exclusive: raises if the id exists
    for f in [mk.BUNDLE_NAME, "design.ngspice"] + [f"body-v{v:.2f}.spice" for v in vdds] + [f"request-{n}.json" for n in names] + [f"report-{n}.json" for n in names]:
        shutil.copy2(work / f, cdir / f)
    shutil.copytree(work / mk.SOURCES_DIR, cdir / mk.SOURCES_DIR)
    snap = exp / "netlist-snapshots" / f"{rid}.spice"
    snap.write_text(_staged_path(work, d["staged_netlist"]).read_text() + "\n* ---- testbench fragment ----\n" + tb.netlist.read_text())

    rem = [r["environment"].get("remote") for r in reports.values()]
    ng = [r["environment"].get("engine_version") for r in reports.values()]
    noncite = []
    if origin["dirty"]:
        noncite.append(f"sources uncommitted at request generation: {', '.join(origin['dirty_paths'])}")
    noncite += [f"origin unverifiable: {u}" for u in unverified]
    if tools_dirty:
        noncite.append(f"derivation tooling (sim/tools, sim/harness) dirty at ingest commit {ingest_sha}")
    # Citable REFERENCE evidence needs BOTH gates: exact PVT/MC coverage
    # (#152, `complete`) and verified source identity (#151, `citable`).
    reference = complete and citable
    if reference:
        claim = "REFERENCE"
    elif not complete:
        claim = "NON-COMPLETE DIAGNOSTIC (NOT reference evidence; coverage incomplete, see INCOMPLETE / FAILED UNITS" + ("; also NOT CITABLE, see Commit" if not citable else "") + ")"
    else:
        claim = "NOT-CITABLE DIAGNOSTIC (NOT reference evidence; source identity not citable, see Commit)"
    lines = [
        f"# Record {rid}",
        "",
        f"- **Record ID**: {rid}",
        f"- **Experiment**: `sim/{a.bench}/` (klt sim requests, one per supply point: {', '.join(names)})",
        f"- **Topology label**: {a.label or d['dut_id']}",
        f"- **Claim**: {claim} against the ratified {label} row (README.md#target-specification-ratified-via-dr-0002; target <= {tgt:g} {unit}, stretch <= {stretch:g} {unit}). Scored, not relaxed.",
        f"- **DUT**: `{d['dut_id']}` -- **{d['provenance']}** -- `{d['netlist']}` (sha256 `{d['netlist_sha256'][:16]}`), binding `{d['binding_config']}` entry `{d['key']}` (sha256 `{d['binding_entry_sha256'][:16]}`), params {json.dumps(d['params'], sort_keys=True)}",
        f"- **Testbench**: `{t['dir']}/{t['netlist']}` (sha256 `{t['netlist_sha256'][:16]}`), manifest sha256 `{t['manifest_sha256'][:16]}`",
        f"- **Commit**: `{sha}` (originating commit, from the source bundle `corners/{rid}/{mk.BUNDLE_NAME}` sha256 `{bundle_sha[:16]}`; sources staged at request generation and verified at ingest)"
        + (f" -- **NOT CITABLE until re-minted from a clean commit**: {'; '.join(noncite)}" if noncite else ""),
        f"- **Ingested**: at commit `{ingest_sha}` by `sim/tools/klt_record.py`; report-to-request linkage verified (netlist sha256" + (", include closure" if not link_notes else "") + ", measurements)",
        f"- **Source drift since generation** (today's checkout vs this record's sources; the record cites the generation-time sources): {', '.join(drift) if drift else 'none'}",
        f"- **Executor**: `klt sim` ({klt_version()}), backend `{os.environ.get('KLT_SIM_BACKEND', '?')}`; remote/batch descriptor(s): `{json.dumps(rem)}`; ngspice engine_version(s) reported: {ng}",
        f"- **Corner matrix**: {len(derived)} of {expected} PVT points with every leg passing (process {'/'.join(dict.fromkeys(p['name'] for r in requests.values() for p in r['corners']['process']))} x {'/'.join(f'{t:g}' for t in dict.fromkeys(t for r in requests.values() for t in r['corners']['temperature_c']))} C x {'/'.join(f'{v:.2f}' for v in vdds)} V)",
    ]
    lines += [f"  - linkage note: {n}" for n in link_notes]
    if a.bench == "comparator-offset-tran":
        mc = next(iter(reports.values()))["environment"].get("monte_carlo", {})
        lines += [
            f"- **Monte Carlo**: seed {mc.get('seed')}, n = {mc.get('n')} draws requested per PVT point{'' if complete else ' (NOT achieved: see INCOMPLETE / FAILED UNITS; achieved draws per point in the n_samples column)'}, vary = {mc.get('vary')} (`.param sw_stat_mismatch=1` set by the fragment); the seed is the one `sim/comparator-offset-mc/` uses, common to every PVT point. One clocked staircase transient per draw; `sigma` = population standard deviation over the draws of the per-draw trip point, with the staircase's uniform quantisation variance (step^2/12) subtracted in quadrature (`sig_vos_tran_raw_mv` is the uncorrected value); stats are computed by `sim/tools/klt_record.py` from the raw `.meas` values in `corners/{rid}/report-main-v*.json`.",
            "- **Derived, NOT simulated**: `sig_rload_mv`, `sig_rload_cons_mv`, `sig_vos_total_mv`, `vos_3sig_total_mv`, `vos_3sig_total_cons_mv`. The PDK models no `ppolyf_u_1k` mismatch (`mis_r` absent/zero), so the load-pair term is a hand budget: sigma(dR/R) = A_R/sqrt(W*L) (pair difference; A_R from the foundry's commented-out `ppolyf_u` mismatch coefficient in the PDK model file, see the bench README), input-referred as (I_D*R / A_v) * sigma(dR/R), where I_D*R / A_v is the measured per-corner load drop over the measured same-draw gain (`vdrop_over_av_mv`), added in quadrature to the simulated sigma. The `_cons` quantities use a 3x larger A_R. The scored column is the conservative total.",
        ]
    if a.bench == "comparator-offset-mc":
        mc = next(iter(reports.values()))["environment"].get("monte_carlo", {})
        lines += [
            f"- **Monte Carlo**: seed {mc.get('seed')}, n = {mc.get('n')} draws requested per PVT point{'' if complete else ' (NOT achieved: see INCOMPLETE / FAILED UNITS; achieved draws per point in the n_samples column)'}, vary = {mc.get('vary')} (`.param sw_stat_mismatch=1` set by the fragment). sigma = population standard deviation of the per-draw input-referred offset `voa` (= -dv/gain, same draw), 3-sigma = 3 x sigma; stats are computed by `sim/tools/klt_record.py` from the raw per-draw values in `corners/{rid}/report-main-v*.json`.",
        ]
    if problems:
        lines += ["- **INCOMPLETE / FAILED UNITS**:"] + [f"  - {p}" for p in problems[:60]]
    cols = list(next(iter(derived.values())).keys())
    lines += ["- **Result**:", "", "  | corner-id | " + " | ".join(f"`{n}`" for n in cols) + " | vs target |", "  |---|" + "---|" * (len(cols) + 1)]
    for cid, dd in derived.items():
        lines.append(f"  | `{cid}` | " + " | ".join(fmt(dd[n]) for n in cols) + f" | {'PASS' if dd[key] <= tgt else 'FAIL'} |")
    lines += [
        "",
        f"- **Score vs ratified bounds** (`{key}`): within target {n_t}/{len(vals)}, within stretch {n_s}/{len(vals)}; min {vals[best_cid]:.6g} @ `{best_cid}`, max {vals[worst_cid]:.6g} @ `{worst_cid}` ({unit}).",
    ]
    if a.bench == "comparator-regeneration":
        pw = {cid: power_uw(a.bench, cid, dd) for cid, dd in derived.items()}
        lines.append(f"- **Static power** (`i_static_ua` x vdd): min {min(pw.values()):.4g} uW, max {max(pw.values()):.4g} uW; within the {POWER_TARGET_UW:g} uW target at {sum(p <= POWER_TARGET_UW for p in pw.values())}/{len(pw)} corners.")
        bad_end = [cid for cid, dd in derived.items() if min(dd["dout_od50_end"], dd["dout_od1_end"], dd["dout_od01_end"]) < 0.9]
        lines.append(f"- **Decision correctness** (`dout_*_end` >= 0.9 at all three overdrives): failing corners: {bad_end or 'none'}.")
    if a.bench == "comparator-kickback":
        bad_end = [cid for cid, dd in derived.items() if min(dd["dout_1k_end"], dd["dout_float_small_end"], dd["dout_float_big_end"]) < 0.9]
        lines.append(f"- **Decision correctness while kicked** (`dout_*_end` >= 0.9): failing corners: {bad_end or 'none'}.")
        lines.append(f"- **Input-node coverage** (issue #160): {node_coverage_line(derived)}")
    sel = d.get("selector")
    lines += [
        "- **Not computed by this executor** (single-analysis `klt sim` requests): "
        + {
            "comparator-preamp-noise": "`vn_in_hf_uv`, `onoise_hf_uv`, `flicker_frac_pct`, `white_nv_rthz`, `enbw_mhz`, `vbias_anchor_mv` (they need a second `.noise` plot / the `.op` in the same run). `vn_in_uv` is the row-facing quantity.",
            "comparator-offset-mc": "`sig_dvos_dn_uv`/`sig_dvos_up_uv` (the +-50 mV CM-step points), `mean_dvos_*`, `mean_vos_sem`, `vbias_anchor_mv` and the in-run `sig_rpair_uv` null control: the 0.5.0 fleet runner cannot express the nested `vcmd` sweep as `.meas` cards, so only the vcmd = 0 offset point (`voa`) is measured.",
            "comparator-offset-tran": "the +-50 mV common-mode dependence (`sig_dvos_*`), the in-run `sig_rpair_uv` null control (it stays in the DC bench's record) and per-draw `vbias_anchor_mv`; the fleet runner's `.meas` cards give the trip time and the end-of-reset preamp samples, and everything else is derived from them.",
            "comparator-kickback": "nothing (all `.meas` ingredients are requested; `.meas` precision is the executor's `measureprec=12`).",
            "comparator-regeneration": "nothing.",
        }[a.bench],
        f"- **Reproduce**: at commit `{sha}`: `KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py {a.bench}" + (f" --dut {sel}" if sel else "") + "`",
        "",
    ]
    (exp / "records" / f"{rid}.md").write_text("\n".join(lines))
    (exp / "records" / f"{rid}.json").write_text(json.dumps({
        "record_id": rid, "bench": a.bench, "commit": sha, "dirty": bool(origin["dirty"]),
        "citable": citable, "not_citable_reasons": noncite,
        "dut": {
            "dut_id": d["dut_id"], "dut_provenance": d["provenance"], "dut_netlist": d["netlist"],
            "dut_netlist_sha256": d["netlist_sha256"], "dut_params": d["params"],
            "dut_selector": d.get("selector"), "dut_binding_config": d["binding_config"],
            "dut_binding_entry_sha256": d["binding_entry_sha256"],
        },
        "testbench": {"dir": t["dir"], "netlist": t["netlist"], "netlist_sha256": t["netlist_sha256"],
                      "manifest_sha256": t["manifest_sha256"]},
        "source_bundle": {"file": f"corners/{rid}/{mk.BUNDLE_NAME}", "sha256": bundle_sha,
                          "schema": b["schema"], "version": b["version"],
                          "origin_commit": origin["commit"], "origin_dirty_paths": origin["dirty_paths"]},
        "ingest": {"commit": ingest_sha, "tools_dirty": tools_dirty, "source_drift": drift,
                   "linkage_notes": link_notes},
        "spec_row": {"label": label, "measure": key, "target_max": tgt, "stretch_max": stretch, "unit": unit},
        "complete": complete, "outcome": "complete" if complete else "incomplete", "expected_points": expected,
        "reference": reference,
        "within_target": n_t, "within_stretch": n_s, "points": len(vals), "problems": problems,
        "derived": derived,
        **({"input_node_coverage": node_coverage(derived)} if a.bench == "comparator-kickback" else {}),
    }, indent=1, allow_nan=False) + "\n")  # strict JSON: no NaN/Infinity tokens
    print(f"record {rid}: {len(derived)} points, {key} within target {n_t}/{len(vals)}, stretch {n_s}/{len(vals)}, worst {vals[worst_cid]:.6g} @ {worst_cid}"
          + ("" if citable else " -- NOT CITABLE: " + "; ".join(noncite)))
    if drift:
        print(f"source drift since generation (record cites the generation-time sources): {', '.join(drift)}")
    if not complete:
        print(f"INCOMPLETE: {len(problems)} coverage/validation problem(s); record is a non-complete diagnostic, not reference evidence", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
