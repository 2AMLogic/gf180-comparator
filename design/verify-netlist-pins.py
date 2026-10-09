#!/usr/bin/env python3
"""Source-pin check for design/comparator.spice (issue #120). Stdlib only.

    python3 design/verify-netlist-pins.py --check   # CI: fail if pins are stale
    python3 design/verify-netlist-pins.py --write   # called by ./design/netlist.sh

``./design/netlist.sh`` (write mode) regenerates ``design/comparator.spice``
with xschem and then calls ``--write``, which records in
``design/comparator.sources.json`` the sha256 of every schematic input that
feeds the netlist and the sha256 of the netlist it just wrote.

``--check`` needs no xschem and no PDK. It re-derives the input set by walking
the schematic hierarchy from ``design/comparator.sch`` (every ``C {name.sym}``
instance whose symbol lives in ``design/`` is an input, together with its
same-named ``.sch``, recursively), re-hashes those files and the netlist, and
fails if any of them differs from the pin file, if the input set itself
changed (a sub-schematic added or removed), or if the pin file is missing.

WHAT THIS PROVES, AND WHAT IT DOES NOT
--------------------------------------
A passing check proves only that the committed schematic inputs and the
committed netlist are byte-identical to the snapshot recorded the last time
the pin file was written -- i.e. that nobody edited a ``.sch``/``.sym`` or the
``.spice`` without re-running the sch->spice step (``./design/netlist.sh``)
afterwards. It does NOT prove that ``design/comparator.spice`` is the correct
xschem output for those schematics: the pin file is plain JSON that anyone can
rewrite, and this check never runs xschem. Only ``./design/netlist.sh --check``
(xschem + PDK) proves derivation. Also not pinned: ``design/xschemrc``,
``design/netlist.sh``'s own post-processing, the PDK's device symbols, and the
xschem version. Do not cite a pass for more than the narrow claim above.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA = "gf180-comparator/netlist-sources/1"
TOP = "comparator"
PIN_FILE = f"design/{TOP}.sources.json"
NETLIST = f"design/{TOP}.spice"
TOP_SCH = f"design/{TOP}.sch"

LIMIT = ("Proves only that the listed sources and the netlist are unchanged "
         "since ./design/netlist.sh last wrote this file; it does NOT prove the "
         "netlist is the correct xschem output (that is ./design/netlist.sh "
         "--check, which needs xschem + PDK).")

_INSTANCE = re.compile(r"^C \{([^}]+\.sym)\}")
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_sources(root: Path) -> list[str]:
    """Repo-relative paths of every schematic input under design/.

    Walks the hierarchy from the top sheet. A ``C {x.sym}`` instance counts
    only when ``design/x.sym`` exists (PDK and xschem-library symbols such as
    ``symbols/nfet_03v3.sym`` / ``devices/ipin.sym`` live outside the repo
    and are not pinned); its same-named ``design/x.sch`` is then an input too
    and is descended into.
    """
    design = root / "design"
    top = root / TOP_SCH
    if not top.is_file():
        raise FileNotFoundError(f"top schematic {TOP_SCH} is missing")
    found: set[str] = {TOP_SCH}
    queue = [top]
    while queue:
        sch = queue.pop()
        for line in sch.read_text().splitlines():
            m = _INSTANCE.match(line)
            if not m:
                continue
            sym = design / m.group(1)
            if not sym.is_file() or design not in sym.resolve().parents:
                continue
            found.add(sym.relative_to(root).as_posix())
            child = sym.with_suffix(".sch")
            rel = child.relative_to(root).as_posix()
            if child.is_file() and rel not in found:
                found.add(rel)
                queue.append(child)
    return sorted(found)


def compute_pins(root: Path) -> dict:
    sources = discover_sources(root)
    netlist = root / NETLIST
    if not netlist.is_file():
        raise FileNotFoundError(f"netlist {NETLIST} is missing")
    return {
        "schema": SCHEMA,
        "generator": "design/netlist.sh",
        "verifier": "design/verify-netlist-pins.py --check",
        "limit": LIMIT,
        "top": TOP_SCH,
        "sources": {rel: _sha256(root / rel) for rel in sources},
        "netlist": {NETLIST: _sha256(netlist)},
    }


def render(pins: dict) -> str:
    return json.dumps(pins, indent=2, sort_keys=False) + "\n"


def write_pins(root: Path) -> Path:
    out = root / PIN_FILE
    out.write_text(render(compute_pins(root)))
    return out


def check_pins(root: Path) -> list[str]:
    """Return a list of problems; empty means the pins are fresh."""
    pin_path = root / PIN_FILE
    if not pin_path.is_file():
        return [f"{PIN_FILE} is missing -- run ./design/netlist.sh"]
    try:
        recorded = json.loads(pin_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{PIN_FILE} is not valid JSON: {exc}"]
    if not isinstance(recorded, dict) or recorded.get("schema") != SCHEMA:
        return [f"{PIN_FILE}: schema is not {SCHEMA!r}"]
    try:
        fresh = compute_pins(root)
    except FileNotFoundError as exc:
        return [str(exc)]

    problems: list[str] = []
    for key in ("sources", "netlist"):
        want = recorded.get(key)
        have = fresh[key]
        if not isinstance(want, dict):
            problems.append(f"{PIN_FILE}: '{key}' is missing or not an object")
            continue
        for rel in sorted(set(want) | set(have)):
            if rel not in have:
                problems.append(f"{rel}: pinned but no longer an input of {TOP_SCH}")
            elif rel not in want:
                problems.append(f"{rel}: input of {TOP_SCH} but not pinned")
            elif want[rel] != have[rel]:
                problems.append(f"{rel}: sha256 {have[rel]} != pinned {want[rel]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="fail if any schematic input or the netlist changed "
                           "since the pin file was written (PDK-free)")
    mode.add_argument("--write", action="store_true",
                      help="rewrite the pin file from the current bytes "
                           "(./design/netlist.sh calls this after netlisting)")
    ap.add_argument("--root", type=Path, default=_REPO_ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root = args.root.resolve()

    if args.write:
        out = write_pins(root)
        print(f"wrote {out.relative_to(root).as_posix()}")
        return 0

    problems = check_pins(root)
    if problems:
        print(f"{NETLIST} source pins are STALE -- re-run ./design/netlist.sh "
              f"(do not hand-edit {PIN_FILE}):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    n = len(json.loads((root / PIN_FILE).read_text())["sources"])
    print(f"{NETLIST} and its {n} schematic inputs match {PIN_FILE} "
          "(proves no edit since the last ./design/netlist.sh run; "
          "not that the netlist is correct xschem output)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
