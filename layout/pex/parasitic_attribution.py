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


# --------------------------------------------------------------------------- #
# Finite ground-C budget study (issue #243)
# --------------------------------------------------------------------------- #
#
# #229 removed ground C entirely, which is a diagnostic endpoint and not a
# realizable layout. #243 asks what FINITE retained fraction of the dominant
# nets' ground C clears the ratified td_od50_ns <= 1.5 ns. Only the ground-C
# cards (`C<net> <net> vsubs <F>`) of the chosen nets are scaled, jointly, by
# one factor; series R, coupling C, device geometry and every other net are
# left byte-for-byte alone. Each variant is centred on its OWN probed trip
# point. DIAGNOSTIC ONLY: a passing point is not PVT closure and not proof
# that a layout can realize the budget; no spec row is scored.

BUDGET_ISSUE = 243

#: Starting set: the four nets #229 found to carry ~71 % of the gap
#: (verified against attribution.json: sum of mean shares 0.7099).
BUDGET_NETS = ("sn", "doutb", "qn", "dout")

#: Stage 1 retained-C fractions (1.0 is the unchanged extracted control).
BUDGET_FRACTIONS = (0.75, 0.5, 0.25, 0.0)


def validate_fraction(f) -> float:
    """A retained-C factor must be a finite real number in [0, 1]. Anything
    else (negative, >1, NaN, inf, bool, non-number) is refused: this study is
    a bounded reduction sweep, never an increase and never an extrapolation."""
    if isinstance(f, bool) or not isinstance(f, (int, float)):
        raise ValueError(f"retained-C factor must be a real number, got {f!r}")
    f = float(f)
    if not (f == f) or f in (float("inf"), float("-inf")) or f < 0.0 or f > 1.0:
        raise ValueError(f"retained-C factor must be finite and within [0, 1], got {f!r}")
    return f


def scale_cg(text: str, nets, factor) -> str:
    """Multiply the ground-C card of each net in `nets` by `factor`; touch
    nothing else. factor == 1.0 returns `text` unchanged (byte-identical);
    factor == 0.0 drops the cards exactly like `drop_cg` (the #229 endpoint)."""
    factor = validate_fraction(factor)
    nets = set(nets)
    if not nets:
        raise ValueError("no nets to scale")
    have = set(parse(text)["cg"])
    unknown = sorted(nets - have)
    if unknown:
        raise ValueError(f"nets with no ground-C card: {unknown}")
    if factor == 1.0:
        return text
    if factor == 0.0:
        return drop_cg(text, nets)
    out = []
    for line in text.splitlines():
        m = _CG_RE.match(line)
        if m and m["net"] in nets:
            line = f"C{m['net']} {m['net']} vsubs {si(m['val']) * factor:.9g}"
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def fraction_id(f: float) -> str:
    return f"cgs-{round(validate_fraction(f) * 1000):04d}"


def retained_ff(text: str, nets) -> dict[str, float]:
    """Actual per-net ground C (fF) present in a variant netlist."""
    cg = parse(text)["cg"]
    return {n: cg.get(n, 0.0) * 1e15 for n in nets}


def budget_variants(text: str, fractions, nets=BUDGET_NETS) -> list[dict]:
    """ctrl (== factor 1.0, byte-identical), the scaled variants, and the
    schematic control. Duplicate or out-of-range factors are refused."""
    fr = [validate_fraction(f) for f in fractions]
    if len(set(fr)) != len(fr):
        raise ValueError(f"duplicate factors: {fractions}")
    if 1.0 in fr:
        raise ValueError("1.0 is the unchanged control `ctrl`; do not list it")
    v = [{"id": "ctrl", "side": "extracted", "centre": "probed", "group": "control",
          "fraction": 1.0, "dut": text, "removes": "nothing (cited extracted DUT)"}]
    for f in fr:
        v.append({"id": fraction_id(f), "side": "extracted", "centre": "probed",
                  "group": "scaled", "fraction": f, "dut": scale_cg(text, nets, f),
                  "removes": f"ground C of {'+'.join(nets)} scaled to {f:g} of extracted"})
    v.append({"id": "sch", "side": "schematic", "centre": "zero", "group": "control",
              "fraction": None, "dut": SCHEMATIC_DUT.read_text(),
              "removes": "schematic leg as cited (ladder at 0 V)"})
    return v


_CID_RE = re.compile(r"^(?P<p>[a-z]+)_(?P<t>-?[0-9.]+)c_(?P<v>[0-9.]+)v$")


def parse_corner_id(cid: str) -> tuple[str, float, float]:
    m = _CID_RE.match(cid)
    if not m:
        raise ValueError(f"unparseable corner id {cid!r}")
    return m["p"], float(m["t"]), float(m["v"])


def failing_points() -> list[tuple[str, float, float]]:
    """The cited report's td_od50_ns delta rows over 1.5 ns (expected: 7)."""
    rep = json.loads(CITED_REPORT.read_text())
    pts = [parse_corner_id(r["corner_id"]) for r in rep["delta"]
           if r["spec_row"] == "td_od50_ns" and r["extracted_value"] > pm.SPEC_TD_OD50_NS_MAX]
    return sorted(pts)


def budget_points(which: str) -> list[tuple[str, float, float]]:
    if which == "two":
        return [(p, TEMP_C, VDD_V) for p in PROCESSES]
    if which == "seven":
        pts = failing_points()
        if len(pts) != 7:
            raise ValueError(f"expected 7 failing delay corners in the cited report, found {len(pts)}")
        return pts
    raise ValueError(which)


def pid(pt) -> str:
    return pm.corner_id(*pt)


def _narrow_to(req: dict, temp_c: float, vdd: float) -> dict:
    req["corners"]["temperature_c"] = [temp_c]
    req["corners"]["supply_v"] = {k: [vdd] for k in req["corners"]["supply_v"]}
    return req


def tv_groups(points) -> dict[tuple[float, float], list[str]]:
    g: dict[tuple[float, float], list[str]] = {}
    for p, t, v in points:
        g.setdefault((t, v), []).append(p)
    return g


def tv_tag(t: float, v: float) -> str:
    return f"{t:g}c_{v:.2f}v"


def budget_probe_request(tag: str, processes, t: float, v: float) -> dict:
    return _narrow_to(pm._request(f"{tag}.spice", list(processes), pm.PROBE_MEAS,
                                  "100n 80u 0 100n", pm.TIMEOUT_PROBE_S, ["vsup"]), t, v)


def budget_ladder_request(tag: str, pt) -> dict:
    p, t, v = pt
    return _narrow_to(pm._request(f"{tag}.spice", [p], pm.MAIN_MEAS, "5p 60n",
                                  pm.TIMEOUT_MAIN_S, ["vsup", "vsupa"]), t, v)


def budget_ladder_deck(dut: str, side: str, process: str, centre: str,
                       vos_at: dict[tuple[float, float], float | None]) -> str:
    """The cited ladder deck; the (T, V) points in `vos_at` carry this
    variant's centring (probed trip point, or 0 V), every other point keeps
    the cited value. For the two #229 points this is `ladder_deck` exactly."""
    keys = [(t, v) for t in pm.TEMPERATURES_C for v in pm.SUPPLIES_V]
    if side == "extracted":
        base = cited_vos("extracted")
        table = {k: base[(process, *k)] for k in keys}
    else:
        table = {k: 0.0 for k in keys}
    for k, x in vos_at.items():
        if centre == "zero":
            table[k] = 0.0
        else:
            if x is None:
                raise ValueError("probed centring needs a probed trip point")
            table[k] = x
    return pm._flatten(dut, pm._main_body(), [pm._vos_source(table)])


def _trip_from_probe(rep: dict) -> dict[tuple[str, float, float], float | None]:
    out = {}
    for c in rep["corners"]:
        t = pm._values(c).get("t_flip")
        out[pm._point_key(c)] = (None if t is None else
                                 -pm.PROBE_VSPAN + 2 * pm.PROBE_VSPAN * t / pm.PROBE_TRAMP)
    return out


def _probe_tag(t, v):
    return f"probe-{tv_tag(t, v)}"


def run_budget_variant(v: dict, outdir: Path, backend: str, points) -> dict:
    vdir = outdir / v["id"]
    vdir.mkdir(parents=True, exist_ok=True)
    log = {"id": v["id"], "jobs": {}}
    trips: dict[tuple[str, float, float], float | None] = {}
    if v["centre"] == "probed":
        for (t, vv), procs in tv_groups(points).items():
            tag = _probe_tag(t, vv)
            r = submit(vdir, tag, probe_deck(v["dut"]), budget_probe_request(tag, procs, t, vv),
                       backend)
            log["jobs"][tag] = {k: r[k] for k in ("ok", "rc", "stderr", "attempts") if k in r}
            if r["ok"]:
                trips.update(_trip_from_probe(r["report"]))
        if any(not j.get("ok") for j in log["jobs"].values()):
            return log
    for pt in points:
        tag = f"ladder-{pid(pt)}"
        if v["centre"] == "probed" and trips.get(pt) is None:
            log["jobs"][tag] = {"ok": False, "stderr": "probe found no trip point"}
            continue
        vos_at = {(t, vv): trips.get((p, t, vv)) for (p, t, vv) in points if p == pt[0]}
        deck = budget_ladder_deck(v["dut"], v["side"], pt[0], v["centre"], vos_at)
        r = submit(vdir, tag, deck, budget_ladder_request(tag, pt), backend)
        log["jobs"][tag] = {k: r[k] for k in ("ok", "rc", "stderr", "attempts") if k in r}
    return log


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def budget_manifest(text: str, plan: list[dict], points, nets) -> dict:
    """Everything the stage depends on, hashed, plus the variant manifest."""
    return {
        "issue": BUDGET_ISSUE,
        "generated_by": "layout/pex/parasitic_attribution.py budget-run",
        "scope": ("diagnostic only: joint ground-C scaling of " + ", ".join(nets)
                  + "; series R, coupling C, device geometry fixed; each variant centred on its "
                    "own probed trip point; no spec row scored, T1 item 7 unchanged"),
        "nets": list(nets),
        "points": [pid(p) for p in points],
        "source_sha256": {
            "extracted_dut": sha(text),
            "schematic_dut": file_sha(SCHEMATIC_DUT),
            "cited_report": file_sha(CITED_REPORT),
            "attribution_json_229": file_sha(
                HERE / "artifacts" / "parasitic-attribution" / "20261010-120720-230574b"
                / "attribution.json"),
            "tb_json_consumed_fields": TB_JSON_CONSUMED_SHA256,
            "pex_measure_py": file_sha(HERE / "pex_measure.py"),
            "parasitic_attribution_py": file_sha(Path(__file__).resolve()),
        },
        "variants": [{
            "id": x["id"], "side": x["side"], "centre": x["centre"], "fraction": x["fraction"],
            "dut_sha256": sha(x["dut"]), "probe_deck_sha256": sha(probe_deck(x["dut"])),
            "retained_ground_c_ff": retained_ff(x["dut"], nets) if x["side"] == "extracted" else None,
        } for x in plan],
    }


def _budget_args(args):
    nets = tuple(args.nets.split(",")) if args.nets else BUDGET_NETS
    fractions = [float(x) for x in args.fractions.split(",")] if args.fractions else \
        list(BUDGET_FRACTIONS)
    return nets, fractions


def cmd_budget_run(args) -> int:
    check_bench()
    text = load_extracted()
    nets, fractions = _budget_args(args)
    plan = budget_variants(text, fractions, nets)
    points = budget_points(args.points)
    if args.backend == "local" and (len(plan) * len(points) != 1):
        sys.exit("--backend local is a single-request debug probe only")
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    man = budget_manifest(text, plan, points, nets)
    return run_stage(outdir, man, plan, points, args.backend, args.jobs, BUDGET_ISSUE)


def run_stage(outdir: Path, man: dict, plan: list[dict], points, backend: str, jobs: int,
              issue: int) -> int:
    """Write (or check, append-only) stage.json, submit every request of the
    plan, write run-log.json."""
    mpath = outdir / "stage.json"
    if mpath.exists():
        # append-only: a stage directory is never re-planned; resuming is fine
        # only for the identical plan (ignoring the script's own hash).
        old = json.loads(mpath.read_text())
        a, b = json.loads(json.dumps(man)), old
        for d in (a, b):
            d["source_sha256"].pop("parasitic_attribution_py", None)
        if a != b:
            sys.exit(f"{mpath} exists with a different plan; stage directories are append-only")
    else:
        mpath.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    client = pm._klt_identity()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        logs = list(pool.map(lambda x: run_budget_variant(x, outdir, backend, points), plan))
    failed = [(l["id"], t) for l in logs for t, j in l["jobs"].items() if not j.get("ok")]
    (outdir / "run-log.json").write_text(json.dumps({
        "issue": issue, "backend": backend, "klt_sim_client": client,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "variants": [l["id"] for l in logs], "failed_jobs": failed,
        "job_errors": {f"{l['id']}/{t}": j.get("stderr") for l in logs
                       for t, j in l["jobs"].items() if not j.get("ok")},
    }, indent=2, sort_keys=True) + "\n")
    print(f"{len(logs)} variants, {len(failed)} failed jobs -> {outdir}")
    for vid, tag in failed:
        print(f"  FAILED {vid}/{tag}")
    return 1 if failed else 0


def cmd_budget_plan(args) -> int:
    text = load_extracted()
    nets, fractions = _budget_args(args)
    points = budget_points(args.points)
    print("points:", ", ".join(pid(p) for p in points))
    for x in budget_variants(text, fractions, nets):
        rf = retained_ff(x["dut"], nets) if x["side"] == "extracted" else {}
        print(f"{x['id']:<10} f={x['fraction']} " + " ".join(f"{n}={c:.3f}fF" for n, c in rf.items()))
    return 0


def _budget_values(vdir: Path, points) -> dict:
    out = {}
    probes = {}
    probe_jobs: set[str] = set()
    for f in sorted(vdir.glob("probe-*.report.json")):
        if f.read_text().strip():
            prep = json.loads(f.read_text())
            probes.update(_trip_from_probe(prep))
            probe_jobs.add(((prep.get("environment") or {}).get("remote") or {}).get("job_id"))
    for pt in points:
        path = vdir / f"ladder-{pid(pt)}.report.json"
        if not path.exists() or not path.read_text().strip():
            continue
        rep = json.loads(path.read_text())
        (corner,) = [c for c in rep["corners"] if c["process"] == pt[0]]
        d = pm._derive(pm._values(corner))
        d["dut_vos_v"] = probes.get(pt)
        d["job_ids"] = sorted({(rep.get("environment") or {}).get("remote", {}).get("job_id")}
                              - {None})
        d["probe_job_ids"] = sorted(probe_jobs - {None})
        d["ladder_netlist_sha256"] = rep["environment"]["netlist_sha256"]
        out[pt] = d
    return out


def _plan_from_manifest(man: dict, text: str) -> list[dict]:
    fr = [x["fraction"] for x in man["variants"] if x["id"] not in ("ctrl", "sch")]
    return budget_variants(text, fr, man["nets"])


def stage_controls(res: dict, points) -> tuple[dict, bool]:
    """`ctrl` / `sch` rerun vs the cited report at every stage point. The
    study is valid only if every control decision time reproduces within
    CONTROL_TOL_NS."""
    cited = {(r["corner_id"], r["spec_row"]): r
             for r in json.loads(CITED_REPORT.read_text())["delta"]}
    controls = {}
    for pt in points:
        cid = pid(pt)
        for vid, key in (("ctrl", "extracted_value"), ("sch", "schematic_value")):
            want = cited[(cid, "td_od50_ns")][key]
            got = res.get(vid, {}).get(pt, {}).get("td_od50_ns")
            controls[f"{vid}@{cid}"] = {
                "cited_td_od50_ns": want, "rerun_td_od50_ns": got,
                "abs_diff_ns": None if got is None else abs(got - want),
                "reproduces": got is not None and abs(got - want) <= CONTROL_TOL_NS}
        want_vos = cited[(cid, "dut_vos_v")]["extracted_value"]
        controls[f"ctrl@{cid}"]["cited_dut_vos_v"] = want_vos
        controls[f"ctrl@{cid}"]["rerun_dut_vos_v"] = res.get("ctrl", {}).get(pt, {}).get("dut_vos_v")
    valid = bool(controls) and all(c["reproduces"] for c in controls.values())
    return controls, valid


def budget_analyze(outdir: Path) -> dict:
    man = json.loads((outdir / "stage.json").read_text())
    text = load_extracted()
    points = [parse_corner_id(c) for c in man["points"]]
    nets = man["nets"]
    plan = {x["id"]: x for x in _plan_from_manifest(man, text)}
    res = {vid: _budget_values(outdir / vid, points) for vid in plan if (outdir / vid).is_dir()}
    missing = [(vid, pid(p)) for vid in plan for p in points if p not in res.get(vid, {})]

    controls, valid = stage_controls(res, points)

    rows = []
    for vid, x in plan.items():
        if vid == "sch":
            continue
        row = {"id": vid, "fraction": x["fraction"],
               "retained_ground_c_ff": retained_ff(x["dut"], nets), "corners": {}}
        for pt in points:
            r, c = res.get(vid, {}).get(pt), res.get("ctrl", {}).get(pt)
            if not r or r["td_od50_ns"] is None:
                row["corners"][pid(pt)] = {"td_od50_ns": None, "unresolved": True,
                                           "job_ids": (r or {}).get("job_ids")}
                continue
            row["corners"][pid(pt)] = {
                "td_od50_ns": r["td_od50_ns"], "td_od1_ns": r["td_od1_ns"],
                "td_od01_ns": r["td_od01_ns"], "tau_ps": r["tau_ps"],
                "dout_od50_end": r["dout_od50_end"],
                "unresolved": any(r[k] is None for k in ("td_od50_ns", "td_od1_ns", "td_od01_ns")),
                "dut_vos_v": r["dut_vos_v"],
                "dut_vos_shift_v": (None if not c or None in (r["dut_vos_v"], c["dut_vos_v"])
                                    else r["dut_vos_v"] - c["dut_vos_v"]),
                "margin_to_1p5ns_ns": pm.SPEC_TD_OD50_NS_MAX - r["td_od50_ns"],
                "meets_1p5ns": r["td_od50_ns"] <= pm.SPEC_TD_OD50_NS_MAX,
                "job_ids": r["job_ids"], "probe_job_ids": r["probe_job_ids"],
                "ladder_netlist_sha256": r["ladder_netlist_sha256"]}
        rows.append(row)
    rows.sort(key=lambda r: -r["fraction"])

    # Outcome. Only TESTED points are evidence: no interpolation between
    # fractions, no monotonicity assumption. Adjacent tested fractions where
    # a corner flips from failing to meeting are reported as brackets.
    cids = [pid(p) for p in points]

    def ok(row, cid):
        x = row["corners"].get(cid)
        return bool(x and x["td_od50_ns"] is not None and x["meets_1p5ns"])
    all_pass = [r["fraction"] for r in rows if all(ok(r, c) for c in cids)]
    brackets, nonmono = {}, {}
    for cid in cids:
        seq = [(r["fraction"], r["corners"].get(cid)) for r in rows]
        seq = [(f, x["td_od50_ns"]) for f, x in seq if x and x["td_od50_ns"] is not None]
        brackets[cid] = [{"fails_at": a[0], "meets_at": b[0]}
                         for a, b in zip(seq, seq[1:])
                         if a[1] > pm.SPEC_TD_OD50_NS_MAX >= b[1]]
        nonmono[cid] = any(b[1] > a[1] for a, b in zip(seq, seq[1:]))
    finite = [f for f in all_pass if f > 0.0]
    if not valid:
        outcome = "refused: controls do not reproduce the cited decision times or are missing"
    elif finite:
        outcome = (f"largest tested finite fraction meeting 1.5 ns at every stage point: "
                   f"{max(finite):g} (tested points only; not a minimum, not an extrapolation)")
    else:
        tested = ", ".join(f"{r['fraction']:g}" for r in rows if r["id"] != "ctrl")
        if 0.0 in all_pass:
            outcome = ("no finite tested fraction clears the bound at every stage point; "
                       f"only zero ground C does (tested: {tested})")
        else:
            outcome = ("no-crossing: no tested fraction clears the bound at every stage point "
                       f"(tested: {tested})")
    return {
        "issue": BUDGET_ISSUE, "generated_by": "layout/pex/parasitic_attribution.py budget-analyze",
        "scope": man["scope"], "nets": nets, "points": cids,
        "source_sha256": man["source_sha256"],
        "controls": controls, "study_valid": valid, "missing": missing,
        "outcome": outcome, "fractions_meeting_all_points": all_pass,
        "brackets_per_corner": brackets, "non_monotonic_per_corner": nonmono,
        "variants": rows,
    }


def budget_table_md(a: dict) -> str:
    cids = a["points"]
    head = ("| variant | retained C fF (" + ", ".join(a["nets"]) + ") | "
            + " | ".join(f"{c}: td_od50 ns / margin ns / vos shift mV" for c in cids) + " |")
    lines = [head, "|---|---|" + "---|" * len(cids)]
    for r in a["variants"]:
        ff = ", ".join(f"{r['retained_ground_c_ff'][n]:.2f}" for n in a["nets"])
        cells = []
        for c in cids:
            x = r["corners"].get(c)
            if not x or x["td_od50_ns"] is None:
                cells.append("UNRESOLVED")
                continue
            sh = x["dut_vos_shift_v"]
            cells.append(f"{x['td_od50_ns']:.4f} / {x['margin_to_1p5ns_ns']:+.4f} / "
                         + ("n/a" if sh is None else f"{sh * 1e3:+.2f}")
                         + (" PASS" if x["meets_1p5ns"] else " fail")
                         + (" (rung unresolved)" if x["unresolved"] else ""))
        lines.append(f"| `{r['id']}` (f={r['fraction']:g}) | {ff} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def cmd_budget_analyze(args) -> int:
    outdir = Path(args.outdir).resolve()
    a = budget_analyze(outdir)
    (outdir / "budget.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
    (outdir / "budget-table.md").write_text(
        "<!-- GENERATED by layout/pex/parasitic_attribution.py budget-analyze -- do not edit -->\n"
        + budget_table_md(a))
    print(f"study_valid={a['study_valid']} missing={len(a['missing'])}\n{a['outcome']}")
    return 0 if a["study_valid"] and not a["missing"] else 1


#: stage.json `source_sha256` keys that record the CODE the stage ran with.
#: They are provenance: verifying committed evidence must not require the
#: working tree's source to still hash the same (any later, unrelated edit to
#: pex_measure.py would otherwise break every committed stage -- the #249
#: failure). Drift is reported, never an error. The integrity gates are the
#: data-input hashes below, the regenerated deck sha256s vs. each report's
#: netlist_sha256, and the control / study_valid derivation of budget.json.
BUDGET_PROVENANCE_SOURCE_KEYS = ("parasitic_attribution_py", "pex_measure_py",
                                 "tb_json_consumed_fields")
#: Narrative manifest fields written from code constants; provenance as well.
BUDGET_PROVENANCE_FIELDS = ("generated_by", "scope")


def budget_manifest_diff(committed: dict, regenerated: dict) -> tuple[list[str], list[str]]:
    """Compare a committed stage.json with the regenerated manifest.

    Returns (errors, drift). Errors: anything that defines the plan or its
    data inputs (issue, nets, points, variants with their DUT / probe-deck /
    retained-C values, and the extracted / schematic DUT, cited report and
    #229 attribution hashes). Drift: provenance keys whose working-tree value
    differs from the recorded one -- informational only."""
    a = json.loads(json.dumps(committed))
    b = json.loads(json.dumps(regenerated))
    drift = []
    for k in BUDGET_PROVENANCE_SOURCE_KEYS:
        x = a.get("source_sha256", {}).pop(k, None)
        y = b.get("source_sha256", {}).pop(k, None)
        if x != y:
            drift.append(f"source_sha256.{k}: recorded {x}, working tree {y}")
    for k in BUDGET_PROVENANCE_FIELDS:
        x, y = a.pop(k, None), b.pop(k, None)
        if x != y:
            drift.append(f"{k}: recorded text differs from the current code's")
    errors = []
    for k in sorted(set(a) | set(b)):
        if k == "source_sha256":
            sa, sb = a.get(k, {}), b.get(k, {})
            for s in sorted(set(sa) | set(sb)):
                if sa.get(s) != sb.get(s):
                    errors.append(f"stage.json source_sha256.{s} differs from the regenerated "
                                  f"manifest ({sa.get(s)} vs {sb.get(s)})")
        elif a.get(k) != b.get(k):
            errors.append(f"stage.json {k} differs from the regenerated manifest")
    return errors, drift


def cmd_budget_verify(args) -> int:
    """PDK-free: stage.json's plan and data-input hashes are what the code
    regenerates (source-code hashes are recorded provenance; drift is only
    reported), every report ran the deck regenerated here, and budget.json is
    what `budget-analyze` derives."""
    outdir = Path(args.outdir).resolve()
    check_bench()
    text = load_extracted()
    man = json.loads((outdir / "stage.json").read_text())
    points = [parse_corner_id(c) for c in man["points"]]
    plan = _plan_from_manifest(man, text)
    errors, drift = budget_manifest_diff(
        man, budget_manifest(text, plan, points, man["nets"]))
    for d in drift:
        print(f"NOTE provenance drift (not an error): {d}")
    errors += verify_stage_reports(outdir, plan, points)
    committed = outdir / "budget.json"
    if not committed.exists():
        errors.append("budget.json missing")
    elif json.loads(committed.read_text()) != json.loads(json.dumps(budget_analyze(outdir))):
        errors.append("budget.json is not what `budget-analyze` derives from the reports")
    for e in errors:
        print(f"FAIL {e}")
    print(f"budget-verify: {len(errors)} error(s)")
    return 1 if errors else 0


def verify_stage_reports(outdir: Path, plan: list[dict], points) -> list[str]:
    """Every probe / ladder report of the plan ran the deck regenerated here
    from the committed inputs, from the request generated here."""
    errors = []
    for v in plan:
        vdir = outdir / v["id"]
        if not vdir.is_dir():
            errors.append(f"{v['id']}: no evidence directory")
            continue
        vals = _budget_values(vdir, points)
        if v["centre"] == "probed":
            for (t, vv), procs in tv_groups(points).items():
                tag = _probe_tag(t, vv)
                rp = vdir / f"{tag}.report.json"
                if not rp.exists():
                    errors.append(f"{v['id']}/{tag}: no report")
                    continue
                if json.loads(rp.read_text())["environment"]["netlist_sha256"] != \
                        sha(probe_deck(v["dut"])):
                    errors.append(f"{v['id']}/{tag}: report ran a different deck")
                if json.loads((vdir / f"{tag}.request.json").read_text()) != \
                        budget_probe_request(tag, procs, t, vv):
                    errors.append(f"{v['id']}/{tag}: request differs from the generated one")
        for pt in points:
            tag = f"ladder-{pid(pt)}"
            if pt not in vals:
                errors.append(f"{v['id']}/{tag}: no report")
                continue
            vos_at = {(t, vv): vals.get((p, t, vv), {}).get("dut_vos_v")
                      for (p, t, vv) in points if p == pt[0]}
            deck = budget_ladder_deck(v["dut"], v["side"], pt[0], v["centre"], vos_at)
            if vals[pt]["ladder_netlist_sha256"] != sha(deck):
                errors.append(f"{v['id']}/{tag}: report ran a different deck")
            if json.loads((vdir / f"{tag}.request.json").read_text()) != \
                    budget_ladder_request(tag, pt):
                errors.append(f"{v['id']}/{tag}: request differs from the generated one")
    return errors


# --------------------------------------------------------------------------- #
# Combined finite ground-C x series-R budget (issue #264)
# --------------------------------------------------------------------------- #
#
# #243 found no finite four-net ground-C budget that clears ss_125c_2.97v and
# said another lever must be combined with it. #264 scales, jointly, ALL
# extracted ground-C cards (`C<net> <net> vsubs`, every net incl. rails) by
# f_c and ALL series-R leg cards (`R<net>_t<k> <net>__t<k> <net>`) by f_r,
# both finite and in (0, 1]. Coupling C, device geometry and the vsubs DC tie
# are left byte-for-byte alone. Each variant is centred on its OWN probed trip
# point. Interaction is MEASURED per cell, never summed from single-lever
# shares. DIAGNOSTIC ONLY: a passing cell is not PVT closure, not proof a
# layout can realize it, and scores no spec row; T1 item 7 is unchanged.

COMBO_ISSUE = 264
COMBO_C_FRACTIONS = (0.75, 0.5, 0.25)
COMBO_R_FRACTIONS = (1.0, 0.5)

#: Declared fleet request budget (issue #264 curator section). A stage's
#: planned request count must fit its kind's cap, and the sum of every stage
#: planned under one artifact directory must fit the hard total cap.
COMBO_STAGE_CAPS = {"grid": 23, "refine": 12, "seven": 29}
COMBO_TOTAL_CAP = 64
#: A refinement stage adds at most this many cells, along ONE axis.
COMBO_REFINE_MAX_CELLS = 4


def validate_positive_fraction(f, what: str = "retained") -> float:
    """A combined-study factor: a finite real number in (0, 1]. Zero is
    refused (positive retained C and R is a requirement of #264), as are
    negative, >1, NaN, inf, bool and non-numbers."""
    if isinstance(f, bool) or not isinstance(f, (int, float)):
        raise ValueError(f"{what} factor must be a real number, got {f!r}")
    f = float(f)
    if not (f == f) or f in (float("inf"), float("-inf")) or f <= 0.0 or f > 1.0:
        raise ValueError(f"{what} factor must be finite and within (0, 1], got {f!r}")
    return f


def scale_r(text: str, nets, factor) -> str:
    """Multiply every series-R leg card of each net in `nets` by `factor`;
    touch nothing else (the `Rvsubs_dctie` tie is not a leg card). factor ==
    1.0 returns `text` unchanged (the same object)."""
    factor = validate_positive_fraction(factor, "series-R")
    nets = set(nets)
    if not nets:
        raise ValueError("no nets to scale")
    unknown = sorted(nets - set(parse(text)["legs"]))
    if unknown:
        raise ValueError(f"nets with no series-R leg card: {unknown}")
    if factor == 1.0:
        return text
    out = []
    for line in text.splitlines():
        m = _LEG_RE.match(line)
        if m and m["net"] in nets:
            n, k = m["net"], m["k"]
            line = f"R{n}_t{k} {n}__t{k} {n} {si(m['val']) * factor:.12g}"
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def scale_cg_r(text: str, fc, fr) -> str:
    """Every ground-C card scaled by fc and every series-R leg by fr (both in
    (0, 1]). The two edits touch disjoint cards, so the order is immaterial
    (unit-tested)."""
    fc = validate_positive_fraction(fc, "ground-C")
    fr = validate_positive_fraction(fr, "series-R")
    p = parse(text)
    return scale_r(scale_cg(text, set(p["cg"]), fc), set(p["legs"]), fr)


def combo_id(fc, fr) -> str:
    return (f"cgr-{round(validate_positive_fraction(fc, 'ground-C') * 1000):04d}"
            f"-{round(validate_positive_fraction(fr, 'series-R') * 1000):04d}")


def retained_r_ohm(text: str, nets=None) -> dict[str, float]:
    """Actual per-net series-R leg sum (ohm) present in a variant netlist."""
    legs = parse(text)["legs"]
    return {n: sum(v for _, v in legs.get(n, [])) for n in (nets or sorted(legs))}


def combo_cells(c_fractions=COMBO_C_FRACTIONS, r_fractions=COMBO_R_FRACTIONS) -> list:
    return [(c, r) for r in r_fractions for c in c_fractions]


def combo_variants(text: str, cells) -> list[dict]:
    """ctrl (== (1.0, 1.0), byte-identical), one variant per (f_c, f_r)
    cell, and the schematic control. Invalid factors, duplicate cells or ids,
    an empty grid and the (1.0, 1.0) cell are refused."""
    cl = [(validate_positive_fraction(c, "ground-C"), validate_positive_fraction(r, "series-R"))
          for c, r in cells]
    if not cl:
        raise ValueError("empty cell grid")
    if len(set(cl)) != len(cl):
        raise ValueError(f"duplicate cells: {cells}")
    if (1.0, 1.0) in cl:
        raise ValueError("(1.0, 1.0) is the unchanged control `ctrl`; do not list it")
    ids = [combo_id(c, r) for c, r in cl]
    if len(set(ids)) != len(ids):
        raise ValueError(f"cells collide at the id's thousandths resolution: {ids}")
    v = [{"id": "ctrl", "side": "extracted", "centre": "probed", "group": "control",
          "fraction_c": 1.0, "fraction_r": 1.0, "dut": text,
          "removes": "nothing (cited extracted DUT)"}]
    for (c, r), vid in zip(cl, ids):
        v.append({"id": vid, "side": "extracted", "centre": "probed", "group": "scaled",
                  "fraction_c": c, "fraction_r": r, "dut": scale_cg_r(text, c, r),
                  "removes": f"all ground C x {c:g}, all series R x {r:g}"})
    v.append({"id": "sch", "side": "schematic", "centre": "zero", "group": "control",
              "fraction_c": None, "fraction_r": None, "dut": SCHEMATIC_DUT.read_text(),
              "removes": "schematic leg as cited (ladder at 0 V)"})
    return v


def count_requests(plan: list[dict], points) -> int:
    """`klt sim` requests a stage submits: one probe per (T, V) group for a
    probed variant, one ladder per point for every variant."""
    groups = len(tv_groups(points))
    return sum((groups if v["centre"] == "probed" else 0) + len(points) for v in plan)


def one_axis(cells) -> bool:
    """True if the cells vary along one axis only (all share f_r, or all f_c)."""
    return len({r for _, r in cells}) <= 1 or len({c for c, _ in cells}) <= 1


def combo_manifest(text: str, plan: list[dict], points, kind: str,
                   controls_from: str | None = None) -> dict:
    p = parse(text)
    cg_nets, leg_nets = sorted(p["cg"]), sorted(p["legs"])
    man = {
        "issue": COMBO_ISSUE,
        "generated_by": "layout/pex/parasitic_attribution.py combo-run",
        "scope": ("diagnostic only: every extracted ground-C card x f_c and every series-R leg "
                  "card x f_r, f_c and f_r in (0, 1]; coupling C, device geometry and the vsubs "
                  "tie fixed; each variant centred on its own probed trip point; no spec row "
                  "scored, T1 item 7 unchanged"),
        "kind": kind,
        "controls_from": controls_from,
        "cg_nets": cg_nets, "leg_nets": leg_nets,
        "points": [pid(x) for x in points],
        "requests_planned": count_requests(plan, points),
        "source_sha256": {
            "extracted_dut": sha(text),
            "schematic_dut": file_sha(SCHEMATIC_DUT),
            "cited_report": file_sha(CITED_REPORT),
            "attribution_json_229": file_sha(
                HERE / "artifacts" / "parasitic-attribution" / "20261010-120720-230574b"
                / "attribution.json"),
            "ground_c_budget_243_readme": file_sha(
                HERE / "artifacts" / "ground-c-budget" / "20261010-154019-b9fff0f" / "README.md"),
            "tb_json_consumed_fields": TB_JSON_CONSUMED_SHA256,
            "pex_measure_py": file_sha(HERE / "pex_measure.py"),
            "parasitic_attribution_py": file_sha(Path(__file__).resolve()),
        },
        "variants": [],
    }
    for x in plan:
        e = {"id": x["id"], "side": x["side"], "centre": x["centre"],
             "fraction_c": x["fraction_c"], "fraction_r": x["fraction_r"],
             "dut_sha256": sha(x["dut"]), "probe_deck_sha256": sha(probe_deck(x["dut"]))}
        if x["side"] == "extracted":
            cf, rr = retained_ff(x["dut"], cg_nets), retained_r_ohm(x["dut"], leg_nets)
            e.update({"retained_ground_c_ff": cf, "retained_series_r_ohm": rr,
                      "total_ground_c_ff": sum(cf.values()),
                      "total_series_r_ohm": sum(rr.values())})
        man["variants"].append(e)
    return man


def _combo_plan_from_manifest(man: dict, text: str) -> list[dict]:
    cells = [(x["fraction_c"], x["fraction_r"]) for x in man["variants"]
             if x["id"] not in ("ctrl", "sch")]
    plan = combo_variants(text, cells)
    have = {x["id"] for x in man["variants"]}
    return [v for v in plan if v["id"] in have]


def _combo_args(args) -> list:
    if args.cells:
        cells = []
        for tok in args.cells.split(","):
            c, _, r = tok.partition(":")
            try:
                cells.append((float(c), float(r)))
            except ValueError:
                sys.exit(f"--cells entry {tok!r} is not f_c:f_r")
        return cells
    return combo_cells()


def combo_stage_plan(text: str, cells, kind: str, controls_from: str | None):
    """The variant plan of one stage kind, with the stage-kind rules:
    grid / seven rerun both controls; a refinement adds at most
    COMBO_REFINE_MAX_CELLS cells along one axis and takes its controls from
    an earlier stage (`controls_from`)."""
    plan = combo_variants(text, cells)
    if kind == "refine":
        if not controls_from:
            raise ValueError("a refine stage needs --controls-from <earlier stage dir>")
        if len(cells) > COMBO_REFINE_MAX_CELLS or not one_axis(cells):
            raise ValueError(f"a refine stage adds at most {COMBO_REFINE_MAX_CELLS} cells "
                             "along one axis")
        plan = [v for v in plan if v["group"] == "scaled"]
    elif controls_from:
        raise ValueError("--controls-from is only for a refine stage")
    if kind == "seven" and len(cells) != 1:
        raise ValueError("the seven-corner check runs exactly one candidate cell")
    return plan


def check_request_budget(outdir: Path, kind: str, planned: int) -> None:
    """Refuse a stage over its kind's cap, or one that would push the sum of
    planned requests of every stage in the artifact directory over the hard
    total cap."""
    if planned > COMBO_STAGE_CAPS[kind]:
        raise ValueError(f"{kind} stage plans {planned} requests > cap {COMBO_STAGE_CAPS[kind]}")
    others = 0
    for st in sorted(outdir.parent.glob("*/stage.json")):
        if st.parent.resolve() == outdir.resolve():
            continue
        others += json.loads(st.read_text()).get("requests_planned", 0)
    if others + planned > COMBO_TOTAL_CAP:
        raise ValueError(f"{others} requests already planned in {outdir.parent} + {planned} "
                         f"> total cap {COMBO_TOTAL_CAP}")


def _combo_points(kind: str):
    return budget_points("seven" if kind == "seven" else "two")


def cmd_combo_plan(args) -> int:
    text = load_extracted()
    points = _combo_points(args.kind)
    plan = combo_stage_plan(text, _combo_args(args), args.kind, args.controls_from)
    print(f"kind={args.kind} points: " + ", ".join(pid(p) for p in points))
    print(f"requests planned: {count_requests(plan, points)} "
          f"(stage cap {COMBO_STAGE_CAPS[args.kind]}, total cap {COMBO_TOTAL_CAP})")
    for x in plan:
        if x["side"] != "extracted":
            print(f"{x['id']:<15} schematic")
            continue
        c = sum(retained_ff(x["dut"], sorted(parse(text)["cg"])).values())
        r = sum(retained_r_ohm(x["dut"]).values())
        print(f"{x['id']:<15} f_c={x['fraction_c']:g} f_r={x['fraction_r']:g} "
              f"total ground C {c:.2f} fF, total leg R {r:.1f} ohm")
    return 0


def cmd_combo_run(args) -> int:
    check_bench()
    text = load_extracted()
    points = _combo_points(args.kind)
    outdir = Path(args.outdir).resolve()
    try:
        plan = combo_stage_plan(text, _combo_args(args), args.kind, args.controls_from)
        planned = count_requests(plan, points)
        check_request_budget(outdir, args.kind, planned)
    except ValueError as e:
        sys.exit(str(e))
    if args.backend == "local" and planned != 1:
        sys.exit("--backend local is a single-request debug probe only")
    outdir.mkdir(parents=True, exist_ok=True)
    man = combo_manifest(text, plan, points, args.kind, args.controls_from)
    return run_stage(outdir, man, plan, points, args.backend, args.jobs, COMBO_ISSUE)


def _ok(x) -> bool:
    return bool(x and x.get("td_od50_ns") is not None and x["meets_1p5ns"])


def combo_analyze(outdir: Path) -> dict:
    man = json.loads((outdir / "stage.json").read_text())
    text = load_extracted()
    points = [parse_corner_id(c) for c in man["points"]]
    cids = [pid(p) for p in points]
    plan = {x["id"]: x for x in _combo_plan_from_manifest(man, text)}
    mvar = {x["id"]: x for x in man["variants"]}
    res = {vid: _budget_values(outdir / vid, points) for vid in plan if (outdir / vid).is_dir()}
    missing = [(vid, pid(p)) for vid in plan for p in points if p not in res.get(vid, {})]
    ctrl_src = None
    if man.get("controls_from"):
        cdir = (outdir / man["controls_from"]).resolve()
        ctrl_src = {"dir": man["controls_from"],
                    "stage_json_sha256": file_sha(cdir / "stage.json")}
        for vid in ("ctrl", "sch"):
            res[vid] = _budget_values(cdir / vid, points)
            missing += [(f"{man['controls_from']}/{vid}", pid(p)) for p in points
                        if p not in res[vid]]
    controls, valid = stage_controls(res, points)

    rows = []
    for vid, x in plan.items():
        if vid == "sch":
            continue
        m = mvar[vid]
        row = {"id": vid, "fraction_c": x["fraction_c"], "fraction_r": x["fraction_r"],
               "total_ground_c_ff": m["total_ground_c_ff"],
               "total_series_r_ohm": m["total_series_r_ohm"],
               "probe_deck_sha256": m["probe_deck_sha256"], "corners": {}}
        for pt in points:
            r, c = res.get(vid, {}).get(pt), res.get("ctrl", {}).get(pt)
            if not r or r["td_od50_ns"] is None:
                row["corners"][pid(pt)] = {"td_od50_ns": None, "unresolved_count": None,
                                           "missing": not r,
                                           "job_ids": (r or {}).get("job_ids")}
                continue
            row["corners"][pid(pt)] = {
                "td_od50_ns": r["td_od50_ns"], "td_od1_ns": r["td_od1_ns"],
                "td_od01_ns": r["td_od01_ns"], "tau_ps": r["tau_ps"],
                "dout_od50_end": r["dout_od50_end"],
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
    rows.sort(key=lambda r: (-r["fraction_r"], -r["fraction_c"]))

    # Outcome: only TESTED cells are evidence. No interpolation, no
    # monotonicity assumption, no extrapolation to untested cells.
    scaled = [r for r in rows if r["id"] != "ctrl"]
    cands = [r for r in scaled if all(_ok(r["corners"].get(c)) for c in cids)]
    for r in cands:
        r["min_margin_ns"] = min(r["corners"][c]["margin_to_1p5ns_ns"] for c in cids)
    # Brackets along each axis (the other held fixed), per point and for
    # "every point": adjacent tested cells, failing -> meeting.
    brackets = []
    for axis, fixed in (("fraction_c", "fraction_r"), ("fraction_r", "fraction_c")):
        for val in sorted({r[fixed] for r in rows}, reverse=True):
            seq = sorted((r for r in rows if r[fixed] == val), key=lambda r: -r[axis])
            for a, b in zip(seq, seq[1:]):
                for cid in cids + ["all"]:
                    sel = cids if cid == "all" else [cid]
                    if (not all(_ok(a["corners"].get(c)) for c in sel)
                            and all(_ok(b["corners"].get(c)) for c in sel)):
                        brackets.append({"axis": axis, fixed: val, "point": cid,
                                         "fails_at": a[axis], "meets_at": b[axis],
                                         "fails_id": a["id"], "meets_id": b["id"]})
    nonmono = {}
    for cid in cids:
        flags = []
        for axis, fixed in (("fraction_c", "fraction_r"), ("fraction_r", "fraction_c")):
            for val in {r[fixed] for r in rows}:
                seq = sorted((r for r in rows if r[fixed] == val
                              and (r["corners"].get(cid) or {}).get("td_od50_ns") is not None),
                             key=lambda r: -r[axis])
                flags += [b["corners"][cid]["td_od50_ns"] > a["corners"][cid]["td_od50_ns"]
                          for a, b in zip(seq, seq[1:])]
        nonmono[cid] = any(flags)
    best = {}
    for cid in cids:
        xs = [(r["corners"][cid]["td_od50_ns"], r["id"]) for r in scaled
              if (r["corners"].get(cid) or {}).get("td_od50_ns") is not None]
        if xs:
            td, vid = min(xs)
            best[cid] = {"id": vid, "td_od50_ns": td, "margin_to_1p5ns_ns": pm.SPEC_TD_OD50_NS_MAX - td}
    tested = ", ".join(f"({r['fraction_c']:g}, {r['fraction_r']:g})" for r in scaled)
    if not valid:
        outcome = "refused: controls do not reproduce the cited decision times or are missing"
        selected = None
    elif cands:
        sel = max(cands, key=lambda r: (r["fraction_c"], r["fraction_r"]))
        selected = sel["id"]
        outcome = (f"{len(cands)} tested cell(s) meet 1.5 ns at every stage point; selected "
                   f"{sel['id']} (largest f_c, then largest f_r), minimum measured margin "
                   f"{sel['min_margin_ns'] * 1e3:+.1f} ps at these points (tested cells only; "
                   f"not a minimum budget, not an extrapolation)")
    else:
        selected = None
        open_b = [b for b in brackets if b["point"] == "all"]
        outcome = ("no tested cell meets 1.5 ns at every stage point "
                   + ("(an every-point bracket exists; see brackets)" if open_b
                      else "and no every-point crossing bracket exists")
                   + f" (tested (f_c, f_r): {tested})")
    return {
        "issue": COMBO_ISSUE,
        "generated_by": "layout/pex/parasitic_attribution.py combo-analyze",
        "scope": man["scope"], "kind": man["kind"], "points": cids,
        "source_sha256": man["source_sha256"], "controls_from": ctrl_src,
        "controls": controls, "study_valid": valid, "missing": missing,
        "outcome": outcome, "candidates": [r["id"] for r in cands],
        "selected_candidate": selected,
        "brackets": brackets, "non_monotonic_per_point": nonmono,
        "fastest_scaled_per_point": best,
        "variants": rows,
    }


def combo_table_md(a: dict, man: dict) -> str:
    cids = a["points"]
    lines = ["| variant | f_c | f_r | total ground C fF | total leg R ohm | "
             + " | ".join(f"{c}: td_od50 ns / margin ns / vos shift mV / unresolved"
                          for c in cids) + " |",
             "|---|---|---|---|---|" + "---|" * len(cids)]
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
                         + f" / {x['unresolved_count']}"
                         + (" PASS" if x["meets_1p5ns"] else " fail"))
        lines.append(f"| `{r['id']}` | {r['fraction_c']:g} | {r['fraction_r']:g} | "
                     f"{r['total_ground_c_ff']:.2f} | {r['total_series_r_ohm']:.1f} | "
                     + " | ".join(cells) + " |")
    ext = [x for x in man["variants"] if x["side"] == "extracted"]
    lines += ["", "Retained ground C per net (fF), from the variant netlists:", "",
              "| net | " + " | ".join(f"`{x['id']}`" for x in ext) + " |",
              "|---|" + "---|" * len(ext)]
    for n in man["cg_nets"]:
        lines.append(f"| {n} | " + " | ".join(f"{x['retained_ground_c_ff'][n]:.3f}"
                                                for x in ext) + " |")
    lines += ["", "Retained series-R leg sum per net (ohm), from the variant netlists:", "",
              "| net | " + " | ".join(f"`{x['id']}`" for x in ext) + " |",
              "|---|" + "---|" * len(ext)]
    for n in man["leg_nets"]:
        lines.append(f"| {n} | " + " | ".join(f"{x['retained_series_r_ohm'][n]:.2f}"
                                                for x in ext) + " |")
    return "\n".join(lines) + "\n"


def cmd_combo_analyze(args) -> int:
    outdir = Path(args.outdir).resolve()
    a = combo_analyze(outdir)
    man = json.loads((outdir / "stage.json").read_text())
    (outdir / "combo.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
    (outdir / "combo-table.md").write_text(
        "<!-- GENERATED by layout/pex/parasitic_attribution.py combo-analyze -- do not edit -->\n"
        + combo_table_md(a, man))
    print(f"study_valid={a['study_valid']} missing={len(a['missing'])}\n{a['outcome']}")
    return 0 if a["study_valid"] and not a["missing"] else 1


def cmd_combo_verify(args) -> int:
    """PDK-free: stage.json's plan and data-input hashes are what the code
    regenerates (code hashes are provenance; drift is only reported), every
    report ran the deck regenerated here, and combo.json / combo-table.md are
    what `combo-analyze` derives."""
    outdir = Path(args.outdir).resolve()
    check_bench()
    text = load_extracted()
    man = json.loads((outdir / "stage.json").read_text())
    points = [parse_corner_id(c) for c in man["points"]]
    plan = _combo_plan_from_manifest(man, text)
    errors, drift = budget_manifest_diff(
        man, combo_manifest(text, plan, points, man["kind"], man.get("controls_from")))
    for d in drift:
        print(f"NOTE provenance drift (not an error): {d}")
    errors += verify_stage_reports(outdir, plan, points)
    committed = outdir / "combo.json"
    if not committed.exists():
        errors.append("combo.json missing")
    else:
        a = combo_analyze(outdir)
        if json.loads(committed.read_text()) != json.loads(json.dumps(a)):
            errors.append("combo.json is not what `combo-analyze` derives from the reports")
        tbl = outdir / "combo-table.md"
        if not tbl.exists() or tbl.read_text().split("\n", 1)[1] != combo_table_md(a, man):
            errors.append("combo-table.md is not what `combo-analyze` generates")
    for e in errors:
        print(f"FAIL {e}")
    print(f"combo-verify: {len(errors)} error(s)")
    return 1 if errors else 0


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
    for name in ("budget-plan", "budget-run"):
        b = sub.add_parser(name, help="finite ground-C budget sweep (issue #243)")
        if name == "budget-run":
            b.add_argument("outdir")
            b.add_argument("--backend", default="batch", choices=("batch", "local"))
            b.add_argument("--jobs", type=int, default=2)
        b.add_argument("--points", default="two", choices=("two", "seven"),
                       help="two: the #229 corners; seven: every failing delay corner")
        b.add_argument("--fractions", help="comma list of retained-C fractions in [0,1), "
                                           "default 0.75,0.5,0.25,0")
        b.add_argument("--nets", help="comma list (default sn,doutb,qn,dout)")
    for name in ("budget-analyze", "budget-verify"):
        s = sub.add_parser(name)
        s.add_argument("outdir")
    for name in ("combo-plan", "combo-run"):
        c = sub.add_parser(name, help="combined ground-C x series-R budget (issue #264)")
        if name == "combo-run":
            c.add_argument("outdir")
            c.add_argument("--backend", default="batch", choices=("batch", "local"))
            c.add_argument("--jobs", type=int, default=2)
        c.add_argument("--kind", default="grid", choices=tuple(COMBO_STAGE_CAPS),
                       help="grid: two corners, controls rerun; refine: <= 4 cells on one "
                            "axis, controls from --controls-from; seven: one candidate at "
                            "the seven failing corners, controls rerun")
        c.add_argument("--cells", help="comma list of f_c:f_r (each in (0,1]); default the "
                                       "#264 grid 0.75,0.5,0.25 x 1.0,0.5")
        c.add_argument("--controls-from", help="refine only: the earlier stage directory "
                                               "(relative to OUTDIR) whose ctrl/sch are used")
    for name in ("combo-analyze", "combo-verify"):
        s = sub.add_parser(name)
        s.add_argument("outdir")
    args = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "analyze": cmd_analyze,
            "verify": cmd_verify, "budget-plan": cmd_budget_plan,
            "budget-run": cmd_budget_run, "budget-analyze": cmd_budget_analyze,
            "budget-verify": cmd_budget_verify, "combo-plan": cmd_combo_plan,
            "combo-run": cmd_combo_run, "combo-analyze": cmd_combo_analyze,
            "combo-verify": cmd_combo_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
