#!/usr/bin/env python3
"""FEASIBILITY path for the whole-comparator transient offset Monte Carlo
against the EXTRACTED binding (issue #219).

This is deliberately a separate tool from `mk_klt_request.py` /
`klt_record.py`. Those keep their production refusals (schematic provenance
only; every record minted under a bench's `records/`). Nothing here can mint a
reference record: the only outputs are `contract.json` and
`feasibility-<point>.json` under a feasibility directory, each stamped
`feasibility_only: true`. Unsupported paths REFUSE (`Refusal`), they never
fall back to a guess.

THE MEASUREMENT CONTRACT
------------------------
* DUT: the flat extraction re-made with the klt version recorded in the
  committed extraction report, so the raw netlist's sha256 equals the
  report's `netlist_sha256` (a different klt re-extracts different poly
  resistance: the identity check catches it), adapted by
  `layout/run_extract_sim.py`'s own adaptation.
* Device mismatch: every adapted MOS card must call the PDK `nfet_03v3` /
  `pfet_03v3` subckt (whose body scales `delvto`/`mulu0` by
  `sw_stat_mismatch`), and the multiset of (model, L, W) must equal the
  schematic's, so the Pelgrom area every mismatch sigma depends on is
  unchanged.
* Body bias: every NMOS bulk must resolve to the `vss` hub and every PMOS bulk
  to the `vdd` hub, and the extraction report must list no unbiased PMOS body
  nets / missing flavour markers.
* Observation nodes: `layout/pex/preamp_nodes.py` derives the preamp output
  hubs from connectivity (fail closed); the hierarchical names
  `xa.xlayout_dut.<hub>` are generated into the body, never written in a
  fragment.
* Staircase: 64 levels x 0.16 mV (the schematic bench's shape), START centred
  per PVT point on the mismatch-DISABLED trip point from `tb_trip_probe.spice`
  (rounded to `centre_resolution_mv`), preserved across the point's whole
  population. The reported trip point is ABSOLUTE:
  `trip = centre + stair_v0 + k*step - step/2`. Its population mean (systematic
  + draw mean) and the quantisation-corrected random sigma are separate
  numbers; the centre is never subtracted from the mean. Sign: the trip point
  is the differential input (vinp - vinn) at which the decision flips; the
  input-referred offset is its negative.
* Validation per draw is `klt_record.derive_offset_tran` (endpoint decisions,
  trip bracket, evaluate-phase flip, gain sign, finite ingredients); on top:
  mismatch actually exercised (sigma > 0), edge margin, and the probe's
  mismatch-free trip inside the population's bracket.
* WITHHELD (not substantiated for the extracted netlist): the same-draw
  preamp/latch decomposition and the resistor hand-budget term. The gain is
  computed only as a validity gate, never published as `Vos_pre`.
* Executor: single-unit probe may run locally; the multi-unit Monte Carlo goes
  to the batch fleet via `klt sim` (KLT_SIM_BACKEND=batch). A failed submit is
  reported verbatim; there is no local fallback.

Usage
-----
    extracted_tran_feasibility.py contract  OUTDIR
    extracted_tran_feasibility.py probe     OUTDIR --point tt_27c_3.30v
    extracted_tran_feasibility.py mc        OUTDIR --point P --probe-report R [--mc-n 20]
    extracted_tran_feasibility.py evaluate  OUTDIR --point P
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "layout"))
sys.path.insert(0, str(REPO / "layout" / "pex"))

import klt_record as kr  # noqa: E402
import mk_klt_request as mk  # noqa: E402
import preamp_nodes as pn  # noqa: E402
from harness import dut as hdut  # noqa: E402
from harness import pdk as hpdk  # noqa: E402
from harness import testbench as htb  # noqa: E402

BENCH = "comparator-offset-tran-extracted-feasibility"
#: The only PVT points this feasibility path may be asked about: the nominal
#: point and the point whose systematic offset was the largest in the
#: committed extracted regeneration record (-21.57 mV, ff/125 C/3.63 V,
#: `sim/comparator-regeneration/records/20261002-202641-baeffe5.json`).
POINTS = {"tt_27c_3.30v": ("tt", 27.0, 3.30), "ff_125c_3.63v": ("ff", 125.0, 3.63)}
MAX_MC_N = 50          # a feasibility probe, never a campaign
SEED = mk.OFFSET_MC_SEED
PROBE_OPTIONS = ["reltol=1e-4", "vntol=1e-9", "abstol=1e-13"]  # as the regeneration probe
EXTRACT_REPORT = REPO / "layout" / "lvs" / "comparator.extract-rc.json"
GDS = REPO / "layout" / "comparator.gds"
SCHEMATIC = REPO / "design" / "comparator.spice"
INST_PREFIX = "xa.xlayout_dut"
MM_NETLIST = "comparator.dut-layout-mm.spice"
KLT_EXTRACT_ARGS = ["--deck", "gf180mcu", "--top", "COMPARATOR", "--pins",
                    ",".join(pn.INTERFACE_PINS), "--parasitics", "--format", "json"]


class Refusal(Exception):
    """The feasibility contract is not met: evidence must not be published."""

    def __init__(self, code: str, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code, self.msg = code, msg


def sha256_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def finite(v) -> bool:
    return kr._finite(v)


# ---------------------------------------------------------------------------
# netlist facts (pure functions of text: PDK-free, klt-free)
# ---------------------------------------------------------------------------

_SCALE = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6}


def spice_number(tok: str) -> float:
    m = re.fullmatch(r"([-+]?[0-9.]+(?:e[-+]?\d+)?)(meg|[fpnumk])?", tok.strip().lower())
    if not m:
        raise ValueError(f"not a SPICE number: {tok!r}")
    return float(m.group(1)) * _SCALE.get(m.group(2) or "", 1.0)


def _params(toks) -> dict:
    return {k.lower(): v for k, _, v in (t.partition("=") for t in toks if "=" in t)}


def device_multiset(text: str) -> dict:
    """{(model, L, W): count} over every nfet_03v3/pfet_03v3 card in `text`
    (an `M<name>` MOS card or an `X<name> ... <model>` subckt call), plus
    {('ppolyf_u_1k', r_length, r_width): count} for the load resistors.
    Geometry values are normalised to metres (rounded to 1e-12) so `2U`/`2u`
    and `0.5U`/`0.5u` compare equal."""
    out: dict = {}
    for line in pn._logical_lines(text):
        toks = line.split()
        if not toks or toks[0][0].upper() not in "MX":
            continue
        model = next((t.lower() for t in toks[1:] if t.lower() in
                      (*pn.MOS_MODELS, pn.RES_MODEL)), None)
        if model is None:
            continue
        p = _params(toks)
        try:
            if model == pn.RES_MODEL:
                g = (p["r_length"], p["r_width"])
            else:
                g = (p["l"], p["w"])
            key = (model, round(spice_number(g[0]), 12), round(spice_number(g[1]), 12))
        except (KeyError, ValueError) as e:
            raise Refusal("DEVICE_GEOMETRY_UNPARSED", f"{toks[0]}: {e!r}")
        out[key] = out.get(key, 0) + 1
    return out


_MOS_CARD = re.compile(r"^([MX]\S*)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(nfet_03v3|pfet_03v3)(\s.*)?$",
                       re.IGNORECASE)


def mos_cards(text: str) -> list[dict]:
    """Every nfet_03v3/pfet_03v3 device card, whichever form it is written in:
    `M<name> d g s b <model> ...` (a bare BSIM instance: the PDK `.model` of
    that name) or `X<name> d g s b <model> ...` (a call of the PDK subckt)."""
    out = []
    for line in pn._logical_lines(text):
        m = _MOS_CARD.match(line)
        if m:
            out.append({"name": m.group(1), "form": "bare_model" if m.group(1)[0] in "mM" else "subckt",
                        "nets": dict(zip("dgsb", (m.group(i).lower() for i in range(2, 6)))),
                        "model": m.group(6).lower()})
    return out


def mismatch_capable(text: str) -> str:
    """FEASIBILITY-ONLY re-adaptation: rewrite each bare-model MOS card
    (`M<n> d g s b nfet_03v3 L= W= AS= ...`) into a call of the PDK subckt of
    the same name (`X<n> d g s b nfet_03v3 L= W= AS= ...`), which is the form
    the schematic netlist uses and the only one whose body scales
    `delvto`/`mulu0` by `sw_stat_mismatch`. Nets, geometry and the
    source/drain area/perimeter parameters are untouched; nothing else in the
    netlist changes. `layout/run_extract_sim.py`'s adapter, which the
    committed `comparator-dr0001-layout` binding uses, is NOT modified."""
    out = []
    for raw in text.splitlines():
        m = _MOS_CARD.match(raw.strip())
        if m and m.group(1)[0] in "mM":
            raw = f"X{m.group(1)[1:]} {' '.join(m.group(i) for i in range(2, 7))}{m.group(7) or ''}"
        out.append(raw)
    return "\n".join(out) + "\n"


def check_device_mismatch_support(adapted: str, schematic: str, pdk_lib: str) -> dict:
    """Mismatch support of the adapted MOS cards (see module docstring)."""
    cards = mos_cards(adapted)
    if not cards:
        raise Refusal("NO_MOS_DEVICES", "no MOS cards recognised in the adapted netlist")
    bare = [c["name"] for c in cards if c["form"] == "bare_model"]
    if bare:
        raise Refusal(
            "ADAPTED_MOS_BYPASS_MISMATCH",
            f"{len(bare)} of {len(cards)} MOS cards ({', '.join(bare[:4])}...) are bare `M` instances "
            "of the PDK .model, not calls of the `nfet_03v3`/`pfet_03v3` subckt: the "
            "`delvto='mis_vth*sw_stat_mismatch'` / `mulu0='1-mis_k*sw_stat_mismatch'` mismatch "
            "lives only in the subckt body, so sw_stat_mismatch=1 changes NOTHING for these devices")
    for model in sorted({c["model"] for c in cards}):
        blocks = re.findall(rf"(?is)^\s*\.subckt\s+{model}\s+(.*?)^\s*\.ends", pdk_lib, re.M)
        if len(blocks) != 1:
            raise Refusal("PDK_MISMATCH_MODEL_AMBIGUOUS",
                          f"expected exactly one `.subckt {model}` in the PDK library, found {len(blocks)}")
        if "sw_stat_mismatch" not in blocks[0] or "agauss" not in blocks[0]:
            raise Refusal("PDK_MISMATCH_MODEL_MISSING",
                          f"`.subckt {model}` carries no sw_stat_mismatch-scaled agauss mismatch")
    got, want = device_multiset(adapted), device_multiset(schematic)
    if got != want:
        diff = {str(k): (got.get(k, 0), want.get(k, 0)) for k in set(got) | set(want)
                if got.get(k, 0) != want.get(k, 0)}
        raise Refusal("DEVICE_GEOMETRY_MISMATCH",
                      f"adapted (L, W) multiset differs from the schematic's (extracted, schematic): {diff}")
    return {"mos_devices": len(cards), "models": sorted({c["model"] for c in cards}),
            "card_form": "subckt call",
            "mismatch_switch": "sw_stat_mismatch (PDK subckt body scales delvto/mulu0)",
            "geometry_multiset_equals_schematic": True,
            "resistors": {f"{k[1]:g}/{k[2]:g}": v for k, v in got.items() if k[0] == pn.RES_MODEL}}


def check_body_bias(adapted: str, report: dict) -> dict:
    """Every NMOS bulk on the vss hub, every PMOS bulk on the vdd hub."""
    legs = pn.parse_top(adapted)["legs"]
    hub = lambda n: legs.get(n, n)  # noqa: E731
    bad = []
    for d in mos_cards(adapted):
        want = "vss" if d["model"] == "nfet_03v3" else "vdd"
        if hub(d["nets"]["b"]) != want:
            bad.append(f"{d['name']} ({d['model']}) bulk on {hub(d['nets']['b'])!r}, want {want!r}")
    if bad:
        raise Refusal("BODY_NOT_BIASED", "; ".join(bad))
    flagged = {k: report.get(k) for k in ("unbiased_pmos_body_nets", "missing_flavour_markers")
               if report.get(k)}
    if flagged:
        raise Refusal("EXTRACTION_BODY_WARNINGS", f"extraction report flags {flagged}")
    return {"nmos_bulk_hub": "vss", "pmos_bulk_hub": "vdd",
            "unbiased_pmos_body_nets": report.get("unbiased_pmos_body_nets"),
            "missing_flavour_markers": report.get("missing_flavour_markers")}


def observation_nodes(adapted: str, report: dict) -> dict:
    """Preamp output nodes from connectivity; every failure is a Refusal
    (missing, ambiguous, swapped labels, or disagreeing with the report)."""
    try:
        mapping = pn.derive(adapted)
        pn.crosscheck_labels(mapping)
        pn.crosscheck_report(mapping, report)
    except pn.MappingError as e:
        raise Refusal("OBSERVATION_NODES", str(e))
    nodes = pn.observation_nodes(mapping, INST_PREFIX)
    return {"aop": nodes["aop"]["hub"], "aon": nodes["aon"]["hub"],
            "derivation": "layout/pex/preamp_nodes.py structural rule (loads on vdd, "
                          "input-pair drains, one decision-stage gate each); labels and the "
                          "klt extract report cross-checked",
            "load_resistors": [mapping["aop"]["load_resistor"], mapping["aon"]["load_resistor"]]}


def check_report_identity(report: dict, raw_netlist: Path, klt_used: str | None) -> dict:
    """The raw netlist re-made for this run must be the one the committed
    extraction report documents."""
    want = report.get("netlist_sha256")
    got = sha256_file(raw_netlist)
    if got != want:
        raise Refusal("EXTRACTION_IDENTITY",
                      f"raw extracted netlist sha256 {got[:16]} != committed report "
                      f"netlist_sha256 {str(want)[:16]} (report klt "
                      f"{(report.get('provenance') or {}).get('klt_version')}, used {klt_used})")
    return {"raw_netlist_sha256": got, "report_netlist_sha256": want, "match": True}


def build_contract(adapted_text: str, schematic_text: str, pdk_lib: str, report: dict,
                   raw_netlist: Path, klt_used: str | None) -> tuple[dict, str]:
    """-> (the feasibility artifact body, the mismatch-capable netlist text)
    or a Refusal. The STANDARD adapter's output is checked first and its
    verdict recorded; the simulation netlist is the feasibility-only
    mismatch-capable variant, which must itself pass every check."""
    try:
        standard = {"status": "ok", **check_device_mismatch_support(adapted_text, schematic_text, pdk_lib)}
    except Refusal as e:
        standard = {"status": "REFUSED", "code": e.code, "reason": e.msg}
    variant = mismatch_capable(adapted_text)
    return {
        "identity": check_report_identity(report, raw_netlist, klt_used),
        "standard_adapter_mismatch_support": standard,
        "device_mismatch": check_device_mismatch_support(variant, schematic_text, pdk_lib),
        "body_bias": check_body_bias(variant, report),
        "observation_nodes": observation_nodes(adapted_text, report),
    }, variant


# ---------------------------------------------------------------------------
# stimulus
# ---------------------------------------------------------------------------

def stair_pwl(centre_v: float, v0_v: float, step_v: float, levels: int, t0_ns: float,
              period_ns: float, lead: int) -> str:
    """The `vsd` card of the staircase, level k at V = centre + v0 + k*step.

    Reproduces the committed schematic fragment's timing exactly at
    centre = 0: the level changes at t0 + c*T + 9 ns over 1 ns, cycles
    0..lead sit on level 0, the last three cycles on the last level."""
    lvl = lambda c: min(max(c - lead, 0), levels - 1)  # noqa: E731
    v = lambda k: centre_v + v0_v + k * step_v  # noqa: E731
    fmt = lambda x: f"{x * 1e3:.4f}m".replace("-0.0000m", "0.0000m")  # noqa: E731
    pts = [(0.0, v(0))]
    for c in range(lead + levels + 1):      # level changes at c = 0..66
        ta = t0_ns + c * period_ns + 9
        pts += [(ta, v(lvl(c))), (ta + 1, v(lvl(c + 1)))]
    toks = [f"{t:g}n {fmt(x)}" for t, x in pts]
    lines, cur = [], "vsd sd 0 pwl("
    for t in toks:
        if len(cur) + len(t) + 1 > 76:
            lines.append(cur)
            cur = "+ "
        cur += t + " "
    lines.append(cur.rstrip())
    lines.append("+ )")
    return "\n".join(lines)


def centre_from_probe(report: dict, request: dict, resolution_mv: float, vspan_mv: float) -> dict:
    """Validate a trip-point probe report and derive the staircase centre."""
    if request.get("monte_carlo"):
        raise Refusal("PROBE_NOT_MISMATCH_FREE", "the probe request carries a monte_carlo block")
    body = (request.get("_body") or "")
    if body and "sw_stat_mismatch=0" not in body.replace(" ", "") and ".param sw_stat_mismatch=1" in body:
        raise Refusal("PROBE_NOT_MISMATCH_FREE", "probe body enables sw_stat_mismatch")
    units = report.get("corners") or []
    if len(units) != 1:
        raise Refusal("PROBE_UNITS", f"expected exactly one probe unit, report has {len(units)}")
    u = units[0]
    if u.get("status") != "pass":
        raise Refusal("PROBE_FAILED", f"probe unit {u.get('corner_id')} status {u.get('status')!r}")
    vals = {m["name"]: m.get("value") for m in u.get("measurements", [])}
    for n in ("t_flip", "vos_v"):
        if not finite(vals.get(n)):
            raise Refusal("PROBE_NONFINITE", f"probe measurement {n} = {vals.get(n)!r} "
                          "(no decision flip inside the +-span ramp)")
    trip_mv = vals["vos_v"] * 1e3
    if abs(trip_mv) >= 0.95 * vspan_mv:
        raise Refusal("PROBE_AT_SPAN_EDGE", f"probed trip {trip_mv:.3f} mV is within 5% of the "
                      f"+-{vspan_mv} mV ramp span")
    centre_mv = round(trip_mv / resolution_mv) * resolution_mv
    return {"probe_unit": u.get("corner_id"), "trip_mv": trip_mv, "t_flip_s": vals["t_flip"],
            "centre_mv": round(centre_mv, 6), "centre_resolution_mv": resolution_mv}


# ---------------------------------------------------------------------------
# validation of a Monte-Carlo population
# ---------------------------------------------------------------------------

def tb_view(tb, centre_mv: float):
    """`derive_offset_tran` sees an ABSOLUTE staircase: stair_v0 = centre + rel v0."""
    params = dict(tb.params)
    params["stair_v0_mv"] = centre_mv + tb.params["stair_v0_mv"]
    return types.SimpleNamespace(params=params, measure=tb.measure, name=tb.name)


def trip_levels(tb, raw: dict) -> dict:
    """{sample: level k} (same arithmetic as derive_offset_tran) for draws
    that already passed its validation."""
    P = tb.params
    t0, T = P["stair_t0_ns"] * 1e-9, P["stair_period_ns"] * 1e-9
    return {s: math.floor((v["t_trip"] - t0) / T) - int(P["stair_lead_cycles"])
            for s, v in raw.items()}


def evaluate_population(tb, cid: str, raw: dict, centre_mv: float, probe_trip_mv: float,
                        n_requested: int) -> dict:
    """Validate one PVT point's draws and return the feasibility numbers, or
    raise Refusal listing every problem. `raw` = {sample: {ingredient: value}}."""
    problems: list[str] = []
    view = tb_view(tb, centre_mv)
    res = kr.derive_offset_tran(view, {cid: raw}, [cid], problems)
    if problems:
        raise Refusal("DRAW_VALIDATION", "; ".join(problems[:6])
                      + (f" (+{len(problems) - 6} more)" if len(problems) > 6 else ""))
    if cid not in res:
        raise Refusal("NO_RESULT", f"{cid}: no derived result")
    d = res[cid]
    if d["n_samples"] != n_requested:
        raise Refusal("SAMPLE_COUNT", f"{cid}: {d['n_samples']} valid draws, {n_requested} requested")
    if not d["sig_trip_raw_mv"] > 0:
        raise Refusal("MISMATCH_NOT_EXERCISED",
                      f"{cid}: zero trip-point spread over {d['n_samples']} draws "
                      "(mismatch is not reaching the adapted devices, or the staircase is too coarse)")
    P = tb.params
    levels, margin = int(P["stair_levels"]), int(P["edge_margin_steps"])
    ks = trip_levels(tb, raw).values()
    if min(ks) < margin or max(ks) > levels - 1 - margin:
        raise Refusal("EDGE_MARGIN", f"{cid}: trip levels {min(ks)}..{max(ks)} come within {margin} "
                      f"steps of the staircase ends (1..{levels - 1}): centre/range inadequate")
    step = P["stair_step_mv"]
    v_lo = centre_mv + P["stair_v0_mv"] + min(ks) * step - step / 2
    v_hi = centre_mv + P["stair_v0_mv"] + max(ks) * step - step / 2
    if not (v_lo - step <= probe_trip_mv <= v_hi + step):
        raise Refusal("PROBE_NOT_BRACKETED", f"{cid}: mismatch-free probe trip {probe_trip_mv:.3f} mV is "
                      f"outside the population's bracket [{v_lo:.3f}, {v_hi:.3f}] mV +- one step")
    return {
        "n_valid_draws": d["n_samples"],
        "trip_abs_mean_mv": d["trip_abs_mean_mv"],
        "sig_trip_mv": d["sig_trip_mv"],
        "sig_trip_raw_mv": d["sig_trip_raw_mv"],
        "trip_abs_min_mv": v_lo, "trip_abs_max_mv": v_hi,
        "trip_levels": [min(ks), max(ks)],
        "probe_trip_mv": probe_trip_mv,
        "centre_mv": centre_mv,
        "convention": "trip = differential input at which the decision flips (absolute, centre NOT "
                      "subtracted); input-referred offset = -trip; sigma is quantisation-corrected "
                      "population (ddof=0) sigma",
    }


# ---------------------------------------------------------------------------
# request generation
# ---------------------------------------------------------------------------

def dut_binding(outdir: Path, netlist: Path) -> Path:
    """A by-path binding json for the freshly adapted extracted netlist."""
    cfg = json.loads((SIM / "dut.json").read_text())["duts"]["comparator-dr0001-layout"]
    cfg = dict(cfg, netlist=str(netlist.resolve()))
    p = outdir / "dut-binding.json"
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    return p


def _require_point(point: str):
    if point not in POINTS:
        raise Refusal("POINT_NOT_ALLOWED", f"{point!r}: feasibility points are {sorted(POINTS)}")
    return POINTS[point]


def body_lines(tb, dut, vdd: float, sources: list[str], staged: dict, extra: list[str],
               options: list[str], fragment: str, single_thread: bool) -> list[str]:
    return [
        f"* {tb.name} -- GENERATED by sim/tools/extracted_tran_feasibility.py, do not edit",
        f"* FEASIBILITY ONLY. dut={dut.dut_id} ({dut.provenance}) sha256={dut.netlist_sha256[:16]}",
        *sources,
        f".param vdd_nom={tb.nominal_supply_v!r}",
        f".param vdd_val={vdd!r}",
        ".param temp_c=27.0",
        *dut.param_lines(),
        ".param dut_vos=0.0",
        *(f".param {k}={v}" for k, v in tb.params.items() if k.startswith("stair_")),
        *extra,
        '.include "design.ngspice"',
        *(f".options {o}" for o in options),
        f'.include "{staged["dut"]}"',
        f'.include "{staged["testbench_dir"]}/{fragment}"',
        *(mk.SINGLE_THREAD_CONTROL if single_thread else []),
        "",
    ]


def make_request(body_name: str, analysis: str, measurements: list[dict], corner: str,
                 temp: float, mc: dict | None) -> dict:
    kind, args = analysis.split(None, 1)
    from harness import corners as hc
    c = hc.resolve_corners([corner])[0]
    req = {
        "netlist": body_name, "engine": "ngspice",
        "models": {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"},
        "corners": {"process": [{"name": c.name, "sections": list(c.sections)}],
                    "temperature_c": [temp]},
        "batch": {"runner_version_check": "warn", "capacity_wait_s": mk.BATCH_CAPACITY_WAIT_S},
        "analysis": {"kind": kind, "args": args},
        "measurements": measurements,
        "options": {"timeout_s": 3000, "keep_artifacts": True, "ngspice_init": mk.NGSPICE_INIT},
    }
    if mc:
        req["monte_carlo"] = mc
    return req


def prepare(outdir: Path, point: str, leg: str, centre_mv: float | None = None,
            mc_n: int | None = None, adapted_netlist: Path | None = None) -> Path:
    """Write the request/body/bundle for one leg ('probe' or 'mc') of one point."""
    corner, temp, vdd = _require_point(point)
    outdir.mkdir(parents=True, exist_ok=True)
    tb = htb.load(SIM / BENCH)
    netlist = adapted_netlist or (outdir / "extract" / MM_NETLIST)
    if not netlist.is_file():
        raise Refusal("NO_ADAPTED_NETLIST", f"{netlist} missing: run the `contract` step first")
    binding_path = dut_binding(outdir, netlist)
    dut = hdut.load(path=binding_path)
    if dut.provenance != "extracted":
        raise Refusal("NOT_EXTRACTED", f"binding provenance is {dut.provenance!r}")
    binding = mk.binding_entry(str(binding_path))
    staged = mk.stage_sources(outdir, tb, dut, binding, str(binding_path))
    sources = mk.source_sha_lines(outdir)
    commit, dirty = mk.git_state(mk.source_paths(BENCH, binding[0], dut.netlist))
    pdk = hpdk.find_pdk()
    (outdir / "design.ngspice").write_text(Path(pdk.design_include).read_text())
    vtag = f"v{vdd:.2f}"
    tag = f"{leg}-{point}"
    extra: list[str] = []
    if leg == "probe":
        analyses = json.loads((tb.directory / "tb.json").read_text())["probe"]["analyses"]
        fragment, single = "tb_trip_probe.spice", False
        options, mc = PROBE_OPTIONS, None
    else:
        analyses, fragment, single = tb.analyses, "tb_offset_tran_extracted.spice", True
        options = tb.options
        if centre_mv is None or mc_n is None:
            raise Refusal("MC_ARGS", "mc leg needs a centre and a draw count")
        if not 1 <= mc_n <= MAX_MC_N:
            raise Refusal("MC_N_OUT_OF_SCOPE", f"mc_n {mc_n}: a feasibility probe is 1..{MAX_MC_N} "
                          "draws; a campaign needs its own proposal")
        # nodes are a function of connectivity, identical in both card forms;
        # derive from the STANDARD adapter's text (preamp_nodes parses `M` cards)
        adapted_text = (netlist.parent / "comparator.dut-layout.spice").read_text()
        report = json.loads(EXTRACT_REPORT.read_text())
        obs = observation_nodes(adapted_text, report)
        P = tb.params
        extra = [
            f".param stair_centre_mv={centre_mv!r}",
            stair_pwl(centre_mv * 1e-3, P["stair_v0_mv"] * 1e-3, P["stair_step_mv"] * 1e-3,
                      int(P["stair_levels"]), P["stair_t0_ns"], P["stair_period_ns"],
                      int(P["stair_lead_cycles"])),
            f"Eddprobe dd 0 {obs['aop']} {obs['aon']} 1",
            f"Eapo apo 0 {obs['aop']} 0 1",
        ]
    body = "\n".join(body_lines(tb, dut, vdd, sources, staged, extra, options, fragment, single))
    body_name = f"body-{tag}.spice"
    (outdir / body_name).write_text(body)
    cards = [{"name": ln.split()[2], "spice": "." + ln}
             for ln in analyses[1:]]
    mc = None if leg == "probe" else {"n": mc_n, "seed": SEED, "vary": "mismatch"}
    req = make_request(body_name, analyses[0], cards, corner, temp, mc)
    req_name = f"request-{tag}.json"
    (outdir / req_name).write_text(json.dumps(req, indent=2) + "\n")
    requests = {}
    plan_path = outdir / "plan.json"
    if bundle_path := outdir / mk.BUNDLE_NAME:
        if bundle_path.is_file():
            requests = json.loads(bundle_path.read_text()).get("requests", {})
    requests[tag] = {"leg": leg, "vdd": vdd, "request": req_name,
                     "request_sha256": mk.sha256_file(outdir / req_name),
                     "netlist": body_name, "netlist_sha256": mk.sha256_file(outdir / body_name)}
    mk.write_bundle(outdir, BENCH, tb, dut, binding, str(binding_path), staged, commit, dirty,
                    mk.source_paths(BENCH, binding[0], dut.netlist),
                    {"point": point, "mc_n": mc_n, "feasibility_only": True,
                     "centre_mv": centre_mv}, requests)
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else {}
    plan.setdefault(point, {})[leg] = {"request": req_name, "centre_mv": centre_mv, "mc_n": mc_n,
                                       "dirty_paths": dirty}
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    return outdir / req_name


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_contract(outdir: Path, klt_cmd: list[str] | None) -> dict:
    import run_extract_sim as res  # noqa: E402  (layout/ on sys.path)
    report = json.loads(EXTRACT_REPORT.read_text())
    want = (report.get("provenance") or {}).get("klt_version")
    if not want:
        raise Refusal("EXTRACTION_IDENTITY", "committed report records no klt_version")
    ex = outdir / "extract"
    ex.mkdir(parents=True, exist_ok=True)
    raw, adapted = ex / "comparator.extracted-rc.spice", ex / "comparator.dut-layout.spice"
    cmd = klt_cmd or ["uvx", "--from", f"klayout-tools=={want}", "klt"]
    proc = subprocess.run([*cmd, "extract", str(GDS.relative_to(REPO)), *KLT_EXTRACT_ARGS,
                           "-o", str(raw)], capture_output=True, text=True, cwd=REPO)
    if proc.returncode != 0:
        raise Refusal("EXTRACT_FAILED", proc.stderr.strip()[-400:])
    (ex / "comparator.extract-rc.rerun.json").write_text(proc.stdout)
    res._adapt_netlist(str(raw), str(adapted))
    res._check_interface_contract(str(adapted))
    pdk = hpdk.find_pdk()
    lib = Path(pdk.path) / "libs.tech/ngspice/sm141064.ngspice"
    contract, variant = build_contract(adapted.read_text(), SCHEMATIC.read_text(),
                                       lib.read_text(), report, raw, want)
    mm = ex / MM_NETLIST
    mm.write_text(variant)
    res._check_interface_contract(str(mm))
    art = {
        "feasibility_only": True,
        "issue": 219,
        "claim": "none: measurement-contract check; not signoff item 7, not a reference record",
        "extraction": {
            "gds_sha256": sha256_file(GDS), "raw_netlist_sha256": sha256_file(raw),
            "adapted_netlist_sha256": sha256_file(adapted),
            "simulated_netlist": f"extract/{MM_NETLIST} (feasibility-only mismatch-capable variant)",
            "simulated_netlist_sha256": sha256_file(mm),
            "report": str(EXTRACT_REPORT.relative_to(REPO)),
            "report_sha256": sha256_file(EXTRACT_REPORT), "klt_pinned_by_report": want},
        "contract": contract,
        "trip_convention": "absolute trip (centre not subtracted); mean and sigma separate",
        "executor": {"probe": "klt sim, single unit (local)",
                     "monte_carlo": "klt sim --backend batch (fleet); no local fallback",
                     "num_threads": 1},
        "withheld": {
            "same_draw_preamp_latch_decomposition": "not substantiated for the extracted netlist: "
                "Vos_pre extrapolates a linear gain over the layout's systematic offset from "
                "series-R hub nodes, never validated; gain is used only as a validity gate",
            "resistor_hand_budget": "not carried over: the schematic's rmis_* dimensions were "
                "matched against the extracted resistors "
                f"({contract['device_mismatch']['resistors']}) but the budget's vdrop/Av term needs "
                "the withheld same-draw gain",
        },
    }
    (outdir / "contract.json").write_text(json.dumps(art, indent=2) + "\n")
    return art


def cmd_evaluate(outdir: Path, point: str) -> dict:
    _require_point(point)
    plan = json.loads((outdir / "plan.json").read_text())[point]
    tb = htb.load(SIM / BENCH)
    corner, temp, vdd = POINTS[point]
    out = {"feasibility_only": True, "point": point, "mints_record": False}
    probe_req = json.loads((outdir / plan["probe"]["request"]).read_text())
    probe_rep = json.loads((outdir / f"report-probe-{point}.json").read_text())
    pc = centre_from_probe(probe_rep, probe_req, tb.params["centre_resolution_mv"],
                           tb.params["probe_vspan_mv"])
    out["probe"] = pc
    mcp = plan["mc"]
    if abs(mcp["centre_mv"] - pc["centre_mv"]) > 1e-9:
        raise Refusal("CENTRE_MISMATCH", f"plan centre {mcp['centre_mv']} != probe-derived {pc['centre_mv']}")
    body = (outdir / f"body-mc-{point}.spice").read_text()
    m = re.search(r"\.param stair_centre_mv=(\S+)", body)
    if not m or abs(float(m.group(1)) - pc["centre_mv"]) > 1e-9:
        raise Refusal("CENTRE_MISMATCH", "body netlist staircase centre differs from the probe's")
    req = json.loads((outdir / mcp["request"]).read_text())
    rep = json.loads((outdir / f"report-mc-{point}.json").read_text())
    got = kr._report_netlist_sha(rep)
    if got != mk.sha256_file(outdir / f"body-mc-{point}.spice"):
        raise Refusal("REPORT_UNLINKED", "report's netlist sha256 is not the submitted body's")
    collected, bad, issues = kr.collect_checked(rep, req, vdd, tag=point)
    if issues:
        raise Refusal("REPORT_COVERAGE", "; ".join(issues[:6]))
    cid = point
    out["population"] = evaluate_population(tb, cid, collected[cid], pc["centre_mv"],
                                            pc["trip_mv"], req["monte_carlo"]["n"])
    env = rep.get("environment") or {}
    out["executor"] = {"remote": env.get("remote"), "monte_carlo": env.get("monte_carlo"),
                       "engine_version": env.get("engine_version")}
    out["seed"], out["n"] = req["monte_carlo"]["seed"], req["monte_carlo"]["n"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("contract", "probe", "mc", "evaluate"):
        s = sub.add_parser(name)
        s.add_argument("outdir")
        if name != "contract":
            s.add_argument("--point", required=True)
        if name == "contract":
            s.add_argument("--klt-cmd", nargs="+", default=None)
        if name == "mc":
            s.add_argument("--probe-report", required=True)
            s.add_argument("--mc-n", type=int, default=20)
    a = ap.parse_args(argv)
    out = Path(a.outdir).resolve()
    try:
        if a.cmd == "contract":
            art = cmd_contract(out, a.klt_cmd)
            print(json.dumps(art["contract"], indent=2))
        elif a.cmd == "probe":
            print(prepare(out, a.point, "probe"))
        elif a.cmd == "mc":
            tb = htb.load(SIM / BENCH)
            plan_req = json.loads((out / f"request-probe-{a.point}.json").read_text())
            rep = json.loads(Path(a.probe_report).read_text())
            pc = centre_from_probe(rep, plan_req, tb.params["centre_resolution_mv"],
                                   tb.params["probe_vspan_mv"])
            (out / f"report-probe-{a.point}.json").write_text(json.dumps(rep, indent=2) + "\n")
            print(f"probe trip {pc['trip_mv']:.4f} mV -> centre {pc['centre_mv']} mV")
            print(prepare(out, a.point, "mc", centre_mv=pc["centre_mv"], mc_n=a.mc_n))
        else:
            try:
                res = cmd_evaluate(out, a.point)
            except Refusal as e:
                (out / f"refusal-{a.point}.json").write_text(json.dumps(
                    {"feasibility_only": True, "point": a.point, "published": False,
                     "code": e.code, "reason": e.msg}, indent=2) + "\n")
                raise
            (out / f"feasibility-{a.point}.json").write_text(json.dumps(res, indent=2) + "\n")
            print(json.dumps(res, indent=2))
    except Refusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
