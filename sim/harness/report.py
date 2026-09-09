"""Check evaluation and evidence-record rendering.

Ported from ``2AMLogic/gf180-sar-adc``'s ``sim/harness/report.py``: the
check vocabulary (``min`` / ``max`` / ``min_spread_pct`` / ``max_spread_pct``
and their per-axis variants), the per-axis sensitivity guard, the
grid/spread/per-axis table layout of an evidence record, and the
``<UTC-timestamp>-<short-sha>`` record-id convention.

Written fresh rather than ported: the ``DUT provenance`` header line and the
placeholder banner, which have no counterpart over there because that repo's
comparator netlist was already real when its harness was written.

**The per-axis sensitivity guard is the load-bearing part of this module.**
A ``min_spread_pct_by_axis`` entry asserts that the measurement actually
MOVES when that axis alone is swept. It is not a design claim -- it is the
proof that the corner runner is really switching models / temperature /
supply, so that a run under ``--sabotage-corners`` (every section forced to
typical) fails instead of quietly reporting a "valid" typical-only matrix.
"""

from __future__ import annotations

import json
import statistics
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .runner import PointResult
from .testbench import Testbench

REPO_ROOT = Path(__file__).resolve().parents[2]

AXES = ("process", "temperature", "supply")

#: How a point's key is built for each axis: the OTHER two axes are held
#: fixed inside a slice, and the named axis is what varies within it.
_SLICE_KEY = {
    "process": lambda p: (p.temp_c, p.vdd),
    "temperature": lambda p: (p.corner.name, p.vdd),
    "supply": lambda p: (p.corner.name, p.temp_c),
}


def spread_pct(values: list[float]) -> float:
    """Peak-to-peak as a percentage of the mean magnitude.

    Referenced to ``abs(mean)`` rather than to ``mean`` so that a
    measurement centred near zero reports a large spread instead of a
    sign-flipped one, and to a small epsilon when the mean is exactly zero.
    """
    if len(values) < 2:
        return 0.0
    lo, hi = min(values), max(values)
    mean = statistics.fmean(values)
    denom = abs(mean) if abs(mean) > 1e-30 else 1e-30
    return (hi - lo) / denom * 100.0


@dataclass
class Axis:
    name: str
    weakest: float = 0.0
    strongest: float = 0.0
    varies: bool = False


@dataclass
class MeasurementSummary:
    name: str
    values: dict[str, float]                 # corner-id -> value
    minimum: float = 0.0
    maximum: float = 0.0
    mean: float = 0.0
    at_min: str = ""
    at_max: str = ""
    spread: float = 0.0
    axes: dict[str, Axis] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def per_axis_spreads(results: list[PointResult], name: str) -> dict[str, Axis]:
    """Weakest / strongest single-axis spread for one measurement."""
    axes: dict[str, Axis] = {}
    for axis in AXES:
        buckets: dict[tuple, list[float]] = {}
        for result in results:
            if name not in result.measurements:
                continue
            buckets.setdefault(_SLICE_KEY[axis](result.point), []).append(
                result.measurements[name]
            )
        slices = [spread_pct(v) for v in buckets.values() if len(v) > 1]
        if not slices:
            axes[axis] = Axis(name=axis, varies=False)
        else:
            axes[axis] = Axis(
                name=axis, weakest=min(slices), strongest=max(slices), varies=True
            )
    return axes


def swept_axes(results: list[PointResult]) -> set[str]:
    """Axes the grid actually varies (>= 2 distinct values).

    A per-axis sensitivity check asserts that a measurement MOVES when an
    axis is swept. If the grid never sweeps that axis -- a one-point smoke
    run, or `--corners tt` -- there is nothing to assert, so the check is
    SKIPPED rather than failed. Skips are reported in the record so a
    single-point run can never be mistaken for a full-grid one.

    Note this keys on the grid, not on the model sections: under
    ``--sabotage-corners`` the five process corner NAMES are still present,
    so the process axis counts as swept and the sabotage run still fails its
    sensitivity check -- which is exactly what the negative control needs.
    """
    axes: set[str] = set()
    if len({r.point.corner.name for r in results}) > 1:
        axes.add("process")
    if len({r.point.temp_c for r in results}) > 1:
        axes.add("temperature")
    if len({r.point.vdd for r in results}) > 1:
        axes.add("supply")
    return axes


def summarize(tb: Testbench, results: list[PointResult]) -> dict[str, MeasurementSummary]:
    ok = [r for r in results if r.status == "ok"]
    swept = swept_axes(results)
    summaries: dict[str, MeasurementSummary] = {}
    for name in tb.measure:
        values = {r.point.corner_id: r.measurements[name] for r in ok if name in r.measurements}
        summary = MeasurementSummary(name=name, values=values)
        if values:
            summary.minimum = min(values.values())
            summary.maximum = max(values.values())
            summary.mean = statistics.fmean(values.values())
            summary.at_min = min(values, key=lambda k: values[k])
            summary.at_max = max(values, key=lambda k: values[k])
            summary.spread = spread_pct(list(values.values()))
            summary.axes = per_axis_spreads(ok, name)
        summaries[name] = summary

    for name, spec in tb.checks.items():
        summary = summaries[name]
        if not summary.values:
            summary.failures.append("no completed points produced this measurement")
            continue
        if "min" in spec and summary.minimum < spec["min"]:
            summary.failures.append(
                f"min {summary.minimum:g} at `{summary.at_min}` < required {spec['min']:g}"
            )
        if "max" in spec and summary.maximum > spec["max"]:
            summary.failures.append(
                f"max {summary.maximum:g} at `{summary.at_max}` > allowed {spec['max']:g}"
            )
        if "max_spread_pct" in spec and summary.spread > spec["max_spread_pct"]:
            summary.failures.append(
                f"grid spread {summary.spread:g} % > allowed {spec['max_spread_pct']:g} %"
            )
        if "min_spread_pct" in spec and summary.spread < spec["min_spread_pct"]:
            summary.failures.append(
                f"grid spread {summary.spread:g} % < required {spec['min_spread_pct']:g} %"
            )
        for axis, bound in (spec.get("min_spread_pct_by_axis") or {}).items():
            observed = summary.axes.get(axis)
            if axis not in swept:
                summary.skipped.append(
                    f"min_spread_pct_by_axis[{axis}] >= {bound:g} % — SKIPPED, "
                    "this grid does not sweep that axis"
                )
            elif observed is None or not observed.varies:
                summary.failures.append(f"axis {axis!r} never varies -- cannot check sensitivity")
            elif observed.weakest < bound:
                summary.failures.append(
                    f"weakest {axis} slice spread {observed.weakest:g} % < required {bound:g} % "
                    "(the corner runner may not be sweeping this axis at all)"
                )
        for axis, bound in (spec.get("max_spread_pct_by_axis") or {}).items():
            observed = summary.axes.get(axis)
            if axis not in swept:
                summary.skipped.append(
                    f"max_spread_pct_by_axis[{axis}] <= {bound:g} % — SKIPPED, "
                    "this grid does not sweep that axis"
                )
            elif observed is None or not observed.varies:
                summary.failures.append(f"axis {axis!r} never varies -- cannot check sensitivity")
            elif observed.strongest > bound:
                summary.failures.append(
                    f"strongest {axis} slice spread {observed.strongest:g} % > allowed {bound:g} %"
                )
    return summaries


def git_short_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, check=False, timeout=20,
        )
        return out.stdout.strip() or "nogit"
    except (FileNotFoundError, subprocess.TimeoutExpired):  # pragma: no cover
        return "nogit"


#: Path fragments whose UNTRACKED files do not make a tree "dirty" for the
#: purpose of a record's citability. These are the evidence directories the
#: harness itself writes into: a run necessarily creates its own logs and
#: record before it can stamp the header, and a *previous* run's not-yet-
#: committed record says nothing about whether THIS run is reproducible from
#: committed sources. Tracked modifications anywhere, and untracked files
#: anywhere else, still count.
_EVIDENCE_DIRS = ("/records/", "/corners/", "/netlist-snapshots/")


def dirty_paths() -> list[str]:
    """Working-tree paths that would make a record non-citable.

    "Dirty" here means: something that feeds this record is not what is
    committed. Tracked modifications always qualify. Untracked files qualify
    too -- an untracked testbench fragment would be a genuinely uncitable
    record -- EXCEPT under the harness's own evidence directories, which a
    run unavoidably writes into before it can stamp its own header.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):  # pragma: no cover
        return []
    offenders: list[str] = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        status, _, path = line[:2], line[2], line[3:]
        normalized = "/" + path.strip().strip('"')
        if status == "??" and any(frag in normalized for frag in _EVIDENCE_DIRS):
            continue
        offenders.append(f"{status.strip() or '??'} {path.strip()}")
    return offenders


def git_dirty() -> bool:
    return bool(dirty_paths())


def record_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{git_short_sha()}"


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _limits_text(spec: dict) -> str:
    parts = []
    for key in ("min", "max", "min_spread_pct", "max_spread_pct"):
        if key in spec:
            parts.append(f"{key}={spec[key]:g}")
    for key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
        for axis, bound in (spec.get(key) or {}).items():
            parts.append(f"{key}[{axis}]={bound:g}")
    return ", ".join(parts) or "—"


def render_record(
    tb: Testbench,
    results: list[PointResult],
    summaries: dict[str, MeasurementSummary],
    context: dict,
) -> str:
    """Render the markdown evidence record (sim/README.md 'Record format')."""
    ok = [r for r in results if r.status == "ok"]
    names = list(tb.measure)
    corners = sorted({r.point.corner.name for r in results}, key=lambda c: [
        r.point.index for r in results if r.point.corner.name == c
    ][0])
    temps = sorted({r.point.temp_c for r in results})
    supplies = sorted({r.point.vdd for r in results})
    passed = not any(s.failures for s in summaries.values()) and len(ok) == len(results)

    lines: list[str] = [f"# Record {context['record_id']}", ""]

    if context.get("dut_provenance") == "placeholder":
        lines += [
            "> **PLACEHOLDER DUT — THIS RECORD SUBSTANTIATES THE HARNESS, NOT A",
            "> SPEC ROW.** Every number below was measured against",
            f"> `{context['dut_netlist']}` (`{context['dut_id']}`), a deliberately",
            "> crude stub that exists only to exercise this plumbing end to end.",
            "> It is NOT a design candidate and NOT the topology this block will",
            "> ship — that decision is a separate decision record",
            "> (`spec/porting-plan.md` next step 1). Do not quote any number here",
            "> against `README.md`'s target-specification table.",
            "",
        ]

    lines += [
        f"- **Record ID**: {context['record_id']}",
        f"- **Experiment**: `sim/{tb.experiment}/`",
        f"- **Claim**: {tb.claim or '(none stated)'}",
        f"- **DUT**: `{context['dut_id']}` — **{context['dut_provenance']}** — "
        f"`{context['dut_netlist']}` (sha256 `{context['dut_netlist_sha256'][:16]}`)",
        f"- **Testbench**: `sim/{tb.experiment}/testbench/{tb.netlist.name}` "
        f"(sha256 `{tb.netlist_sha256[:16]}`), manifest sha256 "
        f"`{tb.manifest_sha256[:16]}`",
        f"- **Commit**: `{context['commit']}`"
        + ("  — **taken against a DIRTY working tree**; not citable as a "
           "clean-tree result" if context.get("dirty") else ""),
        f"- **PDK**: {context['pdk']['variant']} @ open_pdks "
        f"`{context['pdk']['open_pdks_version']}` (found via "
        f"{context['pdk']['discovered_via']})",
        f"- **Toolchain**: {context['toolchain']['observed']['ngspice']}, "
        f"Python {context['toolchain']['observed']['python']}",
    ]
    if context["toolchain"]["drift"]:
        lines.append("- **TOOLCHAIN DRIFT ACCEPTED** (`--allow-toolchain-drift`):")
        lines += [f"  - {d}" for d in context["toolchain"]["drift"]]
    lines += [
        "- **Corner matrix run**:",
        f"  - Process: {', '.join(corners)}",
        f"  - Temperature: {', '.join(f'{t:g} °C' for t in temps)}",
        f"  - Supply: {', '.join(f'{v:.2f} V' for v in supplies)}",
        f"  - {len(results)} point full-factorial grid (process × temperature × "
        f"supply), {len(ok)} completed",
    ]
    evidence = tb.evidence or {}
    lines.append(
        f"- **Record kind**: {evidence.get('record_kind', 'corner-matrix')}"
    )
    if evidence.get("mc_seed"):
        lines.append(f"- **Monte-Carlo seed / draws**: {evidence['mc_seed']}")
    if evidence.get("mc_scope"):
        lines.append(f"- **Monte-Carlo scope**: {evidence['mc_scope']}")
    if evidence.get("mc_sigma"):
        lines.append(f"- **Sigma derivation**: {evidence['mc_sigma']}")
    else:
        lines.append(
            "- **Statistical convention**: N/A (corner-matrix claim, not a "
            "distribution claim)"
        )
    for note in evidence.get("notes", ()):
        lines.append(f"- **Note**: {note}")

    lines += ["- **Result**:", ""]
    header = "  | corner-id | " + " | ".join(f"`{n}`" for n in names) + " | pass/fail |"
    sep = "  |---|" + "---|" * (len(names) + 1)
    lines += [header, sep]
    for result in results:
        if result.status != "ok":
            cells = " | ".join("—" for _ in names)
            lines.append(
                f"  | `{result.point.corner_id}` | {cells} | "
                f"**{result.status.upper()}**: {result.message} |"
            )
            continue
        cells = " | ".join(_fmt(result.measurements[n]) for n in names)
        lines.append(f"  | `{result.point.corner_id}` | {cells} | PASS |")

    lines += ["", "  Spread across the grid:", ""]
    lines += [
        "  | measurement | min | max | mean | spread % | limits |",
        "  |---|---|---|---|---|---|",
    ]
    for name in names:
        s = summaries[name]
        if not s.values:
            lines.append(f"  | `{name}` | — | — | — | — | {_limits_text(tb.checks.get(name, {}))} |")
            continue
        lines.append(
            f"  | `{name}` | {_fmt(s.minimum)} (`{s.at_min}`) | "
            f"{_fmt(s.maximum)} (`{s.at_max}`) | {_fmt(s.mean)} | "
            f"{_fmt(s.spread)} | {_limits_text(tb.checks.get(name, {}))} |"
        )

    lines += [
        "",
        "  Per-axis corner sensitivity (spread observed when only that axis",
        "  varies, weakest → strongest slice of the grid):",
        "",
        "  | measurement | process | temperature | supply |",
        "  |---|---|---|---|",
    ]
    for name in names:
        s = summaries[name]
        cells = []
        for axis in AXES:
            a = s.axes.get(axis)
            cells.append(
                f"{_fmt(a.weakest)} → {_fmt(a.strongest)} %" if a and a.varies else "—"
            )
        lines.append(f"  | `{name}` | " + " | ".join(cells) + " |")

    failures = {n: s.failures for n, s in summaries.items() if s.failures}
    skipped = {n: s.skipped for n, s in summaries.items() if s.skipped}
    lines += ["", f"- **Verdict**: {'PASS' if passed else 'FAIL'}"]
    if skipped:
        lines.append(
            "- **Checks NOT evaluated on this grid** (an unswept axis has no "
            "sensitivity to assert; a record with skips is weaker evidence "
            "than one without):"
        )
        for name, reasons in skipped.items():
            for reason in reasons:
                lines.append(f"  - `{name}`: {reason}")
    if failures:
        lines.append("- **Check failures**:")
        for name, reasons in failures.items():
            for reason in reasons:
                lines.append(f"  - `{name}`: {reason}")
    incomplete = [r for r in results if r.status != "ok"]
    if incomplete:
        lines.append(f"- **Incomplete points**: {len(incomplete)}")
        for r in incomplete:
            lines.append(f"  - `{r.point.corner_id}`: {r.status} — {r.message}")

    lines += [
        "",
        "- **Raw logs**: "
        f"`sim/{tb.experiment}/corners/{context['record_id']}/<corner-id>.log` "
        "(one per PVT point, the exact ngspice output)",
        "- **Netlist snapshot**: "
        f"`sim/{tb.experiment}/netlist-snapshots/{context['record_id']}.spice` "
        "(testbench fragment + DUT netlist as simulated)",
        "- **Reproduce**:",
        "",
        "  ```",
        f"  python3 sim/run_corners.py {tb.experiment}",
        "  ```",
        "",
    ]
    return "\n".join(lines)


def write_record(
    tb: Testbench,
    results: list[PointResult],
    summaries: dict[str, MeasurementSummary],
    context: dict,
    dut_netlist: Path,
) -> Path:
    """Write the markdown record, its JSON twin, and the netlist snapshot."""
    experiment_dir = tb.experiment_dir
    rid = context["record_id"]

    records_dir = experiment_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    record_path = records_dir / f"{rid}.md"
    record_path.write_text(render_record(tb, results, summaries, context))

    snapshots_dir = experiment_dir / "netlist-snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / f"{rid}.spice").write_text(
        f"* Netlist snapshot for record {rid} -- exactly what was simulated.\n"
        f"* DUT: {context['dut_id']} ({context['dut_provenance']}), "
        f"{context['dut_netlist']}\n"
        f"* Testbench: sim/{tb.experiment}/testbench/{tb.netlist.name}\n"
        "* ---------------- DUT NETLIST ----------------\n"
        + dut_netlist.read_text()
        + "\n* ---------------- TESTBENCH FRAGMENT ----------------\n"
        + tb.netlist.read_text()
    )

    json_path = records_dir / f"{rid}.json"
    json_path.write_text(
        json.dumps(
            {
                "record_id": rid,
                "context": context,
                "testbench": tb.provenance(),
                "checks": tb.checks,
                "points": [r.as_dict() for r in results],
                "summary": {
                    name: {
                        "min": s.minimum,
                        "max": s.maximum,
                        "mean": s.mean,
                        "at_min": s.at_min,
                        "at_max": s.at_max,
                        "spread_pct": s.spread,
                        "per_axis": {
                            a: {"weakest": ax.weakest, "strongest": ax.strongest,
                                "varies": ax.varies}
                            for a, ax in s.axes.items()
                        },
                        "failures": s.failures,
                        "skipped_checks": s.skipped,
                    }
                    for name, s in summaries.items()
                    if s.values
                },
            },
            indent=2,
        )
        + "\n"
    )
    return record_path
