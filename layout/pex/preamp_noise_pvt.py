#!/usr/bin/env python3
"""Paired schematic/extracted preamp noise over the 45-point PVT matrix (issue #209).

Extends the NOMINAL paired feasibility probe of issue #202
(`layout/pex/preamp_noise_probe.py`, evidence in
`layout/pex/artifacts/preamp-noise/`) to the bench's full grid: the `mos`
corner set (tt ff ss fs sf) x {-40, 27, 125} C x {2.97, 3.30, 3.63} V.

EXECUTION. The grid is a `klt sim` request set for the batch fleet; this
host never runs it. A request expresses the committed methodology in ONE
deck per unit through `analysis_steps` (klt #2482):

    op      operating point (bias anchor, both DC outputs)
    nfull   noise v(P,N) vd dec 20 1 1e9       -> onoise_total, inoise_total
    nhf     noise v(P,N) vd dec 20 1e3 1e9     -> onoise_total
    nwhite  noise v(P,N) vd lin 11 0.995e6 1.005e6 -> white density at 1 MHz
    ac      ac dec 20 1 1e9                    -> av_dc = |v(P)-v(N)| at 1 Hz

and the referral (`vn_in_uv` = nfull.onoise / ac.av_dc) as a derived `expr`
measurement. Those two request features (`analysis_steps`, `measurements[].
expr`) are what the fleet runner must support; a runner without them is
refused BEFORE any corner runs (`batch.runner_version_check: enforce`) and
the campaign stops with UNSUPPORTED_EXECUTOR_CAPABILITY. There is no local
substitute for the grid.

White density. A step-scoped expression evaluates against the step's own
totals plot, so the 1 MHz bin of the spectrum plot (the bench's
`noise1.onoise_spectrum[120]`) is not addressable from a request; `nwhite`
integrates a 10 kHz band centred on 1 MHz instead and divides by
sqrt(10 kHz). On the nominal reproduction that agrees with the spectrum bin
to well inside the tolerance below.

SOURCES. Identical to issue #202 and pinned to it: the schematic leg is
`design/comparator.spice` (sha256 = #202's schematic identity), the extracted
leg is the committed adapted netlist
`layout/pex/artifacts/preamp-noise/comparator.dut-layout.cir` (sha256 =
#202's `results.extracted.dut_sha256`), observed at #202's connectivity-
derived hub nodes. Same stimulus lines (taken from #202's own deck builder),
same `dut_ib`/`dut_vcm` (`sim/dut.json`, both entries), fnoicor = PDK default,
mismatch off, clk held low. The like-for-like schematic leg carries NO 10 fF
routing allowance (extraction supplies the loading); the bench's allowance
is the committed `sim/comparator-preamp-noise/` record, cited, not re-run.

SCOPE. Reset-state `.noise` measures the PREAMP (with the real latch gate
load). It EXCLUDES the latch's regenerative noise and is not whole-
comparator decision noise. Nothing here scores a spec row or promotes T1.

    python3 layout/pex/preamp_noise_pvt.py requests OUTDIR [--nominal]
    python3 layout/pex/preamp_noise_pvt.py probe OUTDIR --backend local|batch [--legs ...]
    python3 layout/pex/preamp_noise_pvt.py campaign OUTDIR --probe-report REPORT
    python3 layout/pex/preamp_noise_pvt.py ingest OUTDIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "sim"))
sys.path.insert(0, str(REPO / "sim" / "tools"))

import preamp_noise_probe as pnp  # noqa: E402
from harness import corners as hc  # noqa: E402

ISSUE = 209
NOMINAL_DIR = REPO / "layout" / "pex" / "artifacts" / "preamp-noise"
NOMINAL_RECORD = NOMINAL_DIR / "record.json"
EXTRACTED_DUT = NOMINAL_DIR / "comparator.dut-layout.cir"
SCHEMATIC_DUT = REPO / "design" / "comparator.spice"
TB_JSON = REPO / "sim" / "comparator-preamp-noise" / "testbench" / "tb.json"
DUT_JSON = REPO / "sim" / "dut.json"

BUNDLE_NAME = "source-bundle.json"
BUNDLE_SCHEMA = "gf180-comparator/preamp-noise-pvt-bundle"
BUNDLE_VERSION = 1
SUMMARY_NAME = "paired-summary.json"
SOURCE_SHA_PREFIX = "* source-sha256 "

#: The two legs of the pair. `record_case` names the issue-#202 result whose
#: DUT identity and nominal values this leg must reproduce.
LEGS = ("schematic", "extracted")
LEG_SPEC = {
    "schematic": {"dut": SCHEMATIC_DUT, "record_case": "schematic_croute0",
                  "nodes": ("xdut.aop", "xdut.aon"), "c_route": "0"},
    "extracted": {"dut": EXTRACTED_DUT, "record_case": "extracted",
                  "nodes": None, "c_route": "0"},  # nodes: from #202's mapping
}

#: Runner features a request uses: `analysis_steps` (klt #2482) and
#: `measurements[].expr` (klt #2533). Both ship in the 0.7.0 client.
MIN_RUNNER_KLT = (0, 7, 0)
#: Seconds `klt sim --backend batch` keeps retrying a Spot capacity refusal.
BATCH_CAPACITY_WAIT_S = 1800
NGSPICE_INIT = ["set measureprec=12", "set numdgt=12"]
#: Pin ngspice to one device-evaluation thread per unit (issue #157).
SINGLE_THREAD_CONTROL = [".control", "set num_threads=1", ".endc"]

WHITE_BAND = (0.995e6, 1.005e6)
WHITE_BW_HZ = WHITE_BAND[1] - WHITE_BAND[0]

#: Relative agreement the request-expressed method must reach against the
#: committed #202 nominal values (`record.json`) at tt/27 C/3.30 V. 1e-4 is
#: ~400x the worst observed disagreement (2.5e-7, the band-integrated white
#: density vs #202's single spectrum bin; every other quantity agrees to
#: <= 3e-11), and still far below any PVT spread this campaign resolves.
NOMINAL_TOLERANCE_REL = 1e-4
#: Relative agreement between klt's derived referral and the referral
#: recomputed here from the same unit's raw step values.
REFERRAL_TOLERANCE_REL = 1e-6
#: The bench's sanity floor (tb.json checks.av_dc.min): below unity gain the
#: divide-by-gain referral is meaningless.
MIN_GAIN = 1.0

#: quantity -> (record.json key suffix, how it is computed from raw values)
QUANTITIES = ("av_dc", "onoise_uv", "onoise_hf_uv", "vn_in_uv", "vn_in_hf_uv",
              "inoise_band_uv", "white_nv_rthz", "enbw_mhz")
#: quantities that must be finite AND positive at every corner of both legs
REQUIRED_POSITIVE = QUANTITIES + ("vbias_anchor_mv",)

EXCLUSION = ("Reset-state `.noise` about the clk-low operating point: the preamp's thermal "
             "and flicker noise with the real latch gate load, referred by the measured DC "
             "gain. It EXCLUDES the latch's regenerative noise (no operating point to "
             "linearise about during regeneration) and is NOT whole-comparator decision "
             "noise; it cannot by itself complete T1 item 7.")
PROMOTION = ("No T1 promotion, spec-row verdict or signoff input follows from this summary, "
             "complete or not; a partial-coverage result is never presented as complete.")


class Refusal(SystemExit):
    """A named, fail-closed stop (code + message)."""

    def __init__(self, name: str, message: str):
        super().__init__(f"{name}: {message}")
        self.name = name


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p) -> str:
    return sha256_bytes(Path(p).read_bytes())


def finite_positive(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) and v > 0)


# --------------------------------------------------------------------------- #
# Executor capability
# --------------------------------------------------------------------------- #

def parse_klt_version(text) -> tuple[int, int, int] | None:
    """'0.7.0+g5e5b55' / 'klt 0.5.0' -> (0, 7, 0); None when unparseable."""
    if not isinstance(text, str):
        return None
    for tok in text.replace("klt", " ").split():
        parts = tok.split("+", 1)[0].split(".")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return tuple(int(p) for p in parts)
    return None


def executor_capability_gap(runner_version, client_version=None) -> str | None:
    """None when a runner at `runner_version` can execute these requests,
    else the precise missing capability. Under `runner_version_check:
    enforce` the runner must also equal the submitting client exactly."""
    v = parse_klt_version(runner_version)
    need = ".".join(map(str, MIN_RUNNER_KLT))
    if v is None or v < MIN_RUNNER_KLT:
        return (f"fleet runner klt {runner_version!r} cannot execute the paired preamp-noise "
                "request: it needs `analysis_steps` (klt #2482; ordered op/noise/noise/noise/ac "
                "solves in one deck) and `measurements[].expr` (klt #2533; onoise_total, "
                "inoise_total and the measured-gain referral nfull.onoise/ac.av_dc), because "
                "ngspice has no `.meas noise` and a `.meas`-only runner cannot read a noise "
                f"integral (klt #2938). Needs a runner with klt >= {need}.")
    if client_version is not None and runner_version != client_version:
        return (f"fleet runner klt {runner_version!r} != submitting client {client_version!r}; "
                "the request is submitted with runner_version_check=enforce, so a mismatched "
                "runner is refused before simulating rather than allowed to drop request keys")
    return None


def runner_identity(report: dict) -> list[dict]:
    remote = (report.get("environment") or {}).get("remote")
    if isinstance(remote, dict):
        return remote.get("fleet") or [remote]
    return remote if isinstance(remote, list) else []


def check_executor(report: dict) -> list[str]:
    """UNSUPPORTED_EXECUTOR_CAPABILITY issues for one fleet report."""
    err = report.get("error")
    if isinstance(err, dict):
        return [f"UNSUPPORTED_EXECUTOR_CAPABILITY: fleet refused the request before simulating: "
                f"{err.get('code')}: {err.get('message')}"]
    runners = runner_identity(report)
    if not runners:
        return ["UNSUPPORTED_EXECUTOR_CAPABILITY: report names no fleet runner (environment.remote)"]
    issues = []
    # The runner's own refusal text (a preflight rejection lands as a
    # per-corner batch_job_failed diagnostic carrying runner_code).
    refusals = {f"{d.get('runner_code')}: {d.get('message')}"
                for c in report.get("corners") or [] for d in c.get("diagnostics") or []
                if isinstance(d, dict) and d.get("runner_code")}
    issues += [f"UNSUPPORTED_EXECUTOR_CAPABILITY: fleet refused the request: {m}"
               for m in sorted(refusals)]
    for r in runners:
        r = r if isinstance(r, dict) else {}
        gap = executor_capability_gap(r.get("runner_klt_version"))
        if gap:
            issues.append(f"UNSUPPORTED_EXECUTOR_CAPABILITY: {gap}")
        elif r.get("runner_compatibility") != "match":
            issues.append("UNSUPPORTED_EXECUTOR_CAPABILITY: runner_compatibility "
                          f"{r.get('runner_compatibility')!r}, not 'match'")
    return issues


# --------------------------------------------------------------------------- #
# Request shape
# --------------------------------------------------------------------------- #

def stimulus_lines() -> list[str]:
    """The circuit lines (sources, stimulus, the whole DUT in reset) of
    #202's own deck builder, sliced out of its output so the two can never
    drift apart. No routing allowance, no observation-specific line."""
    fake = SimpleNamespace(design_include="@PDK@", model_lib="@LIB@")
    deck = pnp.build_deck("x", "@DUT@", fake, [("hub", "p", "n")], "0", None,
                          {"dut_ib": 0, "dut_vcm": 0}).splitlines()
    start = deck.index('.include "@DUT@"') + 1
    stop = deck.index(".control")
    return [line for line in deck[start:stop] if line.strip()]


def stimulus_sha256() -> str:
    return sha256_bytes("\n".join(stimulus_lines()).encode())


def analysis_steps(p: str, n: str) -> list[dict]:
    out = f"v({p},{n})"
    return [
        {"name": "op", "analysis": {"kind": "op", "args": ""},
         "measurements": [{"name": "vbias_mv", "expr": "v(ibn)*1e3"},
                          {"name": "dc_p", "expr": f"v({p})"},
                          {"name": "dc_n", "expr": f"v({n})"}]},
        {"name": "nfull", "analysis": {"kind": "noise", "args": f"{out} vd dec 20 1 1e9"},
         "measurements": [{"name": "onoise", "expr": "onoise_total"},
                          {"name": "inoise", "expr": "inoise_total"}]},
        {"name": "nhf", "analysis": {"kind": "noise", "args": f"{out} vd dec 20 1e3 1e9"},
         "measurements": [{"name": "onoise", "expr": "onoise_total"}]},
        {"name": "nwhite", "analysis": {"kind": "noise",
                                        "args": f"{out} vd lin 11 {WHITE_BAND[0]:g} {WHITE_BAND[1]:g}"},
         "measurements": [{"name": "onoise", "expr": "onoise_total"}]},
        {"name": "ac", "analysis": {"kind": "ac", "args": "dec 20 1 1e9"},
         "measurements": [{"name": "av_dc", "expr": f"mag(v({p})-v({n}))[0]"}]},
    ]


def derived_measurements() -> list[dict]:
    bw = f"{WHITE_BW_HZ:g}"
    return [
        {"name": "vn_in_uv", "expr": "nfull.onoise/ac.av_dc*1e6"},
        {"name": "vn_in_hf_uv", "expr": "nhf.onoise/ac.av_dc*1e6"},
        {"name": "onoise_uv", "expr": "nfull.onoise*1e6"},
        {"name": "onoise_hf_uv", "expr": "nhf.onoise*1e6"},
        {"name": "inoise_band_uv", "expr": "nfull.inoise*1e6"},
        {"name": "white_nv_rthz", "expr": f"nwhite.onoise/sqrt({bw})*1e9"},
        {"name": "enbw_mhz", "expr": f"nfull.onoise^2/(nwhite.onoise^2/{bw})/1e6"},
    ]


def build_request(body: str, process: list[dict], temps: list[float], nodes: tuple[str, str]) -> dict:
    return {
        "netlist": body,
        "engine": "ngspice",
        "models": {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"},
        "corners": {"process": process, "temperature_c": temps},
        # A runner that cannot honour analysis_steps/expr must refuse BEFORE
        # simulating, never drop the keys and return something else.
        "batch": {"runner_version_check": "enforce", "capacity_wait_s": BATCH_CAPACITY_WAIT_S},
        "analysis_steps": analysis_steps(*nodes),
        "measurements": derived_measurements(),
        "options": {"timeout_s": 900, "keep_artifacts": True, "ngspice_init": NGSPICE_INIT},
    }


def body_text(leg: str, vdd: float, params: dict, dut_rel: str, source_lines: list[str]) -> str:
    L = [f"* preamp-noise-pvt leg={leg} -- GENERATED by layout/pex/preamp_noise_pvt.py "
         f"(issue #{ISSUE}), do not edit",
         *source_lines,
         f".param vdd_nom={pnp.VDD!r}", f".param vdd_val={vdd!r}", ".param temp_c=27.0",
         *(f".param {k}={v!r}" for k, v in sorted(params.items())),
         '.include "design.ngspice"',
         f'.include "{dut_rel}"',
         *stimulus_lines(),
         *SINGLE_THREAD_CONTROL, ""]
    return "\n".join(L)


def leg_nodes(leg: str, record: dict) -> tuple[str, str]:
    if LEG_SPEC[leg]["nodes"]:
        return LEG_SPEC[leg]["nodes"]
    obs = record["observation_nodes_extracted"]
    return obs["aop"]["hub"], obs["aon"]["hub"]


def grid(nominal: bool) -> dict:
    tb = json.loads(TB_JSON.read_text())
    if nominal:
        names, temps, vdds = ["tt"], [pnp.TEMP_C], [pnp.VDD]
    else:
        names = [c.name for c in hc.resolve_corners(tb["corners"])]
        temps = [float(t) for t in tb["temperatures_c"]]
        vdds = hc.supply_points(tb["nominal_supply_v"], tb["supply_tolerance"])
    sections = {c.name: list(c.sections) for c in hc.resolve_corners(names)}
    return {"process": names, "process_sections": sections,
            "temperatures_c": temps, "supply_v": vdds}


def expected_corners(g: dict) -> set[str]:
    return {corner_key(p, t, v) for p in g["process"] for t in g["temperatures_c"]
            for v in g["supply_v"]}


def corner_key(process: str, temp: float, vdd: float) -> str:
    return f"{process}_{float(temp):g}c_{float(vdd):.2f}v"


def git_state(paths: list[str]) -> tuple[str, list[str]]:
    def git(*a):
        return subprocess.check_output(["git", "-C", str(REPO), *a], text=True)
    sha = git("rev-parse", "HEAD").strip()
    status = git("status", "--porcelain", "--untracked-files=all", "--", *paths)
    return sha, [line[3:] for line in status.splitlines() if line.strip()]


def pinned_identity(record: dict) -> dict:
    res = record["results"]
    return {"record": str(NOMINAL_RECORD.relative_to(REPO)),
            "record_sha256": sha256_file(NOMINAL_RECORD),
            "schematic": res[LEG_SPEC["schematic"]["record_case"]]["dut_sha256"],
            "extracted": res[LEG_SPEC["extracted"]["record_case"]]["dut_sha256"],
            "params": record["point"]["dut_params"]}


def write_request_set(out: Path, nominal: bool, legs=LEGS) -> dict:
    """Stage sources, bodies and requests into `out`; write the bundle."""
    from harness.pdk import find_pdk
    record = json.loads(NOMINAL_RECORD.read_text())
    pin = pinned_identity(record)
    duts = json.loads(DUT_JSON.read_text())["duts"]
    params = duts["comparator-dr0001"]["params"]
    if params != duts["comparator-dr0001-layout"]["params"] or params != pin["params"]:
        raise Refusal("BIAS_MISMATCH", "sim/dut.json schematic/layout params differ from each "
                      "other or from the #202 record's dut_params")
    for leg in legs:
        got = sha256_file(LEG_SPEC[leg]["dut"])
        if got != pin[leg]:
            raise Refusal("SOURCE_IDENTITY_MISMATCH", f"{leg} DUT {LEG_SPEC[leg]['dut']} sha256 "
                          f"{got[:16]} != #202 identity {pin[leg][:16]}")
    out.mkdir(parents=True, exist_ok=True)
    src = out / "sources"
    if src.exists():
        shutil.rmtree(src)
    src.mkdir()
    staged_dut = {}
    for leg in legs:
        rel = f"sources/{leg}/{LEG_SPEC[leg]['dut'].name}"
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(LEG_SPEC[leg]["dut"], out / rel)
        staged_dut[leg] = rel
    shutil.copyfile(find_pdk().design_include, out / "design.ngspice")
    g = grid(nominal)
    process = [{"name": p, "sections": g["process_sections"][p]} for p in g["process"]]
    requests = {}
    for leg in legs:
        src_lines = [f"{SOURCE_SHA_PREFIX}{sha256_file(out / staged_dut[leg])} {staged_dut[leg]}"]
        nodes = leg_nodes(leg, record)
        for vdd in g["supply_v"]:
            tag = f"{leg}-v{vdd:.2f}"
            body = f"body-{tag}.spice"
            (out / body).write_text(body_text(leg, vdd, params, staged_dut[leg], src_lines))
            req = build_request(body, process, g["temperatures_c"], nodes)
            (out / f"request-{tag}.json").write_text(json.dumps(req, indent=2) + "\n")
            requests[tag] = {"leg": leg, "vdd": vdd, "request": f"request-{tag}.json",
                             "request_sha256": sha256_file(out / f"request-{tag}.json"),
                             "netlist": body, "netlist_sha256": sha256_file(out / body)}
    # Sources only: never the output tree itself (it is being written).
    commit, dirty = git_state(["design", "layout/pex/preamp_noise_pvt.py",
                               "layout/pex/preamp_noise_probe.py",
                               "layout/pex/artifacts/preamp-noise", "sim/dut.json",
                               "sim/harness", "sim/comparator-preamp-noise/testbench"])
    files = sorted({out / "design.ngspice"} | {out / r["request"] for r in requests.values()}
                   | {out / r["netlist"] for r in requests.values()}
                   | {p for p in src.rglob("*") if p.is_file()})
    bundle = {
        "schema": BUNDLE_SCHEMA, "version": BUNDLE_VERSION,
        "generator": "layout/pex/preamp_noise_pvt.py", "issue": ISSUE,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "origin": {"commit": commit, "dirty": bool(dirty), "dirty_paths": dirty},
        "nominal_only": nominal,
        "params": params,
        "grid": g,
        "stimulus_sha256": stimulus_sha256(),
        "pinned_identity": pin,
        "legs": {leg: {"dut_source": str(LEG_SPEC[leg]["dut"].relative_to(REPO)),
                       "dut_sha256": sha256_file(LEG_SPEC[leg]["dut"]),
                       "staged_dut": staged_dut[leg], "observation": list(leg_nodes(leg, record)),
                       "c_route": LEG_SPEC[leg]["c_route"]} for leg in legs},
        "requests": requests,
        "staged": {p.relative_to(out).as_posix(): sha256_file(p) for p in files},
    }
    (out / BUNDLE_NAME).write_text(json.dumps(bundle, indent=1) + "\n")
    return bundle


# --------------------------------------------------------------------------- #
# Validation (pure: bundle dict + report dicts -> rows + issues)
# --------------------------------------------------------------------------- #

def raw_corner_id(raw: str) -> tuple[str, float]:
    parts = raw.split("/")
    temp = next(float(x[:-1]) for x in parts[1:] if x.endswith("C"))
    return parts[0], temp


def values_from_corner(c: dict) -> dict[str, float]:
    return {m["name"]: m["value"] for m in c.get("measurements", []) if m.get("value") is not None}


def quantities(v: dict) -> tuple[dict, list[str]]:
    """Raw step values of one unit -> (quantities, gain-referral issues).

    Every referral is RECOMPUTED here from the same unit's raw step values
    and must equal klt's derived value; a referral to some other gain (or a
    stale/derived value that does not follow from the raw ingredients) is a
    GAIN_REFERRAL_MISMATCH, never a result."""
    issues = []
    raw = {k: v.get(k) for k in ("ac.av_dc", "nfull.onoise", "nfull.inoise", "nhf.onoise",
                                 "nwhite.onoise", "op.vbias_mv", "op.dc_p", "op.dc_n")}
    missing = [k for k, x in raw.items() if not finite_positive(x)]
    if missing:
        return {}, [f"NONFINITE_OR_NONPOSITIVE: raw {', '.join(f'{k}={raw[k]!r}' for k in missing)}"]
    av = raw["ac.av_dc"]
    white = raw["nwhite.onoise"] / math.sqrt(WHITE_BW_HZ)
    q = {"av_dc": av,
         "onoise_uv": raw["nfull.onoise"] * 1e6,
         "onoise_hf_uv": raw["nhf.onoise"] * 1e6,
         "vn_in_uv": raw["nfull.onoise"] / av * 1e6,
         "vn_in_hf_uv": raw["nhf.onoise"] / av * 1e6,
         "inoise_band_uv": raw["nfull.inoise"] * 1e6,
         "white_nv_rthz": white * 1e9,
         "enbw_mhz": raw["nfull.onoise"] ** 2 / white ** 2 / 1e6,
         "vbias_anchor_mv": raw["op.vbias_mv"],
         "dc_p_v": raw["op.dc_p"], "dc_n_v": raw["op.dc_n"]}
    if av < MIN_GAIN:
        issues.append(f"GAIN_BELOW_UNITY: av_dc={av!r} < {MIN_GAIN}; the divide-by-gain "
                      "referral is meaningless")
    for k in ("vn_in_uv", "vn_in_hf_uv", "onoise_uv", "onoise_hf_uv", "inoise_band_uv",
              "white_nv_rthz", "enbw_mhz"):
        got = v.get(k)
        if not finite_positive(got):
            issues.append(f"NONFINITE_OR_NONPOSITIVE: {k}={got!r}")
        elif abs(got - q[k]) > REFERRAL_TOLERANCE_REL * abs(q[k]):
            issues.append(f"GAIN_REFERRAL_MISMATCH: reported {k}={got!r} but the unit's own raw "
                          f"values give {q[k]!r}")
    if raw["nhf.onoise"] > raw["nfull.onoise"]:
        issues.append(f"NOISE_BAND_INCONSISTENT: >1 kHz noise {raw['nhf.onoise']!r} exceeds the "
                      f"full-band total {raw['nfull.onoise']!r}")
    return q, issues


def check_requests(bundle: dict, requests: dict[str, dict]) -> list[str]:
    """Every request must be the canonical one for its leg/supply, over the
    bundle's grid; the legs must share grid, stimulus and bias."""
    issues = []
    g = bundle["grid"]
    process = [{"name": p, "sections": g["process_sections"][p]} for p in g["process"]]
    for tag, r in sorted(bundle["requests"].items()):
        req = requests.get(tag)
        if req is None:
            issues.append(f"REQUEST_MISSING: {tag}")
            continue
        leg = r["leg"]
        want = build_request(r["netlist"], process, g["temperatures_c"],
                             tuple(bundle["legs"][leg]["observation"]))
        for key in ("corners", "analysis_steps", "measurements", "batch", "netlist"):
            if req.get(key) != want[key]:
                issues.append(f"REQUEST_MISMATCH: {tag} {key} is not the canonical paired request")
    legs_present = {r["leg"] for r in bundle["requests"].values()}
    if legs_present != set(LEGS):
        issues.append(f"LEG_MISSING: bundle legs {sorted(legs_present)} != {list(LEGS)}")
    vdds = {leg: sorted(r["vdd"] for r in bundle["requests"].values() if r["leg"] == leg)
            for leg in legs_present}
    if len({tuple(v) for v in vdds.values()}) > 1:
        issues.append(f"GRID_MISMATCH: legs request different supplies {vdds}")
    if bundle.get("stimulus_sha256") != stimulus_sha256():
        issues.append("STIMULUS_MISMATCH: bundle stimulus differs from #202's deck builder")
    pin = bundle.get("pinned_identity") or {}
    if bundle.get("params") != pin.get("params"):
        issues.append(f"BIAS_MISMATCH: bundle params {bundle.get('params')!r} != #202 "
                      f"{pin.get('params')!r}")
    for leg, spec in (bundle.get("legs") or {}).items():
        if spec.get("dut_sha256") != pin.get(leg):
            issues.append(f"SOURCE_IDENTITY_MISMATCH: {leg} DUT sha256 "
                          f"{str(spec.get('dut_sha256'))[:16]} != #202 identity {str(pin.get(leg))[:16]}")
        if bundle.get("staged", {}).get(spec.get("staged_dut")) != spec.get("dut_sha256"):
            issues.append(f"SOURCE_IDENTITY_MISMATCH: staged {leg} DUT is not the declared DUT")
    return issues


def report_netlist_sha(report: dict) -> str | None:
    env = report.get("environment") or {}
    if env.get("netlist_sha256"):
        return env["netlist_sha256"]
    h = ((report.get("provenance") or {}).get("input") or {}).get("content_hash") or ""
    return h.split(":", 1)[1] if h.startswith("sha256:") else None


def collect_leg(bundle: dict, reports: dict[str, dict], leg: str,
                require_fleet: bool = True) -> tuple[dict, list[str]]:
    """-> ({corner_key: {quantities..., source}}, issues) for one leg."""
    issues: list[str] = []
    rows: dict[str, dict] = {}
    want = expected_corners(bundle["grid"])
    failed: set[str] = set()
    for tag, r in sorted(bundle["requests"].items()):
        if r["leg"] != leg:
            continue
        rep = reports.get(tag)
        if rep is None:
            issues.append(f"REPORT_MISSING: {tag} has no report")
            continue
        if require_fleet:
            issues += [f"{tag}: {i}" for i in check_executor(rep)]
        if isinstance(rep.get("error"), dict):
            continue
        got = report_netlist_sha(rep)
        if got is None:
            issues.append(f"REPORT_UNLINKED: {tag} report carries no simulated-netlist sha256")
            continue
        if got != r["netlist_sha256"]:
            issues.append(f"REPORT_SOURCE_MISMATCH: {tag} report simulated {got[:16]}, bundled "
                          f"body is {r['netlist_sha256'][:16]}")
            continue
        seen: set[str] = set()
        for c in rep.get("corners") or []:
            raw = c.get("corner_id", "")
            try:
                proc, temp = raw_corner_id(raw)
            except StopIteration:
                issues.append(f"UNEXPECTED_CORNER: {tag} {raw!r} is not a process/temperature id")
                continue
            key = corner_key(proc, temp, r["vdd"])
            if raw in seen or key in rows:
                issues.append(f"DUPLICATE_CORNER: {leg} {key} ({tag} {raw}) appears more than once")
                continue
            seen.add(raw)
            if key not in want:
                issues.append(f"UNEXPECTED_CORNER: {leg} {key} ({tag} {raw}) is not in the grid")
                continue
            if c.get("status") != "pass":
                failed.add(key)
                issues.append(f"FAILED_UNIT: {leg} {key} ({tag} {raw}) -> {c.get('status')}")
                continue
            q, bad = quantities(values_from_corner(c))
            if bad:
                failed.add(key)
                issues += [f"{leg} {key}: {b}" for b in bad]
                continue
            q["source"] = {"request": r["request"], "report": f"report-{tag}.json",
                           "netlist_sha256": got, "corner_id": raw}
            rows[key] = q
    for key in sorted(want - set(rows) - failed):
        issues.append(f"MISSING_CORNER: {leg} {key} has no result")
    return rows, issues


def pct(a: float, b: float) -> float:
    return (a - b) / b * 100.0


def pair(schem: dict, extr: dict) -> dict[str, dict]:
    """Per-corner extracted-vs-schematic deltas, each citing both sources."""
    out = {}
    for key in sorted(set(schem) & set(extr)):
        s, e = schem[key], extr[key]
        out[key] = {
            "schematic": {k: s[k] for k in QUANTITIES},
            "extracted": {k: e[k] for k in QUANTITIES},
            "delta_pct": {k: pct(e[k], s[k]) for k in ("av_dc", "vn_in_uv", "vn_in_hf_uv",
                                                       "white_nv_rthz", "enbw_mhz",
                                                       "inoise_band_uv")},
            "sources": {"schematic": s["source"], "extracted": e["source"]},
        }
    return out


def binding_corners(paired: dict) -> dict:
    """The corners that bind each reading, with their sources."""
    if not paired:
        return {}

    def pick(label, fn, best):
        key = best(paired, key=lambda k: fn(paired[k]))
        return {"what": label, "corner": key, "value": fn(paired[key]),
                "sources": paired[key]["sources"]}
    return {
        "max_extracted_vn_in_uv": pick("highest extracted vn_in_uv",
                                       lambda r: r["extracted"]["vn_in_uv"], max),
        "max_schematic_vn_in_uv": pick("highest like-for-like schematic vn_in_uv",
                                       lambda r: r["schematic"]["vn_in_uv"], max),
        "max_delta_vn_in_pct": pick("largest (least negative) extracted-vs-schematic vn_in change",
                                    lambda r: r["delta_pct"]["vn_in_uv"], max),
        "max_delta_white_pct": pick("largest white-density change",
                                    lambda r: r["delta_pct"]["white_nv_rthz"], max),
        "min_extracted_av_dc": pick("lowest extracted gain",
                                    lambda r: r["extracted"]["av_dc"], min),
    }


def validate_campaign(bundle: dict, requests: dict[str, dict], reports: dict[str, dict],
                      require_fleet: bool = True) -> dict:
    """The paired summary. `verdict` is "complete" ONLY when both legs carry
    exactly the expected corners, every source/referral check passes, and
    (for a fleet campaign) every runner is supported; otherwise "incomplete"
    with every reason listed. Never a spec or T1 verdict."""
    issues = check_requests(bundle, requests)
    want = expected_corners(bundle["grid"])
    if bundle.get("nominal_only") or len(want) != 45:
        issues.append(f"COVERAGE_INCOMPLETE: the bundle's grid has {len(want)} corners, not the "
                      "45-point PVT matrix")
    legs = {}
    for leg in LEGS:
        rows, bad = collect_leg(bundle, reports, leg, require_fleet)
        legs[leg] = rows
        issues += bad
    for leg in LEGS:
        if set(legs[leg]) != want:
            issues.append(f"COVERAGE_INCOMPLETE: {leg} has {len(legs[leg])}/{len(want)} valid corners")
    paired = pair(legs["schematic"], legs["extracted"])
    complete = not issues
    return {
        "issue": ISSUE,
        "verdict": "complete" if complete else "incomplete",
        "issues": issues,
        "coverage": {leg: f"{len(legs[leg])}/{len(want)}" for leg in LEGS},
        "grid": bundle["grid"],
        "params": bundle.get("params"),
        "pinned_identity": bundle.get("pinned_identity"),
        "legs": bundle.get("legs"),
        "per_corner": paired,
        "binding_corners": binding_corners(paired) if complete else {},
        "scope": {"excludes": EXCLUSION, "promotion": PROMOTION, "t1_promotion": False,
                  "spec_row_verdict": None,
                  "schematic_allowance": "The like-for-like schematic leg has NO 10 fF routing "
                  "allowance; the bench's 10 fF-allowance numbers are the committed "
                  "sim/comparator-preamp-noise/ records and are not the like-for-like "
                  "comparison. Extracted capacitance supplies the extracted leg's loading.",
                  "bandwidth_note": "Report gain, noise, white density AND ENBW together: a "
                  "lower vn_in from heavier extracted loading is a narrower noise bandwidth, "
                  "not a quieter preamp.",
                  "disclosures": "Body bias: preamp NMOS bulks and resistor substrate resolve "
                  "to vss (#202 mapping). Extraction: first-order lumped RC per net, no lateral "
                  "coupling, distributed_rc false (#202 record identity)."},
    }


# --------------------------------------------------------------------------- #
# Work-dir I/O
# --------------------------------------------------------------------------- #

def verify_staged(work: Path, bundle: dict) -> None:
    if bundle.get("schema") != BUNDLE_SCHEMA or bundle.get("version") != BUNDLE_VERSION:
        raise Refusal("SOURCE_BUNDLE_UNSUPPORTED", f"{work}/{BUNDLE_NAME} is not a "
                      f"{BUNDLE_SCHEMA} v{BUNDLE_VERSION} bundle")
    for rel, want in sorted((bundle.get("staged") or {}).items()):
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            raise Refusal("SOURCE_BUNDLE_INCONSISTENT", f"staged path {rel!r} escapes the work dir")
        f = work / p
        if not f.is_file():
            raise Refusal("STAGED_SOURCE_MISSING", f"{rel} listed in the bundle but absent")
        if sha256_file(f) != want:
            raise Refusal("STAGED_SOURCE_TAMPERED", f"{rel} no longer has its recorded sha256")
    for tag, r in bundle["requests"].items():
        for k in ("request", "netlist"):
            if bundle["staged"].get(r[k]) != r[f"{k}_sha256"]:
                raise Refusal("SOURCE_BUNDLE_INCONSISTENT", f"{tag} {k} identity is not staged")


def load_work(work: Path) -> tuple[dict, dict, dict]:
    bundle = json.loads((work / BUNDLE_NAME).read_text())
    verify_staged(work, bundle)
    requests = {t: json.loads((work / r["request"]).read_text()) for t, r in bundle["requests"].items()}
    reports = {}
    for t in bundle["requests"]:
        p = work / f"report-{t}.json"
        if p.is_file() and p.read_text().strip():
            reports[t] = json.loads(p.read_text())
    return bundle, requests, reports


def run_klt(work: Path, tags: list[str], backend: str) -> dict[str, int]:
    """Run `klt sim` on the named requests; each report lands in report-<tag>.json."""
    rcs = {}
    procs = {t: subprocess.Popen(
        ["klt", "sim", "--backend", backend, "--format", "json", "-o", str(work / f"out-{t}"),
         str(work / f"request-{t}.json")],
        stdout=(work / f"report-{t}.json").open("w"), stderr=(work / f"stderr-{t}.txt").open("w"))
        for t in tags}
    for t, p in procs.items():
        rcs[t] = p.wait()
    return rcs


def nominal_comparison(bundle: dict, reports: dict) -> dict:
    """Request-expressed nominal values vs #202's committed record."""
    record = json.loads(NOMINAL_RECORD.read_text())
    out = {"tolerance_rel": NOMINAL_TOLERANCE_REL, "legs": {}, "within_tolerance": True}
    for leg in LEGS:
        rows, issues = collect_leg(bundle, reports, leg, require_fleet=False)
        ref = record["results"][LEG_SPEC[leg]["record_case"]]["values"]
        key = corner_key("tt", pnp.TEMP_C, pnp.VDD)
        row = rows.get(key)
        cmp = {}
        if row is None:
            out["within_tolerance"] = False
        else:
            for q in QUANTITIES:
                r = ref[f"m_hub_{q}"]
                d = (row[q] - r) / r
                cmp[q] = {"request": row[q], "record_202": r, "rel": d,
                          "ok": abs(d) <= NOMINAL_TOLERANCE_REL}
                out["within_tolerance"] &= cmp[q]["ok"]
        out["legs"][leg] = {"comparison": cmp, "issues": issues,
                            "source": row["source"] if row else None}
    return out


def _bare(issue: str) -> str:
    prefix = "UNSUPPORTED_EXECUTOR_CAPABILITY: "
    return issue[len(prefix):] if issue.startswith(prefix) else issue


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("requests", help="stage the request set (no simulation)")
    a.add_argument("outdir")
    a.add_argument("--nominal", action="store_true", help="tt/27 C/3.30 V only (the probe)")
    a = sub.add_parser("probe", help="ONE nominal unit per leg: request expressibility + executor")
    a.add_argument("outdir")
    a.add_argument("--backend", choices=("local", "batch"), required=True)
    a.add_argument("--legs", nargs="*", default=list(LEGS))
    a = sub.add_parser("campaign", help="the 45-point paired grid on the batch fleet")
    a.add_argument("outdir")
    a.add_argument("--probe-report", required=True,
                   help="report of a nominal FLEET probe proving the runner's capability")
    a = sub.add_parser("ingest", help="validate reports and write the paired summary")
    a.add_argument("outdir")
    args = ap.parse_args()
    out = Path(args.outdir).resolve()

    if args.cmd == "requests":
        b = write_request_set(out, args.nominal)
        print(f"wrote {len(b['requests'])} requests to {out}")
        return 0

    if args.cmd == "probe":
        b = write_request_set(out, nominal=True)
        tags = [t for t, r in b["requests"].items() if r["leg"] in args.legs]
        rcs = run_klt(out, tags, args.backend)
        bundle, _, reports = load_work(out)
        summary = {"issue": ISSUE, "backend": args.backend, "klt_rc": rcs,
                   "client_klt": subprocess.run(["klt", "--version"], capture_output=True,
                                                text=True).stdout.strip()}
        if args.backend == "batch":
            summary["executor"] = {t: {"runner": runner_identity(reports[t]) if t in reports else None,
                                       "issues": check_executor(reports[t]) if t in reports
                                       else [f"REPORT_MISSING: {t}"]} for t in tags}
            summary["supported"] = not any(v["issues"] for v in summary["executor"].values())
        if set(tags) == {t for t in b["requests"]} and not any(
                isinstance(reports.get(t, {}).get("error"), dict) for t in tags):
            summary["nominal_vs_202"] = nominal_comparison(bundle, reports)
        (out / "probe-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=1, sort_keys=True))
        if args.backend == "batch" and not summary["supported"]:
            issues = [i for v in summary["executor"].values() for i in v["issues"]]
            raise Refusal("UNSUPPORTED_EXECUTOR_CAPABILITY", "; ".join(map(_bare, issues)))
        return 0

    if args.cmd == "campaign":
        probe = json.loads(Path(args.probe_report).read_text())
        gap = check_executor(probe)
        if gap:
            # Stop BEFORE anything is staged or submitted; no local grid.
            raise Refusal("UNSUPPORTED_EXECUTOR_CAPABILITY", "; ".join(map(_bare, gap)))
        if os.environ.get("KLT_SIM_BACKEND") != "batch":
            raise Refusal("LOCAL_GRID_REFUSED", "KLT_SIM_BACKEND is not 'batch'; the 45-point "
                          "grid is never run on a shared dispatch worker")
        b = write_request_set(out, nominal=False)
        run_klt(out, sorted(b["requests"]), "batch")
        args.cmd = "ingest"

    if args.cmd == "ingest":
        bundle, requests, reports = load_work(out)
        summary = validate_campaign(bundle, requests, reports)
        (out / SUMMARY_NAME).write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print(f"verdict: {summary['verdict']} coverage {summary['coverage']}")
        for i in summary["issues"][:40]:
            print(f"  {i}")
        return 0 if summary["verdict"] == "complete" else 3
    return 2


if __name__ == "__main__":
    sys.exit(main())
