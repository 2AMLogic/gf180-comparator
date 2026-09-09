"""``sim/run_corners.py`` -- the one-command PVT corner runner.

Ported from ``2AMLogic/gf180-sar-adc``'s ``sim/harness/cli.py``, trimmed to
the subcommand surface this repo actually has work for. Kept: ``--check-env``,
``--list``, ``--print-env``, ``--corners``, ``--temps``, ``--jobs``,
``--no-write``, ``--sabotage-corners`` (forced ``--no-write``),
``--allow-toolchain-drift``. Not ported: the ``--netlist`` override and
``--netlist-provenance`` flags -- the DUT is bound in ``sim/dut.json`` here
(see ``harness/dut.py``), so pointing a run at a different netlist is a
``--dut`` swap rather than a per-run string a caller could mislabel.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import corners as corners_mod
from . import dut as dut_mod
from . import pdk as pdk_mod
from . import report as report_mod
from . import runner as runner_mod
from . import testbench as tb_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
WORK_DIR = SIM_DIR / ".work"


def _print_env() -> int:
    """Emit shell exports for ``source sim/env.sh``."""
    try:
        pdk = pdk_mod.find_pdk()
    except pdk_mod.PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1
    lib = ";".join(
        str(SIM_DIR / slug / "testbench") for slug in sorted(
            p.name for p in tb_mod.discover(SIM_DIR)
        )
    )
    print(f'export PDK_ROOT="{pdk.path.parent}"')
    print(f'export PDK="{pdk.variant}"')
    print(f'export GF180_PDK_PATH="{pdk.path}"')
    print(f'export GF180_MODELS="{pdk.ngspice_dir}"')
    print(f'export XSCHEM_USER_LIBRARY_PATH="{lib}"')
    return 0


def _check_env(allow_drift: bool) -> int:
    ok = True
    try:
        pdk = pdk_mod.find_pdk()
        print(f"PDK        : {pdk.variant} @ {pdk.path}")
        print(f"             open_pdks {pdk.version} (via {pdk.source})")
    except pdk_mod.PdkNotFound as exc:
        print(f"PDK        : NOT FOUND\n{exc}", file=sys.stderr)
        return 1
    try:
        banner = runner_mod.ngspice_version()
        print(f"ngspice    : {banner}")
    except runner_mod.NgspiceMissing as exc:
        print(f"ngspice    : NOT FOUND\n{exc}", file=sys.stderr)
        return 1

    from . import toolchain as toolchain_mod

    print(f"xschem     : {toolchain_mod.xschem_banner()}  (recorded, not checked)")
    chain = toolchain_mod.check(pdk.version, banner)
    if chain.drift:
        ok = allow_drift
        print("toolchain  : DRIFT" + ("  (accepted via --allow-toolchain-drift)" if allow_drift else ""))
        for item in chain.drift:
            print(f"             - {item}")
    else:
        print("toolchain  : matches sim/toolchain.json pins")

    try:
        dut = dut_mod.load()
        flag = "  <-- PLACEHOLDER, not a design" if dut.is_placeholder else ""
        print(f"DUT        : {dut.dut_id} ({dut.provenance}){flag}")
        print(f"             {dut.netlist.relative_to(REPO_ROOT)}")
    except dut_mod.DutError as exc:
        print(f"DUT        : INVALID\n{exc}", file=sys.stderr)
        return 1

    experiments = tb_mod.discover(SIM_DIR)
    print(f"experiments: {len(experiments)} -> {', '.join(p.name for p in experiments)}")
    return 0 if ok else 2


def _list() -> int:
    for directory in tb_mod.discover(SIM_DIR):
        tb = tb_mod.load(directory)
        grid = len(corners_mod.resolve_corners(list(tb.corners))) * len(
            tb.temperatures_c
        ) * len(corners_mod.supply_points(tb.nominal_supply_v, tb.supply_tolerance))
        print(f"{directory.name:28s} {grid:4d} points  {tb.description[:80]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_corners.py",
        description="PVT corner runner for gf180-comparator (stdlib only).",
    )
    parser.add_argument("experiment", nargs="?", help="experiment slug under sim/")
    parser.add_argument("--check-env", action="store_true", help="verify PDK / tools / DUT and exit")
    parser.add_argument("--print-env", action="store_true", help="emit shell exports (sim/env.sh)")
    parser.add_argument("--list", action="store_true", help="list known experiments and exit")
    parser.add_argument("--corners", nargs="*", help="corner or corner-set names (default: manifest)")
    parser.add_argument("--temps", nargs="*", type=float, help="temperatures in degC")
    parser.add_argument("--supply-tolerance", type=float, help="fractional supply tolerance")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="concurrent ngspice processes")
    parser.add_argument("--num-threads", type=int, default=1,
                        help="ngspice internal threads per point (0 = ngspice default)")
    parser.add_argument("--timeout", type=int, default=runner_mod.DEFAULT_TIMEOUT_S,
                        help="per-point ngspice timeout in seconds")
    parser.add_argument("--no-write", action="store_true",
                        help="run and print, but do not mint an evidence record")
    parser.add_argument("--sabotage-corners", action="store_true",
                        help="NEGATIVE CONTROL: force every corner to typical. "
                             "Per-axis process checks MUST fail. Implies --no-write.")
    parser.add_argument("--allow-toolchain-drift", action="store_true",
                        help="run despite a toolchain pin mismatch, and stamp it into the record")
    parser.add_argument("--dut", help="path to an alternate DUT binding json (default sim/dut.json)")
    args = parser.parse_args(argv)

    if args.print_env:
        return _print_env()
    if args.check_env:
        return _check_env(args.allow_toolchain_drift)
    if args.list or not args.experiment:
        return _list()

    directory = SIM_DIR / args.experiment
    if not directory.is_dir():
        print(f"no experiment directory sim/{args.experiment}", file=sys.stderr)
        return 1
    tb = tb_mod.load(directory)

    try:
        pdk = pdk_mod.find_pdk()
    except pdk_mod.PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        banner = runner_mod.ngspice_version()
    except runner_mod.NgspiceMissing as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        dut = dut_mod.load(args.dut)
    except dut_mod.DutError as exc:
        print(exc, file=sys.stderr)
        return 1

    from . import toolchain as toolchain_mod

    chain = toolchain_mod.check(pdk.version, banner)
    if chain.drift and not args.allow_toolchain_drift:
        print("TOOLCHAIN DRIFT -- refusing to simulate:", file=sys.stderr)
        for item in chain.drift:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nA record taken under different device models is not comparable "
            "with the ones already in sim/. Re-run with --allow-toolchain-drift "
            "to accept and stamp the drift into the record.",
            file=sys.stderr,
        )
        return 3

    corner_names = args.corners if args.corners else list(tb.corners)
    corner_list = corners_mod.resolve_corners(corner_names)
    sabotaged = bool(args.sabotage_corners)
    if sabotaged:
        corner_list = corners_mod.sabotage(corner_list)
    temperatures = args.temps if args.temps else list(tb.temperatures_c)
    tolerance = (
        args.supply_tolerance if args.supply_tolerance is not None else tb.supply_tolerance
    )
    supplies = corners_mod.supply_points(tb.nominal_supply_v, tolerance)
    points = corners_mod.build_grid(corner_list, temperatures, supplies)

    write = not (args.no_write or sabotaged)
    rid = report_mod.record_id()
    # Captured BEFORE the run writes anything, so the flag describes the tree
    # this record was produced from rather than the tree the run left behind.
    dirty_at_start = report_mod.dirty_paths()
    workdir = WORK_DIR / tb.experiment / rid
    log_dir = (tb.experiment_dir / "corners" / rid) if write else workdir

    banner_bits = [
        f"experiment sim/{tb.experiment}",
        f"{len(points)} PVT points",
        f"dut={dut.dut_id}({dut.provenance})",
        f"pdk={pdk.variant}@{pdk.version[:7]}",
    ]
    print("=" * 78)
    print("  " + "  |  ".join(banner_bits))
    if sabotaged:
        print("  *** SABOTAGED CORNERS (negative control) -- evidence writing disabled ***")
    if dut.is_placeholder:
        print("  *** PLACEHOLDER DUT -- results substantiate the harness, not a spec row ***")
    print("=" * 78)

    done = [0]

    def _progress(result: runner_mod.PointResult) -> None:
        done[0] += 1
        flag = "ok " if result.status == "ok" else result.status.upper()
        print(f"  [{done[0]:3d}/{len(points)}] {flag} {result.point.corner_id} "
              f"({result.seconds:.1f}s)" + (f" -- {result.message}" if result.message else ""))

    results = runner_mod.run_grid(
        tb, pdk, dut, points, workdir,
        jobs=max(1, args.jobs),
        timeout_s=args.timeout,
        on_result=_progress,
        log_dir=log_dir,
        num_threads=args.num_threads,
    )

    summaries = report_mod.summarize(tb, results)
    completed = sum(1 for r in results if r.status == "ok")
    failures = {n: s.failures for n, s in summaries.items() if s.failures}

    print("-" * 78)
    for name in tb.measure:
        s = summaries[name]
        if not s.values:
            print(f"  {name:24s} (no completed points)")
            continue
        print(f"  {name:24s} min {s.minimum:12.6g} @ {s.at_min:16s} "
              f"max {s.maximum:12.6g} @ {s.at_max:16s} spread {s.spread:8.4g} %")
        # Per-axis weakest->strongest slice spread. Printed for every run
        # because it is what a `min_spread_pct_by_axis` floor has to be
        # calibrated against -- reading it out of a committed record only
        # works once a record exists, which is a chicken-and-egg problem the
        # first time a check is authored.
        axis_bits = [
            f"{axis[:4]} {s.axes[axis].weakest:.4g}->{s.axes[axis].strongest:.4g}%"
            for axis in report_mod.AXES
            if axis in s.axes and s.axes[axis].varies
        ]
        if axis_bits:
            print(f"  {'':24s}   per-axis: " + "  ".join(axis_bits))
    if failures:
        print("-" * 78)
        print("  CHECK FAILURES:")
        for name, reasons in failures.items():
            for reason in reasons:
                print(f"    {name}: {reason}")

    passed = not failures and completed == len(results)
    print("-" * 78)
    print(f"  {completed}/{len(results)} points completed -- "
          f"{'PASS' if passed else 'FAIL'}")

    if sabotaged:
        # Under sabotage a FAIL is the desired outcome: it proves the per-axis
        # process-sensitivity checks would have caught a runner stuck on typical.
        print("  (sabotage run: FAIL is the expected, correct outcome)")
        shutil.rmtree(workdir, ignore_errors=True)
        return 0 if not passed else 4

    if write:
        context = {
            "record_id": rid,
            "commit": report_mod.git_short_sha(),
            "dirty": bool(dirty_at_start),
            "dirty_paths": dirty_at_start[:20],
            "pdk": pdk.provenance(),
            "toolchain": chain.as_dict(),
            **dut.provenance_record(),
        }
        path = report_mod.write_record(tb, results, summaries, context, dut.netlist)
        print(f"  record: {path.relative_to(REPO_ROOT)}")
        print(f"  logs:   sim/{tb.experiment}/corners/{rid}/")
    else:
        print("  (--no-write: no evidence record minted)")
    shutil.rmtree(workdir, ignore_errors=True)

    return 0 if passed else 1
