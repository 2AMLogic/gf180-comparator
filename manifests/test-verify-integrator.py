#!/usr/bin/env python3
"""Regression matrix for ``manifests/verify-integrator.py``.

Runs the committed verifier inside scratch sandboxes (temp copies of the
verifier plus doctored ``integrator.json`` / ``signoff-report.json``
pairs) and asserts the exit code for every case the consistency contract
names -- including the malformed-report case the review of PR #93 added:
a report whose ``tier`` key is missing entirely must FAIL, not pass as an
implicit ``null``. Against the pre-fix verifier (which read the tier with
``.get()``) that case exits 0, so this matrix fails there -- it is the
committed, CI-run form of the test-first claim for this guard.

Issue #161 extends the matrix to the structural checks: published paths
(missing, absolute, ``..``, untracked in a git sandbox), the top
subcircuit, ordered ports (reordered / duplicated / missing / extra),
disagreement with the active DUT binding (``sim/dut.json``), top-cell
identity, and area (non-finite, non-positive, non-numeric, outside the
rounding tolerance, plus pass cases exactly on the rounding boundary).
Failing structural cases also assert the FAIL text names the manifest
field and its authoritative source. Each sandbox carries copies of every
committed file the verifier reads (``SANDBOX_FILES``), so no PDK or
simulator is needed.

Also asserts the real committed pair (``manifests/integrator.json`` vs
``signoff/signoff-report.json``) passes.

Run from anywhere inside the repository:

    python3 manifests/test-verify-integrator.py

CI runs this command (a step in ``.github/workflows/signoff.yml``).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFIER = REPO_ROOT / "manifests" / "verify-integrator.py"
INTEGRATOR = REPO_ROOT / "manifests" / "integrator.json"
REPORT = REPO_ROOT / "signoff" / "signoff-report.json"


def run_verifier(sandbox: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(sandbox / "manifests" / "verify-integrator.py")],
        capture_output=True,
        text=True,
    )


ENVELOPE = "layout/comparator.gen-compose.json"

#: Committed files the verifier reads besides the two JSONs: the harness
#: DUT loader, the binding and the netlists it may bind, the placement
#: envelope, and every path the manifest publishes.
SANDBOX_FILES = (
    "sim/harness/dut.py",
    "sim/dut.json",
    "sim/dut/README.md",
    "sim/dut/experiment_comparator_dr0004_cascode.spice",
    "design/comparator.spice",
    ENVELOPE,
    "layout/comparator.gds",
    "signoff/block-manifest.json",
    "signoff/README.md",
    "signoff/regenerate.sh",
    "spec/consumers.md",
    "README.md",
)


def derived_area_um2() -> float:
    bbox = json.loads((REPO_ROOT / ENVELOPE).read_text())["bbox_um"]
    return (bbox["x1"] - bbox["x0"]) * (bbox["y1"] - bbox["y0"])


def make_sandbox(root: Path, mutate, fs=None) -> Path:
    """Copy the verifier, both committed JSON files and SANDBOX_FILES into
    a scratch sandbox, apply ``mutate(manifest_dict, report_dict)``, write
    back, then apply the optional file-level hook ``fs(sandbox)``."""
    sandbox = Path(tempfile.mkdtemp(prefix="integrator-verify-test-", dir=root))
    (sandbox / "manifests").mkdir()
    (sandbox / "signoff").mkdir()
    shutil.copy2(VERIFIER, sandbox / "manifests" / "verify-integrator.py")
    for rel in SANDBOX_FILES:
        (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, sandbox / rel)
    manifest = json.loads(INTEGRATOR.read_text())
    report = json.loads(REPORT.read_text())
    mutate(manifest, report)
    (sandbox / "manifests" / "integrator.json").write_text(json.dumps(manifest))
    (sandbox / "signoff" / "signoff-report.json").write_text(json.dumps(report))
    if fs is not None:
        fs(sandbox)
    return sandbox


def no_change(manifest, report):
    pass


def set_field(dotted: str, value):
    def mutate(manifest, report):
        node = manifest
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node[part]
        node[leaf] = value
    return mutate


def drop_field(dotted: str):
    def mutate(manifest, report):
        node = manifest
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node[part]
        node.pop(leaf, None)
    return mutate


def edit_ports(edit):
    def mutate(manifest, report):
        manifest["ports"] = edit(list(manifest["ports"]))
    return mutate


def swap_first_two(ports):
    ports[0], ports[1] = ports[1], ports[0]
    return ports


def duplicate_port(ports):
    ports[3] = dict(ports[0])  # ibias replaced by a second vinp
    return ports


def missing_port(ports):
    return [p for p in ports if p["name"] != "ibias"]


def extra_port(ports):
    return ports + [{"name": "vbias", "direction": "input", "meaning": "x"}]


def edit_json_file(rel: str, edit):
    def fs(sandbox: Path):
        path = sandbox / rel
        document = json.loads(path.read_text())
        edit(document)
        path.write_text(json.dumps(document))
    return fs


def set_bbox(**coords):
    def edit(envelope):
        envelope["bbox_um"].update(coords)
    return edit_json_file(ENVELOPE, edit)


def activate_cascode(binding):
    binding["active"] = "comparator-dr0004-cascode-exp"


def reorder_netlist_pins(sandbox: Path):
    path = sandbox / "design" / "comparator.spice"
    path.write_text(
        path.read_text().replace(
            ".subckt comparator_dut vinp vinn clk ibias dout doutb vdd vss",
            ".subckt comparator_dut vinn vinp clk ibias dout doutb vdd vss",
        )
    )


def git_sandbox(untrack: str | None):
    """Make the sandbox a git work tree with every file staged, then
    optionally unstage ``untrack`` (tracked-ness is checked via the index)."""
    def fs(sandbox: Path):
        git = ["git", "-C", str(sandbox)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        if untrack:
            subprocess.run(git + ["rm", "-q", "--cached", untrack], check=True)
    return fs


def set_rung(value):
    def mutate(manifest, report):
        manifest["maturity"]["rung"] = value
    return mutate


def set_rung_and_tier(rung, tier):
    def mutate(manifest, report):
        manifest["maturity"]["rung"] = rung
        report["tier"] = tier
    return mutate


def drop_tier_key(manifest, report):
    report.pop("tier", None)


def drop_rung_key(manifest, report):
    manifest["maturity"].pop("rung", None)


def repoint_verdict(manifest, report):
    manifest["maturity"]["verdict_of_record"] = "signoff/elsewhere.json"


#: (name, mutate, expected) -- expected is the verifier's exit status.
CASES = [
    ("issue's bug: advertise T1 while report tier is null", set_rung("T1"), 1),
    ("understate: rung null while report grades T1", set_rung_and_tier(None, "T1"), 1),
    (
        "prose rung value",
        set_rung("T1 (design-evidence tiers, graded)"),
        1,
    ),
    ("supported but differing tiers (T1 vs T2)", set_rung_and_tier("T1", "T2"), 1),
    (
        "malformed report: tier key missing entirely (PR #93)",
        drop_tier_key,
        1,
    ),
    ("malformed manifest: rung key missing", drop_rung_key, 1),
    ("verdict pointer repointed elsewhere", repoint_verdict, 1),
    ("matching null passes", set_rung(None), 0),
    ("matching T1 passes", set_rung_and_tier("T1", "T1"), 0),
    ("matching T4 passes", set_rung_and_tier("T4", "T4"), 0),
]

AREA = derived_area_um2()
AREA_MM2 = AREA / 1e6

#: Structural cases (issue #161): (name, mutate, fs, expected exit,
#: substrings the FAIL output must contain -- field and authoritative source).
STRUCT_CASES = [
    # -- pass cases
    ("committed manifest in a scratch sandbox passes", no_change, None, 0, ()),
    ("um2 exactly +0.5 (rounding boundary) passes", set_field("area.value_um2", AREA + 0.5), None, 0, ()),
    ("um2 exactly -0.5 (rounding boundary) passes", set_field("area.value_um2", AREA - 0.5), None, 0, ()),
    ("um2 unrounded passes", set_field("area.value_um2", AREA), None, 0, ()),
    ("mm2 exactly +0.00005 (rounding boundary) passes", set_field("area.value_mm2", AREA_MM2 + 0.00005), None, 0, ()),
    ("mm2 exactly -0.00005 (rounding boundary) passes", set_field("area.value_mm2", AREA_MM2 - 0.00005), None, 0, ()),
    ("mm2 rounded to 4 decimals passes", set_field("area.value_mm2", round(AREA_MM2, 4)), None, 0, ()),
    ("git sandbox, every path tracked, passes", no_change, git_sandbox(None), 0, ()),
    # -- paths
    ("netlist.path does not exist", set_field("netlist.path", "design/nope.spice"), None, 1,
     ("netlist.path", "does not exist", "sim/dut.json")),
    ("layout.gds does not exist", set_field("layout.gds", "layout/nope.gds"), None, 1,
     ("layout.gds", "does not exist", "gds_path")),
    ("absolute path", set_field("spec.consumers", str(REPO_ROOT / "spec" / "consumers.md")), None, 1,
     ("spec.consumers", "not absolute")),
    ("'..' path segment", set_field("netlist.interface_contract", "sim/../sim/dut/README.md"), None, 1,
     ("netlist.interface_contract", "normalized")),
    ("path field missing", drop_field("layout.placement_evidence"), None, 1,
     ("layout.placement_evidence is missing",)),
    ("prose-prefixed path wrong", set_field("area.source", "layout/nope.json (evidence)"), None, 1,
     ("area.source (leading path)", "does not exist")),
    ("anchored path to missing file", set_field("spec.target_table", "NOPE.md#x"), None, 1,
     ("spec.target_table", "does not exist")),
    ("git sandbox, published GDS untracked", no_change, git_sandbox("layout/comparator.gds"), 1,
     ("layout.gds", "not tracked by git")),
    # -- top subcircuit
    ("wrong top subckt (declared partition)", set_field("netlist.top_subckt", "comparator_dut_analog"), None, 1,
     ("netlist.top_subckt", "REQUIRED_SUBCKTS_BY_PROVENANCE")),
    ("top subckt not declared anywhere", set_field("netlist.top_subckt", "comparator_top"), None, 1,
     ("netlist.top_subckt", "not declared in netlist.path")),
    # -- ordered ports
    ("ports reordered", edit_ports(swap_first_two), None, 1,
     ("ports[].name order", "reordered", "REQUIRED_SUBCKTS", "design/comparator.spice")),
    ("port duplicated", edit_ports(duplicate_port), None, 1,
     ("ports[].name lists 'vinp' more than once", "missing ibias")),
    ("port missing", edit_ports(missing_port), None, 1,
     ("ports[].name order", "missing ibias", "authoritative source")),
    ("extra port", edit_ports(extra_port), None, 1,
     ("ports[].name order", "unexpected vbias")),
    ("port name not a string", edit_ports(lambda p: p[:-1] + [{"direction": "power"}]), None, 1,
     ("ports[7].name is null",)),
    # -- DUT binding disagreement
    ("netlist.path names a non-active binding's netlist",
     set_field("netlist.path", "sim/dut/experiment_comparator_dr0004_cascode.spice"), None, 1,
     ("netlist.path", "active DUT binding", "comparator-dr0001", "authoritative source: sim/dut.json")),
    ("active binding switched away from the manifest's netlist", no_change,
     edit_json_file("sim/dut.json", activate_cascode), 1,
     ("netlist.path", "comparator-dr0004-cascode-exp", "authoritative source: sim/dut.json")),
    ("netlist.provenance disagrees with binding", set_field("netlist.provenance", "extracted"), None, 1,
     ("netlist.provenance", "'schematic'", "authoritative source: sim/dut.json")),
    ("netlist.binding repointed", set_field("netlist.binding", "sim/dut/README.md"), None, 1,
     ("netlist.binding", "DUT_CONFIG")),
    ("committed netlist pin order drifts", no_change, reorder_netlist_pins, 1,
     ("does not load", "pin order", "`.subckt comparator_dut` pin list in design/comparator.spice")),
    # -- top cell
    ("top_cell disagrees with envelope", set_field("top_cell", "COMPARATOR_V2"), None, 1,
     ("top_cell", "cell_name", "layout/comparator.gen-compose.json")),
    ("layout.gds disagrees with envelope gds_path", set_field("layout.gds", "signoff/README.md"), None, 1,
     ("layout.gds", "gds_path")),
    # -- area values
    ("um2 NaN", set_field("area.value_um2", float("nan")), None, 1, ("area.value_um2 is nan", "finite positive")),
    ("um2 +inf", set_field("area.value_um2", float("inf")), None, 1, ("area.value_um2 is inf",)),
    ("mm2 zero", set_field("area.value_mm2", 0.0), None, 1, ("area.value_mm2 is 0.0", "finite positive")),
    ("um2 negative", set_field("area.value_um2", -AREA), None, 1, ("area.value_um2", "finite positive")),
    ("um2 string", set_field("area.value_um2", "20596"), None, 1, ("area.value_um2", "finite positive")),
    ("um2 boolean", set_field("area.value_um2", True), None, 1, ("area.value_um2", "finite positive")),
    ("um2 null", set_field("area.value_um2", None), None, 1, ("area.value_um2 is null",)),
    ("um2 just outside tolerance (+0.51)", set_field("area.value_um2", AREA + 0.51), None, 1,
     ("area.value_um2", "rounding tolerance 0.5", "bbox_um")),
    ("um2 well outside tolerance", set_field("area.value_um2", 20000.0), None, 1,
     ("area.value_um2", "authoritative source: layout/comparator.gen-compose.json bbox_um")),
    ("mm2 just outside tolerance (+0.00006)", set_field("area.value_mm2", AREA_MM2 + 0.00006), None, 1,
     ("area.value_mm2", "rounding tolerance 5e-05", "bbox_um")),
    ("mm2 mis-scaled (um2 value in mm2)", set_field("area.value_mm2", 20596.0), None, 1,
     ("area.value_mm2",)),
    ("area object missing", drop_field("area"), None, 1, ("area is missing",)),
    # -- envelope bbox
    ("envelope bbox non-finite", no_change, set_bbox(x1=float("inf")), 1,
     ("bbox_um has non-finite", "x1=inf")),
    ("envelope bbox degenerate (zero width)", no_change, set_bbox(x1=-0.25), 1,
     ("bbox_um is degenerate", "positive")),
    ("envelope bbox grew, manifest area stale", no_change, set_bbox(x1=335.43), 1,
     ("area.value_um2", "area.value_mm2", "bbox_um")),
]


def main() -> None:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="integrator-verify-suite-") as tmp:
        root = Path(tmp)
        for name, mutate, expected in CASES:
            sandbox = make_sandbox(root, mutate)
            result = run_verifier(sandbox)
            ok = result.returncode == expected
            print(
                f"{'ok  ' if ok else 'FAIL'} {name}: "
                f"exit {result.returncode} (expected {expected})"
            )
            if not ok:
                detail = (result.stderr or result.stdout).strip().splitlines()
                failures.append(
                    f"{name}: exit {result.returncode}, expected {expected}"
                    + (f" -- {detail[0][:120]}" if detail else "")
                )
            shutil.rmtree(sandbox)

        have_git = shutil.which("git") is not None
        for name, mutate, fs, expected, needles in STRUCT_CASES:
            if fs is not None and getattr(fs, "__qualname__", "").startswith("git_sandbox") and not have_git:
                print(f"skip {name}: git not available")
                continue
            sandbox = make_sandbox(root, mutate, fs)
            result = run_verifier(sandbox)
            output = result.stderr + result.stdout
            missing = [n for n in needles if n not in output]
            ok = result.returncode == expected and not missing
            print(
                f"{'ok  ' if ok else 'FAIL'} {name}: "
                f"exit {result.returncode} (expected {expected})"
                + (f"; output lacks {missing}" if missing else "")
            )
            if not ok:
                detail = output.strip().splitlines()
                failures.append(
                    f"{name}: exit {result.returncode}, expected {expected}"
                    + (f"; output lacks {missing}" if missing else "")
                    + (f" -- {detail[0][:200]}" if detail else "")
                )
            shutil.rmtree(sandbox)

    # The committed pair itself must pass.
    committed = subprocess.run(
        [sys.executable, str(VERIFIER)], capture_output=True, text=True
    )
    ok = committed.returncode == 0
    print(
        f"{'ok  ' if ok else 'FAIL'} committed integrator.json/report pair: "
        f"exit {committed.returncode} (expected 0)"
    )
    if not ok:
        failures.append(
            "committed pair fails the verifier: "
            + (committed.stderr or committed.stdout).strip()[:200]
        )

    if failures:
        print(f"\n{len(failures)} case(s) failed:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)
    print(f"\nall {len(CASES) + len(STRUCT_CASES) + 1} cases as expected")


if __name__ == "__main__":
    main()
