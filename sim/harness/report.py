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
import math
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


def _strict_json_safe(obj, path: str, omitted: list[str]):
    """Copy of ``obj`` with non-finite floats replaced by None (explicit
    missing); each replaced location is appended to ``omitted``."""
    if isinstance(obj, float) and not math.isfinite(obj):
        omitted.append(path)
        return None
    if isinstance(obj, dict):
        return {k: _strict_json_safe(v, f"{path}.{k}", omitted) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_strict_json_safe(v, f"{path}[{i}]", omitted) for i, v in enumerate(obj)]
    return obj


def _is_finite(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def summarize(tb: Testbench, results: list[PointResult]) -> dict[str, MeasurementSummary]:
    ok = [r for r in results if r.status == "ok"]
    swept = swept_axes(results)
    summaries: dict[str, MeasurementSummary] = {}
    for name in tb.measure:
        values = {r.point.corner_id: r.measurements[name] for r in ok if name in r.measurements}
        # Non-finite values never enter the statistics (NaN would also make
        # every bound comparison silently False): they are failures.
        bad = sorted(k for k, v in values.items() if not _is_finite(v))
        values = {k: v for k, v in values.items() if k not in bad}
        summary = MeasurementSummary(name=name, values=values)
        if bad:
            summary.failures.append(
                f"NONFINITE_MEASUREMENT: {name} is not finite at {', '.join(f'`{k}`' for k in bad)}"
            )
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
            summary.failures.append("no completed points produced a finite value for this measurement")
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


class GitInspectionError(RuntimeError):
    """Git could not establish whether the working tree is clean.

    Distinct from a verified clean tree: callers must not treat this as
    ``[]`` (issue #260).
    """


def dirty_paths() -> list[str]:
    """Working-tree paths that would make a record non-citable.

    "Dirty" here means: something that feeds this record is not what is
    committed. Tracked modifications always qualify. Untracked files qualify
    too -- an untracked testbench fragment would be a genuinely uncitable
    record -- EXCEPT under the harness's own evidence directories, which a
    run unavoidably writes into before it can stamp its own header.

    Raises :class:`GitInspectionError` if git is missing, times out, or exits
    nonzero: an uninspectable tree is not a clean tree.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except FileNotFoundError as exc:
        raise GitInspectionError(f"git executable not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitInspectionError(
            f"git status timed out after {exc.timeout}s") from exc
    except OSError as exc:
        raise GitInspectionError(f"git status could not run: {exc}") from exc
    if out.returncode != 0:
        raise GitInspectionError(
            f"git status exited {out.returncode}: {(out.stderr or '').strip()}")
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


def record_id(now: datetime | None = None) -> str:
    """Mint a candidate record id: ``YYYYmmdd-HHMMSSffffff-<sha>``.

    Microsecond precision; it still sorts chronologically against legacy
    ``YYYYmmdd-HHMMSS-<sha>`` ids (within one second, ``-`` sorts before any
    digit). The id is only a *candidate* until ``reserve_run`` has
    exclusively created its namespace (issue #85).
    """
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y%m%d-%H%M%S%f')}-{git_short_sha()}"


def reserve_run(
    experiment_dir: Path,
    now: datetime | None = None,
    *,
    logs_root: Path | None = None,
    check_published: bool = True,
) -> tuple[str, Path]:
    """Atomically reserve a unique run namespace BEFORE any simulation runs.

    The reservation is an exclusive ``mkdir`` of ``<logs_root>/<rid>``
    (default ``<experiment_dir>/corners/<rid>``), which is also the
    corner-log directory. If it already exists, or a record/snapshot with the
    same id is already published (legacy ids), a fresh id is allocated by
    appending ``.N``; nothing pre-existing is touched.
    Returns ``(record_id, log_dir)``.
    """
    root = logs_root if logs_root is not None else experiment_dir / "corners"
    root.mkdir(parents=True, exist_ok=True)
    base = record_id(now)
    n = 0
    while True:
        rid = base if n == 0 else f"{base}.{n}"
        n += 1
        if check_published and any(
            (experiment_dir / sub / f"{rid}{ext}").exists()
            for sub, ext in (("records", ".md"), ("records", ".json"),
                             ("netlist-snapshots", ".spice"))
        ):
            continue
        try:
            (root / rid).mkdir()
        except FileExistsError:
            continue
        return rid, root / rid


def _write_new(path: Path, text: str) -> None:
    """Create ``path`` exclusively; never replace an existing artifact."""
    with open(path, "x") as fh:
        fh.write(text)


def _latest_schematic_record(tb: Testbench) -> tuple[str, dict] | None:
    """The newest committed record of this experiment measured against a
    ``schematic``-provenance DUT -- the counterpart a post-layout
    (``extracted``) record documents its delta against. Record ids sort
    lexicographically by mint time (``YYYYMMDD-HHMMSS-<sha>``), so a plain
    max() over the parsed ``context.record_id`` picks the latest.
    """
    best: tuple[str, dict] | None = None
    for path in sorted((tb.experiment_dir / "records").glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue  # a torn/unparseable sibling record is not this run's problem
        ctx = doc.get("context") or {}
        if ctx.get("dut_provenance") != "schematic":
            continue
        rid = str(ctx.get("record_id") or path.stem)
        if best is None or rid > best[0]:
            best = (rid, doc)
    return best


def _nominal_measurement(doc: dict, tb: Testbench, name: str) -> float | None:
    """Measurement ``name`` at this bench's nominal PVT point
    (``tt`` / 27 C / nominal supply), read from a record's points."""
    for point in doc.get("points", []):
        if point.get("status") != "ok":
            continue
        if point.get("corner") != "tt" or float(point.get("temp_c", -1e9)) != 27.0:
            continue
        if abs(float(point.get("vdd", -1e9)) - tb.nominal_supply_v) > 1e-9:
            continue
        value = (point.get("measurements") or {}).get(name)
        if value is not None:
            return float(value)
    return None


def _postlayout_delta_lines(
    tb: Testbench,
    results: list[PointResult],
    summaries: dict[str, MeasurementSummary],
    context: dict,
) -> list[str]:
    """The schematic-vs-extracted delta section of an extracted-provenance
    record (issue #23's acceptance criterion: a post-layout record documents
    its delta from the schematic-level counterpart, not just the new number
    in isolation -- the convention gf180-sar-adc's `Supersedes` delta
    summaries follow, stated here as a table instead of prose).
    """
    counterpart = _latest_schematic_record(tb)
    if counterpart is None:
        return [
            "",
            "- **Post-layout delta**: NO schematic-provenance counterpart record "
            "exists under records/ -- the delta this section exists to document "
            "cannot be computed. This record stands alone, which is weaker "
            "evidence than the convention asks for.",
        ]
    rid, doc = counterpart
    ok = [r for r in results if r.status == "ok"]
    lines = [
        "",
        f"- **Post-layout delta** vs schematic record `{rid}` "
        f"(`{doc['context'].get('dut_id', '?')}`): nominal column is the "
        f"`tt_27c_{tb.nominal_supply_v:.2f}v` point of each record; mean column "
        "is each record's whole-grid mean.",
        "",
        "  | measurement | schematic nominal | post-layout nominal | Δ nominal | schematic mean | post-layout mean | Δ mean |",
        "  |---|---|---|---|---|---|---|",
    ]
    for name in tb.measure:
        s = summaries[name]
        if not s.values:
            continue
        now_nom = next(
            (r.measurements[name] for r in ok
             if r.point.corner.name == "tt" and r.point.temp_c == 27.0
             and abs(r.point.vdd - tb.nominal_supply_v) < 1e-9
             and name in r.measurements),
            None,
        )
        then_nom = _nominal_measurement(doc, tb, name)
        then_sum = (doc.get("summary") or {}).get(name) or {}
        then_mean = then_sum.get("mean")
        if now_nom is None or then_nom is None or then_mean is None:
            lines.append(f"  | `{name}` | — | — | — | — | — | — |")
            continue
        d_nom = (now_nom - then_nom) / abs(then_nom) * 100.0 if then_nom else float("nan")
        d_mean = (s.mean - then_mean) / abs(then_mean) * 100.0 if then_mean else float("nan")
        lines.append(
            f"  | `{name}` | {_fmt(then_nom)} | {_fmt(now_nom)} | "
            f"{d_nom:+.6g}% | {_fmt(then_mean)} | {_fmt(s.mean)} | {d_mean:+.6g}% |"
        )
    return lines



def point_check_outcome(tb: Testbench, result: PointResult) -> dict:
    """Point-local min/max verdict for one completed point.

    Only the per-point bounds (`min` / `max`) can be attributed to a single
    corner; grid spread and per-axis checks stay in the aggregate verdict.
    A required measurement that is absent or non-finite never passes.
    """
    if result.status != "ok":
        return {"status": "not_evaluated", "failures": []}
    failures: list[str] = []
    for name, spec in tb.checks.items():
        if "min" not in spec and "max" not in spec:
            continue
        value = result.measurements.get(name)
        if value is None or not _is_finite(value):
            failures.append(f"{name} missing or non-finite")
            continue
        if "min" in spec and value < spec["min"]:
            failures.append(f"{name} {value:g} < required min {spec['min']:g}")
        if "max" in spec and value > spec["max"]:
            failures.append(f"{name} {value:g} > allowed max {spec['max']:g}")
    return {"status": "fail" if failures else "pass", "failures": failures}


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
    # The probed systematic offset rides along as a per-point measurement on
    # extracted-provenance runs (issue #23) -- surfaced as an extra column
    # so a reader sees WHAT the ladder was referred to at each corner.
    if any("dut_vos_v" in r.measurements for r in results):
        names.append("dut_vos_v")
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
                f"**{result.status.upper()}**: {result.message}"
                + (
                    f" (⚠ {len(result.warnings)} warning(s): {'; '.join(result.warnings)})"
                    if result.warnings else ""
                )
                + " |"
            )
            continue
        cells = " | ".join(
            _fmt(result.measurements[n]) if n in result.measurements else "—"
            for n in names
        )
        outcome = point_check_outcome(tb, result)
        verdict = (
            "PASS" if outcome["status"] == "pass"
            else f"**FAIL**: {'; '.join(outcome['failures'])}"
        )
        if result.warnings:
            verdict += f" (⚠ {len(result.warnings)} warning(s): {'; '.join(result.warnings)})"
        lines.append(f"  | `{result.point.corner_id}` | {cells} | {verdict} |")

    lines += [
        "",
        "  The pass/fail column is the point-local `min`/`max` verdict for that",
        "  corner only. Grid-spread and per-axis checks are aggregate checks over",
        "  the whole grid, not per-corner verdicts; they are reported under",
        "  **Check failures** below.",
        "",
        "  Spread across the grid:",
        "",
    ]
    lines += [
        "  | measurement | min | max | mean | spread % | limits |",
        "  |---|---|---|---|---|---|",
    ]
    for name in names:
        if name == "dut_vos_v" and name not in summaries:
            # The probed offset is stamped per point by the runner (issue
            # #23), not produced by a manifest measure expr, so summarize it
            # straight off the results.
            values = {
                r.point.corner_id: r.measurements[name]
                for r in ok if name in r.measurements
            }
            if values:
                at_min = min(values, key=lambda k: values[k])
                at_max = max(values, key=lambda k: values[k])
                mean = statistics.fmean(values.values())
                lines.append(
                    f"  | `{name}` | {_fmt(values[at_min])} (`{at_min}`) | "
                    f"{_fmt(values[at_max])} (`{at_max}`) | {_fmt(mean)} | "
                    f"{_fmt(spread_pct(list(values.values())))} | "
                    "— (context, not checked) |"
                )
                continue
        s = summaries.get(name)
        if s is None or not s.values:
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
        s = summaries.get(name)
        if s is None:
            continue  # dut_vos_v context column: no per-axis sensitivity to state
        cells = []
        for axis in AXES:
            a = s.axes.get(axis)
            cells.append(
                f"{_fmt(a.weakest)} → {_fmt(a.strongest)} %" if a and a.varies else "—"
            )
        lines.append(f"  | `{name}` | " + " | ".join(cells) + " |")

    failures = {n: s.failures for n, s in summaries.items() if s.failures}
    skipped = {n: s.skipped for n, s in summaries.items() if s.skipped}
    if context.get("dut_provenance") == "extracted":
        lines += _postlayout_delta_lines(tb, results, summaries, context)
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

    reproduce = [f"  python3 sim/run_corners.py {tb.experiment}"]
    if context.get("dut_provenance") == "extracted":
        # The bound netlist is regenerated scratch (gitignored): the record's
        # reproduce step must build it first, and name the --dut entry that
        # selects it (issue #23).
        reproduce = [
            "  python3 layout/run_extract_sim.py",
            f"  python3 sim/run_corners.py {tb.experiment} --dut {context['dut_id']}",
        ]
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
        *reproduce,
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
    snapshots_dir = experiment_dir / "netlist-snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    json_path = records_dir / f"{rid}.json"
    snapshot_path = snapshots_dir / f"{rid}.spice"
    clash = [t for t in (record_path, json_path, snapshot_path) if t.exists()]
    if clash:
        raise FileExistsError(
            "refusing to overwrite append-only evidence: "
            + ", ".join(str(t) for t in clash)
        )
    _write_new(record_path, render_record(tb, results, summaries, context))

    _write_new(snapshot_path,
        f"* Netlist snapshot for record {rid} -- exactly what was simulated.\n"
        f"* DUT: {context['dut_id']} ({context['dut_provenance']}), "
        f"{context['dut_netlist']}\n"
        f"* Testbench: sim/{tb.experiment}/testbench/{tb.netlist.name}\n"
        "* ---------------- DUT NETLIST ----------------\n"
        + dut_netlist.read_text()
        + "\n* ---------------- TESTBENCH FRAGMENT ----------------\n"
        + tb.netlist.read_text()
    )

    nonfinite_paths: list[str] = []
    doc = (
            {
                "record_id": rid,
                "context": context,
                "testbench": tb.provenance(),
                "checks": tb.checks,
                "points": [
                    {**r.as_dict(), "check_outcome": point_check_outcome(tb, r)}
                    for r in results
                ],
                "summary": {
                    name: {
                        "min": s.minimum if s.values else None,
                        "max": s.maximum if s.values else None,
                        "mean": s.mean if s.values else None,
                        "at_min": s.at_min,
                        "at_max": s.at_max,
                        "spread_pct": s.spread if s.values else None,
                        "per_axis": {
                            a: {"weakest": ax.weakest, "strongest": ax.strongest,
                                "varies": ax.varies}
                            for a, ax in s.axes.items()
                        },
                        "failures": s.failures,
                        "skipped_checks": s.skipped,
                    }
                    for name, s in summaries.items()
                    if s.values or s.failures
                },
            }
    )
    doc = _strict_json_safe(doc, "$", nonfinite_paths)
    if nonfinite_paths:
        doc["nonfinite_omitted"] = nonfinite_paths
    _write_new(json_path,
        # strict JSON: never write NaN/Infinity tokens
        json.dumps(doc, indent=2, allow_nan=False)
        + "\n"
    )
    return record_path
