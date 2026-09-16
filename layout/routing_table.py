#!/usr/bin/env python3
"""Emit `layout/README.md`'s routing-status table mechanically from the
committed routing evidence, so the prose can never drift from the files it
cites.

The table was hand-transcribed once and was wrong (PR #29 review): six nets
were mislabelled, including `aop` -- a core preamp->latch analog net with
ZERO routed legs -- being listed as merely "partially routed". Nothing here
is a judgement call: every number and every net name below is read straight
out of two committed JSON documents.

* `layout/comparator.routing.json` -- `layout/route_nets.py`'s own report:
  per net, how many pins it joins, how many risers and horizontal trunks
  were drawn for it, whether it needed a channel link, and how much metal it
  cost.
* `layout/comparator.gen-compose.json` -- the `klt gen-compose` response
  that PLACED the blocks. Since issue #30 this is a declare-only request
  (no `routing` block): gen-compose still validates every `connectivity[]`
  net against the blocks' own reported ports, so this file remains the
  authority on what the intended connectivity IS, while
  `comparator.routing.json` is the authority on what got DRAWN. The two are
  cross-checked against each other below -- a net declared in one and
  missing from the other is a hard error, not a silently smaller table.

Usage
-----
    python3 layout/routing_table.py            # print the markdown block
    python3 layout/routing_table.py --write    # rewrite the block in README.md
    python3 layout/routing_table.py --check    # exit 1 if README.md is stale

`--check` is the guard: run it after any re-run of `gen_comparator.py` (or in
review) to prove the README still matches the JSON.

Pin accounting: `route_nets.py` draws a *channel route* -- one horizontal
Metal3 trunk per net per channel, one vertical riser per pin -- so a net is
either fully joined (every one of its pins reaches its trunk) or the router
raises rather than emitting a partial result. The table therefore reports
`pins joined / pins declared`, which is the same connectivity claim the old
`legs drawn / MST legs` column made of `klt gen-compose`'s spanning-tree
router, stated in the terms the current router actually works in.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPOSE_JSON = os.path.join(HERE, "comparator.gen-compose.json")
ROUTING_JSON = os.path.join(HERE, "comparator.routing.json")
README = os.path.join(HERE, "README.md")

BEGIN = "<!-- BEGIN generated: python3 layout/routing_table.py --write -->"
END = "<!-- END generated -->"


def load() -> tuple[list[dict], dict, dict]:
    with open(ROUTING_JSON, encoding="utf-8") as fh:
        routing = json.load(fh)
    with open(COMPOSE_JSON, encoding="utf-8") as fh:
        compose = json.load(fh)
    return routing["nets"], routing["totals"], compose


def render(nets: list[dict], totals: dict, compose: dict) -> str:
    # Cross-check: the drawn result must cover exactly the declared
    # connectivity, net for net and pin for pin.
    declared = {n["net"]: len(n["pins"]) for n in compose["nets"]}
    drawn = {n["net"]: n for n in nets}
    if set(declared) != set(drawn):
        raise SystemExit(
            "routing evidence disagrees with the gen-compose connectivity: "
            f"declared-only={sorted(set(declared) - set(drawn))} "
            f"drawn-only={sorted(set(drawn) - set(declared))}")

    lines = [
        BEGIN,
        "",
        "| Net | Pins joined | Metal3 trunks | Channel link | Metal drawn (um) |",
        "|---|---|---|---|---|",
    ]
    for net in nets:
        name = net["net"]
        # A tap pin (a drawn well/substrate tie) is a pin of the net that no
        # schematic connectivity[] entry declares -- it has no device
        # terminal behind it -- so the two counts differ by exactly the taps
        # this net collected, and that is reported, not hidden.
        taps = net["pins"] - declared[name]
        joined = f"{net['pins']}/{declared[name]}"
        if taps:
            joined += f" (+{taps} body ties)"
        trunks = ", ".join(t["channel"] for t in net["trunks"])
        link = "yes" if net["link_x_um"] is not None else "-"
        lines.append(
            f"| `{name}` | {joined} | {len(net['trunks'])} ({trunks}) | "
            f"{link} | {net['route_length_um']:.1f} |")

    unjoined = [n["net"] for n in nets if n["pins"] < declared[n["net"]]]
    verdict = (
        "every pin of every net is joined by real drawn metal"
        if not unjoined
        else f"NOT complete -- still unjoined: {', '.join(unjoined)}")
    lines += [
        "",
        f"Overall: **{len(nets)} of {len(declared)} declared nets routed, "
        f"{totals['pins']} pins ({totals['device_pins']} device terminals + "
        f"{totals['tap_pins']} drawn body ties), "
        f"{totals['route_length_um']:.0f} um of metal, "
        f"{totals['channel_links']} channel links -- {verdict}.**",
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
    block = render(*load())

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
                "layout/comparator.routing.json.\n"
                "Fix: python3 layout/routing_table.py --write\n")
            raise SystemExit(1)
        print("layout/README.md routing table matches comparator.routing.json")
    elif mode == "--write":
        with open(README, "w", encoding="utf-8") as fh:
            fh.write(updated)
        print(f"wrote routing table into {README}")
    else:
        raise SystemExit(f"unknown option {mode!r} (use --write or --check)")


if __name__ == "__main__":
    main()
