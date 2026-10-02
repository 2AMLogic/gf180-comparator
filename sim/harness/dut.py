"""The device-under-test binding.

**This module is the one deliberate structural DIVERGENCE from
``gf180-sar-adc``'s harness, and it exists because of this repo's own
situation.** Over there, each testbench fragment carries a verbatim copy of
the comparator netlist between ``COMPARATOR-NETLIST-BEGIN``/``-END`` markers,
kept in step with ``design/`` by a bespoke ``sim/tools/
sync_comparator_netlist.py``. That works when the topology is settled. Here
it is not: `spec/porting-plan.md` next-step 1 (the topology decision record)
is explicitly out of scope for the harness, so the harness has to be able to
run *before* a design exists and then accept the real design without editing
four testbenches.

So the DUT is bound ONCE, in ``sim/dut.json``, and the harness includes it
ahead of the testbench fragment. Swapping the placeholder for the ratified
design is a one-line edit of that file, not a four-way netlist copy -- and,
critically, every record the harness writes stamps ``dut_provenance``, so a
number measured against the placeholder can never be quoted as if it were
measured against the design.

The interface contract every DUT netlist must satisfy is documented in
``sim/dut/README.md`` and asserted (by name, not by simulation) here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
DUT_CONFIG = SIM_DIR / "dut.json"

#: ``provenance`` values a DUT binding may declare, and what each means for
#: the records produced against it.
PROVENANCE_KINDS = {
    "placeholder": (
        "a harness-exercising stub, NOT a design candidate; records made "
        "against it substantiate that the plumbing runs, never a spec row"
    ),
    "schematic": "the ratified schematic netlist from design/",
    "extracted": "a post-layout extracted netlist from layout/",
}

#: Subcircuits every DUT netlist must define, and the pin order each takes.
#: Checked textually at load time -- a missing or reordered pin list is a
#: silent wrong-node connection otherwise, which in a comparator testbench
#: shows up as a plausible number rather than as an error.
REQUIRED_SUBCKTS: dict[str, tuple[str, ...]] = {
    # Full comparator: clocked, digital outputs held between decisions.
    "comparator_dut": (
        "vinp", "vinn", "clk", "ibias", "dout", "doutb", "vdd", "vss",
    ),
    # The DC-resolvable front end, exposed separately because two of this
    # repo's four experiments (offset-MC, preamp-noise) are small-signal
    # analyses about a DC operating point and a reset-and-regenerate stage
    # does not have one. See sim/dut/README.md "Why there are two subckts".
    "comparator_dut_analog": (
        "vinp", "vinn", "ibias", "aop", "aon", "vdd", "vss",
    ),
    # The decision stage on its own. sim/comparator-preamp-noise/ instantiates
    # it with clk held low so that the front end's noise bandwidth is set by
    # the load it actually drives, rather than by an invented lumped cap.
    "comparator_dut_latch": (
        "inp", "inn", "clk", "dout", "doutb", "vdd", "vss",
    ),
}


class DutError(RuntimeError):
    """Raised when sim/dut.json or the netlist it names is unusable."""


#: Which subcircuits a binding must define, by provenance. A `schematic` or
#: `placeholder` netlist carries the full two-level hierarchy from ``design/``
#: and must define all three. An ``extracted`` netlist is FLAT by construction
#: (``klt extract``'s layout-side output always is -- see ``layout/
#: run_lvs.py``), so the analog/latch partition is structurally absent and
#: only the whole-comparator ``comparator_dut`` can be required; the benches
#: that instantiate the partition (offset-mc, preamp-noise) are refused by
#: the CLI's DUT-compatibility check instead, with a message naming the
#: schematic binding to use.
REQUIRED_SUBCKTS_BY_PROVENANCE: dict[str, dict[str, tuple[str, ...]]] = {
    "placeholder": REQUIRED_SUBCKTS,
    "schematic": REQUIRED_SUBCKTS,
    "extracted": {
        "comparator_dut": REQUIRED_SUBCKTS["comparator_dut"],
    },
}


@dataclass(frozen=True)
class Dut:
    """The bound device under test."""

    netlist: Path
    dut_id: str
    provenance: str
    description: str
    params: dict[str, float] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    available_ids: tuple[str, ...] = ()

    @property
    def netlist_sha256(self) -> str:
        return hashlib.sha256(self.netlist.read_bytes()).hexdigest()

    @property
    def is_placeholder(self) -> bool:
        return self.provenance == "placeholder"

    def provides(self, name: str) -> bool:
        """Whether the bound netlist defines subcircuit ``name``.

        Load-time checking is provenance-conditional (see
        REQUIRED_SUBCKTS_BY_PROVENANCE), so this is the runtime-facing half
        of that contract: the CLI consults it before running a bench whose
        fragment instantiates ``name``.
        """
        return name in _declared_subckts(self.netlist.read_text())

    def param_lines(self) -> list[str]:
        """``.param`` lines every testbench fragment may rely on."""
        return [f".param {key}={value!r}" for key, value in sorted(self.params.items())]

    def provenance_record(self) -> dict:
        return {
            "dut_id": self.dut_id,
            "dut_provenance": self.provenance,
            "dut_netlist": str(self.netlist.relative_to(REPO_ROOT)),
            "dut_netlist_sha256": self.netlist_sha256,
            "dut_params": dict(sorted(self.params.items())),
        }



def _declared_subckts(text: str) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.lower().startswith(".subckt"):
            continue
        tokens = line.split()
        if len(tokens) < 2:
            continue
        # Drop trailing `name=value` default-parameter tokens; they are not pins.
        pins = tuple(t.lower() for t in tokens[2:] if "=" not in t)
        found[tokens[1].lower()] = pins
    return found


def load(path: str | Path | None = None, select: str | None = None) -> Dut:
    """Load a DUT binding and validate the netlist it binds.

    ``sim/dut.json`` may hold more than one binding: a ``{"active": <id>,
    "duts": {<id>: <binding>}}`` document selects ``active`` by default, or
    the id ``select`` names (this is how the post-layout
    ``comparator-dr0001-layout`` binding is reached via ``--dut <id>``). A
    legacy single-binding document (no ``duts`` key) loads exactly as it
    always did, and ``select`` must be None for it.
    """
    config_path = Path(path) if path is not None else DUT_CONFIG
    if not config_path.is_file():
        raise DutError(f"no DUT binding at {config_path}; see sim/dut/README.md")
    try:
        document = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        raise DutError(f"{config_path} is not valid JSON: {exc}") from exc

    available: tuple[str, ...] = ()
    if "duts" in document:
        entries = document["duts"]
        if not isinstance(entries, dict) or not entries:
            raise DutError(
                f"{config_path}: 'duts' must be a non-empty object of bindings"
            )
        available = tuple(entries)
        chosen_id = select or document.get("active")
        if chosen_id not in entries:
            raise DutError(
                f"{config_path}: no DUT entry {chosen_id!r}"
                + (f" (--dut {select})" if select else " ('active')")
                + f"; available: {', '.join(available)}"
            )
        if select and select != document.get("active"):
            pass  # an explicit --dut selection legitimately overrides 'active'
        config = entries[chosen_id]
        if not isinstance(config, dict):
            raise DutError(f"{config_path}: DUT entry {chosen_id!r} must be an object")
    else:
        if select:
            raise DutError(
                f"{config_path}: --dut {select!r} names no entry (this binding "
                "file holds a single entry with no 'duts' map)"
            )
        config = document

    for key in ("netlist", "id", "provenance"):
        if key not in config:
            raise DutError(f"{config_path}: missing required key {key!r}")

    provenance = str(config["provenance"])
    if provenance not in PROVENANCE_KINDS:
        raise DutError(
            f"{config_path}: provenance {provenance!r} is not one of "
            f"{', '.join(sorted(PROVENANCE_KINDS))}"
        )

    netlist = (SIM_DIR / config["netlist"]).resolve()
    if not netlist.is_file():
        raise DutError(
            f"{config_path}: netlist {netlist} does not exist"
            + (
                " -- a post-layout binding's netlist is regenerated by "
                "`python3 layout/run_extract_sim.py` (issue #23)"
                if provenance == "extracted"
                else ""
            )
        )

    text = netlist.read_text()
    declared = _declared_subckts(text)
    required = REQUIRED_SUBCKTS_BY_PROVENANCE[provenance]
    for name, pins in required.items():
        if name not in declared:
            raise DutError(
                f"{netlist}: DUT netlist must define `.subckt {name} "
                f"{' '.join(pins)}` (sim/dut/README.md 'Interface contract'); "
                f"found: {', '.join(sorted(declared)) or '<none>'}"
            )
        if declared[name] != pins:
            raise DutError(
                f"{netlist}: `.subckt {name}` pin order is "
                f"{' '.join(declared[name])}, contract requires "
                f"{' '.join(pins)} (sim/dut/README.md 'Interface contract'). "
                "A reordered pin list silently miswires every testbench."
            )

    # The DUT netlist is included by the harness alongside the corner libs, so
    # it must not carry any of the directives the harness owns.
    for lineno, raw in enumerate(text.splitlines(), start=1):
        directive = raw.strip().lower().split()[0] if raw.strip().startswith(".") else ""
        if directive in (".control", ".endc", ".end", ".lib", ".temp", ".include"):
            raise DutError(
                f"{netlist}:{lineno}: DUT netlist must not contain {directive} -- "
                "the harness supplies models, corner libs, temperature and the "
                "control block"
            )

    params = {str(k): float(v) for k, v in (config.get("params") or {}).items()}
    return Dut(
        netlist=netlist,
        dut_id=str(config["id"]),
        provenance=provenance,
        description=str(config.get("description", "")),
        params=params,
        notes=tuple(config.get("notes") or ()),
        available_ids=available,
    )
