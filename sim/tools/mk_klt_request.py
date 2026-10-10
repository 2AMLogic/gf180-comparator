#!/usr/bin/env python3
"""Emit `klt sim` requests for the four benches, derived from their tb.json.

Why this exists: `sim/run_corners.py` fans ngspice out from the invoking
host. Shared dispatch workers must not run SPICE grids themselves; they
express the grid as a `klt sim` request and let `KLT_SIM_BACKEND=batch` send
it to the Spot fleet. The request is derived from the bench's own `tb.json`,
`sim/dut.json` and `sim/harness/corners.py`, so the corner list, supply
points, DUT binding, fragment and measurement definitions are the harness's,
not a second hand-maintained copy.

One `klt sim` request carries ONE analysis, so a bench becomes one or more
"legs":

    comparator-kickback     leg `main`  (tran + .meas cards)
    comparator-regeneration leg `main`  (tran + .meas cards)
    comparator-preamp-noise leg `noise` (noise 1 Hz..1 GHz), leg `ac` (gain)
    comparator-offset-mc    leg `main`  (monte_carlo, one dc sweep per draw)
    comparator-offset-tran  leg `main`  (monte_carlo, one clocked staircase
                            transient per draw; issue #157)
    comparator-offset-cm-index
                            leg `main` (monte_carlo, one monotonic-index dc
                            sweep `vidx 0 5 1` per draw, raw `.meas dc ...
                            at=k` cards; issue #218)
    comparator-offset-cm-window
                            REFUSED (UNSUPPORTED_EXECUTOR_CAPABILITY, issue
                            #182): the six-point same-draw request is
                            specified by `cm_window_leg`, but the fleet
                            runner cannot address the nested sweep's points

Derived quantities (`tb.json` "measure") are computed from the raw per-leg
values by `sim/tools/klt_record.py`; the `.meas` cards / expressions below
are the raw ingredients.

    python3 sim/tools/mk_klt_request.py BENCH OUTDIR [--corners ...]
        [--temps ...] [--supply-tolerance F] [--mc-n N] [--dut ID|BINDING.json]

`--dut` selects a `sim/dut.json` entry by id (default: the `active`, ratified
binding) or loads a binding json by path -- e.g. `--dut
comparator-dr0004-cascode-exp` for the proposed DR-0004 cascode experiment
netlist, which deliberately is NOT design/comparator.spice.

Source bundle (issue #151). Alongside the requests, OUTDIR receives a
versioned `source-bundle.json` and a `sources/` tree: byte copies of the
selected DUT netlist, the bench's whole `testbench/` directory (fragment,
`tb.json` manifest with the `measure` expressions, any probe fragment) and
the selected DUT binding entry. The body netlists `.include` those STAGED
copies (relative paths), so what the fleet simulates is exactly what the
bundle hashes, and carry a `* source-sha256 <hex> <path>` comment per staged
file, so the body's own sha256 (which a fleet report quotes) binds the
included sources' CONTENT, not just their file names. The bundle names the originating commit, the dirty state of
every source the run depends on, the selected DUT and its parameters, and
the sha256 of every staged file. `klt_record.py` mints records from this
bundle -- never from whatever the checkout holds at ingest time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
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
from harness import pdk as hpdk  # noqa: E402
from harness import testbench as htb  # noqa: E402

#: ngspice 46 prints `.meas` results with 5 mantissa decimals by default;
#: widen so sub-microvolt kickback differences are not quantised away.
NGSPICE_INIT = ["set measureprec=12", "set numdgt=12"]

OFFSET_MC_SEED = 20260909
OFFSET_MC_N = 200
#: Seconds `klt sim --backend batch` keeps re-launching after a
#: `batch_no_capacity` refusal (request.batch.capacity_wait_s).
BATCH_CAPACITY_WAIT_S = 1800
#: Benches whose requests carry a `monte_carlo` block.
MC_BENCHES = ("comparator-offset-mc", "comparator-offset-tran", "comparator-offset-cm-window",
              "comparator-offset-cm-index")

#: Supplemental consumer-window common-mode bench (issue #182). Separately
#: named: comparator-offset-mc's +-50 mV bench and records are untouched.
CM_WINDOW_BENCH = "comparator-offset-cm-window"
#: ONE nested dc analysis per draw: `vd` is the inner (fast) sweep, `vcmd`
#: the outer one, so ngspice's flattened vectors are ordered 2*j + i.
CM_WINDOW_DC_ARGS = "vd 0 2m 2m vcmd -100m 100m 100m"
CM_WINDOW_VD_STEP_V = 2e-3
#: label -> (common-mode delta vcmd [V], differential stimulus vd [V], index
#: into the nested sweep's vectors). The identity of every reported value.
CM_WINDOW_POINTS = {
    "dn_0": (-0.1, 0.0, 0), "dn_2m": (-0.1, 2e-3, 1),
    "mid_0": (0.0, 0.0, 2), "mid_2m": (0.0, 2e-3, 3),
    "up_0": (0.1, 0.0, 4), "up_2m": (0.1, 2e-3, 5),
}
#: Per point: the differential output and BOTH coordinates read back from the
#: same solve, so a report's labels can be checked against what was simulated.
CM_WINDOW_QUANTITIES = {"dv": "v(dd)[{k}]", "xcm": "v(cm)[{k}]-v(cmb)[{k}]", "xvd": "v(vd)[{k}]"}
#: `measurements[].expr` (klt #2533) first shipped in klt 0.7.0; a `.meas dc
#: ... at=` card can only search the inner sweep's scale and so cannot name
#: the outer coordinate (it returns the first outer slice).
CM_WINDOW_MIN_RUNNER_KLT = (0, 7, 0)
#: The fleet runner's klt as reported in environment.remote.runner_klt_version
#: by every batch record in this repository through 2026-10-10.
FLEET_RUNNER_KLT_OBSERVED = "0.5.0"


#: Monotonic-index variant of the consumer-window bench (issue #218). A SEPARATE
#: bench: the nested-sweep bench above keeps its refused/expr contract, and
#: historical sources are not rewritten. ONE source `vidx` is swept 0..5 in
#: unit steps and behavioural sources map each index k to the same (vcmd, vd)
#: pair as CM_WINDOW_POINTS[label][2], so a raw `.meas dc ... find ... at=<k>`
#: names each point unambiguously on a klt 0.5.0 runner (no `expr` needed).
CM_INDEX_BENCH = "comparator-offset-cm-index"
CM_INDEX_DC_ARGS = "vidx 0 5 1"
#: Per quantity, the single node a `.meas` card reads (a 0.5.0 `.meas` cannot
#: evaluate v(a)-v(b), so the fragment provides `xcm` = v(cm)-v(cmb) as a probe).
CM_INDEX_NODES = {"dv": "v(dd)", "xcm": "v(xcm)", "xvd": "v(vd)"}


def cm_index_measurements() -> list[dict]:
    """The 18 raw `.meas dc` cards of the index request, label-major. Each
    names one index `at=<k>` of the one monotonic scale, so no card can
    address a coordinate other than the one its label says."""
    return [{"name": f"{q}_{label}",
             "spice": f".meas dc {q}_{label} find {CM_INDEX_NODES[q]} at={k}"}
            for label, (_, _, k) in CM_WINDOW_POINTS.items()
            for q in CM_INDEX_NODES]


def cm_index_leg(mc_n: int) -> dict:
    """ONE `dc vidx 0 5 1` analysis per draw; all six points are one solve
    sequence of one instance of one mismatch draw."""
    return {
        "analysis": {"kind": "dc", "args": CM_INDEX_DC_ARGS},
        "measurements": cm_index_measurements(),
        "monte_carlo": {"n": mc_n, "seed": OFFSET_MC_SEED, "vary": "mismatch"},
    }


def parse_klt_version(text) -> tuple[int, int, int] | None:
    """'0.7.0+g5e5b55' / 'klt 0.5.0' -> (0, 7, 0); None when unparseable."""
    if not isinstance(text, str):
        return None
    for tok in text.replace("klt", " ").split():
        parts = tok.split("+", 1)[0].split(".")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return tuple(int(p) for p in parts)
    return None


def cm_window_capability_gap(runner_version) -> str | None:
    """None when a fleet runner at `runner_version` can execute the six-point
    request, else the exact missing capability (issue #182)."""
    v = parse_klt_version(runner_version)
    if v is not None and v >= CM_WINDOW_MIN_RUNNER_KLT:
        return None
    return (f"fleet runner klt {runner_version!r} cannot address the six points of the nested sweep "
            f"`dc {CM_WINDOW_DC_ARGS}`: it accepts only `.meas` cards (`measurements[].spice`; an "
            "`expr` entry is refused with \"each request.measurements[] entry requires 'name' and "
            "'spice'\"), and `.meas dc ... at=` searches only the inner `vd` scale, so it cannot "
            "select the outer `vcmd` coordinate. Needs a runner with `measurements[].expr` (klt >= "
            f"{'.'.join(map(str, CM_WINDOW_MIN_RUNNER_KLT))}, klt #2533). Full consumer-window "
            "coverage stays pending; see sim/comparator-offset-cm-window/README.md")


def cm_window_measurements() -> list[dict]:
    """The 18 `expr` entries of the six-point request, label-major."""
    return [{"name": f"{q}_{label}", "expr": tmpl.format(k=k)}
            for label, (_, _, k) in CM_WINDOW_POINTS.items()
            for q, tmpl in CM_WINDOW_QUANTITIES.items()]


def cm_window_leg(mc_n: int) -> dict:
    """The supported-path leg (issue #182): ONE dc analysis per draw whose
    six points are all read from the same solve. Used only once a runner
    with `expr` is established; until then `main` refuses."""
    return {
        "analysis": {"kind": "dc", "args": CM_WINDOW_DC_ARGS},
        "measurements": cm_window_measurements(),
        "monte_carlo": {"n": mc_n, "seed": OFFSET_MC_SEED, "vary": "mismatch"},
    }

#: Pin ngspice to ONE OpenMP device-evaluation thread per unit (issue #157).
#: The batch job runs one ngspice per physical core, so any extra threads
#: per process oversubscribe the instance. A same-deck fleet probe ran
#: ~422 s/unit at 8 concurrent units against ~5 s for one local unit
#: (2AMLogic/klayout-tools#2970). The request has no thread knob (the 0.5.0
#: runner drops `options.ngspice_init`, klt #2917), so the body netlist carries
#: its own `.control` block. ngspice runs every `.control` block in deck order,
#: and the body is `.include`d ahead of klt's own `.control ... tran`, so the
#: `set` lands before CKTsetup reads `num_threads`. It is not a circuit element
#: and does not change what is simulated, only how many threads simulate it.
SINGLE_THREAD_BENCHES = ("comparator-offset-tran",)
SINGLE_THREAD_CONTROL = [".control", "set num_threads=1", ".endc"]

#: The source bundle written beside the requests (issue #151).
BUNDLE_NAME = "source-bundle.json"
BUNDLE_SCHEMA = "gf180-comparator/klt-source-bundle"
BUNDLE_VERSION = 2  # v2: body netlists declare the staged sources' sha256
SOURCES_DIR = "sources"
#: Body-netlist comment line binding one staged source's bytes (issue #151):
#: `* source-sha256 <hex> <path relative to OUTDIR>`. Every file under
#: sources/ gets one, so the body's own hash -- the one a fleet report quotes
#: as environment.netlist_sha256 -- changes with any staged source's content,
#: not only with its file name.
SOURCE_SHA_PREFIX = "* source-sha256 "


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_sha256(obj) -> str:
    """sha256 of a JSON value in a key-order/whitespace independent form."""
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())


def repo_rel(path: Path, repo: Path = REPO) -> str | None:
    """Repo-relative posix path, or None for a file outside the repository."""
    try:
        return Path(path).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return None


def binding_entry(dut_arg: str | None) -> tuple[Path, str | None, dict]:
    """The DUT binding `--dut` selects, as written in its config file.

    -> (config path, selected key or None for a single-binding file, entry).
    Mirrors harness.dut.load's selection rule; the raw entry (not the parsed
    Dut) is what the bundle hashes, so a params edit is visible."""
    if dut_arg and Path(dut_arg).is_file():
        config, select = Path(dut_arg).resolve(), None
    else:
        config, select = hdut.DUT_CONFIG, dut_arg
    doc = json.loads(config.read_text())
    if "duts" in doc:
        key = select or doc.get("active")
        return config, key, doc["duts"][key]
    return config, None, doc


def source_paths(bench: str, binding_config: Path, dut_netlist: Path) -> list[str]:
    """Every source a `bench` run depends on, for the dirty check.

    The selected experiment's `testbench/` (NOT the whole `sim/<bench>/`:
    its `records/`, `corners/` and `netlist-snapshots/` are generated
    evidence output), the DUT binding config and netlist, plus the design
    and the request/ingest tooling. A source outside the repository is
    returned as an absolute path; git cannot vouch for it."""
    paths = ["design", "sim/tools", "sim/harness", f"sim/{bench}/testbench"]
    for p in (binding_config, dut_netlist):
        rel = repo_rel(p)
        paths.append(rel if rel is not None else str(Path(p).resolve()))
    return list(dict.fromkeys(paths))


def git_state(paths: list[str], repo: Path = REPO) -> tuple[str, list[str]]:
    """-> (HEAD commit, dirty source paths) for the sources a run depends on.

    Dirty means modified, staged, untracked, or not tracked at all (a
    gitignored or out-of-repo source has no committed identity)."""
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True)

    sha = git("rev-parse", "HEAD").strip()
    inside = [p for p in paths if not Path(p).is_absolute()]
    dirty = [f"{p} (outside the repository)" for p in paths if Path(p).is_absolute()]
    if inside:
        status = git("status", "--porcelain", "--untracked-files=all", "--", *inside)
        dirty += [line[3:] for line in status.splitlines() if line.strip()]
    for p in inside:
        if (Path(repo) / p).is_file() and not git("ls-files", "--", p).strip():
            if not any(d == p for d in dirty):
                dirty.append(f"{p} (not tracked)")
    return sha, dirty


def stage_sources(out: Path, tb, dut, binding: tuple[Path, str | None, dict], selector: str | None) -> dict:
    """Copy the DUT, testbench and binding into OUTDIR/sources/ -> paths."""
    src = out / SOURCES_DIR
    if src.exists():
        shutil.rmtree(src)  # our own generated subtree; never stale sources
    (src / "dut").mkdir(parents=True)
    (src / "testbench").mkdir()
    staged_dut = src / "dut" / dut.netlist.name
    staged_dut.write_bytes(dut.netlist.read_bytes())
    for f in sorted(tb.directory.iterdir()):
        if f.is_file():
            (src / "testbench" / f.name).write_bytes(f.read_bytes())
    config, key, entry = binding
    (src / "dut-binding.json").write_text(json.dumps({
        "config": repo_rel(config) or str(config), "selector": selector,
        "key": key, "entry": entry,
    }, indent=2, sort_keys=True) + "\n")
    return {
        "dut": f"{SOURCES_DIR}/dut/{dut.netlist.name}",
        "testbench_dir": f"{SOURCES_DIR}/testbench",
        "testbench_netlist": f"{SOURCES_DIR}/testbench/{tb.netlist.name}",
        "binding": f"{SOURCES_DIR}/dut-binding.json",
    }


def source_sha_lines(out: Path) -> list[str]:
    """One SOURCE_SHA_PREFIX comment per staged file under OUTDIR/sources/."""
    return [f"{SOURCE_SHA_PREFIX}{sha256_file(p)} {p.relative_to(out).as_posix()}"
            for p in sorted((out / SOURCES_DIR).rglob("*")) if p.is_file()]


def declared_source_shas(body_text: str) -> dict[str, str]:
    """Body netlist text -> {staged path: sha256} from its source-sha256 lines."""
    got: dict[str, str] = {}
    for line in body_text.splitlines():
        if line.startswith(SOURCE_SHA_PREFIX):
            h, _, rel = line[len(SOURCE_SHA_PREFIX):].partition(" ")
            got[rel] = h
    return got


def tran_meas_cards(tb) -> list[dict]:
    """`meas tran ...` analysis lines -> klt `.meas` measurement entries."""
    out = []
    for line in tb.analyses[1:]:
        parts = line.split()
        if parts[0] != "meas":
            raise SystemExit(f"{tb.name}: unexpected analysis card {line!r}")
        out.append({"name": parts[2], "spice": "." + line})
    return out


def legs_for(bench: str, tb, mc_n: int) -> dict[str, dict]:
    """leg name -> {analysis, measurements, monte_carlo?}."""
    if bench in ("comparator-kickback", "comparator-regeneration"):
        kind, args = tb.analyses[0].split(None, 1)
        return {"main": {"analysis": {"kind": kind, "args": args},
                         "measurements": tran_meas_cards(tb)}}
    # The fleet runner's klt (0.5.0) accepts only `{name, spice}` measurement
    # entries (no `expr` algebra), so every leg below is expressed as raw
    # `.meas` cards; the derived quantities are computed by klt_record.py.
    if bench == "comparator-preamp-noise":
        raise SystemExit(
            "comparator-preamp-noise cannot be expressed for the fleet runner: its klt "
            "(0.5.0) has no `noise` analysis / `.meas noise`. Run it as a single "
            "nominal point with sim/run_corners.py instead (see sim/tools/README note "
            "in the DR); file/track the tool gap at 2AMLogic/klayout-tools."
        )
    if bench == "comparator-offset-tran":
        # Whole-comparator transient Monte Carlo: ONE staircase transient per
        # draw; the `.meas` cards in tb.json are the raw ingredients, and
        # klt_record.py derives the trip point / same-draw preamp offset.
        kind, args = tb.analyses[0].split(None, 1)
        return {"main": {"analysis": {"kind": kind, "args": args},
                         "measurements": tran_meas_cards(tb),
                         "monte_carlo": {"n": mc_n, "seed": OFFSET_MC_SEED, "vary": "mismatch"}}}
    if bench == "comparator-offset-mc":
        # Two operating points at vcmd = 0 (the bench's offset point `voa`):
        # vd = 0 and vd = 2 mV, from one `dc` sweep of one draw (same-draw
        # gain). The bench's +-50 mV CM-step points (ddc/dde/drr controls)
        # are not requested -- see the record's "Not computed" line.
        m = [
            {"name": "dv0", "spice": ".meas dc dv0 find v(dd) at=0"},
            {"name": "dv1", "spice": ".meas dc dv1 find v(dd) at=2m"},
        ]
        return {"main": {
            "analysis": {"kind": "dc", "args": "vd 0 2m 2m"},
            "measurements": m,
            "monte_carlo": {"n": mc_n, "seed": OFFSET_MC_SEED, "vary": "mismatch"},
        }}
    if bench == CM_WINDOW_BENCH:
        gap = cm_window_capability_gap(FLEET_RUNNER_KLT_OBSERVED)
        if gap:
            raise SystemExit(f"UNSUPPORTED_EXECUTOR_CAPABILITY: {gap}")
        return {"main": cm_window_leg(mc_n)}
    if bench == CM_INDEX_BENCH:
        return {"main": cm_index_leg(mc_n)}
    raise SystemExit(f"unknown bench {bench!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("outdir")
    ap.add_argument("--corners", nargs="*", default=None)
    ap.add_argument("--temps", nargs="*", type=float, default=None)
    ap.add_argument("--supply-tolerance", type=float, default=None)
    ap.add_argument("--mc-n", type=int, default=OFFSET_MC_N)
    ap.add_argument("--dut", default=None)
    a = ap.parse_args()

    if a.bench == CM_WINDOW_BENCH:
        # Refused BEFORE anything is staged (issue #182): no request set,
        # bundle or body is written for a capability the fleet lacks.
        gap = cm_window_capability_gap(FLEET_RUNNER_KLT_OBSERVED)
        if gap:
            raise SystemExit(f"UNSUPPORTED_EXECUTOR_CAPABILITY: {gap}")
    tb = htb.load(SIM / a.bench)
    pdk = hpdk.find_pdk()
    dut = hdut.load(path=a.dut) if a.dut and Path(a.dut).is_file() else hdut.load(select=a.dut)
    if dut.provenance != "schematic":
        raise SystemExit("mk_klt_request.py supports the schematic binding only "
                         "(dut_vos probe leg is not implemented)")
    out = Path(a.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    binding = binding_entry(a.dut)
    checked = source_paths(a.bench, binding[0], dut.netlist)
    commit, dirty_paths = git_state(checked)
    staged = stage_sources(out, tb, dut, binding, a.dut)
    source_shas = source_sha_lines(out)

    corner_list = hc.resolve_corners(a.corners or list(tb.corners))
    tol = tb.supply_tolerance if a.supply_tolerance is None else a.supply_tolerance
    vdds = hc.supply_points(tb.nominal_supply_v, tol)
    temps = list(a.temps) if a.temps else [float(t) for t in tb.temperatures_c]

    def body_for(vdd: float) -> list[str]:
      return [
        f"* {tb.name} -- GENERATED by sim/tools/mk_klt_request.py, do not edit",
        f"* dut={dut.dut_id} ({dut.provenance}) sha256={dut.netlist_sha256[:16]}",
        # Content binding of every staged source (issue #151): the `.include`
        # lines below name files, these lines name their bytes.
        *source_shas,
        f".param vdd_nom={tb.nominal_supply_v!r}",
        f".param vdd_val={vdd!r}",
        ".param temp_c=27.0",
        *dut.param_lines(),
        # The harness injects dut_vos (0 for a schematic DUT, the probed
        # trip-point offset for an extracted one). Only the schematic
        # binding is supported here; an extracted DUT needs the probe leg.
        ".param dut_vos=0.0",
        # differential probe for the dc `.meas` cards (the 0.5.0 runner cannot
        # evaluate v(a)-v(b) inside .meas); a high-Z VCVS, no loading.
        *(["Eddprobe dd 0 aop aon 1"] if a.bench == "comparator-offset-mc" else []),
        *(f".param {k}={v}" for k, v in tb.params.items()),
        # A copy of the PDK's design.ngspice, staged with the request: an
        # off-host runner does not expand the harness's absolute PDK path.
        '.include "design.ngspice"',
        *(f".options {o}" for o in tb.options),
        # The STAGED copies (issue #151), relative like design.ngspice: the
        # bytes simulated are the bytes the source bundle hashes, not a
        # checkout path that can change before the record is minted.
        f'.include "{staged["dut"]}"',
        f'.include "{staged["testbench_netlist"]}"',
        *(SINGLE_THREAD_CONTROL if a.bench in SINGLE_THREAD_BENCHES else []),
        "",
    ]
    (out / "design.ngspice").write_text(Path(pdk.design_include).read_text())
    requests: dict[str, dict] = {}

    # One request (and one body netlist with `.param vdd_val=<V>` baked in)
    # PER SUPPLY POINT. A `corners.supply_v` sweep cannot be used: it works by
    # ngspice `alter <source>=V`, which (a) is refused for the clock's pulse
    # source and (b) would leave the testbench's {vdd_val}-scaled clock
    # amplitude / vdda rail at nominal. An `alter vdd_val=...` on the .param
    # name is a silent no-op -- an earlier revision of this tool did exactly
    # that and produced supply-independent "45-corner" records.
    process = [{"name": c.name, "sections": list(c.sections)} for c in corner_list]
    for vdd in vdds:
        vtag = f"v{vdd:.2f}"
        (out / f"body-{vtag}.spice").write_text("\n".join(body_for(vdd)))
        for leg, spec in legs_for(a.bench, tb, a.mc_n).items():
            req = {
                "netlist": f"body-{vtag}.spice",
                "engine": "ngspice",
                "models": {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"},
                "corners": {"process": process, "temperature_c": temps},
                # The fleet image's klt can lag the submitting client; run anyway
                # and let the record state the runner/client versions it saw.
                # A Spot capacity refusal is retried with the client's own
                # backoff for up to BATCH_CAPACITY_WAIT_S instead of being
                # terminal on the first refusal (issue #157; klt #2721).
                # The six-point request depends on `expr`, which an older
                # runner may not honour: it must be refused BEFORE simulating
                # (`enforce`), never detected after the fact (issue #182).
                "batch": {"runner_version_check": "enforce" if a.bench == CM_WINDOW_BENCH else "warn",
                          "capacity_wait_s": BATCH_CAPACITY_WAIT_S},
                "analysis": spec["analysis"],
                "measurements": spec["measurements"],
                "options": {
                    "timeout_s": 3000,
                    "keep_artifacts": True,
                    "ngspice_init": NGSPICE_INIT,
                },
            }
            if "monte_carlo" in spec:
                req["monte_carlo"] = spec["monte_carlo"]
            (out / f"request-{leg}-{vtag}.json").write_text(json.dumps(req, indent=2) + "\n")
            requests[f"{leg}-{vtag}"] = {
                "leg": leg, "vdd": vdd,
                "request": f"request-{leg}-{vtag}.json",
                "request_sha256": sha256_file(out / f"request-{leg}-{vtag}.json"),
                "netlist": f"body-{vtag}.spice",
                "netlist_sha256": sha256_file(out / f"body-{vtag}.spice"),
            }
            n = len(corner_list) * len(temps) * (a.mc_n if "monte_carlo" in spec else 1)
            print(f"wrote {out}/request-{leg}-{vtag}.json ({n} units)")
    write_bundle(out, a.bench, tb, dut, binding, a.dut, staged, commit, dirty_paths, checked, {
        "corners": [c.name for c in corner_list], "temperatures_c": temps,
        "supply_tolerance": tol, "supply_v": vdds,
        "mc_n": a.mc_n if a.bench in MC_BENCHES else None,
    }, requests)
    print(f"wrote {out}/{BUNDLE_NAME} (commit {commit[:7]}"
          + (f", DIRTY: {', '.join(dirty_paths)})" if dirty_paths else ", clean)"))
    return 0


def write_bundle(out: Path, bench: str, tb, dut, binding, selector, staged: dict,
                 commit: str, dirty_paths: list[str], checked: list[str],
                 parameters: dict, requests: dict) -> dict:
    """Write OUTDIR/source-bundle.json: the source identity of this request set.

    `staged` maps every generated input (requests, bodies, the PDK include
    copy, every file under sources/) to its sha256; ingestion re-hashes them
    and refuses on any difference before it publishes anything."""
    config, key, entry = binding
    files = sorted(
        {out / "design.ngspice"}
        | {out / r["request"] for r in requests.values()}
        | {out / r["netlist"] for r in requests.values()}
        | {p for p in (out / SOURCES_DIR).rglob("*") if p.is_file()}
    )
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "version": BUNDLE_VERSION,
        "generator": "sim/tools/mk_klt_request.py",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bench": bench,
        "origin": {"commit": commit, "dirty": bool(dirty_paths),
                   "dirty_paths": dirty_paths, "checked_paths": checked},
        "dut": {
            "selector": selector,
            "key": key,
            "dut_id": dut.dut_id,
            "provenance": dut.provenance,
            "netlist": repo_rel(dut.netlist) or str(dut.netlist),
            "netlist_sha256": dut.netlist_sha256,
            "params": dict(sorted(dut.params.items())),
            "binding_config": repo_rel(config) or str(config),
            "binding_entry_sha256": canonical_sha256(entry),
            "staged_netlist": staged["dut"],
            "staged_binding": staged["binding"],
        },
        "testbench": {
            "experiment": bench,
            "dir": repo_rel(tb.directory) or str(tb.directory),
            "netlist": tb.netlist.name,
            "netlist_sha256": tb.netlist_sha256,
            "manifest_sha256": tb.manifest_sha256,
            "staged_dir": staged["testbench_dir"],
        },
        "parameters": parameters,
        "requests": requests,
        "staged": {p.relative_to(out).as_posix(): sha256_file(p) for p in files},
    }
    (out / BUNDLE_NAME).write_text(json.dumps(bundle, indent=1) + "\n")
    return bundle


if __name__ == "__main__":
    raise SystemExit(main())
