#!/usr/bin/env python3
"""Emit `layout/README.md`'s routing-status table mechanically from
`layout/comparator.gen-compose.json`, so the prose can never drift from the
committed evidence file it cites.

The table was hand-transcribed once and was wrong (PR #29 review): six nets
were mislabelled, including `aop` -- a core preamp->latch analog net with
ZERO routed legs -- being listed as merely "partially routed". Nothing here
is a judgement call: every number and every net name below is read straight
out of the `klt gen-compose` response's own `nets[].status`,
`nets[].pins[]`, and `nets[].legs[].routed` fields.

Usage
-----
    python3 layout/routing_table.py            # print the markdown block
    python3 layout/routing_table.py --write    # rewrite the block in README.md
    python3 layout/routing_table.py --check    # exit 1 if README.md is stale

`--check` is the guard: run it after any re-run of `gen_comparator.py` (or in
review) to prove the README still matches the JSON.

Leg accounting matches the response's own model: a net with N pins needs
N-1 minimum-spanning-tree legs, and `legs[]` records every pin pair the
router attempted (so `len(legs)` is >= N-1 for a net whose first choices were
rejected). The "legs drawn" numerator counts `legs[].routed == true`; the
denominator is N-1.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPOSE_JSON = os.path.join(HERE, "comparator.gen-compose.json")
README = os.path.join(HERE, "README.md")

BEGIN = "<!-- BEGIN generated: python3 layout/routing_table.py --write -->"
END = "<!-- END generated -->"

#: status -> (row label, meaning). The `status` values are gen-compose's own.
STATUS_ROWS = [
    ("routed", "**Fully routed**",
     "Every pin on the net is joined by real, drawn Metal1 -- including the "
     "12-pin `vdd` supply bundle."),
    ("partial", "**Partially routed**",
     "Some legs carry real drawn metal, but at least one pin is still "
     "isolated; `nets[].legs[].reason` names the specific rejection "
     "(overwhelmingly \"same-facing port pair\" -- see \"Known klt "
     "gen-compose limitations hit here\" below)."),
    ("unrouted", "**Not routed at all**",
     "Every attempted leg was rejected (`routed: false`, "
     "`route_length_um: null` on the net) -- these nets have NO drawn metal "
     "in `comparator.gds` today and are the bulk of the follow-up "
     "hand-routing effort."),
]


def load_nets(path: str = COMPOSE_JSON) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["nets"]


def render(nets: list[dict]) -> str:
    total_nets = len(nets)
    by_status: dict[str, list[dict]] = {}
    for net in nets:
        by_status.setdefault(net["status"], []).append(net)

    unknown = set(by_status) - {s for s, _, _ in STATUS_ROWS}
    if unknown:
        raise SystemExit(f"unhandled gen-compose net status(es): {sorted(unknown)}")

    def legs(net: dict) -> tuple[int, int]:
        needed = len(net["pins"]) - 1
        drawn = sum(1 for leg in net.get("legs", []) if leg.get("routed"))
        return drawn, needed

    lines = [
        BEGIN,
        "",
        "| Outcome | Nets | MST legs drawn | Meaning |",
        "|---|---|---|---|",
    ]
    tot_drawn = tot_needed = 0
    for status, label, meaning in STATUS_ROWS:
        group = by_status.get(status, [])
        drawn = sum(legs(n)[0] for n in group)
        needed = sum(legs(n)[1] for n in group)
        tot_drawn += drawn
        tot_needed += needed
        names = ", ".join(f"`{n['net']}`" for n in group) or "_(none)_"
        lines.append(
            f"| {label} ({len(group)}/{total_nets}) | {names} | "
            f"{drawn}/{needed} | {meaning} |"
        )

    pct = round(100 * tot_drawn / tot_needed) if tot_needed else 0
    lines += [
        "",
        f"Overall: **{tot_drawn} of the {tot_needed} minimum-spanning-tree legs "
        f"this design's connectivity needs ({pct}%) carry real drawn metal.**",
        "",
        END,
    ]
    return "\n".join(lines)


def splice(readme_text: str, block: str) -> str:
    start = readme_text.find(BEGIN)
    end = readme_text.find(END)
    if start < 0 or end < 0:
        raise SystemExit(f"{README}: generated-block markers not found")
    return readme_text[:start] + block + readme_text[end + len(END):]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    block = render(load_nets())

    if mode == "":
        print(block)
        return

    with open(README, encoding="utf-8") as fh:
        current = fh.read()
    updated = splice(current, block)

    if mode == "--check":
        if updated != current:
            sys.stderr.write(
                "layout/README.md's routing table is STALE relative to "
                "layout/comparator.gen-compose.json.\n"
                "Fix: python3 layout/routing_table.py --write\n")
            raise SystemExit(1)
        print("layout/README.md routing table matches comparator.gen-compose.json")
    elif mode == "--write":
        with open(README, "w", encoding="utf-8") as fh:
            fh.write(updated)
        print(f"wrote routing table into {README}")
    else:
        raise SystemExit(f"unknown option {mode!r} (use --write or --check)")


if __name__ == "__main__":
    main()
