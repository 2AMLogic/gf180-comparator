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


def corner_id(raw: str) -> tuple[str, str]:
    """'tt/3.300V/27C[/mcN]' -> ('tt_27c_3.30v', 'mcN' or '')."""
    parts = raw.split("/")
    proc, vdd, temp = parts[0], float(parts[1].rstrip("V")), float(parts[2].rstrip("C"))
    return f"{proc}_{temp:g}c_{vdd:.2f}v", (parts[3] if len(parts) > 3 else "")


def collect(report: dict) -> tuple[dict, list]:
    """report -> ({corner_id: {sample: {name: value}}}, bad statuses)."""
    out: dict = {}
    bad = []
    for c in report["corners"]:
        cid, sample = corner_id(c["corner_id"])
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
    # offset-mc: population statistics over the draws, exactly the bench's
    # sqrt(sum_sq/n - (sum/n)^2) form.
    pstd = lambda xs: statistics.pstdev(xs)  # noqa: E731
    for cid in ids:
        smp = list(legs["main"][0][cid].values())
        col = lambda k: [s[k] for s in smp]  # noqa: E731
        sig = pstd(col("voa"))
        res[cid] = {
            "n_samples": len(smp),
            "sig_vos_mv": sig * 1e3,
            "vos_3sig_mv": 3 * sig * 1e3,
            "mean_vos_uv": statistics.fmean(col("voa")) * 1e6,
            "sig_dvos_dn_uv": pstd(col("ddc")) * 1e6,
            "sig_dvos_up_uv": pstd(col("dde")) * 1e6,
            "av_mean": statistics.fmean(col("ava")),
            "av_sigma_pct": pstd(col("ava")) / statistics.fmean(col("ava")) * 100,
            "sig_rpair_uv": pstd(col("drr")) * 1e6,
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


def dispatch(work: Path, leg: str) -> None:
    backend = os.environ.get("KLT_SIM_BACKEND", "")
    if backend not in ("batch", "remote"):
        raise SystemExit(
            f"KLT_SIM_BACKEND={backend!r}: refusing to run a multi-unit grid on a "
            "local backend (shared dispatch worker). Export KLT_SIM_BACKEND=batch."
        )
    rc = subprocess.run(
        ["klt", "sim", "-o", str(work / f"out-{leg}"), str(work / f"request-{leg}.json"), "--format", "json"],
        stdout=(work / f"report-{leg}.json").open("w"),
        stderr=(work / f"stderr-{leg}.txt").open("w"),
    ).returncode
    if not (work / f"report-{leg}.json").read_text().strip():
        raise SystemExit(f"klt sim leg {leg} failed (rc={rc}):\n{(work / f'stderr-{leg}.txt').read_text()}")
    print(f"leg {leg}: klt sim rc={rc}")


def fmt(v) -> str:
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench", choices=sorted(LEGS))
    ap.add_argument("--work", default=None, help="scratch dir for requests/reports")
    ap.add_argument("--from-report", default=None, help="ingest a finished work dir, skip dispatch")
    ap.add_argument("--mc-n", type=int, default=200)
    ap.add_argument("--label", default="", help="free-text topology label stamped in the record")
    a = ap.parse_args()

    tb = htb.load(SIM / a.bench)
    dut = hdut.load()
    work = Path(a.from_report or a.work or f"/tmp/klt-{a.bench}").resolve()
    if not a.from_report:
        work.mkdir(parents=True, exist_ok=True)
        subprocess.check_call([sys.executable, str(HERE / "mk_klt_request.py"), a.bench, str(work), "--mc-n", str(a.mc_n)])
        for leg in LEGS[a.bench]:
            dispatch(work, leg)

    reports = {leg: json.loads((work / f"report-{leg}.json").read_text()) for leg in LEGS[a.bench]}
    legs_c = {leg: collect(rep) for leg, rep in reports.items()}
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
    for f in ["body.spice", "design.ngspice"] + [f"request-{l}.json" for l in LEGS[a.bench]] + [f"report-{l}.json" for l in LEGS[a.bench]]:
        shutil.copy2(work / f, cdir / f)
    snap = exp / "netlist-snapshots" / f"{rid}.spice"
    snap.write_text(dut.netlist.read_text() + "\n* ---- testbench fragment ----\n" + tb.netlist.read_text())

    rem = [r["environment"].get("remote") for r in reports.values()]
    ng = [r["environment"].get("engine_version") for r in reports.values()]
    lines = [
        f"# Record {rid}",
        "",
        f"- **Record ID**: {rid}",
        f"- **Experiment**: `sim/{a.bench}/` (klt sim legs: {', '.join(LEGS[a.bench])})",
        f"- **Topology label**: {a.label or dut.dut_id}",
        f"- **Claim**: REFERENCE against the ratified {label} row (README.md#target-specification-ratified-via-dr-0002; target <= {tgt:g} {unit}, stretch <= {stretch:g} {unit}). Scored, not relaxed.",
        f"- **DUT**: `{dut.dut_id}` -- **{dut.provenance}** -- `{dut.netlist.relative_to(REPO)}` (sha256 `{dut.netlist_sha256[:16]}`)",
        f"- **Testbench**: `sim/{a.bench}/testbench/{tb.netlist.name}` (sha256 `{tb.netlist_sha256[:16]}`), manifest sha256 `{tb.manifest_sha256[:16]}`",
        f"- **Commit**: `{sha}`" + (" -- **WORKING TREE DIRTY (design/sim sources uncommitted): not citable until re-minted from a clean commit**" if dirty else ""),
        f"- **Executor**: `klt sim` ({subprocess.check_output(['klt', '--version'], text=True).strip()}), backend `{os.environ.get('KLT_SIM_BACKEND', '?')}`; remote/batch descriptor(s): `{json.dumps(rem)}`; ngspice engine_version(s) reported: {ng}",
        f"- **Corner matrix**: {len(derived)} of {expected} PVT points with every leg passing (process tt/ff/ss/fs/sf x -40/27/125 C x 2.97/3.30/3.63 V)",
    ]
    if a.bench == "comparator-offset-mc":
        mc = reports["main"]["environment"].get("monte_carlo", {})
        lines += [
            f"- **Monte Carlo**: seed {mc.get('seed')}, n = {mc.get('n')} draws per PVT point, vary = {mc.get('vary')} (`.param sw_stat_mismatch=1` set by the fragment). sigma = population standard deviation of the per-draw input-referred offset `voa` (= -dv/gain, same draw), 3-sigma = 3 x sigma; stats are computed by `sim/tools/klt_record.py` from the raw per-draw values in `corners/{rid}/report-main.json`.",
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
            "comparator-offset-mc": "`mean_dvos_*`, `mean_vos_sem`, `vbias_anchor_mv`, the in-run CM-step null control (`sig_rpair_uv` is computed).",
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
