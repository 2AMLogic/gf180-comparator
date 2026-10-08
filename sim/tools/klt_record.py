#!/usr/bin/env python3
"""Dispatch a bench's `klt sim` legs and mint an append-only evidence record.

    python3 sim/tools/klt_record.py BENCH [--work DIR] [--from-report DIR]

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

LEGS = {
    "comparator-kickback": ["main"],
    "comparator-regeneration": ["main"],
    "comparator-preamp-noise": ["noise", "ac"],
    "comparator-offset-mc": ["main"],
}

#: Ratified TARGET / STRETCH bounds (README.md table, DR-0002). Read-only.
#: key -> (label, derived measure name, target max, stretch max, unit)
SPEC = {
    "comparator-kickback": ("Kickback", "kick_1k_peak_mv", 5.0, 2.0, "mV"),
    "comparator-regeneration": ("Decision time @ 50 mV", "td_od50_ns", 1.5, 0.8, "ns"),
    "comparator-preamp-noise": ("Input-referred noise", "vn_in_uv", 1000.0, 600.0, "uV rms"),
    "comparator-offset-mc": ("Offset 3-sigma", "vos_3sig_mv", 15.0, 8.0, "mV"),
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


def derive(bench: str, tb, legs: dict[str, dict]) -> tuple[dict, list]:
    """-> ({corner_id: {derived name: value}}, problems)."""
    problems: list[str] = []
    for leg, (_, bad) in legs.items():
        problems += [f"leg {leg}: {cid} -> {st}" for cid, st in bad]
    ids = sorted(set.intersection(*(set(v[0]) for v in legs.values())), key=lambda s: s)
    res: dict = {}
    if bench in ("comparator-kickback", "comparator-regeneration"):
        raw = legs["main"][0]
        for cid in ids:
            env = dict(MATH, **raw[cid][""])
            res[cid] = {}
            for name, expr in tb.measure.items():
                res[cid][name] = eval(expr.replace("^", "**"), {"__builtins__": {}}, env)
        return res, problems
    if bench == "comparator-preamp-noise":
        for cid in ids:
            n, a = legs["noise"][0][cid][""], legs["ac"][0][cid][""]
            res[cid] = {
                "av_dc": a["av_dc"],
                "onoise_uv": n["onoise_total"] * 1e6,
                "vn_in_uv": n["onoise_total"] / a["av_dc"] * 1e6,
                "inoise_band_uv": n["inoise_total"] * 1e6,
            }
        return res, problems
    # offset-mc: population statistics over the draws. Per draw, gain from the
    # 0 mV and +2 mV points of one dc sweep (same draw), voa = -dv0/gain --
    # the bench's `voa` at vcmd = 0.
    pstd = statistics.pstdev
    for cid in ids:
        smp = list(legs["main"][0][cid].values())
        ava = [(s["dv1"] - s["dv0"]) / 2e-3 for s in smp]
        voa = [-s["dv0"] / g for s, g in zip(smp, ava)]
        sig = pstd(voa)
        res[cid] = {
            "n_samples": len(smp),
            "sig_vos_mv": sig * 1e3,
            "vos_3sig_mv": 3 * sig * 1e3,
            "mean_vos_uv": statistics.fmean(voa) * 1e6,
            "av_mean": statistics.fmean(ava),
            "av_sigma_pct": pstd(ava) / statistics.fmean(ava) * 100,
        }
    return res, problems


def power_uw(bench: str, cid: str, d: dict) -> float | None:
    if bench != "comparator-regeneration":
        return None
    return d["i_static_ua"] * float(cid.rsplit("_", 1)[1].rstrip("v"))


def git_state() -> tuple[str, bool]:
    sha = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "--short=7", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain", "--", "design", "sim/tools", "sim/harness"], text=True).strip())
    return sha, dirty


def dispatch(work: Path, names: list[str]) -> None:
    """Submit every request concurrently (each is a batch job on the fleet)."""
    backend = os.environ.get("KLT_SIM_BACKEND", "")
    if backend not in ("batch", "remote"):
        raise SystemExit(
            f"KLT_SIM_BACKEND={backend!r}: refusing to run a multi-unit grid on a "
            "local backend (shared dispatch worker). Export KLT_SIM_BACKEND=batch."
        )
    procs = {
        n: subprocess.Popen(
            ["klt", "sim", "-o", str(work / f"out-{n}"), str(work / f"request-{n}.json"), "--format", "json"],
            stdout=(work / f"report-{n}.json").open("w"),
            stderr=(work / f"stderr-{n}.txt").open("w"),
        )
        for n in names
    }
    for n, pr in procs.items():
        rc = pr.wait()
        if not (work / f"report-{n}.json").read_text().strip():
            raise SystemExit(f"klt sim request {n} failed (rc={rc}):\n{(work / f'stderr-{n}.txt').read_text()}")
        print(f"request {n}: klt sim rc={rc}", flush=True)


def fmt(v) -> str:
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", choices=sorted(LEGS))
    ap.add_argument("--work", default=None, help="scratch dir for requests/reports")
    ap.add_argument("--from-report", default=None, help="ingest a finished work dir, skip dispatch")
    ap.add_argument("--mc-n", type=int, default=200)
    ap.add_argument("--dut", default=None, help="DUT binding id/path (e.g. a control netlist), as run_corners.py --dut")
    ap.add_argument("--label", default="", help="free-text topology label stamped in the record")
    a = ap.parse_args()

    tb = htb.load(SIM / a.bench)
    dut = hdut.load(select=a.dut)
    vdds = hc.supply_points(tb.nominal_supply_v, tb.supply_tolerance)
    names = {f"{leg}-v{v:.2f}": (leg, v) for leg in LEGS[a.bench] for v in vdds}
    work = Path(a.from_report or a.work or f"/tmp/klt-{a.bench}").resolve()
    if not a.from_report:
        work.mkdir(parents=True, exist_ok=True)
        subprocess.check_call([sys.executable, str(HERE / "mk_klt_request.py"), a.bench, str(work), "--mc-n", str(a.mc_n)] + (["--dut", a.dut] if a.dut else []))
        dispatch(work, list(names))

    reports = {n: json.loads((work / f"report-{n}.json").read_text()) for n in names}
    legs_c: dict = {leg: ({}, []) for leg in LEGS[a.bench]}
    for n, (leg, v) in names.items():
        ok, bad = collect(reports[n], v)
        legs_c[leg][0].update(ok)
        legs_c[leg][1].extend(bad)
    derived, problems = derive(a.bench, tb, legs_c)

    label, key, tgt, stretch, unit = SPEC[a.bench]
    expected = 45
    vals = {cid: d[key] for cid, d in derived.items()}
    worst_cid = max(vals, key=vals.get)
    best_cid = min(vals, key=vals.get)
    n_t = sum(v <= tgt for v in vals.values())
    n_s = sum(v <= stretch for v in vals.values())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    sha, dirty = git_state()
    rid = f"{ts}-{sha}"
    exp = SIM / a.bench
    for sub in ("records", "corners", "netlist-snapshots"):
        (exp / sub).mkdir(exist_ok=True)
    cdir = exp / "corners" / rid
    cdir.mkdir()  # exclusive: raises if the id exists
    for f in ["design.ngspice"] + [f"body-v{v:.2f}.spice" for v in vdds] + [f"request-{n}.json" for n in names] + [f"report-{n}.json" for n in names]:
        shutil.copy2(work / f, cdir / f)
    snap = exp / "netlist-snapshots" / f"{rid}.spice"
    snap.write_text(dut.netlist.read_text() + "\n* ---- testbench fragment ----\n" + tb.netlist.read_text())

    rem = [r["environment"].get("remote") for r in reports.values()]
    ng = [r["environment"].get("engine_version") for r in reports.values()]
    lines = [
        f"# Record {rid}",
        "",
        f"- **Record ID**: {rid}",
        f"- **Experiment**: `sim/{a.bench}/` (klt sim requests, one per supply point: {', '.join(names)})",
        f"- **Topology label**: {a.label or dut.dut_id}",
        f"- **Claim**: REFERENCE against the ratified {label} row (README.md#target-specification-ratified-via-dr-0002; target <= {tgt:g} {unit}, stretch <= {stretch:g} {unit}). Scored, not relaxed.",
        f"- **DUT**: `{dut.dut_id}` -- **{dut.provenance}** -- `{dut.netlist.relative_to(REPO)}` (sha256 `{dut.netlist_sha256[:16]}`)",
        f"- **Testbench**: `sim/{a.bench}/testbench/{tb.netlist.name}` (sha256 `{tb.netlist_sha256[:16]}`), manifest sha256 `{tb.manifest_sha256[:16]}`",
        f"- **Commit**: `{sha}`" + (" -- **WORKING TREE DIRTY (design/sim sources uncommitted): not citable until re-minted from a clean commit**" if dirty else ""),
        f"- **Executor**: `klt sim` ({subprocess.check_output(['klt', '--version'], text=True).strip()}), backend `{os.environ.get('KLT_SIM_BACKEND', '?')}`; remote/batch descriptor(s): `{json.dumps(rem)}`; ngspice engine_version(s) reported: {ng}",
        f"- **Corner matrix**: {len(derived)} of {expected} PVT points with every leg passing (process tt/ff/ss/fs/sf x -40/27/125 C x 2.97/3.30/3.63 V)",
    ]
    if a.bench == "comparator-offset-mc":
        mc = next(iter(reports.values()))["environment"].get("monte_carlo", {})
        lines += [
            f"- **Monte Carlo**: seed {mc.get('seed')}, n = {mc.get('n')} draws per PVT point, vary = {mc.get('vary')} (`.param sw_stat_mismatch=1` set by the fragment). sigma = population standard deviation of the per-draw input-referred offset `voa` (= -dv/gain, same draw), 3-sigma = 3 x sigma; stats are computed by `sim/tools/klt_record.py` from the raw per-draw values in `corners/{rid}/report-main-v*.json`.",
        ]
    if problems:
        lines += ["- **INCOMPLETE / FAILED UNITS**:"] + [f"  - {p}" for p in problems[:60]]
    names = list(next(iter(derived.values())).keys())
    lines += ["- **Result**:", "", "  | corner-id | " + " | ".join(f"`{n}`" for n in names) + " | vs target |", "  |---|" + "---|" * (len(names) + 1)]
    for cid, d in derived.items():
        lines.append(f"  | `{cid}` | " + " | ".join(fmt(d[n]) for n in names) + f" | {'PASS' if d[key] <= tgt else 'FAIL'} |")
    lines += [
        "",
        f"- **Score vs ratified bounds** (`{key}`): within target {n_t}/{len(vals)}, within stretch {n_s}/{len(vals)}; min {vals[best_cid]:.6g} @ `{best_cid}`, max {vals[worst_cid]:.6g} @ `{worst_cid}` ({unit}).",
    ]
    if a.bench == "comparator-regeneration":
        pw = {cid: power_uw(a.bench, cid, d) for cid, d in derived.items()}
        lines.append(f"- **Static power** (`i_static_ua` x vdd): min {min(pw.values()):.4g} uW, max {max(pw.values()):.4g} uW; within the {POWER_TARGET_UW:g} uW target at {sum(p <= POWER_TARGET_UW for p in pw.values())}/{len(pw)} corners.")
        bad_end = [cid for cid, d in derived.items() if min(d["dout_od50_end"], d["dout_od1_end"], d["dout_od01_end"]) < 0.9]
        lines.append(f"- **Decision correctness** (`dout_*_end` >= 0.9 at all three overdrives): failing corners: {bad_end or 'none'}.")
    if a.bench == "comparator-kickback":
        bad_end = [cid for cid, d in derived.items() if min(d["dout_1k_end"], d["dout_float_small_end"], d["dout_float_big_end"]) < 0.9]
        lines.append(f"- **Decision correctness while kicked** (`dout_*_end` >= 0.9): failing corners: {bad_end or 'none'}.")
    lines += [
        "- **Not computed by this executor** (single-analysis `klt sim` requests): "
        + {
            "comparator-preamp-noise": "`vn_in_hf_uv`, `onoise_hf_uv`, `flicker_frac_pct`, `white_nv_rthz`, `enbw_mhz`, `vbias_anchor_mv` (they need a second `.noise` plot / the `.op` in the same run). `vn_in_uv` is the row-facing quantity.",
            "comparator-offset-mc": "`sig_dvos_dn_uv`/`sig_dvos_up_uv` (the +-50 mV CM-step points), `mean_dvos_*`, `mean_vos_sem`, `vbias_anchor_mv` and the in-run `sig_rpair_uv` null control: the 0.5.0 fleet runner cannot express the nested `vcmd` sweep as `.meas` cards, so only the vcmd = 0 offset point (`voa`) is measured.",
            "comparator-kickback": "nothing (all `.meas` ingredients are requested; `.meas` precision is the executor's `measureprec=12`).",
            "comparator-regeneration": "nothing.",
        }[a.bench],
        f"- **Reproduce**: `KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py {a.bench}`",
        "",
    ]
    (exp / "records" / f"{rid}.md").write_text("\n".join(lines))
    (exp / "records" / f"{rid}.json").write_text(json.dumps({
        "record_id": rid, "bench": a.bench, "commit": sha, "dirty": dirty, "dut": dut.provenance_record(),
        "spec_row": {"label": label, "measure": key, "target_max": tgt, "stretch_max": stretch, "unit": unit},
        "within_target": n_t, "within_stretch": n_s, "points": len(vals), "problems": problems,
        "derived": derived,
    }, indent=1) + "\n")
    print(f"record {rid}: {len(derived)} points, {key} within target {n_t}/{len(vals)}, stretch {n_s}/{len(vals)}, worst {vals[worst_cid]:.6g} @ {worst_cid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
