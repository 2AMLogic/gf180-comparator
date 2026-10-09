#!/usr/bin/env python3
"""Keep ``manifests/integrator.json``'s maturity rung consistent with the
committed signoff verdict of record.

The integrator view must not advertise a tier the graded report does not
support (issue #84: the manifest said ``"T1 (design-evidence tiers,
graded)"`` while ``signoff/signoff-report.json`` recorded ``tier: null``
with only part of the T1 checklist met). This verifier is the CI side of
that contract:

- ``maturity.rung`` must equal the report's ``tier``. JSON ``null`` on
  both sides passes (no tier graded), and any supported ladder value
  (``T1``-``T4``, per ``signoff/design-evidence-tiers.md``) passes when
  both sides carry it;
- any mismatch fails, in either direction -- advertising a tier the
  report does not record, or withholding one it does;
- a value outside ``null``/``T1``-``T4`` fails on either side, so a
  prose string like ``"T1 (design-evidence tiers, graded)"`` can never
  pose as a graded rung again;
- a report with no ``tier`` key at all fails as malformed -- an absent
  key must never be read as an explicit graded ``null``;
- ``maturity.verdict_of_record`` must name this repo's fixed verdict of
  record (``signoff/signoff-report.json``), so the manifest cannot dodge
  the comparison by pointing elsewhere.

Issue #161 extends the same check to the manifest's *structural* facts,
each compared against the committed artifact that is authoritative for it
(prose fields -- ``description``, ``meaning``, ``derivation``, ``notes``,
the ``provenance`` stamp -- are deliberately not checked):

- **paths** -- every path field (``PATH_FIELDS`` below) must be a
  normalized repository-relative path (no absolute path, no ``..``/``.``
  segment, no backslash) naming an existing file; inside a git work tree
  it must also be tracked (``git ls-files``), so a gitignored scratch
  artifact can never be published as an integration input;
- **netlist binding** -- ``netlist.binding`` must be the harness's DUT
  binding (``sim/dut.json``); its active entry is loaded with the
  harness's own loader (``sim/harness/dut.py``, which also enforces the
  interface contract on that netlist), and ``netlist.path`` and
  ``netlist.provenance`` must equal the active binding's netlist and
  provenance;
- **top subcircuit** -- ``netlist.top_subckt`` must be the whole-comparator
  subcircuit the harness contract requires of *every* binding provenance
  (``REQUIRED_SUBCKTS_BY_PROVENANCE``), and must be declared in the
  published netlist;
- **ordered ports** -- ``ports[].name`` must be unique, and in order equal
  to both the top subcircuit's ``.subckt`` pin list in the published
  netlist (parsed with the harness's own parser) and the harness interface
  contract (``REQUIRED_SUBCKTS``);
- **top cell** -- ``top_cell`` must equal the placement envelope's
  ``cell_name``, and ``layout.gds`` must be the GDS the envelope's
  ``gds_path`` names (no GDS parser: the envelope already records both);
- **area** -- derived from the placement envelope's ``bbox_um``
  (``(x1-x0) * (y1-y0)``; every coordinate finite, both extents
  positive). ``area.value_um2`` and ``area.value_mm2`` must be finite,
  positive JSON numbers within the documented rounding tolerances of the
  derived area: ``AREA_UM2_TOL`` (half a um2 -- the published um2 value
  may be rounded to a whole um2 or finer) and ``AREA_MM2_TOL`` (half of
  1e-4 mm2 -- the published mm2 value may be rounded to four decimals or
  finer), each widened by ``AREA_FLOAT_SLACK`` so a value exactly on the
  rounding boundary is not rejected by binary floating point.

Every failure names the manifest field and the authoritative source it
disagrees with.

Run from anywhere inside the repository:

    python3 manifests/verify-integrator.py

CI runs this command (a step in ``.github/workflows/signoff.yml``) on
every push/PR, alongside ``signoff/verify-report.py``. Unlike the
re-grading verifier it needs no ``klt`` install, no PDK and no simulator:
it compares committed files only.
"""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATOR = REPO_ROOT / "manifests" / "integrator.json"
REPORT = REPO_ROOT / "signoff" / "signoff-report.json"

#: The one file this repo treats as the verdict of record (manifests/README.md
#: "Where the maturity rung lives"). The maturity pointer must name it.
VERDICT_OF_RECORD = "signoff/signoff-report.json"

#: The tier ladder from signoff/design-evidence-tiers.md. ``klt signoff``
#: records ``null`` until it awards a tier; beyond that only these values
#: are meaningful as a graded rung.
SUPPORTED_TIERS = ("T1", "T2", "T3", "T4")

#: The harness module whose DUT loader and ``.subckt`` parser are the
#: authority for the netlist interface (one parser, no divergent copy).
HARNESS_DUT = REPO_ROOT / "sim" / "harness" / "dut.py"

#: The DUT binding the harness reads (``sim/harness/dut.py`` DUT_CONFIG).
DUT_BINDING = "sim/dut.json"

#: Manifest fields that hold a repository-relative path, as dotted keys.
#: ``"#anchor"`` suffixes are stripped. Fields in PATH_PREFIX_FIELDS are
#: prose whose *leading token* is a path (e.g. ``"sim/dut/README.md
#: (Interface contract; ...)"``); only that token is checked.
PATH_FIELDS = (
    "netlist.path",
    "netlist.binding",
    "netlist.interface_contract",
    "layout.gds",
    "layout.placement_evidence",
    "maturity.verdict_of_record",
    "maturity.manifest",
    "maturity.readme",
    "maturity.regenerate",
    "spec.target_table",
    "spec.consumers",
)
PATH_PREFIX_FIELDS = (
    "port_list_source",
    "area.source",
)

#: Area rounding tolerances (issue #161). The published values are rounded
#: for readability; the derived bbox area is exact to the envelope's
#: coordinates. Half a unit in the last place each field may be rounded to.
AREA_UM2_TOL = 0.5  # value_um2 rounded to a whole um2 (or finer)
AREA_MM2_TOL = 0.00005  # value_mm2 rounded to 4 decimals (or finer)
#: Absorbs binary floating-point error so a value exactly on a rounding
#: boundary passes; far below either tolerance.
AREA_FLOAT_SLACK = 1e-9
UM2_PER_MM2 = 1e6


def fail(problems: list[str]) -> None:
    for line in problems:
        print(f"FAIL: {line}", file=sys.stderr)
    sys.exit(f"{len(problems)} integrator manifest consistency problem(s) -- see above")


def describe(value: Any) -> str:
    return "null" if value is None else repr(value)


def lookup(document: dict, dotted: str) -> tuple[bool, Any]:
    """Return ``(present, value)`` for a dotted key path."""
    node: Any = document
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def git_tracked_checker():
    """Return ``tracked(relpath) -> bool``, or None outside a git work tree
    rooted exactly at REPO_ROOT (e.g. a scratch test sandbox)."""
    try:
        top = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != REPO_ROOT:
        return None

    def tracked(rel: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", "--", rel],
            capture_output=True, text=True,
        )
        return result.returncode == 0

    return tracked


def check_repo_path(field: str, value: Any, tracked) -> str | None:
    """Validate one repository-relative path; return a problem or None."""
    if not isinstance(value, str) or not value.strip():
        return f"{field} is {describe(value)}, expected a repository-relative path string"
    rel = value.split("#", 1)[0]
    if "\\" in rel or rel.startswith("/") or PurePosixPath(rel).is_absolute():
        return f"{field} is {value!r}: must be a repository-relative POSIX path, not absolute"
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return (
            f"{field} is {value!r}: must be a normalized repository-relative "
            "path (no '..', '.', or empty segments)"
        )
    target = REPO_ROOT / rel
    if not target.is_file():
        return (
            f"{field} names {rel!r}, which does not exist in the repository "
            "-- every path the integrator view publishes must resolve to a "
            "committed file (manifests/README.md 'Update discipline')"
        )
    if tracked is not None and not tracked(rel):
        return (
            f"{field} names {rel!r}, which exists but is not tracked by git "
            "-- a scratch or ignored artifact cannot be a published "
            "integration input"
        )
    return None


def check_paths(integrator: dict, tracked) -> list[str]:
    problems: list[str] = []
    for field in PATH_FIELDS:
        present, value = lookup(integrator, field)
        if not present:
            problems.append(f"{field} is missing -- the integrator view must publish it")
            continue
        problem = check_repo_path(field, value, tracked)
        if problem:
            problems.append(problem)
    for field in PATH_PREFIX_FIELDS:
        present, value = lookup(integrator, field)
        if not present:
            problems.append(f"{field} is missing -- the integrator view must publish it")
            continue
        if not isinstance(value, str) or not value.split():
            problems.append(f"{field} is {describe(value)}, expected a string starting with a repository-relative path")
            continue
        problem = check_repo_path(f"{field} (leading path)", value.split()[0], tracked)
        if problem:
            problems.append(problem)
    return problems


def load_harness_dut() -> ModuleType:
    """Import ``sim/harness/dut.py`` by path (stdlib-only module)."""
    name = "_integrator_harness_dut"
    spec = importlib.util.spec_from_file_location(name, HARNESS_DUT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {HARNESS_DUT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def check_netlist_and_ports(integrator: dict) -> list[str]:
    problems: list[str] = []
    if not HARNESS_DUT.is_file():
        return [f"missing {HARNESS_DUT.relative_to(REPO_ROOT)} -- the harness DUT loader is the authority for the netlist interface"]
    harness = load_harness_dut()

    netlist = integrator.get("netlist")
    if not isinstance(netlist, dict):
        return ["netlist is missing or not an object -- the integrator view must publish the netlist binding"]

    binding = netlist.get("binding")
    if binding != DUT_BINDING:
        problems.append(
            f"netlist.binding is {describe(binding)}, expected {DUT_BINDING!r} "
            "-- authoritative source: sim/harness/dut.py DUT_CONFIG (the "
            "binding every bench runs against)"
        )
    # Always compare against the harness's binding, whatever the pointer says.
    try:
        active = harness.load(REPO_ROOT / DUT_BINDING)
    except harness.DutError as exc:
        problems.append(
            f"active DUT binding in {DUT_BINDING} does not load "
            f"(authoritative source: sim/harness/dut.py): {exc}"
        )
        active = None

    path = netlist.get("path")
    path_file = REPO_ROOT / path if isinstance(path, str) else None
    if active is not None:
        try:
            active_rel = active.netlist.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            active_rel = str(active.netlist)
        if path != active_rel:
            problems.append(
                f"netlist.path is {describe(path)} but the active DUT binding "
                f"({DUT_BINDING} 'active' = {active.dut_id!r}) binds "
                f"{active_rel!r} -- authoritative source: {DUT_BINDING}"
            )
        if netlist.get("provenance") != active.provenance:
            problems.append(
                f"netlist.provenance is {describe(netlist.get('provenance'))} "
                f"but the active DUT binding ({DUT_BINDING} 'active' = "
                f"{active.dut_id!r}) declares {active.provenance!r} -- "
                f"authoritative source: {DUT_BINDING}"
            )

    # The top subckt: the whole-comparator subckt every binding provenance
    # must define, per the harness contract.
    required_sets = [set(v) for v in harness.REQUIRED_SUBCKTS_BY_PROVENANCE.values()]
    always_required = sorted(set.intersection(*required_sets)) if required_sets else []
    top = netlist.get("top_subckt")
    if len(always_required) != 1:
        problems.append(
            "cannot identify the top subcircuit from sim/harness/dut.py "
            "REQUIRED_SUBCKTS_BY_PROVENANCE (expected exactly one subckt "
            f"required for every provenance, found {always_required})"
        )
        expected_top = None
    else:
        expected_top = always_required[0]
        if top != expected_top:
            problems.append(
                f"netlist.top_subckt is {describe(top)}, expected "
                f"{expected_top!r} -- authoritative source: "
                "sim/harness/dut.py REQUIRED_SUBCKTS_BY_PROVENANCE (the "
                "whole-comparator subckt every binding must define)"
            )

    declared: dict[str, tuple[str, ...]] = {}
    if path_file is not None and path_file.is_file():
        declared = harness._declared_subckts(path_file.read_text())
        if isinstance(top, str) and top.lower() not in declared:
            problems.append(
                f"netlist.top_subckt {top!r} is not declared in netlist.path "
                f"{path!r} (declares: {', '.join(sorted(declared)) or '<none>'}) "
                f"-- authoritative source: {path}"
            )
    # (a missing/invalid netlist.path is reported by the path checks)

    ports = integrator.get("ports")
    if not isinstance(ports, list) or not ports:
        problems.append("ports is missing or empty -- the integrator view must publish the ordered port list")
        return problems
    names: list[Any] = []
    for index, port in enumerate(ports):
        name = port.get("name") if isinstance(port, dict) else None
        if not isinstance(name, str) or not name:
            problems.append(f"ports[{index}].name is {describe(name)}, expected a pin name string")
        names.append(name)
    seen: set = set()
    dupes = []
    for name in names:
        if name in seen and name not in dupes:
            dupes.append(name)
        seen.add(name)
    if dupes:
        problems.append(
            f"ports[].name lists {', '.join(map(repr, dupes))} more than once "
            "-- each pin is published exactly once"
        )

    def compare(expected: tuple[str, ...], source: str) -> None:
        if list(names) == list(expected):
            return
        missing = [p for p in expected if p not in names]
        extra = [n for n in names if n not in expected]
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unexpected {', '.join(map(str, extra))}")
        if not missing and not extra and not dupes:
            detail.append("reordered")
        problems.append(
            f"ports[].name order is {' '.join(map(str, names))}, expected "
            f"{' '.join(expected)} ({'; '.join(detail) or 'differs'}) -- "
            f"authoritative source: {source}"
        )

    if isinstance(top, str):
        contract = harness.REQUIRED_SUBCKTS.get(top.lower())
        if contract is not None:
            compare(contract, f"sim/harness/dut.py REQUIRED_SUBCKTS[{top!r}] (sim/dut/README.md 'Interface contract')")
        if top.lower() in declared:
            compare(declared[top.lower()], f"the `.subckt {top}` pin list in {path}")
    return problems


def check_layout_and_area(integrator: dict) -> list[str]:
    problems: list[str] = []
    present, envelope_rel = lookup(integrator, "layout.placement_evidence")
    if not present or not isinstance(envelope_rel, str):
        return problems  # reported by the path checks
    envelope_path = REPO_ROOT / envelope_rel
    if not envelope_path.is_file():
        return problems  # reported by the path checks
    try:
        envelope = json.loads(envelope_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"layout.placement_evidence {envelope_rel!r} is not valid JSON: {exc}"]
    if not isinstance(envelope, dict):
        return [f"layout.placement_evidence {envelope_rel!r} is not a JSON object"]

    # Top-cell identity, where the envelope records it.
    if "cell_name" in envelope:
        if integrator.get("top_cell") != envelope["cell_name"]:
            problems.append(
                f"top_cell is {describe(integrator.get('top_cell'))} but the "
                f"placement envelope records cell_name "
                f"{describe(envelope['cell_name'])} -- authoritative source: "
                f"{envelope_rel} cell_name"
            )
    if isinstance(envelope.get("gds_path"), str):
        gds_expected = (envelope_path.parent / envelope["gds_path"]).resolve()
        _, gds = lookup(integrator, "layout.gds")
        if not isinstance(gds, str) or (REPO_ROOT / gds).resolve() != gds_expected:
            try:
                shown = gds_expected.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                shown = str(gds_expected)
            problems.append(
                f"layout.gds is {describe(gds)} but the placement envelope's "
                f"gds_path names {shown!r} -- authoritative source: "
                f"{envelope_rel} gds_path"
            )

    # Area from the envelope bbox.
    bbox = envelope.get("bbox_um")
    source = f"{envelope_rel} bbox_um"
    derived = None
    if not isinstance(bbox, dict):
        problems.append(f"{source} is missing -- cannot derive the published area")
    else:
        coords = {k: bbox.get(k) for k in ("x0", "y0", "x1", "y1")}
        bad = [k for k, v in coords.items() if not is_number(v) or not math.isfinite(v)]
        if bad:
            problems.append(
                f"{source} has non-finite or non-numeric "
                f"{', '.join(f'{k}={describe(coords[k])}' for k in bad)} -- "
                "cannot derive the published area"
            )
        else:
            width = coords["x1"] - coords["x0"]
            height = coords["y1"] - coords["y0"]
            if not (width > 0 and height > 0):
                problems.append(
                    f"{source} is degenerate (width {width!r} um, height "
                    f"{height!r} um) -- the derived area must be positive"
                )
            else:
                derived = width * height

    area = integrator.get("area")
    if not isinstance(area, dict):
        problems.append("area is missing or not an object -- the integrator view must publish the measured area")
        return problems
    for field, scale, tol, unit in (
        ("value_um2", 1.0, AREA_UM2_TOL, "um2"),
        ("value_mm2", 1.0 / UM2_PER_MM2, AREA_MM2_TOL, "mm2"),
    ):
        value = area.get(field)
        if not is_number(value) or not math.isfinite(value) or value <= 0:
            problems.append(
                f"area.{field} is {describe(value)}, expected a finite "
                f"positive number (derived from {source})"
            )
            continue
        if derived is None:
            continue
        expected = derived * scale
        if abs(value - expected) > tol + AREA_FLOAT_SLACK * max(1.0, abs(expected)):
            problems.append(
                f"area.{field} is {value!r} {unit} but the placement bbox "
                f"gives {expected!r} {unit} (|diff| {abs(value - expected):.6g} "
                f"> rounding tolerance {tol} {unit}) -- authoritative source: "
                f"{source}"
            )
    return problems


def check_maturity(integrator: dict, report: dict) -> list[str]:
    maturity = integrator.get("maturity")
    if not isinstance(maturity, dict):
        sys.exit("manifests/integrator.json has no maturity object")

    problems: list[str] = []

    pointer = maturity.get("verdict_of_record")
    if pointer != VERDICT_OF_RECORD:
        problems.append(
            f"maturity.verdict_of_record is {pointer!r}, expected "
            f"{VERDICT_OF_RECORD!r} -- the rung comparison below is against "
            "this repo's fixed verdict of record; re-point it (or move the "
            "verdict of record deliberately and update this verifier in the "
            "same change)"
        )

    if "tier" not in report:
        # A missing key is a malformed report, not a graded null: reading it
        # with .get() would silently equate "tier absent" with "tier: null"
        # and let a report that no longer records a tier verdict pass (the
        # gap the review of PR #93 caught).
        problems.append(
            "signoff/signoff-report.json has no 'tier' key at all -- a "
            "malformed report cannot back any rung value; re-grade and "
            "commit a well-formed report via ./signoff/regenerate.sh"
        )
        tier = None
    else:
        tier = report["tier"]

    rung = maturity.get("rung", "")

    for side, value in (("maturity.rung", rung), ("report tier", tier)):
        if value is not None and value not in SUPPORTED_TIERS:
            problems.append(
                f"{side} is {describe(value)}, expected null or one of "
                f"{'/'.join(SUPPORTED_TIERS)} -- a graded rung is a ladder "
                "value from signoff/design-evidence-tiers.md, never prose"
            )

    if (
        (rung is None or rung in SUPPORTED_TIERS)
        and (tier is None or tier in SUPPORTED_TIERS)
        and rung != tier
    ):
        problems.append(
            f"maturity.rung is {describe(rung)} but the verdict of record "
            f"records tier {describe(tier)} -- the integrator view must "
            "mirror the committed grade exactly; re-grade via "
            "./signoff/regenerate.sh and refresh manifests/integrator.json's "
            "maturity.rung (and provenance) in the same change, or restore "
            "the report"
        )

    return problems


def main() -> None:
    if not INTEGRATOR.is_file():
        sys.exit(f"missing {INTEGRATOR.relative_to(REPO_ROOT)}")
    if not REPORT.is_file():
        sys.exit(
            "missing signoff/signoff-report.json (the committed verdict of "
            "record) -- generate it with ./signoff/regenerate.sh and commit "
            "it alongside the manifest"
        )
    integrator = json.loads(INTEGRATOR.read_text())
    report = json.loads(REPORT.read_text())

    problems = check_maturity(integrator, report)
    tracked = git_tracked_checker()
    problems += check_paths(integrator, tracked)
    problems += check_netlist_and_ports(integrator)
    problems += check_layout_and_area(integrator)

    if problems:
        fail(problems)

    rung = integrator["maturity"].get("rung", "")
    state = "null (no tier graded)" if rung is None else rung
    print("OK: manifests/integrator.json maturity.rung == signoff/signoff-report.json tier")
    print(f"OK: graded maturity rung is {state}; an operator award is a separate act (see manifests/README.md)")
    print(
        "OK: published paths resolve to repository files"
        + (" tracked by git" if tracked is not None else " (not a git work tree: tracked-ness not checked)")
    )
    print(
        f"OK: netlist.path/top_subckt/ports agree with the active DUT binding "
        f"({DUT_BINDING}) and the harness interface contract"
    )
    print(
        "OK: top_cell and area agree with the placement envelope "
        f"(tolerance {AREA_UM2_TOL} um2 / {AREA_MM2_TOL} mm2)"
    )


if __name__ == "__main__":
    main()
