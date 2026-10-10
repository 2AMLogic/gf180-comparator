#!/usr/bin/env python3
"""Parasitic attribution of the post-layout decision-time misses (issue #229).

DIAGNOSTIC ONLY. T1 item 7 is `unmet / check_failed` because 7 of 675
`klt pex` delta rows miss DR-0002's ratified `td_od50_ns <= 1.5 ns`
(`layout/pex/comparator.pex.json`). This script asks WHICH extracted
parasitics produce the +60 % slowdown, at the two worst failing corners
(`ss_125c_2.97v`, `tt_125c_2.97v`). It changes no spec, layout, design,
bench or cited artifact, and scores nothing.

THE EXTRACTED NETLIST IS THE CITED ONE, NOT A NEW EXTRACTION
------------------------------------------------------------
`layout/pex/artifacts/preamp-noise/comparator.dut-layout.cir` (committed by
issue #202) is the adapted extracted DUT whose sha256 equals the cited
extracted leg's `dut_netlist_sha256` (`layout/pex/artifacts/measure/
extracted/summary.json`). That identity is asserted below; a mismatch stops
the script. No `klt pex` / `klt extract` re-run is involved.

VARIANTS (derived from the netlist text, never from a hand-written list)
-----------------------------------------------------------------------
The extraction's parasitic cards have three fixed shapes (the
`klt extract --parasitics` star model): a per-terminal leg
`R<net>_t<k> <net>__t<k> <net> <ohm>`, a per-net ground cap
`C<net> <net> vsubs <F>`, and a vertical-overlap coupling cap
`Ccc_<a>_<b> <a> <b> <F>`. Every net that has legs or a ground cap gets

    r0-<net>    that net's series R removed (its `__t<k>` terminal nodes
                merged into the hub; the leg cards dropped)
    cg0-<net>   that net's ground C removed

plus the aggregate variants

    r0-all      every series R removed
    cg0-all     every ground C removed
    cc0-all     every vertical-overlap coupling C removed
    c0-all      cg0-all + cc0-all
    rc0-all     every extracted parasitic removed (devices only)
    vsubs-tied  the extraction's floating `vsubs` node (a GLOBAL node, so
                shared by the bench's three DUT instances, tied to ground
                only through 1e12 ohm) tied to ground through 1 mohm
    devgeom     every extracted MOSFET's AS/AD/PS/PD/NRS/NRD rewritten to the
                schematic's own convention (design/comparator.spice, nf=1:
                as=ad=0.18u*W, ps=pd=2*(W+0.18u), nrs=nrd=0.18u/W, sa=sb=sd=0),
                all parasitics kept
    devgeom-rc0-all  devgeom with every parasitic removed: the closure check
                (should land on the schematic leg if nothing else differs)

and the controls / confound legs

    ctrl        the extracted DUT unchanged; its decks must be BYTE-IDENTICAL
                to the cited ones (sha256 against the cited reports) and its
                values must reproduce the cited rows
    ctrl-ctr0   ctrl with the ladder centred at 0 V (the schematic leg's
                convention) instead of the probed trip point
    sch         the schematic leg, centred at 0 V as cited (reproduces the
                cited schematic rows)
    sch-probed  the schematic leg centred at ITS probed trip point (the
                extracted leg's convention)

MEASUREMENT (the cited harness, unchanged)
------------------------------------------
Every deck is built by `layout/pex/pex_measure.py`'s own functions
(`_flatten`, `_probe_body`, `_main_body`, `_vos_source`, `_request`,
`_derive`) -- the same hash-pinned bench re-expression and the same `klt sim`
request shape the cited report used. Per variant: one offset-probe request
(process tt and ss, 125 C, 2.97 V) and one ladder request per process (the
`dut_vos` source cannot key on process). The ladder's `dut_vos` table keeps
the cited probe's values at every point this study does not run and puts
this variant's own probed trip point at 125 C / 2.97 V, so the control's
ladder decks are byte-identical to the cited ones.

WHERE THE SIMULATION RUNS
-------------------------
Every request goes to the batch fleet (`klt sim --backend batch`), submitted
by the same released `klayout-tools==0.6.0` client as the cited report
($PEX_SIM_KLT overrides). This script never launches ngspice. `--backend
local` exists only for a single-variant, single-corner debug probe
(`--only ctrl --corner ss`), as host rules allow.

    python3 layout/pex/parasitic_attribution.py plan
    python3 layout/pex/parasitic_attribution.py run OUTDIR [--jobs 2]
    python3 layout/pex/parasitic_attribution.py analyze OUTDIR
    python3 layout/pex/parasitic_attribution.py verify OUTDIR   (PDK-free)

`run` is resumable: a request whose report already exists, parses, and was
run on this exact deck (netlist sha256) is not re-submitted.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import pex_measure as pm  # noqa: E402

ISSUE = 229
EXTRACTED_DUT = HERE / "artifacts" / "preamp-noise" / "comparator.dut-layout.cir"
CITED_REPORT = HERE / "comparator.pex.json"
CITED_MEASURE = HERE / "artifacts" / "measure"
SCHEMATIC_DUT = REPO / "design" / "comparator.spice"

#: The two worst failing corners named by issue #229. Both are 125 C / 2.97 V,
#: so one probe request (process tt + ss) covers both.
TEMP_C = 125.0
VDD_V = 2.97
PROCESSES = ("tt", "ss")
CORNER_IDS = {p: pm.corner_id(p, TEMP_C, VDD_V) for p in PROCESSES}

#: Control acceptance: the control must reproduce the cited value to the
#: report's own printed precision (6 significant digits of seconds, i.e.
#: ~1e-5 ns at 1-2 ns). 1e-4 ns is 10x that; anything larger invalidates
#: the study.
CONTROL_TOL_NS = 1e-4

#: Schematic device-geometry convention (design/comparator.spice, nf=1).
SCH_DIFF_LEN_UM = 0.18

#: The tb.json fields `pex_measure.py`'s re-expression consumes (`options`,
#: `analyses`, `offset_probe.analyses`), hashed as canonical JSON, at the
#: cited commit (9e58676, issue #81). `pex_measure.PINNED_SHA256` pins the
#: whole tb.json file, which #181/#141 have since changed in claim/description
#: text and an added `td_od1_over_tau` row only -- none of which reaches a deck
#: or a request. This study pins exactly what reaches them instead; the two
#: SPICE fragments are still checked against pex_measure's own pins, and the
#: control's decks are checked byte-for-byte against the cited reports.
TB_JSON_CONSUMED_SHA256 = "462b79b389613fbc06de8037311ed54b0820a60f48778e1a1322c48c94a13f74"

#: A launch the fleet refuses for capacity (its shared instance cap, which
#: other sweeps also draw on, or a Spot shortage) ran nothing; it is retried
#: after a randomized wait for up to CAPACITY_WAIT_S. Any other failure is
#: recorded, never retried and never replaced by a local run.
CAPACITY_REFUSALS = ("BATCH_MAX_CONCURRENT_INSTANCES", "InsufficientInstanceCapacity",
                     "capacity-not-available")
CAPACITY_RETRY_S = 60
CAPACITY_WAIT_S = 4 * 3600

#: `vsubs-tied`: the tie resistance replacing the extraction's 1e12 ohm.
VSUBS_TIE_OHM = "1e-3"

# --------------------------------------------------------------------------- #
# Netlist parsing
# --------------------------------------------------------------------------- #

_LEG_RE = re.compile(r"^R(?P<net>\S+)_t(?P<k>\d+) (?P=net)__t(?P=k) (?P=net) (?P<val>\S+)$")
_CG_RE = re.compile(r"^C(?P<net>\S+) (?P=net) vsubs (?P<val>\S+)$")
_CC_RE = re.compile(r"^Ccc_(?P<a>\S+?)_(?P<b>\S+) (?P=a) (?P=b) (?P<val>\S+)$")
_TIE_RE = re.compile(r"^Rvsubs_dctie vsubs 0 (?P<val>\S+)$")
_MOS_RE = re.compile(r"^M\S+ ")
_SI = {"T": 1e12, "G": 1e9, "MEG": 1e6, "K": 1e3, "M": 1e-3, "U": 1e-6,
       "N": 1e-9, "P": 1e-12, "F": 1e-15}


def si(text: str) -> float:
    m = re.fullmatch(r"([-+0-9.eE]+?)(MEG|[TGKMUNPF])?", text.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"not a SPICE number: {text!r}")
    return float(m.group(1)) * (_SI[m.group(2).upper()] if m.group(2) else 1.0)


def parse(text: str) -> dict:
    """The parasitic cards of an extracted netlist, by shape. Raises on a
    netlist with no parasitic cards (nothing to attribute)."""
    legs: dict[str, list[tuple[int, float]]] = {}
    cg: dict[str, float] = {}
    cc: list[tuple[str, str, float]] = []
    tie = None
    for line in text.splitlines():
        if m := _LEG_RE.match(line):
            legs.setdefault(m["net"], []).append((int(m["k"]), si(m["val"])))
        elif m := _CC_RE.match(line):
            cc.append((m["a"], m["b"], si(m["val"])))
        elif m := _CG_RE.match(line):
            cg[m["net"]] = si(m["val"])
        elif m := _TIE_RE.match(line):
            tie = si(m["val"])
    if not legs or not cg:
        raise ValueError("no star-model parasitic cards found")
    nets = sorted(set(legs) | set(cg))
    return {"nets": nets, "legs": legs, "cg": cg, "cc": cc, "vsubs_tie_ohm": tie}


def net_summary(p: dict) -> dict[str, dict]:
    """Per-net totals: leg count, sum and parallel-equivalent of the star
    legs, ground C, and the coupling C touching the net."""
    out = {}
    for n in p["nets"]:
        legs = [v for _, v in p["legs"].get(n, [])]
        cc = sum(v for a, b, v in p["cc"] if n in (a, b))
        out[n] = {
            "legs": len(legs),
            "r_sum_ohm": sum(legs),
            "r_max_leg_ohm": max(legs) if legs else 0.0,
            "c_ground_ff": p["cg"].get(n, 0.0) * 1e15,
            "c_coupling_ff": cc * 1e15,
        }
    return out


# --------------------------------------------------------------------------- #
# Netlist edits (each one a pure text transform of the cited netlist)
# --------------------------------------------------------------------------- #

def _join_continuations(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("+") and out:
            out[-1] = out[-1] + " " + line[1:].strip()
        else:
            out.append(line)
    return out


def drop_r(text: str, nets: set[str]) -> str:
    """Remove the series R of `nets`: drop each leg card and merge the leg's
    terminal node `<net>__t<k>` into the hub `<net>` everywhere else."""
    term = re.compile(r"^(?P<net>.+)__t\d+$")
    out = []
    for line in text.splitlines():
        m = _LEG_RE.match(line)
        if m and m["net"] in nets:
            continue
        if line.startswith(("*", ".")) or not line.strip():
            out.append(line)
            continue
        toks = line.split(" ")
        for i, tok in enumerate(toks):
            t = term.match(tok)
            if t and t["net"] in nets:
                toks[i] = t["net"]
        out.append(" ".join(toks))
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def drop_cg(text: str, nets: set[str]) -> str:
    keep = []
    for line in text.splitlines():
        m = _CG_RE.match(line)
        if m and m["net"] in nets:
            continue
        keep.append(line)
    return "\n".join(keep) + ("\n" if text.endswith("\n") else "")


def drop_cc(text: str) -> str:
    keep = [l for l in text.splitlines() if not _CC_RE.match(l)]
    return "\n".join(keep) + ("\n" if text.endswith("\n") else "")


def tie_vsubs(text: str) -> str:
    out, n = [], 0
    for line in text.splitlines():
        if _TIE_RE.match(line):
            line = f"Rvsubs_dctie vsubs 0 {VSUBS_TIE_OHM}"
            n += 1
        out.append(line)
    if n != 1:
        raise ValueError(f"expected exactly one vsubs tie card, found {n}")
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def schematic_device_geometry(text: str) -> str:
    """Rewrite every MOSFET card's junction geometry to the schematic's
    convention (nf=1). Only AS/AD/PS/PD are replaced; NRS/NRD/SA/SB/SD are
    appended, as the schematic passes them."""
    out, n = [], 0
    d = SCH_DIFF_LEN_UM
    for line in _join_continuations(text):
        if _MOS_RE.match(line):
            w_um = si(re.search(r"\bW=(\S+)", line).group(1)) * 1e6
            line = re.sub(r"\s(AS|AD|PS|PD)=\S+", "", line)
            line += (f" AS={w_um * d:.6g}P AD={w_um * d:.6g}P"
                     f" PS={2 * (w_um + d):.6g}U PD={2 * (w_um + d):.6g}U"
                     f" NRS={d / w_um:.6g} NRD={d / w_um:.6g} SA=0 SB=0 SD=0")
            n += 1
        out.append(line)
    if n == 0:
        raise ValueError("no MOSFET cards to rewrite")
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# Variant plan
# --------------------------------------------------------------------------- #

def variants(text: str) -> list[dict]:
    """Every variant: id, side, DUT text, ladder centring, and what it removes.
    `group` drives the attribution table's classification."""
    p = parse(text)
    nets = p["nets"]
    every = set(nets)
    v: list[dict] = []

    def add(vid, dut, group, what, side="extracted", centre="probed"):
        v.append({"id": vid, "side": side, "centre": centre, "group": group,
                  "removes": what, "dut": dut})

    add("ctrl", text, "control", "nothing (cited extracted DUT, byte-identical decks)")
    add("ctrl-ctr0", text, "centring", "nothing; ladder centred at 0 V instead of the probed trip point",
        centre="zero")
    for n in nets:
        add(f"r0-{n}", drop_r(text, {n}), "net-R", f"series R of net {n}")
    for n in nets:
        add(f"cg0-{n}", drop_cg(text, {n}), "net-Cg", f"ground C of net {n}")
    add("r0-all", drop_r(text, every), "aggregate", "every series R")
    add("cg0-all", drop_cg(text, every), "aggregate", "every ground C")
    add("cc0-all", drop_cc(text), "aggregate", "every vertical-overlap coupling C")
    add("c0-all", drop_cc(drop_cg(text, every)), "aggregate", "every C (ground + coupling)")
    add("rc0-all", drop_cc(drop_cg(drop_r(text, every), every)), "aggregate",
        "every extracted parasitic (devices only)")
    add("vsubs-tied", tie_vsubs(text), "substrate-node",
        f"nothing removed; floating global vsubs tied to ground through {VSUBS_TIE_OHM} ohm")
    add("devgeom", schematic_device_geometry(text), "device-geometry",
        "nothing removed; MOSFET AS/AD/PS/PD/NRS/NRD set to the schematic convention")
    add("devgeom-rc0-all",
        schematic_device_geometry(drop_cc(drop_cg(drop_r(text, every), every))),
        "device-geometry", "every parasitic AND schematic-convention device geometry (closure)")
    sch = SCHEMATIC_DUT.read_text()
    add("sch", sch, "control", "schematic leg as cited (ladder at 0 V)", side="schematic", centre="zero")
    add("sch-probed", sch, "centring", "schematic leg, ladder centred at its probed trip point",
        side="schematic", centre="probed")
    for x in v:
        if x["dut"] == text and x["id"] not in ("ctrl", "ctrl-ctr0"):
            raise ValueError(f"variant {x['id']} did not change the netlist")
    return v


def load_extracted() -> str:
    text = EXTRACTED_DUT.read_text()
    want = json.loads((CITED_MEASURE / "extracted" / "summary.json").read_text())["dut_netlist_sha256"]
    got = hashlib.sha256(text.encode()).hexdigest()
    if got != want:
        sys.exit(f"{EXTRACTED_DUT.relative_to(REPO)} sha256 {got} is not the cited extracted "
                 f"leg's dut_netlist_sha256 {want}")
    return text


def cited_vos(side: str) -> dict[tuple[str, float, float], float]:
    """The cited probe's trip point at every PVT point (pex_measure's rule)."""
    probe = json.loads((CITED_MEASURE / side / "probe.report.json").read_text())
    out = {}
    for c in probe["corners"]:
        t = pm._values(c).get("t_flip")
        if t is not None:
            out[pm._point_key(c)] = -pm.PROBE_VSPAN + 2 * pm.PROBE_VSPAN * t / pm.PROBE_TRAMP
    return out


def cited_rows() -> dict[tuple[str, str], dict]:
    rep = json.loads(CITED_REPORT.read_text())
    return {(r["corner_id"], r["spec_row"]): r for r in rep["delta"]
            if r["corner_id"] in CORNER_IDS.values()}


# --------------------------------------------------------------------------- #
# Decks and requests
# --------------------------------------------------------------------------- #

def probe_deck(dut: str) -> str:
    return pm._flatten(dut, pm._probe_body(), [])


def ladder_deck(dut: str, side: str, process: str, centre: str, vos_here: float | None) -> str:
    """The cited ladder deck shape. Points this study does not run keep the
    cited trip points (extracted) or 0 V (schematic, the cited convention);
    the studied point carries this variant's own centring."""
    keys = [(t, v) for t in pm.TEMPERATURES_C for v in pm.SUPPLIES_V]
    if side == "extracted":
        base = cited_vos("extracted")
        table = {k: base[(process, *k)] for k in keys}
    else:
        table = {k: 0.0 for k in keys}
    if centre == "zero":
        table[(TEMP_C, VDD_V)] = 0.0
    else:
        if vos_here is None:
            raise ValueError("probed centring needs a probed trip point")
        table[(TEMP_C, VDD_V)] = vos_here
    return pm._flatten(dut, pm._main_body(), [pm._vos_source(table)])


def _narrow(req: dict) -> dict:
    req["corners"]["temperature_c"] = [TEMP_C]
    req["corners"]["supply_v"] = {k: [VDD_V] for k in req["corners"]["supply_v"]}
    return req


def probe_request(processes) -> dict:
    return _narrow(pm._request("probe.spice", list(processes), pm.PROBE_MEAS,
                               "100n 80u 0 100n", pm.TIMEOUT_PROBE_S, ["vsup"]))


def ladder_request(process: str) -> dict:
    return _narrow(pm._request(f"ladder-{process}.spice", [process], pm.MAIN_MEAS, "5p 60n",
                               pm.TIMEOUT_MAIN_S, ["vsup", "vsupa"]))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def tb_consumed_sha256(tb: dict) -> str:
    return sha(json.dumps({"options": tb["options"], "analyses": tb["analyses"],
                           "offset_probe_analyses": tb["offset_probe"]["analyses"]},
                          sort_keys=True))


def check_bench() -> None:
    """The bench this study re-expresses is the cited one (see
    TB_JSON_CONSUMED_SHA256)."""
    for path in (pm.TB_MAIN, pm.TB_PROBE):
        if pm._sha256(path) != pm.PINNED_SHA256[path]:
            sys.exit(f"{os.path.relpath(path, REPO)} is not the bench the cited report used")
    got = tb_consumed_sha256(json.loads(Path(pm.TB_JSON).read_text()))
    if got != TB_JSON_CONSUMED_SHA256:
        sys.exit(f"tb.json's consumed fields hash {got}, not the cited {TB_JSON_CONSUMED_SHA256}")
    pm._check_meas_against_manifest()


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #

def _report_ok(path: Path, deck_sha: str) -> dict | None:
    if not path.exists():
        return None
    try:
        rep = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not rep.get("corners") or (rep.get("environment") or {}).get("netlist_sha256") != deck_sha:
        return None
    return rep


def submit(vdir: Path, tag: str, deck: str, request: dict, backend: str) -> dict:
    """Write the deck + request, run `klt sim`, keep the report. Never exits:
    a failure is returned and recorded."""
    deck_path = vdir / request["netlist"]
    deck_path.write_text(deck)
    req_path = vdir / f"{tag}.request.json"
    req_path.write_text(json.dumps(request, indent=2) + "\n")
    rep_path = vdir / f"{tag}.report.json"
    done = _report_ok(rep_path, sha(deck))
    if done is not None:
        return {"tag": tag, "ok": True, "report": done, "resumed": True}
    deadline = time.monotonic() + CAPACITY_WAIT_S
    attempts = 0
    while True:
        attempts += 1
        proc = subprocess.run([*pm._klt(), "sim", req_path.name, "--backend", backend,
                               "--format", "json"], capture_output=True, text=True, cwd=vdir)
        try:
            ok = proc.returncode in (0, 4) and bool(json.loads(proc.stdout).get("corners"))
        except ValueError:
            ok = False
        refused = not ok and any(s in proc.stdout + proc.stderr for s in CAPACITY_REFUSALS)
        if ok or not refused or time.monotonic() > deadline:
            break
        # The fleet's shared instance cap (other sweeps share it) refused the
        # launch before anything ran: wait and resubmit the same request.
        time.sleep(CAPACITY_RETRY_S + random.uniform(0, CAPACITY_RETRY_S))
    rep_path.write_text(proc.stdout)
    if not ok:
        (vdir / f"{tag}.stderr.txt").write_text(proc.stdout[-4000:] + proc.stderr[-8000:])
        return {"tag": tag, "ok": False, "rc": proc.returncode, "attempts": attempts,
                "stderr": (proc.stdout + proc.stderr)[-2000:]}
    stale = vdir / f"{tag}.stderr.txt"
    if stale.exists():
        stale.unlink()
    rep = json.loads(proc.stdout)
    return {"tag": tag, "ok": True, "report": rep, "resumed": False, "attempts": attempts}


def run_variant(v: dict, outdir: Path, backend: str, processes) -> dict:
    vdir = outdir / v["id"]
    vdir.mkdir(parents=True, exist_ok=True)
    log = {"id": v["id"], "jobs": {}}
    vos: dict[str, float | None] = {p: None for p in processes}
    if v["centre"] == "probed":
        r = submit(vdir, "probe", probe_deck(v["dut"]), probe_request(processes), backend)
        log["jobs"]["probe"] = {k: r[k] for k in ("ok", "rc", "stderr", "attempts") if k in r}
        if not r["ok"]:
            return log
        for c in r["report"]["corners"]:
            t = pm._values(c).get("t_flip")
            vos[c["process"]] = (None if t is None else
                                 -pm.PROBE_VSPAN + 2 * pm.PROBE_VSPAN * t / pm.PROBE_TRAMP)
    for p in processes:
        if v["centre"] == "probed" and vos[p] is None:
            log["jobs"][f"ladder-{p}"] = {"ok": False, "stderr": "probe found no trip point"}
            continue
        deck = ladder_deck(v["dut"], v["side"], p, v["centre"], vos[p])
        r = submit(vdir, f"ladder-{p}", deck, ladder_request(p), backend)
        log["jobs"][f"ladder-{p}"] = {k: r[k] for k in ("ok", "rc", "stderr", "attempts")
                                      if k in r}
    return log


def cmd_run(args) -> int:
    check_bench()
    text = load_extracted()
    plan = variants(text)
    if args.only:
        plan = [v for v in plan if v["id"] in args.only]
        if not plan:
            sys.exit("--only matched no variant")
    processes = tuple(args.corner) if args.corner else PROCESSES
    if args.backend == "local" and (len(plan) != 1 or len(processes) != 1):
        sys.exit("--backend local is a single-variant, single-corner debug probe only "
                 "(--only <id> --corner <process>); the grid goes to the batch fleet")
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    client = pm._klt_identity()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        logs = list(pool.map(lambda v: run_variant(v, outdir, args.backend, processes), plan))
    failed = [(l["id"], t) for l in logs for t, j in l["jobs"].items() if not j.get("ok")]
    run_log = {
        "issue": ISSUE, "backend": args.backend, "klt_sim_client": client,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "variants": [l["id"] for l in logs], "failed_jobs": failed,
    }
    name = "run-log.json" if not args.only else f"run-log-{'-'.join(args.only)}.json"
    (outdir / name).write_text(json.dumps(run_log, indent=2, sort_keys=True) + "\n")
    print(f"{len(logs)} variants, {len(failed)} failed jobs -> {outdir}")
    for vid, tag in failed:
        print(f"  FAILED {vid}/{tag}")
    return 1 if failed else 0


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #

def _variant_values(vdir: Path, processes) -> dict[str, dict]:
    out = {}
    probe = None
    if (vdir / "probe.report.json").exists():
        probe = json.loads((vdir / "probe.report.json").read_text())
    for p in processes:
        path = vdir / f"ladder-{p}.report.json"
        if not path.exists() or not path.read_text().strip():
            continue
        rep = json.loads(path.read_text())
        (corner,) = [c for c in rep["corners"] if c["process"] == p]
        d = pm._derive(pm._values(corner))
        if probe:
            (pc,) = [c for c in probe["corners"] if c["process"] == p]
            t = pm._values(pc).get("t_flip")
            d["dut_vos_v"] = None if t is None else (
                -pm.PROBE_VSPAN + 2 * pm.PROBE_VSPAN * t / pm.PROBE_TRAMP)
        d["job_ids"] = sorted({
            (r.get("environment") or {}).get("remote", {}).get("job_id")
            for r in ([rep, probe] if probe else [rep])} - {None})
        d["ladder_netlist_sha256"] = rep["environment"]["netlist_sha256"]
        out[p] = d
    return out


def analyze(outdir: Path) -> dict:
    text = load_extracted()
    plan = {v["id"]: v for v in variants(text)}
    cited = cited_rows()
    res: dict[str, dict] = {}
    for vid in plan:
        vdir = outdir / vid
        if vdir.is_dir():
            res[vid] = _variant_values(vdir, PROCESSES)
    missing = [(vid, p) for vid in plan for p in PROCESSES if p not in res.get(vid, {})]

    controls = {}
    for p in PROCESSES:
        cid = CORNER_IDS[p]
        for vid, key in (("ctrl", "extracted_value"), ("sch", "schematic_value")):
            want = cited[(cid, "td_od50_ns")][key]
            got = (res.get(vid, {}).get(p) or {}).get("td_od50_ns")
            controls[f"{vid}@{cid}"] = {
                "cited_td_od50_ns": want, "rerun_td_od50_ns": got,
                "abs_diff_ns": None if got is None else abs(got - want),
                "reproduces": got is not None and abs(got - want) <= CONTROL_TOL_NS,
            }
        want_vos = cited[(cid, "dut_vos_v")]["extracted_value"]
        got_vos = (res.get("ctrl", {}).get(p) or {}).get("dut_vos_v")
        controls[f"ctrl@{cid}"]["cited_dut_vos_v"] = want_vos
        controls[f"ctrl@{cid}"]["rerun_dut_vos_v"] = got_vos
    # Deck identity: the control's ladder decks must be the cited decks.
    for p in PROCESSES:
        cited_sha = json.loads((CITED_MEASURE / "extracted" / f"ladder-{p}.report.json")
                               .read_text())["environment"]["netlist_sha256"]
        got = (res.get("ctrl", {}).get(p) or {}).get("ladder_netlist_sha256")
        controls[f"ctrl@{CORNER_IDS[p]}"]["deck_sha256_matches_cited"] = got == cited_sha
    valid = all(c["reproduces"] for c in controls.values()) and all(
        c.get("deck_sha256_matches_cited", True) for c in controls.values())

    rows = []
    for vid, v in plan.items():
        row = {"id": vid, "group": v["group"], "removes": v["removes"], "corners": {}}
        for p in PROCESSES:
            r = res.get(vid, {}).get(p)
            c = res.get("ctrl", {}).get(p)
            s = res.get("sch", {}).get(p)
            if not (r and c and s) or None in (r["td_od50_ns"], c["td_od50_ns"], s["td_od50_ns"]):
                row["corners"][CORNER_IDS[p]] = None
                continue
            gap = c["td_od50_ns"] - s["td_od50_ns"]
            row["corners"][CORNER_IDS[p]] = {
                "td_od50_ns": r["td_od50_ns"],
                "td_od1_ns": r["td_od1_ns"], "td_od01_ns": r["td_od01_ns"],
                "tau_ps": r["tau_ps"], "e_dec_fj": r["e_dec_fj"],
                "dut_vos_v": r.get("dut_vos_v"),
                "dout_od50_end": r["dout_od50_end"],
                "delta_vs_ctrl_ns": r["td_od50_ns"] - c["td_od50_ns"],
                "share_of_gap": (c["td_od50_ns"] - r["td_od50_ns"]) / gap,
                "meets_1p5ns": r["td_od50_ns"] <= pm.SPEC_TD_OD50_NS_MAX,
                "job_ids": r["job_ids"],
            }
        shares = [x["share_of_gap"] for x in row["corners"].values() if x]
        row["mean_share"] = sum(shares) / len(shares) if len(shares) == len(PROCESSES) else None
        rows.append(row)

    def ranked(group):
        return sorted((r for r in rows if r["group"] == group and r["mean_share"] is not None),
                      key=lambda r: -r["mean_share"])

    per_net = ranked("net-R") + ranked("net-Cg")
    per_net.sort(key=lambda r: -r["mean_share"])
    sum_r = sum(r["mean_share"] for r in ranked("net-R"))
    sum_cg = sum(r["mean_share"] for r in ranked("net-Cg"))
    return {
        "issue": ISSUE,
        "generated_by": "layout/pex/parasitic_attribution.py analyze",
        "scope": ("diagnostic only: td_od50_ns at " + ", ".join(CORNER_IDS.values())
                  + "; no spec row is scored and T1 item 7 stays unmet"),
        "extracted_dut": {"path": str(EXTRACTED_DUT.relative_to(REPO)), "sha256": sha(text)},
        "share_definition": ("share_of_gap = (td_ctrl - td_variant) / (td_ctrl - td_sch) at the "
                             "same corner; 1.0 = the variant closes the whole post-layout gap"),
        "controls": controls,
        "study_valid": valid,
        "missing": missing,
        "net_parasitics": net_summary(parse(text)),
        "sum_of_single_net_shares": {"net-R": sum_r, "net-Cg": sum_cg},
        "ranking_single_net": [{"id": r["id"], "mean_share": r["mean_share"]} for r in per_net],
        "variants": rows,
    }


def table_md(a: dict) -> str:
    cids = list(CORNER_IDS.values())
    lines = [
        f"| variant | removes | " + " | ".join(f"td_od50 {c} (ns) | share" for c in cids)
        + " | mean share |",
        "|---|---|" + "---|---|" * len(cids) + "---|",
    ]
    order = {"control": 0, "centring": 1, "aggregate": 2, "substrate-node": 3,
             "device-geometry": 4, "net-R": 5, "net-Cg": 6}
    for r in sorted(a["variants"], key=lambda r: (order[r["group"]],
                                                  -(r["mean_share"] or -9e9))):
        cells = []
        for c in cids:
            x = r["corners"].get(c)
            cells.append("n/a | n/a" if not x else
                         f"{x['td_od50_ns']:.4f} | {x['share_of_gap'] * 100:+.1f} %")
        ms = "n/a" if r["mean_share"] is None else f"{r['mean_share'] * 100:+.1f} %"
        lines.append(f"| `{r['id']}` | {r['removes']} | " + " | ".join(cells) + f" | {ms} |")
    return "\n".join(lines) + "\n"


def cmd_analyze(args) -> int:
    outdir = Path(args.outdir).resolve()
    a = analyze(outdir)
    (outdir / "attribution.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
    (outdir / "attribution-table.md").write_text(
        "<!-- GENERATED by layout/pex/parasitic_attribution.py analyze -- do not edit -->\n"
        + table_md(a))
    print(f"study_valid={a['study_valid']} missing={len(a['missing'])}")
    for k, c in a["controls"].items():
        print(f"  control {k}: cited {c['cited_td_od50_ns']} rerun {c['rerun_td_od50_ns']} "
              f"reproduces={c['reproduces']}")
    return 0 if a["study_valid"] and not a["missing"] else 1


def cmd_verify(args) -> int:
    """PDK-free: every committed request/report pair was produced from the
    deck this script regenerates (sha256 of the netlist each report ran),
    and attribution.json is what `analyze` derives from the reports."""
    outdir = Path(args.outdir).resolve()
    check_bench()
    text = load_extracted()
    errors = []
    for v in variants(text):
        vdir = outdir / v["id"]
        if not vdir.is_dir():
            errors.append(f"{v['id']}: no evidence directory")
            continue
        vals = _variant_values(vdir, PROCESSES)
        if v["centre"] == "probed":
            rep = json.loads((vdir / "probe.report.json").read_text())
            if rep["environment"]["netlist_sha256"] != sha(probe_deck(v["dut"])):
                errors.append(f"{v['id']}/probe: report ran a different deck")
        for p in PROCESSES:
            if p not in vals:
                errors.append(f"{v['id']}/ladder-{p}: no report")
                continue
            deck = ladder_deck(v["dut"], v["side"], p, v["centre"], vals[p].get("dut_vos_v"))
            if vals[p]["ladder_netlist_sha256"] != sha(deck):
                errors.append(f"{v['id']}/ladder-{p}: report ran a different deck")
            req = json.loads((vdir / f"ladder-{p}.request.json").read_text())
            if req != ladder_request(p):
                errors.append(f"{v['id']}/ladder-{p}: request differs from the generated one")
    committed = outdir / "attribution.json"
    if committed.exists():
        if json.loads(committed.read_text()) != json.loads(json.dumps(analyze(outdir))):
            errors.append("attribution.json is not what `analyze` derives from the reports")
    else:
        errors.append("attribution.json missing")
    for e in errors:
        print(f"FAIL {e}")
    print(f"verify: {len(errors)} error(s)")
    return 1 if errors else 0


def cmd_plan(args) -> int:
    text = load_extracted()
    for v in variants(text):
        print(f"{v['id']:<18} {v['side']:<9} centre={v['centre']:<6} {v['removes']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("outdir")
    r.add_argument("--backend", default="batch", choices=("batch", "local"))
    r.add_argument("--jobs", type=int, default=2,
                   help="concurrent `klt sim` submissions; the fleet's instance cap is "
                        "shared with other sweeps, so keep this small")
    r.add_argument("--only", action="append", help="variant id (repeatable)")
    r.add_argument("--corner", action="append", choices=PROCESSES,
                   help="process corner (repeatable; default both)")
    for name in ("analyze", "verify"):
        s = sub.add_parser(name)
        s.add_argument("outdir")
    args = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "analyze": cmd_analyze,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
