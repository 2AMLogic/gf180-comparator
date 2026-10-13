#!/usr/bin/env python3
"""Derive the preamp output observation nodes of the flat extracted DUT from
its connectivity (issue #202).

WHY THIS EXISTS
---------------
The flat extraction (`layout/run_extract_sim.py`) defines only the whole-
comparator subckt, so `sim/dut.json` refuses the analog-partition noise bench
against it. The preamp output nets (`aop`/`aon` in the schematic) still exist
INSIDE `COMPARATOR` as internal nets (`klt extract --pins` keeps every non-
interface net internal, issue #514), each split by `--parasitics` into one
"hub" node plus one series-R "leg" node per device terminal
(`<hub>__t<N>`). ngspice can probe a subckt-internal node hierarchically
(`x<inst>.x<inst>.<hub>`) without touching a single device or R/C.

This module identifies WHICH hubs are the two preamp outputs from topology
alone -- never from net numbers, and (for a defence in depth) never from
the label text either: the label-derived names are only CROSS-CHECKED
against the structural answer afterwards, and `crosscheck_report()` also
checks the structural answer against the committed `klt extract` report's
per-net terminal lists.

THE STRUCTURAL RULE (the DR-0001 preamp, design/comparator.spice
comparator_dut_analog)
------------------------------------------------------------------------
* two `ppolyf_u_1k` load resistors, each with exactly one terminal on the
  `vdd` hub; their other terminal's hub is a preamp output;
* per output, exactly one NMOS drain: an input-pair device whose gate hub is
  `vinp` or `vinn` (distinct), sharing one source ("tail") hub, bulk on the
  `vss` hub; the tail is driven by exactly one NMOS gated by the `ibias` hub
  with source on `vss`;
* per output, exactly ONE other device terminal: a gate (the decision-stage
  input). An output hub touching anything beyond {load resistor, input
  drain, one gate} is ambiguous and fails.
* polarity: the output whose input device is gated by `vinn` is `aop` (the
  non-inverted-sense output, XMIN in the schematic), the one gated by `vinp`
  is `aon` (XMIP).

Every violation raises `MappingError` with the specific reason; callers exit
non-zero, they never fall back to a guess.
"""

from __future__ import annotations

import re
from collections import defaultdict

TOP = "COMPARATOR"
INTERFACE_PINS = ("vinp", "vinn", "clk", "ibias", "dout", "doutb", "vdd", "vss")

_LEG_RE = re.compile(r"^(?P<hub>.+)__t(?P<n>\d+)$", re.IGNORECASE)
MOS_MODELS = {"nfet_03v3": "n", "pfet_03v3": "p"}
RES_MODEL = "ppolyf_u_1k"


class MappingError(Exception):
    """The preamp observation mapping could not be derived unambiguously."""


def _logical_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("+") and out:
            out[-1] += " " + raw[1:].strip()
        elif raw.strip() and not raw.lstrip().startswith("*"):
            out.append(raw.strip())
    return out


def parse_top(text: str, top: str = TOP) -> dict:
    """Parse the `.SUBCKT <top>` body: pins, device cards, series-R legs."""
    lines = _logical_lines(text)
    pins = None
    body: list[str] = []
    inside = False
    for line in lines:
        low = line.lower()
        if low.startswith(".subckt"):
            toks = line.split()
            if len(toks) >= 2 and toks[1].lower() == top.lower():
                inside, pins = True, [p.lower() for p in toks[2:] if "=" not in p]
                continue
        if inside and low.startswith(".ends"):
            break
        if inside:
            body.append(line)
    if pins is None:
        raise MappingError(f"no `.SUBCKT {top}` found in the netlist")
    if sorted(pins) != sorted(INTERFACE_PINS):
        raise MappingError(f"{top} pins {pins} are not the interface pin set")

    legs: dict[str, str] = {}      # leg node -> hub node (lowercase)
    devices: list[dict] = []
    for line in body:
        toks = line.split()
        name, kind = toks[0], toks[0][0].upper()
        if kind == "R" and len(toks) == 4:
            m = _LEG_RE.match(toks[1])
            if m and toks[2].lower() == m.group("hub").lower():
                legs[toks[1].lower()] = toks[2].lower()
            continue
        if kind == "M" and len(toks) >= 6 and toks[5].lower() in MOS_MODELS:
            devices.append({"name": name, "kind": "mos", "model": toks[5].lower(),
                            "nets": dict(zip("dgsb", (t.lower() for t in toks[1:5])))})
        elif kind == "X" and len(toks) >= 5 and toks[4].lower() == RES_MODEL:
            devices.append({"name": name, "kind": "res", "model": RES_MODEL,
                            "nets": dict(zip(("a", "b", "sub"), (t.lower() for t in toks[1:4])))})
    return {"pins": pins, "legs": legs, "devices": devices}


def _hub(parsed: dict, node: str) -> str:
    return parsed["legs"].get(node, node)


def derive(text: str, top: str = TOP) -> dict:
    """Return the structural mapping (see module docstring) or raise."""
    p = parse_top(text, top)
    hub = lambda n: _hub(p, n)  # noqa: E731
    devs = p["devices"]
    if not devs:
        raise MappingError("no recognised device cards in the extracted top cell")
    if not p["legs"]:
        raise MappingError("no `<net>__t<N>` series-R legs found: the extraction was "
                           "not made with --parasitics, so there is no hub node to probe")

    # Every terminal of every device, by hub.
    terms: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for d in devs:
        for t, n in d["nets"].items():
            terms[hub(n)].append((d["name"], t))

    res = [d for d in devs if d["kind"] == "res"]
    if len(res) != 2:
        raise MappingError(f"expected exactly 2 {RES_MODEL} load resistors, found {len(res)}")
    outputs: dict[str, dict] = {}
    for r in res:
        ends = [r["nets"]["a"], r["nets"]["b"]]
        on_vdd = [n for n in ends if hub(n) == "vdd"]
        off = [n for n in ends if hub(n) != "vdd"]
        if len(on_vdd) != 1 or len(off) != 1:
            raise MappingError(f"resistor {r['name']} does not have exactly one terminal on vdd")
        if hub(r["nets"]["sub"]) != "vss":
            raise MappingError(f"resistor {r['name']} substrate is on {hub(r['nets']['sub'])!r}, "
                               "not the vss hub")
        h = hub(off[0])
        if h in p["pins"]:
            raise MappingError(f"resistor {r['name']} output hub {h!r} is an interface pin")
        if h in outputs:
            raise MappingError(f"both load resistors drive hub {h!r}")
        outputs[h] = {"hub": h, "load_resistor": r["name"], "load_leg": off[0]}
    if len(outputs) != 2:
        raise MappingError("could not find two distinct preamp output hubs")

    mos = [d for d in devs if d["kind"] == "mos"]
    pair_tail = set()
    by_gate: dict[str, str] = {}
    for h, o in outputs.items():
        cands = [d for d in mos if d["model"] == "nfet_03v3" and hub(d["nets"]["d"]) == h
                 and hub(d["nets"]["g"]) in ("vinp", "vinn")]
        if len(cands) != 1:
            raise MappingError(f"output hub {h!r}: expected exactly one input-pair NMOS "
                               f"drain (gate on vinp/vinn), found {[c['name'] for c in cands]}")
        c = cands[0]
        if hub(c["nets"]["b"]) != "vss":
            raise MappingError(f"input device {c['name']} bulk is on {hub(c['nets']['b'])!r}, "
                               "not the vss hub")
        g = hub(c["nets"]["g"])
        if g in by_gate:
            raise MappingError(f"both input devices are gated by {g!r}")
        by_gate[g] = h
        pair_tail.add(hub(c["nets"]["s"]))
        o.update(input_device=c["name"], drain_leg=c["nets"]["d"], gate=g)
    if len(pair_tail) != 1:
        raise MappingError(f"input pair sources do not share one tail hub: {sorted(pair_tail)}")
    tail = pair_tail.pop()
    if tail in p["pins"]:
        raise MappingError(f"tail hub {tail!r} is an interface pin")
    tails = [d for d in mos if d["model"] == "nfet_03v3" and hub(d["nets"]["d"]) == tail
             and hub(d["nets"]["g"]) == "ibias" and hub(d["nets"]["s"]) == "vss"]
    if len(tails) != 1:
        raise MappingError(f"expected exactly one ibias-gated tail NMOS on {tail!r}, "
                           f"found {[d['name'] for d in tails]}")

    for h, o in outputs.items():
        others = [(n, t) for n, t in terms[h]
                  if n not in (o["load_resistor"], o["input_device"])]
        if len(others) != 1 or others[0][1] != "g":
            raise MappingError(f"output hub {h!r} has unexpected extra terminals "
                               f"{others} beyond one decision-stage gate")
        o["latch_gate"] = others[0][0]
        o["terminal_devices"] = sorted({n for n, _ in terms[h]})

    mapping = {
        "aop": outputs[by_gate["vinn"]],
        "aon": outputs[by_gate["vinp"]],
        "tail_hub": tail,
        "tail_device": tails[0]["name"],
    }
    return mapping


def crosscheck_labels(mapping: dict) -> None:
    """The label-derived hub names must agree with the structural answer."""
    for want in ("aop", "aon"):
        if mapping[want]["hub"] != want:
            raise MappingError(
                f"structural {want} is hub {mapping[want]['hub']!r}: the layout labels "
                "disagree with the topology (swapped or renamed output labels)")


def crosscheck_report(mapping: dict, report: dict) -> None:
    """The structural answer must match `klt extract`'s own per-net terminal
    lists (an independent view of the same connectivity)."""
    nets = {n["net"]: n for n in (report.get("parasitics") or {}).get("nets", [])}
    for key in ("aop", "aon"):
        m = mapping[key]
        n = nets.get(m["hub"])
        if n is None:
            raise MappingError(f"extract report has no parasitic net {m['hub']!r}")
        rep_devs = sorted({t["device"].lstrip("$") for t in n["terminals"]})
        got = sorted({d[1:].lstrip("$") for d in m["terminal_devices"]})
        if rep_devs != got:
            raise MappingError(f"{m['hub']}: report terminals {rep_devs} != netlist {got}")


def observation_nodes(mapping: dict, prefix: str) -> dict:
    """Hierarchical ngspice node names for `prefix` (instance path to the
    COMPARATOR instance, e.g. `xdut.xlayout_dut`). Hub = the lumped net node;
    drain_leg = the same net on the input-device side of its series R."""
    return {k: {"hub": f"{prefix}.{mapping[k]['hub']}",
                "drain_leg": f"{prefix}.{mapping[k]['drain_leg']}"}
            for k in ("aop", "aon")}
