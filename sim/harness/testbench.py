"""Testbench manifests.

Testbenches follow the directory convention ratified in ``sim/README.md``:
each experiment gets ``sim/<experiment-slug>/`` and its testbench lives in
that experiment's ``testbench/`` subdirectory:

    sim/<experiment-slug>/testbench/tb.json            the manifest (this module)
    sim/<experiment-slug>/testbench/<something>.spice  a *netlist fragment*

The fragment must NOT contain ``.include`` of models, ``.lib``, ``.temp``,
``.control`` or ``.end``: the harness owns all of those so that one netlist
can be swept across the whole PVT grid without editing. The harness hands
the fragment these parameters:

    vdd_val   the supply for this PVT point (nominal, +tol or -tol)
    vdd_nom   the nominal supply, for ratio-style measurements
    temp_c    the temperature for this PVT point (also set via .temp)

plus anything in ``sim/dut.json``'s ``params`` map (the bias current and
input common mode the DUT is specified at), plus anything in the manifest's
own ``params`` map. The DUT subcircuits themselves are supplied by the
harness from ``sim/dut.json`` -- a fragment instantiates ``comparator_dut``
or ``comparator_dut_analog`` and never defines them.

Ported from ``2AMLogic/gf180-sar-adc``'s ``sim/harness/testbench.py``. NOT
ported: its ``netlist_provenance`` field, which described whether the
COMPARATOR netlist embedded in the fragment was schematic or extracted --
that role belongs to ``sim/dut.json``'s ``provenance`` here, because the DUT
is bound once for all four experiments rather than copied into each.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .corners import (
    DEFAULT_CORNER_SET,
    DEFAULT_NOMINAL_SUPPLY_V,
    DEFAULT_SUPPLY_TOLERANCE,
    DEFAULT_TEMPERATURES_C,
)

MANIFEST_NAME = "tb.json"

#: Name of the per-experiment subdirectory that holds the testbench, per
#: the directory convention in ``sim/README.md``.
TESTBENCH_DIRNAME = "testbench"

FORBIDDEN_DIRECTIVES = (".control", ".endc", ".end", ".lib", ".temp", ".include")

#: Keys a ``checks`` entry may carry. Anything else is a typo that would
#: otherwise be silently ignored -- and a silently-ignored ``min_spread_pct``
#: is exactly the failure this harness exists to prevent.
CHECK_KEYS = (
    "min",
    "max",
    "max_spread_pct",
    "min_spread_pct",
    "min_spread_pct_by_axis",
    "max_spread_pct_by_axis",
    "description",
)

#: Axis names accepted by the per-axis sensitivity checks.
AXES = ("process", "temperature", "supply")

#: Keys the manifest's ``evidence`` block may carry. These become the
#: narrative header of the evidence record (sim/README.md "Record format").
EVIDENCE_KEYS = ("record_kind", "mc_seed", "mc_scope", "mc_sigma", "notes")


@dataclass
class Testbench:
    directory: Path
    name: str
    netlist: Path
    description: str = ""
    claim: str = ""
    nominal_supply_v: float = DEFAULT_NOMINAL_SUPPLY_V
    supply_tolerance: float = DEFAULT_SUPPLY_TOLERANCE
    temperatures_c: tuple[float, ...] = DEFAULT_TEMPERATURES_C
    corners: tuple[str, ...] = (DEFAULT_CORNER_SET,)
    analyses: tuple[str, ...] = ("op",)
    measure: dict[str, str] = field(default_factory=dict)
    params: dict[str, object] = field(default_factory=dict)
    checks: dict[str, dict] = field(default_factory=dict)
    options: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)
    #: Optional offset-probe declaration (issue #23): a second, tiny fragment
    #:+ analyses/measure pair that measures the DUT's deterministic
    #: systematic input-referred offset at THIS PVT point, so the main deck's
    #: overdrive ladder can be referred to it (the gf180-sar-adc
    #: post-layout precedent -- a flat extracted netlist carries real layout
    #: asymmetry that a symmetric schematic cannot have). Only runs against
    #: an ``extracted``-provenance DUT; the measured offset is injected into
    #: the main deck as the ``dut_vos`` parameter.
    offset_probe: dict = field(default_factory=dict)

    @property
    def experiment(self) -> str:
        """``sim/<experiment-slug>/testbench/tb.json`` -> ``<experiment-slug>``."""
        return self.directory.parent.name

    @property
    def experiment_dir(self) -> Path:
        """``sim/<experiment-slug>/`` -- where records/corners/snapshots live."""
        return self.directory.parent

    @property
    def netlist_sha256(self) -> str:
        return hashlib.sha256(self.netlist.read_bytes()).hexdigest()

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256((self.directory / MANIFEST_NAME).read_bytes()).hexdigest()

    def offset_probe_testbench(self) -> "Testbench | None":
        """The declared offset probe as its own :class:`Testbench`, or None.

        The probe reuses this bench's supply/common-mode/clock conventions
        (its fragment does), so only ``netlist``/``analyses``/``measure``
        are declared; everything else inherits.
        """
        if not self.offset_probe:
            return None
        declaration = self.offset_probe
        netlist = self.directory / declaration["netlist"]
        if not netlist.is_file():
            raise FileNotFoundError(
                f"{self.directory / MANIFEST_NAME}: offset_probe names "
                f"{netlist}, which does not exist"
            )
        measure = dict(declaration.get("measure") or {})
        if "dut_vos" not in measure:
            raise ValueError(
                f"{self.directory / MANIFEST_NAME}: offset_probe's measure "
                "must define 'dut_vos' (the main deck injects it as dut_vos)"
            )
        return Testbench(
            directory=self.directory,
            name=f"{self.name}-vosprobe",
            netlist=netlist,
            description=(
                "systematic input-referred offset probe for the "
                f"{self.name} bench (issue #23)"
            ),
            nominal_supply_v=self.nominal_supply_v,
            supply_tolerance=self.supply_tolerance,
            analyses=tuple(declaration.get("analyses", ("op",))),
            measure=measure,
            options=self.options,
        )

    def provenance(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "claim": self.claim,
            "experiment": self.experiment,
            "directory": self.directory.name,
            "netlist": self.netlist.name,
            "netlist_sha256": self.netlist_sha256,
            "manifest_sha256": self.manifest_sha256,
            "nominal_supply_v": self.nominal_supply_v,
            "supply_tolerance": self.supply_tolerance,
        }


def _require(manifest: dict, key: str, path: Path):
    if key not in manifest:
        raise ValueError(f"{path}: missing required key {key!r}")
    return manifest[key]


class _NonstandardConstant:
    """Placeholder for a NaN / Infinity / -Infinity token found while parsing.

    ``json`` accepts those tokens by default; ``parse_constant`` swaps them for
    this marker so validation can report WHERE (measurement / key / axis) the
    nonstandard constant sat, instead of a context-free parse error.
    """

    def __init__(self, token: str):
        self.token = token

    def __repr__(self) -> str:
        return f"nonstandard JSON constant {self.token}"


def _reject_nonstandard(node, where: str, path: Path) -> None:
    """Raise if a parsed manifest subtree still holds a nonstandard constant."""
    if isinstance(node, _NonstandardConstant):
        raise ValueError(f"{path}: {where} is {node!r}; manifest numbers must be finite")
    if isinstance(node, dict):
        for k, v in node.items():
            _reject_nonstandard(v, f"{where}.{k}" if where else str(k), path)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _reject_nonstandard(v, f"{where}[{i}]", path)


def _check_bound(value, where: str, path: Path, *, nonneg: bool = False) -> float:
    """Return ``value`` if it is a finite real number, else raise ``ValueError``."""
    if isinstance(value, _NonstandardConstant):
        raise ValueError(
            f"{path}: {where} is {value!r}; it must be a finite number"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{path}: {where} must be a finite number, got {type(value).__name__} {value!r}"
        )
    if not math.isfinite(value):
        raise ValueError(f"{path}: {where} must be finite, got {value!r}")
    if nonneg and value < 0:
        raise ValueError(f"{path}: {where} must be >= 0, got {value!r}")
    return value


def _check_pair(lo, hi, lo_where: str, hi_where: str, path: Path) -> None:
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(
            f"{path}: {lo_where} ({lo!r}) is greater than {hi_where} ({hi!r}); "
            "the bounds are reversed"
        )


def _validate_checks(checks: dict[str, dict], measure: dict[str, str], path: Path) -> None:
    for name, spec in checks.items():
        if name not in measure:
            raise ValueError(
                f"{path}: check {name!r} does not name a measurement "
                f"(known: {', '.join(sorted(measure))})"
            )
        if not isinstance(spec, dict):
            raise ValueError(f"{path}: check {name!r} must be an object, got {type(spec).__name__}")
        unknown = sorted(set(spec) - set(CHECK_KEYS))
        if unknown:
            raise ValueError(
                f"{path}: check {name!r} has unknown key(s) {', '.join(unknown)}; "
                f"known: {', '.join(CHECK_KEYS)}"
            )
        for axis_key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
            axes = spec.get(axis_key)
            if axes is None:
                continue
            if not isinstance(axes, dict):
                raise ValueError(f"{path}: check {name!r}: {axis_key} must be an object")
            unknown_axes = sorted(set(axes) - set(AXES))
            if unknown_axes:
                raise ValueError(
                    f"{path}: check {name!r}: unknown axis/axes {', '.join(unknown_axes)} in "
                    f"{axis_key}; known: {', '.join(AXES)}"
                )
        # Numeric validity of every bound (scalar and per-axis alike).
        vals: dict[str, float] = {}
        for key in ("min", "max", "max_spread_pct", "min_spread_pct"):
            if key in spec:
                vals[key] = _check_bound(
                    spec[key], f"check {name!r}: {key}", path,
                    nonneg=key.endswith("_spread_pct"),
                )
        _check_pair(vals.get("min"), vals.get("max"),
                    f"check {name!r}: min", f"max", path)
        _check_pair(vals.get("min_spread_pct"), vals.get("max_spread_pct"),
                    f"check {name!r}: min_spread_pct", "max_spread_pct", path)
        by_axis: dict[str, dict[str, float]] = {}
        for axis_key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
            for axis, bound in (spec.get(axis_key) or {}).items():
                by_axis.setdefault(axis, {})[axis_key] = _check_bound(
                    bound, f"check {name!r}: {axis_key}[{axis}]", path, nonneg=True
                )
        for axis, b in by_axis.items():
            _check_pair(
                b.get("min_spread_pct_by_axis"), b.get("max_spread_pct_by_axis"),
                f"check {name!r}: min_spread_pct_by_axis[{axis}]",
                f"max_spread_pct_by_axis[{axis}]", path,
            )


def load(directory: str | Path) -> Testbench:
    """Load a testbench manifest into a :class:`Testbench`.

    Accepts the experiment directory (``sim/<slug>/``), its ``testbench/``
    subdirectory, or the ``tb.json`` path itself.
    """
    directory = Path(directory).resolve()
    if directory.is_file() and directory.name == MANIFEST_NAME:
        directory = directory.parent
    if (directory / TESTBENCH_DIRNAME / MANIFEST_NAME).is_file():
        directory = directory / TESTBENCH_DIRNAME
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no {MANIFEST_NAME} in {directory}")

    manifest = json.loads(
        manifest_path.read_text(), parse_constant=_NonstandardConstant
    )

    _reject_nonstandard(
        {k: v for k, v in manifest.items() if k != "checks"}, "", manifest_path
    )

    netlist = directory / _require(manifest, "netlist", manifest_path)
    if not netlist.is_file():
        raise FileNotFoundError(f"{manifest_path}: netlist {netlist} does not exist")

    measure = dict(_require(manifest, "measure", manifest_path))
    if not measure:
        raise ValueError(f"{manifest_path}: 'measure' must define at least one measurement")
    for key in measure:
        if not key.replace("_", "").isalnum():
            raise ValueError(
                f"{manifest_path}: measurement name {key!r} must be alphanumeric/underscore "
                "(it becomes an ngspice vector name)"
            )
        if key != key.lower():
            # ngspice folds vector names to lower case, so `let m_Vos = ...`
            # prints back as `m_vos` and the runner's exact-name match never
            # finds it -- every point fails with "no measurements parsed"
            # after the whole grid has already been simulated. Refuse at load
            # time instead of discovering it hours in.
            raise ValueError(
                f"{manifest_path}: measurement name {key!r} must be lower case "
                "(ngspice folds vector names, so an upper-case name is printed "
                f"back as {key.lower()!r} and never matches)"
            )

    checks = dict(manifest.get("checks", {}))
    _validate_checks(checks, measure, manifest_path)

    evidence = dict(manifest.get("evidence", {}))
    unknown_evidence = sorted(set(evidence) - set(EVIDENCE_KEYS))
    if unknown_evidence:
        raise ValueError(
            f"{manifest_path}: evidence block has unknown key(s) "
            f"{', '.join(unknown_evidence)}; known: {', '.join(EVIDENCE_KEYS)}"
        )

    tb = Testbench(
        directory=directory,
        name=manifest.get("name", directory.parent.name),
        netlist=netlist,
        description=manifest.get("description", ""),
        claim=manifest.get("claim", ""),
        nominal_supply_v=float(manifest.get("nominal_supply_v", DEFAULT_NOMINAL_SUPPLY_V)),
        supply_tolerance=float(manifest.get("supply_tolerance", DEFAULT_SUPPLY_TOLERANCE)),
        temperatures_c=tuple(
            float(t) for t in manifest.get("temperatures_c", DEFAULT_TEMPERATURES_C)
        ),
        corners=tuple(manifest.get("corners", (DEFAULT_CORNER_SET,))),
        analyses=tuple(manifest.get("analyses", ("op",))),
        measure=measure,
        params=dict(manifest.get("params", {})),
        checks=checks,
        options=tuple(manifest.get("options", ())),
        evidence=evidence,
        offset_probe=dict(manifest.get("offset_probe", {})),
    )
    validate_netlist(tb)
    probe = tb.offset_probe_testbench()
    if probe is not None:
        validate_netlist(probe)
    return tb


def validate_netlist(tb: Testbench) -> None:
    """Reject fragments that try to own what the harness owns.

    Catching this here is much friendlier than debugging a duplicated
    ``.end`` or a hardcoded ``.temp 27`` that silently pins every corner to
    room temperature.
    """
    problems: list[str] = []
    for lineno, raw in enumerate(tb.netlist.read_text().splitlines(), start=1):
        line = raw.strip().lower()
        if not line.startswith("."):
            continue
        directive = line.split()[0]
        if directive in FORBIDDEN_DIRECTIVES:
            problems.append(f"  line {lineno}: {raw.strip()}")
    if problems:
        raise ValueError(
            f"{tb.netlist}: netlist fragments must not contain "
            f"{', '.join(FORBIDDEN_DIRECTIVES)} -- the harness supplies the models, "
            "corner libs, temperature, the DUT netlist and the control block:\n"
            + "\n".join(problems)
        )


def discover(root: str | Path) -> list[Path]:
    """Every experiment directory under ``root`` that owns a testbench.

    Looks for ``<root>/<experiment-slug>/testbench/tb.json`` and returns the
    ``<experiment-slug>`` directories, sorted.
    """
    root = Path(root)
    return sorted(
        p.parent.parent for p in root.glob(f"*/{TESTBENCH_DIRNAME}/{MANIFEST_NAME}")
    )
