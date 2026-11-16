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
the sha256 of every staged file. A gitignored file source that is staged is
classified as a DR-0008 pinned source (origin.pinned_sources) rather than
dirty: the record's own tree pins its bytes. `klt_record.py` mints records
from this bundle -- never from whatever the checkout holds at ingest time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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
from harness import toolchain as htc  # noqa: E402

#: ngspice 46 prints `.meas` results with 5 mantissa decimals by default;
#: widen so sub-microvolt kickback differences are not quantised away.
NGSPICE_INIT = ["set measureprec=12", "set numdgt=12"]

#: The gf180mcu variant every generated request selects (`models.pdk`). Also
#: snapshotted into the bundle as the variant fleet reports must confirm (#283).
PDK_VARIANT = "gf180mcuD"

OFFSET_MC_SEED = 20260909
OFFSET_MC_N = 200
#: Seconds `klt sim --backend batch` keeps re-launching after a
#: `batch_no_capacity` refusal (request.batch.capacity_wait_s).
BATCH_CAPACITY_WAIT_S = 1800
#: Benches whose requests carry a `monte_carlo` block.
MC_BENCHES = ("comparator-offset-mc", "comparator-offset-tran", "comparator-offset-cm-window",
              "comparator-offset-cm-index")

#: Extracted-binding two-phase flow (issue #374). DR-0006 defines the
#: overdrive as +-v_od about the DUT's OWN trip point -- 0 V for the offset-free
#: schematic, the per-corner probed `dut_vos` for an extracted one -- so a
#: fleet extracted campaign is TWO submissions: phase 1 (`--emit probe`)
#: requests tb.json's `offset_probe` deck over the grid and measures each
#: point's trip time `t_flip`; phase 2 (`--emit main --from-probe`) bakes each
#: point's measured `dut_vos` into its own body netlist. The mechanism is the
#: two-phase pattern `layout/pex/pex_measure.py` shipped for the regeneration
#: bench (issue #164); what is new here is that the production request builder
#: speaks it, so a record can be minted (which pex_measure's klt pex documents
#: cannot be). The carrier is a per-point `.param dut_vos=<probed>` -- the
#: same injection `sim/harness/runner.py:compose_deck` performs locally --
#: not a behavioural `v(vos)` ternary, because the deck's stimulus levels sit
#: inside a `pulse(...)` source that ngspice evaluates at parse time, and a
#: per-point body keeps the staged fragment byte-verbatim (issue #151's
#: invariant at its strongest: the bytes simulated are the bytes hashed).
PROBE_RESULTS_SCHEMA = "probe-results/1"
PROBE_RESULTS_NAME = "probe-results.json"
#: The ramp inversion the probe results carry (vspan/tramp are parsed from the
#: staged deck itself; see `probe_deck_spans`).
PROBE_VOS_FORMULA = "-vspan + 2*vspan*t_flip/tramp"

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



#: Input-referred preamp noise (issue #355). Its two legs are expressed with
#: `measurements[].expr` rather than `.meas` cards: `onoise_total` /
#: `inoise_total` are `.noise` OUTPUT VECTORS with no `.meas noise` target in
#: ngspice at all, and `av_dc` is a vector reduction (`mag(v(a)-v(b))[0]`),
#: not a card's search. Both forms need a runner at EXPR_MIN_RUNNER_KLT.
NOISE_BENCH = "comparator-preamp-noise"
#: tb.json `analyses` index -> leg. One `klt sim` request carries ONE
#: analysis, so the bench's four analysis cards become two requested legs:
#: leg `noise` is the full-band 1 Hz .. 1 GHz `.noise` (analyses[1]) and leg
#: `ac` the gain sweep (analyses[3]). The >1 kHz band (analyses[2]) and the
#: `.op` (analyses[0]) are deliberately NOT requested -- klt_record.py's
#: "Not computed by this executor" line declares the six quantities that
#: would need them (`vn_in_hf_uv`, `onoise_hf_uv`, `flicker_frac_pct`,
#: `white_nv_rthz`, `enbw_mhz`, `vbias_anchor_mv`) out of scope here;
#: `vn_in_uv` is the row-facing quantity and needs only these two legs.
NOISE_LEG_ANALYSIS = {"noise": 1, "ac": 3}
#: Benches whose requests depend on `measurements[].expr`, and which therefore
#: carry `batch.runner_version_check: "enforce"`: an `expr`-dependent request
#: must be refused BEFORE simulating, never diagnosed after a grid has burned
#: fleet time (the precedent CM_WINDOW_BENCH set in issue #182).
EXPR_MEASUREMENT_BENCHES = (NOISE_BENCH,)
#: `measurements[].expr` (klt #2533) first shipped in klt 0.7.0.
EXPR_MIN_RUNNER_KLT = (0, 7, 0)

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

def noise_analysis(tb, leg: str) -> dict:
    """tb.json `analyses[NOISE_LEG_ANALYSIS[leg]]` -> a klt `analysis` block.

    The card is read from the bench's OWN manifest (never a literal copied
    from another campaign): a sibling repo's PEX deck instantiates the DUT as
    `Xdut` and so probes `v(xdut.aop,xdut.aon)`, whereas this bench's
    fragment exposes `aop`/`aon` directly. The `kind` is asserted against the
    leg name so a manifest edit that reorders `analyses` fails here rather
    than silently requesting the wrong analysis for 45 corners."""
    card = tb.analyses[NOISE_LEG_ANALYSIS[leg]]
    kind, args = card.split(None, 1)
    if kind != leg:
        raise SystemExit(f"{tb.name}: analyses[{NOISE_LEG_ANALYSIS[leg]}] is {card!r}, "
                         f"expected a `{leg}` card for leg {leg!r}")
    return {"kind": kind, "args": args}


def noise_legs(tb) -> dict[str, dict]:
    """The preamp-noise bench's two legs (issue #355).

    The measurement NAMES are a contract with `klt_record.derive`, which
    indexes exactly `legs["noise"][cid][""]["onoise_total"]`,
    `["inoise_total"]` and `legs["ac"][cid][""]["av_dc"]` and derives
    `av_dc`, `onoise_uv`, `vn_in_uv` and `inoise_band_uv` from them. Renaming
    one here silently empties the record, so they are spelled literally.

    Every entry is an `expr` (see NOISE_BENCH): ngspice implements no
    `.MEASURE NOISE` at all, so `onoise_total`/`inoise_total` have no `.meas`
    card to be written as, and `av_dc` is a reduction of an `ac` sweep's
    vector rather than a card's search. ngspice leaves the INTEGRATED noise
    plot current after `.noise`, so both totals resolve by bare name; the
    `av_dc` expression is the bench manifest's own, so the record's gain is
    the quantity `tb.json`'s `measure` block defines."""
    return {
        "noise": {"analysis": noise_analysis(tb, "noise"),
                  "measurements": [{"name": "onoise_total", "expr": "onoise_total", "unit": "V"},
                                   {"name": "inoise_total", "expr": "inoise_total", "unit": "V"}]},
        "ac": {"analysis": noise_analysis(tb, "ac"),
               "measurements": [{"name": "av_dc", "expr": tb.measure["av_dc"], "unit": "V/V"}]},
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

#: Solver-tolerance profiles for the bounded convergence probe (issue #240),
#: ordered baseline -> progressively tighter. `baseline` writes ngspice 46's
#: documented defaults EXPLICITLY, so it reproduces the campaign's (uncontrolled)
#: solver settings but is visible in the body. Ordered tuples: the card order is
#: part of the identity. Only comparator-offset-cm-index accepts a profile; a
#: request generated without one is byte-identical to the historical campaign's.
TOLERANCE_PROFILES = {
    "baseline": (("reltol", 1e-3), ("abstol", 1e-12), ("vntol", 1e-6)),
    "tight": (("reltol", 1e-5), ("abstol", 1e-14), ("vntol", 1e-9)),
    "tighter": (("reltol", 1e-7), ("abstol", 1e-16), ("vntol", 1e-11)),
}
TOLERANCE_PROFILE_ORDER = tuple(TOLERANCE_PROFILES)


def tolerance_option_lines(profile: str) -> list[str]:
    """The exact `.options` cards a profile puts in the body (one per line)."""
    if profile not in TOLERANCE_PROFILES:
        raise SystemExit(f"UNKNOWN_TOLERANCE_PROFILE: {profile!r} not in {list(TOLERANCE_PROFILES)}")
    return [f".options {k}={v!r}" for k, v in TOLERANCE_PROFILES[profile]]


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


def _git_ignored(repo: Path, p: str) -> bool:
    """Whether `git check-ignore` matches `p` (exit 0 = ignored)."""
    return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--", p]).returncode == 0


def git_ignored_sources(paths: list[str], repo: Path = REPO) -> list[str]:
    """The FILE sources among `paths` that git ignores (DR-0008 candidates).

    A source that is untracked AND matched by a .gitignore pattern -- the
    extracted-DUT-netlist shape, regenerated per host by layout tooling and
    about to be staged into the request set by stage_sources -- has its bytes
    pinned by the record's own tree rather than by any commit. git_state
    excludes exactly these from its dirty list; write_bundle carries them as
    origin.pinned_sources so ingest can verify the class instead of refusing
    it. A modified tracked source, an untracked-but-not-ignored source, and
    any source outside the repository stay dirty. A path git cannot answer
    for at all (outside a repository, git error) stays dirty: the class
    requires git itself to have ignored the path."""
    out = []
    for p in paths:
        if Path(p).is_absolute() or not (Path(repo) / p).is_file():
            continue
        try:
            if subprocess.check_output(["git", "-C", str(repo), "ls-files", "--", p],
                                       text=True).strip():
                continue  # tracked: git vouches for it directly
            if _git_ignored(repo, p):
                out.append(p)
        except (subprocess.CalledProcessError, OSError):
            continue
    return out


def git_state(paths: list[str], repo: Path = REPO) -> tuple[str, list[str]]:
    """-> (HEAD commit, dirty source paths) for the sources a run depends on.

    Dirty means modified, staged, untracked, outside the repository, or
    tracked-but-uncommitted-in-the-index. One narrow exception (DR-0008,
    operator ruling on #398): a FILE source that is gitignored -- not merely
    untracked -- is staged into the request set and sha256-pinned by every
    deck, so its bytes are identified by the record's own tree rather than by
    a commit; such a source is NOT listed dirty here and is classified by
    git_ignored_sources into origin.pinned_sources instead. The recorded
    bytes being committed is verified by klt_record.verify_origin_commit's
    class legs, not by this function: having a committed identity at the
    origin commit is NOT the same thing as the generation path being tracked.
    A gitignored source staged in the git index but not yet committed is
    still dirty (the porcelain scan sees it) -- the class covers staged bytes
    only once the record carrying them lands."""
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
                if _git_ignored(repo, p):
                    continue  # DR-0008: pinned-source candidate, classified by git_ignored_sources
                dirty.append(f"{p} (not tracked)")
    return sha, dirty


def reverse_ladder_include(staged: dict) -> list[str]:
    """The staged supplemental fragment's `.include` line (issue #158)."""
    return ['.include "' + staged["reverse_ladder_netlist"] + '"']


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
    staged = {
        "dut": f"{SOURCES_DIR}/dut/{dut.netlist.name}",
        "testbench_dir": f"{SOURCES_DIR}/testbench",
        "testbench_netlist": f"{SOURCES_DIR}/testbench/{tb.netlist.name}",
        "binding": f"{SOURCES_DIR}/dut-binding.json",
    }
    if tb.reverse_ladder:
        staged["reverse_ladder_netlist"] = (
            f"{SOURCES_DIR}/testbench/{tb.reverse_ladder['netlist']}")
    if tb.offset_probe:
        # The probe fragment is staged with the rest of the directory; this
        # names its staged path for the extracted-binding probe leg (issue
        # #374). The file exists: htb.load asserts offset_probe's netlist.
        staged["probe_netlist"] = f"{SOURCES_DIR}/testbench/{tb.offset_probe['netlist']}"
    return staged


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


def tran_meas_cards(tb, *, drop_let_pairs: bool = False) -> list[dict]:
    """`meas tran ...` analysis lines -> klt `.meas` measurement entries.

    The forward `analyses` cards first, then any supplemental
    reverse-ladder cards (tb.json `reverse_ladder.analyses`) -- the fleet
    request must measure everything the local harness deck measures.

    `drop_let_pairs` (issue #372): the fleet request schema has no position
    for an interactive `let` between the run and the `.meas` cards, so a
    `let`-defined vector cannot be shipped. A `let` card is dropped TOGETHER
    with the adjacent `meas` card that consumes its vector -- shipping the
    `meas` alone leaves a WHEN card whose right-hand side is an undefined
    vector, the 2AMLogic/klayout-tools#5651 shape that passes `--dry-run`
    and then errors every corner. A `let` that does not form that adjacent
    pair is refused, never silently dropped."""
    out = []
    cards = list(tb.analyses[1:]) + list(tb.reverse_ladder.get("analyses", ()))
    i = 0
    while i < len(cards):
        line = cards[i]
        parts = line.split()
        if parts[0] == "let":
            if not drop_let_pairs:
                raise SystemExit(f"{tb.name}: unexpected analysis card {line!r}")
            nxt = cards[i + 1] if i + 1 < len(cards) else ""
            if not nxt.startswith("meas ") or parts[1] not in nxt:
                raise SystemExit(
                    f"{tb.name}: 'let' card {line!r} is not followed by a 'meas' card "
                    f"consuming {parts[1]!r}; refusing to drop it alone")
            i += 2  # the adjacent pair goes together (issue #372)
            continue
        if parts[0] != "meas":
            raise SystemExit(f"{tb.name}: unexpected analysis card {line!r}")
        out.append({"name": parts[2], "spice": "." + line})
        i += 1
    return out


# --- extracted-binding probe leg (issue #374) ------------------------------ #

#: Subcircuits a testbench fragment may instantiate, mapped to the thing that
#: must supply them. The DUT binding owns all of these (sim/dut/README.md).
_FRAGMENT_DUT_SUBCKTS = ("comparator_dut", "comparator_dut_analog",
                         "comparator_dut_latch")
_FRAGMENT_DUT_RE = {name: re.compile(rf"\b{name}\b") for name in _FRAGMENT_DUT_SUBCKTS}


def check_dut_fragment_compatibility(dut, tb) -> None:
    """Refuse a bench whose fragment instantiates a subckt the bound DUT
    cannot provide -- before any request is written, let alone simulated.

    This is `sim/harness/cli.py`'s runtime DUT-compatibility check, ported to
    the fleet path now that this tool accepts extracted bindings: a flat
    extracted netlist defines only the whole-comparator `comparator_dut`, so
    the two analog-partition benches (offset-mc, preamp-noise) must be told
    apart BEFORE a grid burns on an undefined-subckt deck."""
    fragment = tb.netlist.read_text()
    for name, pattern in _FRAGMENT_DUT_RE.items():
        if pattern.search(fragment) and not dut.provides(name):
            raise SystemExit(
                f"{tb.name}'s fragment instantiates `{name}`, which the bound DUT "
                f"`{dut.dut_id}` ({dut.provenance}) does not define -- a flat extracted "
                "netlist carries no analog/latch partition. Re-run against the "
                "schematic binding (--dut comparator-dr0001, or no --dut at all).")


#: ngspice numeric-literal scale suffixes (a trailing letter after the digits).
_SI_SCALE = {"t": 1e12, "g": 1e9, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9,
             "p": 1e-12, "f": 1e-15}


def parse_si_number(text: str, what: str) -> float:
    """An ngspice numeric literal -> float (`40m` -> 0.04, `80u` -> 8e-5).

    Refuses anything it cannot parse exactly: the probe's dut_vos inversion is
    derived from the deck's own vspan/tramp constants, and a silently-wrong
    parse would mis-refer every point of the campaign."""
    m = re.fullmatch(r"([+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)"
                     r"([a-zA-Z]?)", str(text).strip())
    if not m:
        raise SystemExit(f"cannot parse {what} {text!r} as an ngspice number")
    suffix = m.group(2).lower()
    if suffix and suffix not in _SI_SCALE:
        raise SystemExit(f"cannot parse {what} {text!r}: unknown scale suffix {suffix!r}")
    return float(m.group(1)) * _SI_SCALE.get(suffix, 1.0)


def probe_deck_spans(deck_text: str) -> tuple[float, float, str, str]:
    """(vspan_v, tramp_s, raw-vspan, raw-tramp) from a probe deck's own
    `.param vspan=` / `.param tramp=` cards (tb_vosprobe.spice).

    The dut_vos inversion is derived from the DECK's constants -- never
    hard-coded beside it -- so a changed ramp re-derives instead of silently
    mis-referring; a deck without the two cards is refused."""
    raw = {}
    for name in ("vspan", "tramp"):
        m = re.search(rf"^\s*\.param\s+{name}\s*=\s*(\S+)", deck_text,
                      re.MULTILINE | re.IGNORECASE)
        if not m:
            raise SystemExit(f"the probe deck declares no `.param {name}=...`: "
                             "the dut_vos inversion cannot be derived from it")
        raw[name] = m.group(1).rstrip(",;")
    vspan = parse_si_number(raw["vspan"], "vspan")
    tramp = parse_si_number(raw["tramp"], "tramp")
    if not (vspan > 0.0 and tramp > 0.0):
        raise SystemExit(f"probe deck vspan/tramp must be positive "
                         f"(got vspan={raw['vspan']!r}, tramp={raw['tramp']!r})")
    return vspan, tramp, raw["vspan"], raw["tramp"]


def probe_meas_cards(tb) -> list[dict]:
    """tb.json `offset_probe.analyses` `meas` cards -> klt measurement entries.

    A card whose arguments reference ANOTHER card's result is NOT shipped:
    tb_vosprobe.spice's `vos_v find v(rmp) at=t_flip` reads back a number the
    consumer derives exactly from t_flip alone (the ramp is linear by
    construction -- PROBE_VOS_FORMULA), and no committed fleet report has
    exercised a `.meas ... at=<measured result>` argument on the runner. The
    first extracted campaign must not gamble 45 fleet units on an unproven
    card shape; the bundle's probe block records the derivation so the record
    shows why the card is absent."""
    cards = list(tb.offset_probe.get("analyses", ()))
    names = [line.split()[2] for line in cards
             if line.split() and line.split()[0] == "meas"]
    out = []
    for line in cards:
        parts = line.split()
        if not parts or parts[0] == "*":
            raise SystemExit(f"{tb.name}: offset_probe has an empty/comment card {line!r}")
        if parts[0] == "let":
            raise SystemExit(f"{tb.name}: offset_probe card {line!r} is a `let` -- the fleet "
                             "request schema has no position for one (issue #372's precedent)")
        if parts[0] != "meas":
            continue  # the analysis card; probe_legs ships it as the leg's analysis
        deps = [n for n in names
                if n != parts[2] and re.search(rf"\b{re.escape(n)}\b", line)]
        if deps:
            continue  # derived from another card's result; the consumer re-derives it
        out.append({"name": parts[2], "spice": "." + line})
    if not out:
        raise SystemExit(f"{tb.name}: offset_probe declares no shippable `meas` card")
    return out


def probe_legs(tb) -> dict[str, dict]:
    """The extracted-binding probe leg (issue #374): the `offset_probe` deck's
    analysis plus its shippable `.meas` cards, ONE leg named `probe`.

    The probe bodies carry the full process x temperature grid per supply
    point (the probe fragment is offset-free -- a free-running ramp -- so it
    needs no per-point dut_vos). The consumer derives each point's dut_vos
    from `t_flip`, then asks this tool for the phase-2 main requests."""
    cards = list(tb.offset_probe.get("analyses", ()))
    if not cards or not cards[0].split() or cards[0].split()[0] == "meas":
        raise SystemExit(f"{tb.name}: offset_probe.analyses[0] must be the analysis card "
                         "(e.g. `tran 100n 80u 0 100n`), not a measurement")
    kind, args = cards[0].split(None, 1)
    return {"probe": {"analysis": {"kind": kind, "args": args},
                      "measurements": probe_meas_cards(tb)}}


def resolve_dut(selector: str | None):
    """`--dut` resolution shared with klt_record.py: an id into sim/dut.json,
    or a path to an alternate binding json -- whichever the value names."""
    if selector and Path(selector).is_file():
        return hdut.load(path=selector)
    return hdut.load(select=selector)


def load_probe_results(path: Path, bench: str, vspan: float,
                       wanted: set[str]) -> dict:
    """A probe-results file -> validated dict, for `--emit main --from-probe`.

    Validates the schema and bench identity, that the spans it was derived
    under are the STAGED deck's spans, and that every requested grid point has
    a usable dut_vos. Both trip-point failure modes refuse the campaign here,
    loudly, naming the corners -- never a silent fall back to `dut_vos = 0`
    (an un-referred ladder on an offset-carrying DUT measures the wrong
    operating condition; the local harness runner.py states the same rule)."""
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise SystemExit(f"--from-probe {path}: cannot be read as JSON ({e})")
    if not isinstance(raw, dict) or raw.get("schema") != PROBE_RESULTS_SCHEMA:
        raise SystemExit(f"--from-probe {path}: schema {raw.get('schema')!r} != "
                         f"{PROBE_RESULTS_SCHEMA!r}")
    if raw.get("bench") != bench:
        raise SystemExit(f"--from-probe {path}: generated for bench {raw.get('bench')!r}, "
                         f"not {bench!r}")
    got = raw.get("vspan_v")
    if not isinstance(got, (int, float)) or not math.isfinite(got) \
            or abs(float(got) - vspan) > 1e-12:
        raise SystemExit(f"--from-probe {path}: vspan_v {got!r} does not match the staged "
                         f"probe deck's vspan ({vspan!r}) -- these results were not derived "
                         "from the deck bytes this request set stages")
    vos = raw.get("vos_by_corner")
    if not isinstance(vos, dict) or not vos:
        raise SystemExit(f"--from-probe {path}: no vos_by_corner map")
    missing = sorted(wanted - set(vos))
    if missing:
        raise SystemExit(
            "PROBE_NO_TRIP_POINT: the offset probe produced no usable trip point for "
            + ", ".join(missing)
            + " -- failing the campaign here, never falling back to dut_vos = 0. "
              "See the probe reports named in the results file.")
    bad = {k: v for k, v in vos.items() if k in wanted
           and (not isinstance(v, (int, float)) or isinstance(v, bool)
                or not math.isfinite(v) or abs(v) >= vspan)}
    if bad:
        raise SystemExit(
            f"PROBE_VOS_OUT_OF_SPAN: dut_vos outside the probe ramp (vspan {vspan!r}) "
            f"for {sorted(bad)}: {bad} -- the ramp had clamped before the decision "
            "flipped, so the referral is not established and the point must fail")
    return raw


def legs_for(bench: str, tb, mc_n: int) -> dict[str, dict]:
    """leg name -> {analysis, measurements, monte_carlo?}."""
    if bench in ("comparator-kickback", "comparator-regeneration"):
        kind, args = tb.analyses[0].split(None, 1)
        return {"main": {"analysis": {"kind": kind, "args": args},
                         "measurements": tran_meas_cards(tb)}}
    if bench == "comparator-avg-power":
        # DR-0006 pre-ratification bring-up bench (issue #372): a plain tran
        # plus `.meas` cards, except the `let i_rst_thr` / `meas tran t_rst`
        # pair tran_meas_cards drops together -- the fleet request has no
        # `let` position, and t_rst's only consumer, `reset_margin_ns`,
        # carries no manifest check, so fleet records lose one unchecked
        # proxy and nothing checked (klt_record.py omits the derived
        # quantity and names the gap; see sim/comparator-avg-power/README.md).
        kind, args = tb.analyses[0].split(None, 1)
        return {"main": {"analysis": {"kind": kind, "args": args},
                         "measurements": tran_meas_cards(tb, drop_let_pairs=True)}}
    # Issue #355: this bench's two legs ARE expressible for the fleet runner,
    # and were refused here until 2026-11-14 on a rationale that went stale.
    # The refusal said the fleet runner's klt (0.5.0) had "no `noise`
    # analysis / `.meas noise`" and accepted only `{name, spice}` entries.
    # Measured since: a batch report from 2026-11-05
    # (layout/pex/artifacts/preamp-noise-pvt/20261105-8e25d43/pvt/) records
    # `runner_klt_version: "0.9.0"`, `runner_compatibility: "match"` and
    # `runner_request_features.required: ["analysis_steps",
    # "measurements[].expr", "options.ngspice_init"], "missing": []` for a
    # `{"kind": "noise", ...}` request with `expr` measurements -- i.e. the
    # runner executes both the analysis and the measurement form. The benches
    # below that still use raw `.meas` cards do so on their own merits (a
    # `.meas` card is the exact shape for a transient/dc search), not because
    # `expr` is unavailable. FLEET_RUNNER_KLT_OBSERVED is deliberately left
    # at "0.5.0": it is the pre-launch floor CM_WINDOW_BENCH's refusal is
    # judged against, and un-refusing THAT bench is separate work (#182).
    if bench == NOISE_BENCH:
        return noise_legs(tb)
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
    ap.add_argument("--tolerance-profile", default=None, choices=list(TOLERANCE_PROFILES),
                    help="issue #240 probe only (comparator-offset-cm-index): write this profile's "
                         "`.options reltol/abstol/vntol` cards into the body and bind them in the bundle")
    ap.add_argument("--supply-v", nargs="*", type=float, default=None,
                    help="restrict to these supply points (must be among the tolerance rails)")
    ap.add_argument("--emit", default=None, choices=("probe", "main"),
                    help="extracted DUT binding only (issue #374): `probe` writes the "
                         "offset_probe requests (phase 1); `main` writes the overdrive requests "
                         "with each point's PROBED dut_vos baked in (phase 2, needs --from-probe). "
                         "The schematic binding always emits main and takes no probe.")
    ap.add_argument("--from-probe", default=None, metavar="PROBE_RESULTS_JSON",
                    help="phase-2 input: the probe-results file sim/tools/klt_record.py writes "
                         "after dispatching the phase-1 probe requests")
    a = ap.parse_args()

    if a.tolerance_profile and a.bench != CM_INDEX_BENCH:
        raise SystemExit(f"--tolerance-profile is defined for {CM_INDEX_BENCH} only (issue #240)")

    if a.bench == CM_WINDOW_BENCH:
        # Refused BEFORE anything is staged (issue #182): no request set,
        # bundle or body is written for a capability the fleet lacks.
        gap = cm_window_capability_gap(FLEET_RUNNER_KLT_OBSERVED)
        if gap:
            raise SystemExit(f"UNSUPPORTED_EXECUTOR_CAPABILITY: {gap}")
    tb = htb.load(SIM / a.bench)
    pdk = hpdk.find_pdk()
    dut = resolve_dut(a.dut)
    check_dut_fragment_compatibility(dut, tb)

    # Phase resolution (issue #374). The blanket schematic-only refusal this
    # replaced declared the probe leg "not implemented" -- a declared gap (the
    # message and sim/README.md's tracking citation both said so), now
    # implemented for extracted bindings via the two-phase flow.
    if dut.provenance == "placeholder":
        raise SystemExit("mk_klt_request.py refuses placeholder bindings: records made "
                         "against them substantiate the harness, not a design, and the "
                         "local path mints those")
    probe_section: dict | None = None
    if dut.provenance == "schematic":
        if a.emit == "probe" or a.from_probe:
            raise SystemExit("--emit probe / --from-probe are the extracted binding's dut_vos "
                             "referral (issue #374); the schematic DUT is offset-free by "
                             "construction (dut_vos = 0) and takes no probe")
        phase = "main"
    elif dut.provenance == "extracted":
        if not tb.offset_probe:
            raise SystemExit(f"{tb.name} declares no offset_probe: an extracted DUT's overdrive "
                             "cannot be referred to its own trip point, so this binding has no "
                             "fleet campaign (issue #374)")
        if a.emit is None:
            raise SystemExit("an extracted DUT needs the two-phase flow (issue #374): run once "
                             "with --emit probe, dispatch those requests through `klt sim`, then "
                             "run again with --emit main --from-probe <workdir>/"
                             + PROBE_RESULTS_NAME)
        if a.emit == "probe":
            if a.from_probe:
                raise SystemExit("--from-probe is the phase-2 (`--emit main`) input; phase 1 "
                                 "(--emit probe) must run and be dispatched first")
            phase = "probe"
        else:
            if not a.from_probe:
                raise SystemExit("--emit main for an extracted DUT needs --from-probe "
                                 f"<workdir>/{PROBE_RESULTS_NAME} (the phase-1 probe results); "
                                 "a hard-coded dut_vos = 0 is exactly what this flow exists "
                                 "to prevent")
            phase = "main"
    else:
        raise SystemExit(f"unknown DUT provenance {dut.provenance!r}")

    out = Path(a.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    binding = binding_entry(a.dut)
    checked = source_paths(a.bench, binding[0], dut.netlist)
    commit, dirty_paths = git_state(checked)
    pinned = git_ignored_sources(checked)
    staged = stage_sources(out, tb, dut, binding, a.dut)
    source_shas = source_sha_lines(out)

    corner_list = hc.resolve_corners(a.corners or list(tb.corners))
    tol = tb.supply_tolerance if a.supply_tolerance is None else a.supply_tolerance
    vdds = hc.supply_points(tb.nominal_supply_v, tol)
    if a.supply_v:
        bad = [v for v in a.supply_v if not any(abs(v - r) < 1e-9 for r in vdds)]
        if bad:
            raise SystemExit(f"--supply-v {bad} is not among the supply points {vdds}")
        vdds = [r for r in vdds if any(abs(v - r) < 1e-9 for v in a.supply_v)]
    tol_lines = tolerance_option_lines(a.tolerance_profile) if a.tolerance_profile else []
    temps = list(a.temps) if a.temps else [float(t) for t in tb.temperatures_c]

    def body_for(vdd: float, *, dut_vos_lines: list[str], include_netlist: str,
                 main_leg: bool) -> list[str]:
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
        # The harness injects dut_vos: 0 for a schematic DUT (offset-free by
        # construction); the phase-2 body of an extracted point carries that
        # point's PROBED trip-point offset (issue #374 -- a hard-coded 0.0
        # would measure a different operating condition than DR-0006 defines
        # the overdrive against).
        *dut_vos_lines,
        # differential probe for the dc `.meas` cards (the 0.5.0 runner cannot
        # evaluate v(a)-v(b) inside .meas); a high-Z VCVS, no loading.
        *(["Eddprobe dd 0 aop aon 1"] if a.bench == "comparator-offset-mc" else []),
        *(f".param {k}={v}" for k, v in tb.params.items()),
        # A copy of the PDK's design.ngspice, staged with the request: an
        # off-host runner does not expand the harness's absolute PDK path.
        '.include "design.ngspice"',
        *(f".options {o}" for o in tb.options),
        *tol_lines,
        # The STAGED copies (issue #151), relative like design.ngspice: the
        # bytes simulated are the bytes the source bundle hashes, not a
        # checkout path that can change before the record is minted.
        f'.include "{staged["dut"]}"',
        f'.include "{include_netlist}"',
        # The supplemental reverse-polarity ladder (issue #158): a second
        # staged fragment, so the fleet transient matches the local harness
        # deck and every reverse `.meas` card has its instance. Main legs
        # only -- the probe fragment drives no reverse ladder.
        *(reverse_ladder_include(staged)
          if main_leg and staged.get("reverse_ladder_netlist") else []),
        # One OpenMP thread per unit (issue #157); main legs only -- the
        # probe fragment carries no `.control`-conflicting deck.
        *(SINGLE_THREAD_CONTROL if main_leg and a.bench in SINGLE_THREAD_BENCHES else []),
        "",
    ]
    (out / "design.ngspice").write_text(Path(pdk.design_include).read_text())
    requests: dict[str, dict] = {}

    def write_leg_requests(leg: str, vdd: float, vtag: str, spec: dict,
                           proc_entries: list[dict], leg_temps: list[float]) -> None:
        req = {
            "netlist": f"body-{vtag}.spice",
            "engine": "ngspice",
            "models": {"pdk": PDK_VARIANT, "lib": "libs.tech/ngspice/sm141064.ngspice"},
            "corners": {"process": proc_entries, "temperature_c": leg_temps},
            # The fleet image's klt can lag the submitting client; run anyway
            # and let the record state the runner/client versions it saw.
            # A Spot capacity refusal is retried with the client's own
            # backoff for up to BATCH_CAPACITY_WAIT_S instead of being
            # terminal on the first refusal (issue #157; klt #2721).
            # A request that depends on `expr` must be refused BEFORE
            # simulating (`enforce`), never detected after the fact
            # (issue #182's precedent; issue #355 for the noise legs,
            # whose 45 corners would otherwise burn fleet time before a
            # skew surfaced). Benches whose measurements are plain
            # `.meas` cards stay on `warn`: they run on any runner, and
            # the record states the runner/client versions it saw.
            "batch": {"runner_version_check":
                      "enforce" if a.bench in (CM_WINDOW_BENCH,) + EXPR_MEASUREMENT_BENCHES else "warn",
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
        n = len(proc_entries) * len(leg_temps) * (a.mc_n if "monte_carlo" in spec else 1)
        print(f"wrote {out}/request-{leg}-{vtag}.json ({n} units)")

    # One request (and one body netlist with `.param vdd_val=<V>` baked in)
    # PER SUPPLY POINT on the schematic path. A `corners.supply_v` sweep
    # cannot be used: it works by ngspice `alter <source>=V`, which (a) is
    # refused for the clock's pulse source and (b) would leave the
    # testbench's {vdd_val}-scaled clock amplitude / vdda rail at nominal.
    # An `alter vdd_val=...` on the .param name is a silent no-op -- an
    # earlier revision of this tool did exactly that and produced
    # supply-independent "45-corner" records.
    process = [{"name": c.name, "sections": list(c.sections)} for c in corner_list]
    if phase == "probe":
        # Phase 1 (issue #374): the offset_probe deck over the full grid, one
        # body per supply point (the probe fragment is offset-free -- a
        # free-running ramp -- so nothing point-specific is baked).
        vspan, tramp, _vs_raw, _tr_raw = probe_deck_spans(
            (out / staged["probe_netlist"]).read_text())
        probe_section = {
            "mechanism": "two-phase dut_vos referral (issue #374): these phase-1 requests "
                         "measure each point's trip time t_flip; the phase-2 main bodies "
                         "then bake each point's dut_vos = " + PROBE_VOS_FORMULA,
            "probe_deck": tb.offset_probe["netlist"],
            "vspan_v": vspan, "tramp_s": tramp,
            "vos_formula": PROBE_VOS_FORMULA,
        }
        for vdd in vdds:
            vtag = f"v{vdd:.2f}"
            (out / f"body-{vtag}.spice").write_text("\n".join(body_for(
                vdd, dut_vos_lines=[], include_netlist=staged["probe_netlist"],
                main_leg=False)))
            for leg, spec in probe_legs(tb).items():
                write_leg_requests(leg, vdd, vtag, spec, process, temps)
    elif dut.provenance == "extracted":
        # Phase 2 (issue #374): ONE body -- and one request -- PER PVT POINT,
        # each baking that point's PROBED dut_vos as a parse-time literal. A
        # per-supply body cannot carry a per-corner dut_vos: the request
        # schema has no per-corner param position (the structural difficulty
        # that makes this a two-phase flow at all), and the deck's stimulus
        # levels sit inside a `pulse(...)` evaluated at parse time, so the
        # value must be a literal, not a behavioural expression. The staged
        # fragment is included byte-verbatim (issue #151), exactly as the
        # schematic path and the local harness compose_deck both do.
        vspan, tramp, _vs_raw, _tr_raw = probe_deck_spans(
            (out / staged["probe_netlist"]).read_text())
        wanted = {hc.corner_id(c.name, float(t), vdd)
                  for c in corner_list for t in temps for vdd in vdds}
        # The phase-1 probe requests live on in the phase-2 bundle (same
        # staged sources, same bytes): the record archives ONE bundle whose
        # request set covers both phases, so ingestion verifies and archives
        # the probe evidence beside the main reports. The phase-1 bundle must
        # be present -- without it the probe reports are not part of this
        # request set and the record's dut_vos provenance would rest on the
        # results file's word alone.
        prev = out / BUNDLE_NAME
        if not prev.is_file():
            raise SystemExit(f"--emit main needs the phase-1 bundle {prev} (run --emit probe "
                             "into this workdir first): without it this request set carries no "
                             "probe evidence and the dut_vos provenance has no archived source")
        old = json.loads(prev.read_text())
        carried = {n: r for n, r in (old.get("requests") or {}).items()
                   if r.get("leg") == "probe"}
        if not carried:
            raise SystemExit(f"{prev} carries no probe-leg requests -- it is not a phase-1 "
                             "bundle of this flow; re-run --emit probe into a fresh workdir")
        for n, r in carried.items():
            for f, k in ((r["request"], "request_sha256"), (r["netlist"], "netlist_sha256")):
                got = sha256_file(out / f)
                if got != r[k]:
                    raise SystemExit(f"{f}: sha256 changed since the phase-1 bundle "
                                     f"({got[:16]} != {str(r[k])[:16]}) -- the staged sources "
                                     "moved between phases; re-run --emit probe")
            requests[n] = r
        probe_raw = load_probe_results(Path(a.from_probe), a.bench, vspan, wanted)
        probe_section = {
            "mechanism": "two-phase dut_vos referral (issue #374): the phase-1 requests "
                         "request-probe-*.json measured each point's trip time t_flip; "
                         "these phase-2 bodies bake each point's dut_vos = "
                         + PROBE_VOS_FORMULA,
            "probe_deck": tb.offset_probe["netlist"],
            "vspan_v": vspan, "tramp_s": tramp,
            "vos_formula": PROBE_VOS_FORMULA,
            "vos_by_corner": {k: float(probe_raw["vos_by_corner"][k]) for k in sorted(wanted)},
            "probe_results_sha256": sha256_file(Path(a.from_probe)),
            **({"probe_reports": probe_raw["probe_reports"]}
               if isinstance(probe_raw.get("probe_reports"), dict) else {}),
        }
        for vdd in vdds:
            for c in corner_list:
                for t in temps:
                    cid = hc.corner_id(c.name, float(t), vdd)
                    (out / f"body-{cid}.spice").write_text("\n".join(body_for(
                        vdd,
                        dut_vos_lines=[f".param dut_vos={float(probe_raw['vos_by_corner'][cid])!r}"],
                        include_netlist=staged["testbench_netlist"], main_leg=True)))
                    for leg, spec in legs_for(a.bench, tb, a.mc_n).items():
                        write_leg_requests(leg, vdd, cid, spec,
                                           [{"name": c.name, "sections": list(c.sections)}],
                                           [float(t)])
    else:
        for vdd in vdds:
            vtag = f"v{vdd:.2f}"
            (out / f"body-{vtag}.spice").write_text("\n".join(body_for(
                vdd,
                dut_vos_lines=[".param dut_vos=0.0"],
                include_netlist=staged["testbench_netlist"], main_leg=True)))
            for leg, spec in legs_for(a.bench, tb, a.mc_n).items():
                write_leg_requests(leg, vdd, vtag, spec, process, temps)
    write_bundle(out, a.bench, tb, dut, binding, a.dut, staged, commit, dirty_paths, checked, {
        "corners": [c.name for c in corner_list], "temperatures_c": temps,
        "supply_tolerance": tol, "supply_v": vdds,
        "mc_n": a.mc_n if a.bench in MC_BENCHES else None,
        **({"tolerance_profile": {"name": a.tolerance_profile,
                                  "options": [[k, v] for k, v in TOLERANCE_PROFILES[a.tolerance_profile]],
                                  "cards": tol_lines}} if a.tolerance_profile else {}),
    }, requests, phase=phase, probe_section=probe_section, pinned_sources=pinned)
    print(f"wrote {out}/{BUNDLE_NAME} (commit {commit[:7]}"
          + (f", DIRTY: {', '.join(dirty_paths)}" if dirty_paths else ", clean")
          + (f", pinned (DR-0008): {', '.join(pinned)}" if pinned else "")
          + ")")
    return 0


def toolchain_snapshot(commit: str, path: Path | None = None) -> dict:
    """The ngspice floor in force at generation, frozen into the bundle.

    Ingestion enforces THIS floor, not whatever sim/toolchain.json says at
    ingest time, so a later pin change never alters the meaning of an
    originating bundle (issue #269). Bound to the generation commit and the
    sha256 of the pin file it was read from."""
    path = path or htc.TOOLCHAIN_JSON
    pins = htc.load_pins(path)
    return {"file": repo_rel(path) or str(path), "sha256": sha256_file(path),
            "commit": commit, "ngspice_min_major": pins.get("ngspice_min_major"),
            # Issue #283: the exact open_pdks revision and PDK variant the
            # requests below select; ingestion qualifies every executor
            # report against THESE, never today's checkout.
            "open_pdks": pins.get("open_pdks"), "pdk_variant": PDK_VARIANT}


def write_bundle(out: Path, bench: str, tb, dut, binding, selector, staged: dict,
                 commit: str, dirty_paths: list[str], checked: list[str],
                 parameters: dict, requests: dict, *, phase: str = "main",
                 probe_section: dict | None = None,
                 pinned_sources: list[str] | None = None) -> dict:
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
        "phase": phase,
        # The extracted binding's dut_vos referral (issue #374): spans parsed
        # from the staged probe deck, the inversion formula, and -- on the
        # phase-2 bundle -- the vos each point's body carries plus the sha256
        # of the probe-results file it came from.
        **({"probe": probe_section} if probe_section else {}),
        "origin": {"commit": commit, "dirty": bool(dirty_paths),
                   "dirty_paths": dirty_paths, "checked_paths": checked,
                   # DR-0008: the gitignored-staged sources the record's own
                   # tree pins. Absent when empty: pre-#421 bundles and clean
                   # runs carry the identical origin shape, and ingest
                   # tolerates the missing key.
                   **({"pinned_sources": sorted(pinned_sources)} if pinned_sources else {})},
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
            **({"reverse_ladder_netlist": tb.reverse_ladder["netlist"],
                "reverse_ladder_netlist_sha256": sha256_file(tb.reverse_ladder_path)}
               if tb.reverse_ladder else {}),
        },
        "toolchain": toolchain_snapshot(commit),
        "parameters": parameters,
        "requests": requests,
        "staged": {p.relative_to(out).as_posix(): sha256_file(p) for p in files},
    }
    (out / BUNDLE_NAME).write_text(json.dumps(bundle, indent=1) + "\n")
    return bundle


if __name__ == "__main__":
    raise SystemExit(main())
