#!/usr/bin/env python3
"""Design-lever study for the post-layout decision-time misses (issue #323).

DIAGNOSTIC ONLY. T1 item 7 is `unmet / check_failed` because 7 of 675 `klt pex`
delta rows miss DR-0002's ratified `td_od50_ns <= 1.5 ns`. #229, #243 and #264
showed that trimming extracted parasitics cannot close `ss_125c_2.97v`. This
script measures DESIGN-side levers on the same cited extracted netlist
(`layout/pex/artifacts/preamp-noise/comparator.dut-layout.cir`, hash-asserted
by `parasitic_attribution.load_extracted`) at `tt_125c_2.97v` and
`ss_125c_2.97v`, and feeds the proposed DR-0007. It changes no spec row, no
layout, no cited artifact, and scores nothing.

LEVER TRANSFORMS (device cards only)
------------------------------------
A lever rewrites `W=` of the named extracted MOSFET cards by a factor and
scales `AS`/`AD` by the same factor; `PS`/`PD` keep their constant part, i.e.
new = old + 2 (W_new - W_old). Terminal legs, ground C, coupling C and the
vsubs tie are NOT touched: the transform does not add the routing parasitics a
re-laid-out wider device would bring, so an upsizing result is OPTIMISTIC on
wiring load and must be re-measured on a re-extraction. A factor of 1.0
returns the source text object unchanged; non-positive, non-finite, bool and
non-numeric factors, unknown devices and an empty device set fail closed.

Every variant is probe-centred on its OWN offset-probe trip point (the cited
convention, same harness as #264: `parasitic_attribution.run_stage`). The
schematic control `sch` is centred at 0 V as cited.

WHERE THE SIMULATION RUNS
-------------------------
Every request goes to the batch fleet (`klt sim --backend batch`); this script
never launches ngspice. `--backend local` is a single-request debug probe only.
Request budget, declared up front: 3 requests per probed variant (1 probe
shared by both corners + 2 ladders), 2 per schematic control. Default plan:
ctrl + 6 levers + sch = 7 x 3 + 2 = 23 requests (cap 23).

    python3 layout/pex/design_lever_study.py plan
    python3 layout/pex/design_lever_study.py run OUTDIR [--jobs 2]
    python3 layout/pex/design_lever_study.py analyze OUTDIR
    python3 layout/pex/design_lever_study.py verify OUTDIR   (PDK-free)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parasitic_attribution as pa  # noqa: E402
import pex_measure as pm  # noqa: E402

LEVER_ISSUE = 323
LEVER_REQUEST_CAP = 23

_MOS_CARD_RE = re.compile(r"^(?P<name>M\S+) (?P<nodes>(?:\S+ ){4})(?P<model>[np]fet_03v3) "
                          r"(?P<params>.*)$")
_PARAM_RE = re.compile(r"(?P<k>[A-Za-z]+)=(?P<v>\S+)")

#: Device roles in the extracted COMPARATOR subckt (D G S B read off the cards).
#: tail: clocked latch tail; pair: aop/aon-gated latch input pair; regen_n /
#: regen_p: cross-coupled regeneration pairs on qn/qp; stage2: sp/sn drivers
#: whose gates load the regeneration nodes.
DEVICES = {
    "tail": ("M$12",),
    "pair": ("M$9", "M$13"),
    "regen_n": ("M$8", "M$11"),
    "regen_p": ("M$20", "M$25"),
    "stage2": ("M$1", "M$5", "M$18", "M$24"),
}

#: (id, description, {device group: W factor}); each lever independent of the
#: input-cascode DR-0004 only where `cascode_independent` says so.
LEVERS = (
    ("tail-x1.5", "latch tail W x1.5", {"tail": 1.5}, True),
    ("pair-x1.5", "latch input pair W x1.5", {"pair": 1.5}, False),
    ("regen-x1.5", "both regeneration pairs W x1.5", {"regen_n": 1.5, "regen_p": 1.5}, True),
    ("regenload-x0.7", "sp/sn driver W x0.7 (regeneration-node load reduction)",
     {"stage2": 0.7}, True),
    ("tail+regenload", "tail W x1.5 with sp/sn driver W x0.7",
     {"tail": 1.5, "stage2": 0.7}, True),
    ("tail+regen", "tail W x1.5 with both regeneration pairs W x1.5",
     {"tail": 1.5, "regen_n": 1.5, "regen_p": 1.5}, True),
)


def validate_factor(f) -> float:
    if isinstance(f, bool) or not isinstance(f, (int, float)):
        raise ValueError(f"W factor must be a real number, got {f!r}")
    f = float(f)
    if not math.isfinite(f) or f <= 0.0:
        raise ValueError(f"W factor must be finite and positive, got {f!r}")
    return f


def _scale_card(line: str, factor: float) -> str:
    m = _MOS_CARD_RE.match(line)
    params = {p["k"].upper(): p["v"] for p in _PARAM_RE.finditer(m["params"])}
    w_old = pa.si(params["W"])
    w_new = w_old * factor
    out = []
    for p in _PARAM_RE.finditer(m["params"]):
        k, v = p["k"].upper(), p["v"]
        if k == "W":
            v = f"{w_new * 1e6:.12g}U"
        elif k in ("AS", "AD"):
            v = f"{pa.si(v) * factor * 1e12:.12g}P"
        elif k in ("PS", "PD"):
            v = f"{(pa.si(v) + 2 * (w_new - w_old)) * 1e6:.12g}U"
        out.append(f"{p['k']}={v}")
    return f"{m['name']} {m['nodes']}{m['model']} " + " ".join(out)


def scale_devices(text: str, factors: dict[str, float]) -> str:
    """Multiply W (and the junction geometry) of each named device card by its
    factor. `factors` maps device name -> factor. All factors 1.0 returns
    `text` unchanged (same object)."""
    if not factors:
        raise ValueError("no devices to scale")
    factors = {d: validate_factor(f) for d, f in factors.items()}
    names = {m["name"] for m in map(_MOS_CARD_RE.match, pa._join_continuations(text)) if m}
    unknown = sorted(set(factors) - names)
    if unknown:
        raise ValueError(f"devices not in the netlist: {unknown}")
    if all(f == 1.0 for f in factors.values()):
        return text
    # Only the targeted cards are rewritten (their `+` continuation lines are
    # folded into one card); every other line stays byte-identical.
    out: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and lines[j].startswith("+"):
            j += 1
        joined = " ".join([lines[i]] + [x[1:].strip() for x in lines[i + 1:j]])
        m = _MOS_CARD_RE.match(joined)
        if m and factors.get(m["name"], 1.0) != 1.0:
            out.append(_scale_card(joined, factors[m["name"]]))
        else:
            out.extend(lines[i:j])
        i = j
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def device_widths_um(text: str) -> dict[str, float]:
    out = {}
    for line in pa._join_continuations(text):
        m = _MOS_CARD_RE.match(line)
        if m:
            out[m["name"]] = pa.si(dict((p["k"].upper(), p["v"])
                                        for p in _PARAM_RE.finditer(m["params"]))["W"]) * 1e6
    return out


def lever_factors(spec: dict[str, float]) -> dict[str, float]:
    unknown = sorted(set(spec) - set(DEVICES))
    if unknown:
        raise ValueError(f"unknown device groups: {unknown}")
    return {dev: spec[g] for g in spec for dev in DEVICES[g]}


def lever_variants(text: str, levers=LEVERS) -> list[dict]:
    ids = [x[0] for x in levers]
    if not levers or len(set(ids)) != len(ids):
        raise ValueError("lever grid is empty or has duplicate ids")
    v = [{"id": "ctrl", "side": "extracted", "centre": "probed", "group": "control",
          "dut": text, "factors": {}, "description": "cited extracted DUT, unchanged"}]
    for vid, desc, spec, indep in levers:
        fac = lever_factors(spec)
        v.append({"id": vid, "side": "extracted", "centre": "probed", "group": "lever",
                  "dut": scale_devices(text, fac), "factors": fac, "description": desc,
                  "cascode_independent": indep})
    v.append({"id": "sch", "side": "schematic", "centre": "zero", "group": "control",
              "dut": pa.SCHEMATIC_DUT.read_text(), "factors": {},
              "description": "schematic leg as cited (ladder at 0 V)"})
    return v


def check_budget(plan: list[dict], points) -> int:
    n = pa.count_requests(plan, points)
    if n > LEVER_REQUEST_CAP:
        raise ValueError(f"plan needs {n} requests > cap {LEVER_REQUEST_CAP}")
    return n


def manifest(text: str, plan: list[dict], points) -> dict:
    base = device_widths_um(text)
    man = {
        "issue": LEVER_ISSUE,
        "generated_by": "layout/pex/design_lever_study.py run",
        "scope": ("diagnostic only: device-W levers applied to the cited extracted netlist, "
                  "parasitic cards unchanged; each variant centred on its own probed trip point; "
                  "no spec row scored, T1 item 7 unchanged"),
        "points": [pa.pid(p) for p in points],
        "requests_planned": check_budget(plan, points),
        "request_cap": LEVER_REQUEST_CAP,
        "source_sha256": {
            "extracted_dut": pa.sha(text),
            "schematic_dut": pa.file_sha(pa.SCHEMATIC_DUT),
            "cited_report": pa.file_sha(pa.CITED_REPORT),
            "tb_json_consumed_fields": pa.TB_JSON_CONSUMED_SHA256,
            "pex_measure_py": pa.file_sha(HERE / "pex_measure.py"),
            "parasitic_attribution_py": pa.file_sha(HERE / "parasitic_attribution.py"),
            "design_lever_study_py": pa.file_sha(Path(__file__).resolve()),
        },
        "variants": [],
    }
    for x in plan:
        e = {"id": x["id"], "side": x["side"], "centre": x["centre"],
             "description": x["description"], "dut_sha256": pa.sha(x["dut"]),
             "probe_deck_sha256": pa.sha(pa.probe_deck(x["dut"])),
             "cascode_independent": x.get("cascode_independent")}
        if x["side"] == "extracted":
            w = device_widths_um(x["dut"])
            e["device_w_um"] = {d: w[d] for d in sorted(x["factors"])}
            e["device_w_um_source"] = {d: base[d] for d in sorted(x["factors"])}
        man["variants"].append(e)
    return man


def _plan_from_manifest(man: dict, text: str) -> list[dict]:
    keep = {x["id"] for x in man["variants"]}
    return [v for v in lever_variants(text, [x for x in LEVERS if x[0] in keep])
            if v["id"] in keep]


def analyze(outdir: Path) -> dict:
    man = json.loads((outdir / "stage.json").read_text())
    text = pa.load_extracted()
    points = [pa.parse_corner_id(c) for c in man["points"]]
    cids = [pa.pid(p) for p in points]
    plan = {x["id"]: x for x in _plan_from_manifest(man, text)}
    res = {vid: pa._budget_values(outdir / vid, points) for vid in plan
           if (outdir / vid).is_dir()}
    missing = [(vid, pa.pid(p)) for vid in plan for p in points if p not in res.get(vid, {})]
    controls, valid = pa.stage_controls(res, points)
    rows = []
    for vid, x in plan.items():
        if vid == "sch":
            continue
        mv = next(m for m in man["variants"] if m["id"] == vid)
        row = {"id": vid, "description": x["description"],
               "cascode_independent": x.get("cascode_independent"),
               "device_w_um": mv.get("device_w_um"),
               "device_w_um_source": mv.get("device_w_um_source"), "corners": {}}
        for pt in points:
            r, c = res.get(vid, {}).get(pt), res.get("ctrl", {}).get(pt)
            if not r or r["td_od50_ns"] is None:
                row["corners"][pa.pid(pt)] = {"td_od50_ns": None, "missing": not r,
                                              "unresolved_count": None}
                continue
            row["corners"][pa.pid(pt)] = {
                "td_od50_ns": r["td_od50_ns"], "td_od1_ns": r["td_od1_ns"],
                "td_od01_ns": r["td_od01_ns"], "tau_ps": r["tau_ps"],
                "unresolved_count": sum(r[k] is None for k in
                                        ("td_od50_ns", "td_od1_ns", "td_od01_ns")),
                "dut_vos_v": r["dut_vos_v"],
                "dut_vos_shift_v": (None if not c or None in (r["dut_vos_v"], c["dut_vos_v"])
                                    else r["dut_vos_v"] - c["dut_vos_v"]),
                "margin_to_1p5ns_ns": pm.SPEC_TD_OD50_NS_MAX - r["td_od50_ns"],
                "meets_1p5ns": r["td_od50_ns"] <= pm.SPEC_TD_OD50_NS_MAX,
                "job_ids": r["job_ids"], "probe_job_ids": r["probe_job_ids"],
                "ladder_netlist_sha256": r["ladder_netlist_sha256"]}
        rows.append(row)
    levers = [r for r in rows if r["id"] != "ctrl"]
    cands = [r for r in levers if all(pa._ok(r["corners"].get(c)) for c in cids)]
    for r in cands:
        r["min_margin_ns"] = min(r["corners"][c]["margin_to_1p5ns_ns"] for c in cids)
    ss = pa.CORNER_IDS["ss"]
    ranked = sorted((r for r in levers if (r["corners"].get(ss) or {}).get("td_od50_ns")
                     is not None), key=lambda r: r["corners"][ss]["td_od50_ns"])
    if not valid:
        outcome = "refused: controls do not reproduce the cited decision times or are missing"
    elif cands:
        best = max(cands, key=lambda r: r["min_margin_ns"])
        outcome = (f"{len(cands)} lever(s) meet 1.5 ns at both corners; best by minimum margin: "
                   f"{best['id']} ({best['min_margin_ns'] * 1e3:+.1f} ps). Item-5 rows are NOT "
                   "measured by this stage")
    else:
        outcome = "no tested lever meets 1.5 ns at both corners (negative result)"
    return {
        "issue": LEVER_ISSUE, "generated_by": "layout/pex/design_lever_study.py analyze",
        "scope": man["scope"], "points": cids, "source_sha256": man["source_sha256"],
        "controls": controls, "study_valid": valid, "missing": missing,
        "outcome": outcome, "candidates": [r["id"] for r in cands],
        "ranked_by_ss_td_od50": [r["id"] for r in ranked], "variants": rows,
    }


def table_md(a: dict) -> str:
    cids = a["points"]
    lines = ["| variant | " + " | ".join(f"{c}: td_od50 ns / margin ns / vos shift mV / unresolved"
                                         for c in cids) + " |",
             "|---|" + "---|" * len(cids)]
    for r in a["variants"]:
        cells = []
        for c in cids:
            x = r["corners"].get(c)
            if not x or x["td_od50_ns"] is None:
                cells.append("MISSING" if (x or {}).get("missing", True) else "UNRESOLVED")
                continue
            sh = x["dut_vos_shift_v"]
            cells.append(f"{x['td_od50_ns']:.4f} / {x['margin_to_1p5ns_ns']:+.4f} / "
                         + ("n/a" if sh is None else f"{sh * 1e3:+.2f}")
                         + f" / {x['unresolved_count']}" + (" PASS" if x["meets_1p5ns"] else " fail"))
        lines.append(f"| `{r['id']}` | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def cmd_plan(args) -> int:
    text = pa.load_extracted()
    points = pa.budget_points("two")
    plan = lever_variants(text)
    print(f"requests planned: {check_budget(plan, points)} (cap {LEVER_REQUEST_CAP})")
    for x in plan:
        print(f"{x['id']:<16} {x['description']}")
    return 0


def cmd_run(args) -> int:
    pa.check_bench()
    text = pa.load_extracted()
    points = pa.budget_points("two")
    plan = lever_variants(text)
    try:
        man = manifest(text, plan, points)
    except ValueError as e:
        sys.exit(str(e))
    if args.backend == "local" and man["requests_planned"] != 1:
        sys.exit("--backend local is a single-request debug probe only")
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return pa.run_stage(outdir, man, plan, points, args.backend, args.jobs, LEVER_ISSUE)


def cmd_analyze(args) -> int:
    outdir = Path(args.outdir).resolve()
    a = analyze(outdir)
    (outdir / "levers.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
    (outdir / "levers-table.md").write_text(
        "<!-- GENERATED by layout/pex/design_lever_study.py analyze -- do not edit -->\n"
        + table_md(a))
    print(f"study_valid={a['study_valid']} missing={len(a['missing'])}\n{a['outcome']}")
    return 0 if a["study_valid"] and not a["missing"] else 1


def cmd_verify(args) -> int:
    outdir = Path(args.outdir).resolve()
    pa.check_bench()
    text = pa.load_extracted()
    man = json.loads((outdir / "stage.json").read_text())
    points = [pa.parse_corner_id(c) for c in man["points"]]
    plan = _plan_from_manifest(man, text)
    errors, drift = pa.budget_manifest_diff(man, manifest(text, plan, points))
    for d in drift:
        print(f"NOTE provenance drift (not an error): {d}")
    errors += pa.verify_stage_reports(outdir, plan, points)
    committed = outdir / "levers.json"
    if not committed.exists():
        errors.append("levers.json missing")
    else:
        a = analyze(outdir)
        if json.loads(committed.read_text()) != json.loads(json.dumps(a)):
            errors.append("levers.json is not what `analyze` derives from the reports")
        tbl = outdir / "levers-table.md"
        if not tbl.exists() or tbl.read_text().split("\n", 1)[1] != table_md(a):
            errors.append("levers-table.md is not what `analyze` generates")
    for e in errors:
        print(f"FAIL {e}")
    print(f"verify: {len(errors)} error(s)")
    return 1 if errors else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("outdir")
    r.add_argument("--backend", default="batch", choices=("batch", "local"))
    r.add_argument("--jobs", type=int, default=2)
    for name in ("analyze", "verify"):
        sub.add_parser(name).add_argument("outdir")
    args = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "analyze": cmd_analyze,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
