#!/usr/bin/env python3
"""`klt pex --measure-command` probe for this block (issue #81, T1 item 7).

`klt pex` (klayout-tools >= 0.7.0) extracts `layout/comparator.gds` itself and
then runs THIS script twice -- once on the schematic reference netlist
(`design/comparator.spice`, `KLT_PEX_SIDE=schematic`) and once on the netlist
it just extracted (`KLT_PEX_SIDE=extracted`) -- passing the netlist path as
the final argument. This script measures the comparator-regeneration spec
rows on that netlist over the full 45-point PVT grid and prints a `klt pex`
measurement document on stdout. `klt pex` computes every schematic-vs-
extracted delta row itself; nothing here compares the two sides.

WHY A MEASURE COMMAND, NOT A `klt sim` TESTBENCH SET
-----------------------------------------------------
The extracted leg of the regeneration bench is a two-stage measurement per
PVT point: an offset probe finds the comparator's own trip point, then the
overdrive ladder is centred on it (`dut_vos`, issue #23 -- a flat extraction
carries a deterministic systematic offset several times the Monte-Carlo
3-sigma, and a 0 V-referenced ladder's small rungs sit inside it). A `klt sim`
request has no per-corner parameter and no way to feed one analysis's result
into another, so `klt pex`'s testbench mode cannot express it. This is the
"threshold crossing located by a rule across separate runs" case `klt pex
--help` names for `--measure-command`.

WHERE THE SIMULATION RUNS
-------------------------
Every multi-corner run below is a `klt sim` request submitted to the batch
fleet (`--backend batch`) -- this script never launches ngspice itself.
The submitting client is the released `klayout-tools==0.6.0` wheel
(`uvx --isolated --from klayout-tools==0.6.0 klt`, override with
$PEX_SIM_KLT): the
fleet's runner image runs klt 0.5.0 and refuses a 0.7.0 client outright
(`batch_runner_version_mismatch`), while 0.5.0 itself has no `batch`
backend. Each request uses only fields the 0.5.0 runner implements
(`netlist`, `models`, `corners` with string-section process bundles,
`supply_v`, `temperature_c`, `analysis`, `.meas` measurements,
`options.timeout_s`). Every `klt sim` report is kept under
$KLT_PEX_ARTIFACTS_DIR, so the runner identity (`environment.remote`) of
every job travels with the evidence.

THE BENCH IS THE COMMITTED ONE, MECHANICALLY RE-EXPRESSED
---------------------------------------------------------
The two bench fragments are read from `sim/comparator-regeneration/
testbench/` (pinned by sha256 below) and rewritten by exact-match line
substitutions, each asserted to apply exactly once. The rewrites exist only
because `klt sim` sets the supply corner with `alter <source>=<dc>`, which
cannot reach a `{vdd_val}` parameter inside a PULSE/PWL source:

* the strobe `vclk ... pulse(0 {vdd_val} ...)` becomes a unit pulse times
  `v(vdd)` (an ideal B-source -- the same waveform at every supply point);
* each ladder source `pwl(0 {dut_vos-dv} ... {dut_vos+dv})` becomes a
  `+/-dv` PWL plus `v(vos)`, where `vos` is an ideal B-source that selects
  this PVT point's `dut_vos` from `temper` and `v(vdd)` (one request per
  process corner, so the process is fixed within a request).

The harness's model preamble is reproduced in the flattened netlist: the
PDK `design.ngspice` switch params (inlined -- the batch job uploads only the
netlist file), the bench `.options`, the `sim/dut.json` operating-point
params, and the DUT netlist itself. Corner `.lib` sections, `.temp` and the
supply are applied by `klt sim` from the per-process bundles below, which
copy `sim/harness/corners.py`'s `mos` corner set.

dut_vos CONVENTION (the harness's, unchanged): the schematic leg's ladder is
referred to 0 V (a symmetric schematic is offset-free by construction --
`sim/comparator-regeneration/README.md`); the extracted leg's ladder is
referred to its probed trip point. The probe still RUNS on both legs, so the
systematic offset itself (`dut_vos_v`) gets a genuine delta row.

GRADING (the per-measurement `status` `klt pex` turns into delta-row status)
---------------------------------------------------------------------------
* `td_od50_ns`: fails above DR-0002's ratified decision-time TARGET
  (<= 1.5 ns at 50 mV overdrive) or outside the bench's own sanity envelope.
  The <= 0.8 ns stretch is not a pass/fail bar here (it is scored in
  `measurements/characterization-report.md`, same as for the schematic).
* `p_static_uw` (static current x supply): fails above DR-0002's ratified
  supply/power TARGET (<= 1 mW).
* every other row: the bench's own `checks` from `tb.json` (sanity floors
  and the polarity proof); a row with no check is reported as `pass` when it
  produced a value. `dut_vos_v` must lie inside the probe span.
No bound is relaxed: the spec numbers are DR-0002's, the checks are the
committed bench's.

Usage (normally via `layout/pex/run_pex.py`, never by hand):
    KLT_PEX_SIDE=schematic python3 layout/pex/pex_measure.py design/comparator.spice
Debug one PVT point locally (a single-corner probe, allowed on any host):
    python3 layout/pex/pex_measure.py --debug-corner tt_27c_3.30v \
        --side schematic design/comparator.spice
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
BENCH_DIR = os.path.join(REPO_ROOT, "sim", "comparator-regeneration", "testbench")
TB_JSON = os.path.join(BENCH_DIR, "tb.json")
TB_MAIN = os.path.join(BENCH_DIR, "tb_regeneration.spice")
TB_PROBE = os.path.join(BENCH_DIR, "tb_vosprobe.spice")
DUT_JSON = os.path.join(REPO_ROOT, "sim", "dut.json")
SCHEMATIC_NETLIST = os.path.join(REPO_ROOT, "design", "comparator.spice")

#: The committed bench files this re-expression was written against. A
#: changed fragment fails loudly here instead of being silently re-expressed
#: by rewrite rules written for a different text.
PINNED_SHA256 = {
    TB_JSON: "e2418d7b77608291036bdaca675d3bba95d0ed3724fcaf034b53eefa4d190704",
    TB_MAIN: "ef3dc3be1476a8cbacf2afc13c33abb3b116dd7e7fd7e3e81219f0f12edf66da",
    TB_PROBE: "56475d33709d034f209970fe4cecd0d8095e2b9a0c9aaa078569dadf9674a0d0",
}

#: The PDK `design.ngspice` global switches the harness `.include`s ahead of
#: every corner section (sim/harness/corners.py), inlined verbatim because a
#: batch job uploads only the netlist file. Mismatch off, as in the harness.
DESIGN_SWITCHES = (
    ".param sw_stat_global=0 sw_stat_mismatch=0 mc_skew=3 res_mc_skew=3 "
    "cap_mc_skew=3 fnoicor=0"
)

MODELS = {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"}

#: sim/harness/corners.py's `mos` corner set, section for section, in the
#: harness's own family order (mos, res, bjt, diode, moscap, mimcap).
_TYP = ["typical", "res_typical", "bjt_typical", "diode_typical",
        "moscap_typical", "mimcap_typical"]
PROCESS_BUNDLES = {
    "tt": list(_TYP),
    "ff": ["ff", "res_ff", "bjt_ff", "diode_ff", "moscap_ff", "mimcap_ff"],
    "ss": ["ss", "res_ss", "bjt_ss", "diode_ss", "moscap_ss", "mimcap_ss"],
    "fs": ["fs"] + _TYP[1:],
    "sf": ["sf"] + _TYP[1:],
}
TEMPERATURES_C = (-40.0, 27.0, 125.0)
VDD_NOM = 3.3
SUPPLIES_V = (round(VDD_NOM * 0.9, 6), VDD_NOM, round(VDD_NOM * 1.1, 6))

#: DR-0002's ratified TARGET bounds for the rows this bench measures.
SPEC_TD_OD50_NS_MAX = 1.5
SPEC_P_STATIC_UW_MAX = 1000.0

#: Per-point wall-clock caps handed to `klt sim` (`options.timeout_s`). The
#: probe's 80 us slow-ramp transient gets the harness's own wider bound.
TIMEOUT_MAIN_S = 900
TIMEOUT_PROBE_S = 1800

#: The probe's ramp (tb_vosprobe.spice: vrmp pwl(0 -vspan tramp +vspan)).
PROBE_VSPAN = 40e-3
PROBE_TRAMP = 80e-6


def corner_id(process: str, temp_c: float, vdd: float) -> str:
    """sim/harness/corners.py's PvtPoint.corner_id, so rows line up with the
    committed records' own corner ids."""
    return f"{process}_{temp_c:g}c_{vdd:.2f}v"


def _sha256(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _check_pins() -> None:
    for path, want in PINNED_SHA256.items():
        got = _sha256(path)
        if got != want:
            sys.exit(
                f"{os.path.relpath(path, REPO_ROOT)}: sha256 {got} is not the "
                f"pinned {want} this re-expression was written against -- "
                "update the rewrite rules in layout/pex/pex_measure.py and "
                "re-pin, do not just re-pin"
            )


def _replace_once(text: str, old: str, new: str, where: str) -> str:
    count = text.count(old)
    if count != 1:
        sys.exit(f"{where}: expected exactly one {old!r}, found {count}")
    return text.replace(old, new)


def _strip_comments(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("*"))


# --------------------------------------------------------------------------- #
# Bench re-expression
# --------------------------------------------------------------------------- #

_CLOCK_OLD = "vclk clk 0 pulse(0 {vdd_val} 10n 100p 100p 10n 30n)"
_CLOCK_NEW = (
    "vclku clku 0 pulse(0 1 10n 100p 100p 10n 30n)\n"
    "Bclk clk 0 v = 'v(clku)*v(vdd)'"
)


def _main_body() -> str:
    text = _strip_comments(open(TB_MAIN).read())
    text = _replace_once(text, _CLOCK_OLD, _CLOCK_NEW, "tb_regeneration.spice")
    for inst, rung in (("a", "dv_big"), ("b", "dv_mid"), ("c", "dv_tiny")):
        old = (
            f"vs{inst}  s{inst} 0 pwl(0 {{dut_vos-{rung}}} {{t_flip}} "
            f"{{dut_vos-{rung}}} {{t_flip+1n}} {{dut_vos+{rung}}})"
        )
        new = (
            f"vs{inst}u s{inst}u 0 pwl(0 {{-{rung}}} {{t_flip}} {{-{rung}}} "
            f"{{t_flip+1n}} {{{rung}}})\n"
            f"Bs{inst} s{inst} 0 v = 'v(s{inst}u)+v(vos)'"
        )
        text = _replace_once(text, old, new, "tb_regeneration.spice")
    if "dut_vos" in text:
        sys.exit("tb_regeneration.spice: a dut_vos reference survived the rewrite")
    _assert_vdd_val_only_on_supplies(text, ("vsup", "vsupa"), "tb_regeneration.spice")
    return text


def _probe_body() -> str:
    text = _strip_comments(open(TB_PROBE).read())
    text = _replace_once(text, _CLOCK_OLD, _CLOCK_NEW, "tb_vosprobe.spice")
    _assert_vdd_val_only_on_supplies(text, ("vsup",), "tb_vosprobe.spice")
    return text


def _assert_vdd_val_only_on_supplies(text: str, sources: tuple[str, ...], where: str) -> None:
    """After the rewrite, {vdd_val} may only feed the DC supply sources `klt
    sim` alters -- anywhere else it would stay frozen at nominal."""
    for line in text.splitlines():
        if "vdd_val" in line and line.split()[0].lower() not in sources:
            sys.exit(f"{where}: {{vdd_val}} still used outside the supplies: {line!r}")


def _vos_source(vos_by_point: dict[tuple[float, float], float]) -> str:
    """An ideal source carrying this PVT point's dut_vos, selected from
    `temper` and the (altered) supply -- one request per process corner."""
    def by_vdd(temp_c: float) -> str:
        a, b, c = (vos_by_point[(temp_c, v)] for v in SUPPLIES_V)
        lo = (SUPPLIES_V[0] + SUPPLIES_V[1]) / 2
        hi = (SUPPLIES_V[1] + SUPPLIES_V[2]) / 2
        return f"(v(vdd) < {lo:g} ? {a!r} : (v(vdd) < {hi:g} ? {b!r} : {c!r}))"

    t_lo = (TEMPERATURES_C[0] + TEMPERATURES_C[1]) / 2
    t_hi = (TEMPERATURES_C[1] + TEMPERATURES_C[2]) / 2
    expr = (
        f"(temper < {t_lo:g} ? {by_vdd(TEMPERATURES_C[0])} : "
        f"(temper < {t_hi:g} ? {by_vdd(TEMPERATURES_C[1])} : {by_vdd(TEMPERATURES_C[2])}))"
    )
    return f"Bvos vos 0 v = '{expr}'"


def _dut_params() -> list[str]:
    duts = json.load(open(DUT_JSON))["duts"]
    params = duts["comparator-dr0001"]["params"]
    layout_params = duts["comparator-dr0001-layout"]["params"]
    if params != layout_params:
        sys.exit("sim/dut.json: schematic and layout entries no longer share params")
    return [f".param {k}={v!r}" for k, v in params.items()]


def _flatten(dut_netlist_text: str, body: str, extra: list[str]) -> str:
    tb = json.load(open(TB_JSON))
    lines = [
        "* GENERATED by layout/pex/pex_measure.py (issue #81) -- do not edit",
        DESIGN_SWITCHES,
        f".param vdd_nom={VDD_NOM!r}",
        f".param vdd_val={VDD_NOM!r}",
        *_dut_params(),
        *(f".options {o}" for o in tb["options"]),
        "",
        "* ---- device under test ----",
        dut_netlist_text.rstrip(),
        "",
        "* ---- testbench (re-expressed from sim/comparator-regeneration/testbench) ----",
        body.rstrip(),
        *extra,
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# klt sim requests
# --------------------------------------------------------------------------- #

MAIN_MEAS = [
    ("vsup_v", "meas tran vsup_v find v(vdd) at=25n"),
    ("td_a", "meas tran td_a trig v(clkn) val=0.5 rise=2 targ v(dan) val=0.5 rise=1 td=35n"),
    ("td_b", "meas tran td_b trig v(clkn) val=0.5 rise=2 targ v(dbn) val=0.5 rise=1 td=35n"),
    ("td_c", "meas tran td_c trig v(clkn) val=0.5 rise=2 targ v(dcn) val=0.5 rise=1 td=35n"),
    ("da_first", "meas tran da_first find v(dan) at=18n"),
    ("db_first", "meas tran db_first find v(dbn) at=18n"),
    ("dc_first", "meas tran dc_first find v(dcn) at=18n"),
    ("da_end", "meas tran da_end find v(dan) at=55n"),
    ("db_end", "meas tran db_end find v(dbn) at=55n"),
    ("dc_end", "meas tran dc_end find v(dcn) at=55n"),
    ("i_stat", "meas tran i_stat avg i(vsupa) from=25n to=29n"),
    ("q_dec", "meas tran q_dec integ i(vsupa) from=39.9n to=48n"),
]
PROBE_MEAS = [("t_flip", "meas tran t_flip when v(dn)=0.5 rise=1 td=8u")]


def _check_meas_against_manifest() -> None:
    """The `.meas` cards above are the manifest's own analyses, verbatim."""
    tb = json.load(open(TB_JSON))
    if [c for _, c in MAIN_MEAS] != tb["analyses"][1:] or tb["analyses"][0] != "tran 5p 60n":
        sys.exit("tb.json analyses changed -- MAIN_MEAS no longer mirrors them")
    probe = tb["offset_probe"]["analyses"]
    if probe[0] != "tran 100n 80u 0 100n" or probe[1] != PROBE_MEAS[0][1]:
        sys.exit("tb.json offset_probe analyses changed -- PROBE_MEAS no longer mirrors them")


def _request(netlist: str, processes: list[str], meas, tran: str, timeout_s: int,
             supplies: list[str]) -> dict:
    return {
        "netlist": netlist,
        "models": MODELS,
        "corners": {
            "process": [{"name": p, "sections": PROCESS_BUNDLES[p]} for p in processes],
            "supply_v": {s: list(SUPPLIES_V) for s in supplies},
            "temperature_c": list(TEMPERATURES_C),
        },
        "analysis": {"kind": "tran", "args": tran},
        "measurements": [{"name": n, "spice": "." + card} for n, card in meas],
        "options": {"timeout_s": timeout_s},
    }


def _klt() -> list[str]:
    return shlex.split(os.environ.get(
        "PEX_SIM_KLT", "uvx --isolated --from klayout-tools==0.6.0 klt"))


def _klt_identity() -> dict:
    """The submitting client's build identity -- must be a released wheel
    (a same-version snapshot is not the same code, signoff/regenerate.sh)."""
    proc = subprocess.run([*_klt(), "version", "--format", "json"],
                          capture_output=True, text=True, check=True)
    info = json.loads(proc.stdout)
    if info.get("is_release") is not True or not info.get("git_tag"):
        sys.exit(f"klt sim client is not a released wheel: {info}")
    return {k: info.get(k) for k in ("version", "git_tag", "git_commit", "is_release")}


def _run_klt_sim(request: dict, workdir: str, tag: str, backend: str) -> dict:
    req_path = os.path.join(workdir, f"{tag}.request.json")
    with open(req_path, "w") as f:
        json.dump(request, f, indent=2)
        f.write("\n")
    cmd = [*_klt(), "sim", req_path, "--backend", backend, "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
    report_path = os.path.join(workdir, f"{tag}.report.json")
    with open(report_path, "w") as f:
        f.write(proc.stdout)
    if proc.returncode not in (0, 4) or not proc.stdout.strip():
        sys.stderr.write(proc.stderr[-4000:])
        sys.exit(f"klt sim ({tag}) exited {proc.returncode} with no report")
    return json.loads(proc.stdout)


def _point_key(corner: dict) -> tuple[str, float, float]:
    supply = corner["supply_v"]["vsup"]
    return corner["process"], float(corner["temperature_c"]), float(supply)


def _values(corner: dict) -> dict[str, float | None]:
    return {m["name"]: m["value"] for m in corner["measurements"]}


# --------------------------------------------------------------------------- #
# Derived quantities and grading
# --------------------------------------------------------------------------- #

def _derive(raw: dict[str, float | None]) -> dict[str, float | None]:
    """tb.json's `measure` block, evaluated in Python on klt sim's raw values."""
    def get(*names):
        vals = [raw.get(n) for n in names]
        return None if any(v is None for v in vals) else vals

    out: dict[str, float | None] = {}
    v = get("td_a"); out["td_od50_ns"] = v and v[0] * 1e9
    v = get("td_b"); out["td_od1_ns"] = v and v[0] * 1e9
    v = get("td_c"); out["td_od01_ns"] = v and v[0] * 1e9
    v = get("td_b", "td_c")
    if v and v[1] != v[0]:
        tau = (v[1] - v[0]) / math.log(10)
        out["tau_ps"] = tau * 1e12
        out["resolve_decades"] = v[0] / tau
    else:
        out["tau_ps"] = out["resolve_decades"] = None
    for rung, inst in (("od50", "a"), ("od1", "b"), ("od01", "c")):
        out[f"dout_{rung}_end"] = raw.get(f"d{inst}_end")
        out[f"dout_{rung}_first"] = raw.get(f"d{inst}_first")
    v = get("i_stat"); out["i_static_ua"] = v and abs(v[0]) * 1e6
    v = get("q_dec", "i_stat", "vsup_v")
    out["e_dec_fj"] = v and abs(v[0] - v[1] * 8.1e-9) * v[2] * 1e15
    v = get("i_stat", "vsup_v")
    out["p_static_uw"] = v and abs(v[0]) * v[1] * 1e6
    return out


def _grade(name: str, value: float | None, checks: dict) -> str:
    if value is None:
        return "error"
    ok = True
    check = checks.get(name) or {}
    if "min" in check and value < check["min"]:
        ok = False
    if "max" in check and value > check["max"]:
        ok = False
    if name == "td_od50_ns" and value > SPEC_TD_OD50_NS_MAX:
        ok = False
    if name == "p_static_uw" and value > SPEC_P_STATIC_UW_MAX:
        ok = False
    if name == "dut_vos_v" and abs(value) >= PROBE_VSPAN:
        ok = False
    return "pass" if ok else "fail"


UNITS = {
    "td_od50_ns": "ns", "td_od1_ns": "ns", "td_od01_ns": "ns", "tau_ps": "ps",
    "i_static_ua": "uA", "e_dec_fj": "fJ", "p_static_uw": "uW", "dut_vos_v": "V",
}


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def _dut_text(side: str, netlist: str, workdir: str) -> tuple[str, str]:
    """The comparator_dut netlist text this side is measured on, and its sha256."""
    if side == "schematic":
        if os.path.realpath(netlist) != os.path.realpath(SCHEMATIC_NETLIST):
            sys.exit(f"schematic side got {netlist}, expected design/comparator.spice")
        text = open(netlist).read()
        return text, _sha256(netlist)
    # run_extract_sim imports its sibling `layout_common` by bare name.
    sys.path.insert(0, os.path.join(REPO_ROOT, "layout"))
    spec = importlib.util.spec_from_file_location(
        "run_extract_sim", os.path.join(REPO_ROOT, "layout", "run_extract_sim.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dut_path = os.path.join(workdir, "comparator.dut-layout.spice")
    mod._adapt_netlist(netlist, dut_path)
    mod._check_interface_contract(dut_path)
    return open(dut_path).read(), _sha256(dut_path)


def measure(side: str, netlist: str, workdir: str, backend: str,
            only: tuple[str, float, float] | None = None) -> dict:
    _check_pins()
    _check_meas_against_manifest()
    os.makedirs(workdir, exist_ok=True)
    checks = json.load(open(TB_JSON))["checks"]
    client = _klt_identity()
    dut_text, dut_sha = _dut_text(side, netlist, workdir)
    processes = [only[0]] if only else list(PROCESS_BUNDLES)

    def narrowed(req: dict) -> dict:
        if only:
            req["corners"]["temperature_c"] = [only[1]]
            req["corners"]["supply_v"] = {k: [only[2]] for k in req["corners"]["supply_v"]}
        return req

    # Stage 1: the offset probe, every point, one request.
    probe_net = os.path.join(workdir, "probe.spice")
    with open(probe_net, "w") as f:
        f.write(_flatten(dut_text, _probe_body(), []))
    probe_req = narrowed(_request("probe.spice", processes, PROBE_MEAS,
                                  "100n 80u 0 100n", TIMEOUT_PROBE_S, ["vsup"]))
    probe = _run_klt_sim(probe_req, workdir, "probe", backend)
    vos: dict[tuple[str, float, float], float | None] = {}
    for corner in probe["corners"]:
        t_flip = _values(corner).get("t_flip")
        # vrmp is a linear PWL from -vspan at t=0 to +vspan at tramp, so the
        # ramp value at the flip (the harness's `find v(rmp) at=t_flip`) is
        # exactly this line.
        vos[_point_key(corner)] = (
            None if t_flip is None
            else -PROBE_VSPAN + 2 * PROBE_VSPAN * t_flip / PROBE_TRAMP
        )

    # Stage 2: the overdrive ladder, one request per process corner (the
    # dut_vos source is keyed on temperature and supply only).
    def ladder(process: str) -> dict:
        keys = [(process, t, v) for t in TEMPERATURES_C for v in SUPPLIES_V]
        if side == "schematic":
            centre = {(t, v): 0.0 for _, t, v in keys}
        else:
            centre = {(t, v): vos.get((process, t, v)) for _, t, v in keys}
            if only:
                centre = {k: (val if val is not None else 0.0) if (process, *k) == only else 0.0
                          for k, val in centre.items()}
            missing = [k for k, val in centre.items() if val is None]
            if missing:
                sys.exit(f"offset probe produced no trip point at {process} {missing}")
        net = f"ladder-{process}.spice"
        with open(os.path.join(workdir, net), "w") as f:
            f.write(_flatten(dut_text, _main_body(), [_vos_source(centre)]))
        req = narrowed(_request(net, [process], MAIN_MEAS, "5p 60n", TIMEOUT_MAIN_S,
                                ["vsup", "vsupa"]))
        return _run_klt_sim(req, workdir, f"ladder-{process}", backend)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(processes)) as pool:
        reports = list(pool.map(ladder, processes))

    corners = []
    for report in reports:
        for corner in report["corners"]:
            key = _point_key(corner)
            derived = _derive(_values(corner))
            derived["dut_vos_v"] = vos.get(key)
            rows = []
            for name, value in derived.items():
                row = {"name": name, "value": value, "status": _grade(name, value, checks)}
                if name in UNITS:
                    row["unit"] = UNITS[name]
                rows.append(row)
            corners.append({"corner_id": corner_id(*key), "measurements": rows})
    order = {corner_id(p, t, v): i for i, (p, t, v) in enumerate(
        (p, t, v) for p in PROCESS_BUNDLES for t in TEMPERATURES_C for v in SUPPLIES_V)}
    corners.sort(key=lambda c: order[c["corner_id"]])

    summary = {
        "side": side,
        "dut_netlist_sha256": dut_sha,
        "klt_sim_client": client,
        "ladder_centre": "0 V (harness convention)" if side == "schematic" else "probed dut_vos",
        "klt_sim_reports": sorted(f for f in os.listdir(workdir) if f.endswith(".report.json")),
        "runners": sorted({
            json.dumps({k: (r.get("environment") or {}).get("remote", {}).get(k)
                        for k in ("provider", "runner_klt_version", "client_klt_version",
                                  "instance_type", "lifecycle", "state")}, sort_keys=True)
            for r in [probe, *reports]
        }),
    }
    with open(os.path.join(workdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"corners": corners}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("netlist")
    ap.add_argument("--side", default=os.environ.get("KLT_PEX_SIDE"))
    ap.add_argument("--workdir", default=os.environ.get("KLT_PEX_ARTIFACTS_DIR"))
    ap.add_argument("--backend", default="batch")
    ap.add_argument("--debug-corner", help="run ONE PVT point (e.g. tt_27c_3.30v) "
                    "with --backend local: a single-corner debug probe")
    args = ap.parse_args()
    if args.side not in ("schematic", "extracted"):
        sys.exit("side must be schematic or extracted ($KLT_PEX_SIDE or --side)")
    only = None
    if args.debug_corner:
        m = re.fullmatch(r"(\w+?)_(-?\d+)c_([\d.]+)v", args.debug_corner)
        if not m:
            sys.exit(f"bad corner id {args.debug_corner!r}")
        only = (m.group(1), float(m.group(2)), float(m.group(3)))
        args.backend = "local"
    workdir = args.workdir or tempfile.mkdtemp(prefix=f"pex-{args.side}-")
    os.makedirs(workdir, exist_ok=True)
    doc = measure(args.side, os.path.abspath(args.netlist), os.path.abspath(workdir),
                  args.backend, only)
    json.dump(doc, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
