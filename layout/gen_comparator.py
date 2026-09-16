#!/usr/bin/env python3
"""Generate `layout/comparator.gds` -- the physical layout of DR-0001's
comparator topology (`design/comparator_dut_analog.sch` +
`design/comparator_dut_latch.sch`) -- via `klt gen` (2AMLogic/klayout-tools)
device generators, `klt gen-compose` for placement, and `route_nets.py` for
the routing.

Issues #18 (the layout) and #30 (completing its routing). This is fresh
physical design work, not a port of any other repo's layout -- see
`layout/README.md` for the full methodology writeup and what is/is not
verified.

WHAT THIS SCRIPT DOES
----------------------
1. For every device GROUP below (`BLOCKS`), calls `klt gen mos_array` /
   `klt gen diff_pair` / `klt gen res_array` at the exact W/L/flavor DR-0001
   sizes, writing each block's own GDS + JSON `generator_report` under
   `layout/_gen/` (regenerated every run, not committed -- see "What is
   committed" in `layout/README.md`).
2. Assembles ONE flat `klt gen-compose` request (`layout/_gen/request.json`)
   placing all 16 blocks in a single left-to-right row, in the same device
   order DR-0001's sizing tables list them (preamp, then the StrongARM latch,
   then the isolation inverters, then the NOR SR latch) -- so the drawn
   floorplan reads left-to-right the same way the schematic and the decision
   record do.
3. Declares every schematic net (`NETS` below, transcribed directly from
   `design/comparator_dut_analog.sch` / `design/comparator_dut_latch.sch`'s
   own `N {...} {lab=...}` labels, plus `comparator_dut.sch`'s own `XA`/`XL`
   instance lines for the preamp->latch hand-off) as a `connectivity[]`
   entry. The request carries NO `routing` block: gen-compose still
   validates every declared pin against the blocks' own reported ports (a
   typo'd or stale port name is still a hard request error), but draws no
   metal -- see `build_request()` and `route_nets.py`'s docstring for why
   this design's net graph needs a two-layer channel router rather than
   gen-compose's own one-plane-per-net spanning-tree router.
4. Writes the placed result to `layout/comparator.gds` plus its
   `klt gen-compose` JSON response (`layout/comparator.gen-compose.json`,
   committed as the placement/connectivity-declaration evidence).
5. Runs `layout/route_nets.py` against that placed `comparator.gds`: draws
   the well/substrate body ties the device generators do not report a port
   for, then routes 100% of `NETS` as a Metal2/Metal3 channel route,
   and re-runs `klt drc` against the result. Its own per-net report is
   `layout/comparator.routing.json` (committed evidence; the source
   `layout/routing_table.py` renders this README's routing table from).

WHAT IS NOT ATTEMPTED HERE (stated, not hidden -- see `layout/README.md`)
--------------------------------------------------------------------------
* Guard rings. Every `diff_pair` block is drawn with `add_guard_ring:
  false` -- a closed ring makes the block's own ports unreachable for any
  router, this one included.
* Parasitic-aware routing. Track and channel assignment here is ordinal
  (declaration order), not driven by any extracted R/C or a matching
  constraint; post-layout simulation (#23) is what will judge it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import route_nets

HERE = os.path.dirname(os.path.abspath(__file__))
GENDIR = os.path.join(HERE, "_gen")
PDK = "gf180mcuC"  # 3.3 V flavor, per DR-0001's rail discipline

# ---------------------------------------------------------------------------
# Device groups, transcribed from design/comparator_dut_analog.sch and
# design/comparator_dut_latch.sch. Each block is one `klt gen` call; a
# "diff_pair" block draws TWO matched devices (Q1/Q2, ports "Q1_1_*"/
# "Q2_1_*" at splits=1 -- one sub-instance each, no common-centroid
# interleaving) so a single block can stand in for a schematic's matched
# pair (input pair, cross-coupled pair, precharge pair, isolation-inverter
# half, NOR-latch half) while a singleton device (MB/MT/MTL, no schematic
# twin) is a "mos_array" 1x1. `add_guard_ring: false` on every diff_pair
# call is a stated, deliberate choice -- klayout-tools' own gen-compose
# router cannot route to a port on a block whose ring is closed (see
# layout/README.md's "Known klt gen-compose limitations hit here"), so a
# ring here would make every one of these blocks' internal nets
# unroutable. `gate_contact: true` everywhere finishes each device's gate
# stack (contact + local metal pad) so the gate port reports on the
# `metal` role like S/D, not bare poly -- otherwise a `metal`-role route
# could not land on it at all.
# ---------------------------------------------------------------------------

_NFET = {"flavor": "nfet"}
_PFET = {"flavor": "pfet"}


def _mos(w_um, l_um, **extra):
    p = {"w_um": w_um, "l_um": l_um, "rows": 1, "cols": 1, "dummy": 0,
         "gate_contact": True}
    p.update(extra)
    return ("mos_array", p)


def _pair(w_um, l_um, **extra):
    p = {"w_um": w_um, "l_um": l_um, "splits": 1, "add_guard_ring": False,
         "gate_contact": True}
    p.update(extra)
    return ("diff_pair", p)


#: (block id, (generator, params), schematic device -> block port suffix)
BLOCKS = [
    # -- comparator_dut_analog (the static differential preamplifier) -----
    ("mb", _mos(5, 4, **_NFET), {"MB": "U0"}),
    ("mt", _mos(10, 4, **_NFET), {"MT": "U0"}),
    ("mip_min", _pair(30, 2, **_NFET), {"MIP": "Q1_1", "MIN": "Q2_1"}),
    ("rn_rp", ("res_array",
               {"length_um": 120, "width_um": 1, "num": 2, "dummy": 0,
                "flavor": "1k"}),
     {"RN": "R0", "RP": "R1"}),
    # -- comparator_dut_latch (StrongARM + isolation invs + NOR SR latch) -
    ("mtl", _mos(16, 0.5, **_NFET), {"MTL": "U0"}),
    ("m1_m2", _pair(8, 0.5, **_NFET), {"M1": "Q1_1", "M2": "Q2_1"}),
    ("m3_m4", _pair(6, 0.5, **_NFET), {"M3": "Q1_1", "M4": "Q2_1"}),
    ("m5_m6", _pair(6, 0.5, **_PFET), {"M5": "Q1_1", "M6": "Q2_1"}),
    ("m7_m8", _pair(4, 0.5, **_PFET), {"M7": "Q1_1", "M8": "Q2_1"}),
    ("m9_m10", _pair(2, 0.5, **_PFET), {"M9": "Q1_1", "M10": "Q2_1"}),
    ("ip1_ip2", _pair(5, 0.5, **_PFET), {"IP1": "Q1_1", "IP2": "Q2_1"}),
    ("in1_in2", _pair(2, 0.5, **_NFET), {"IN1": "Q1_1", "IN2": "Q2_1"}),
    ("a1p_b1p", _pair(10, 0.5, **_PFET), {"A1P": "Q1_1", "B1P": "Q2_1"}),
    ("a2p_b2p", _pair(10, 0.5, **_PFET), {"A2P": "Q1_1", "B2P": "Q2_1"}),
    ("a1n_b1n", _pair(2, 0.5, **_NFET), {"A1N": "Q1_1", "B1N": "Q2_1"}),
    ("a2n_b2n", _pair(2, 0.5, **_NFET), {"A2N": "Q1_1", "B2N": "Q2_1"}),
]

#: block id -> {schematic device name: block port suffix}, flattened
_DEV2BLOCK: dict[str, tuple[str, str]] = {}
for _bid, _gen, _devs in BLOCKS:
    for _dev, _suffix in _devs.items():
        _DEV2BLOCK[_dev] = (_bid, _suffix)


#: `res_array` reports generic terminal names ("R0_A"/"R0_B"), not the
#: schematic's own resistor pin names ("m"/"p") -- this maps the two per
#: resistor device (the schematic's "b" bulk pin is excluded everywhere, see
#: the module docstring).
_RES_TERMINAL = {"m": "A", "p": "B"}


def _p(dev: str, terminal: str) -> dict:
    """Resolve a schematic '<device>_<terminal>' pin (e.g. 'MIP_d') to a
    {"block": ..., "port": ...} connectivity[]/pins[] entry."""
    bid, suffix = _DEV2BLOCK[dev]
    if suffix.startswith("R"):  # res_array block: suffix is "R0"/"R1"
        return {"block": bid, "port": f"{suffix}_{_RES_TERMINAL[terminal]}"}
    return {"block": bid, "port": f"{suffix}_{terminal.upper()}"}


#: Every schematic net wider than one pin, transcribed directly from the
#: `N {...} {lab=<net>}` labels in both .sch files (body/bulk terminals
#: excluded -- see the module docstring's "What is not attempted here").
NETS: dict[str, list[tuple[str, str]]] = {
    # comparator_dut_analog
    "ibias": [("MB", "d"), ("MB", "g"), ("MT", "g")],
    "atail": [("MT", "d"), ("MIP", "s"), ("MIN", "s")],
    # The preamp -> latch hand-off, transcribed from `comparator_dut.sch`'s
    # own instance line rather than from the two cells' pin *names*:
    #   XL aop aon clk dout doutb vdd vss comparator_dut_latch
    # binds the latch's `inp` to `aop` and its `inn` to `aon` -- i.e. the
    # preamp's INVERTING output (`aon`, MIP's drain) drives the latch's
    # `inn` (M2's gate), and `aop` drives `inp` (M1's gate). Wiring these
    # the other way round still compares *topologically* clean (this
    # comparator is fully symmetric, so `klayout.db.NetlistComparer` simply
    # resolves the ambiguity by pairing every latch-internal net with its
    # twin), but it inverts the sense of the `dout`/`doutb` boundary pins
    # against `sim/dut/README.md`'s interface contract -- an LVS report's
    # `net_correspondence` is what catches it, not its `status`. See
    # layout/README.md's "Pin-order interface-contract check".
    "aon": [("MIP", "d"), ("RN", "m"), ("M2", "g")],   # preamp -> latch (inn)
    "aop": [("MIN", "d"), ("RP", "m"), ("M1", "g")],   # preamp -> latch (inp)
    "vdd": [
        ("RN", "p"), ("RP", "p"),
        ("M5", "s"), ("M6", "s"), ("M7", "s"), ("M8", "s"),
        ("M9", "s"), ("M10", "s"), ("IP1", "s"), ("IP2", "s"),
        ("A1P", "s"), ("B1P", "s"),
    ],
    "vss": [
        ("MB", "s"), ("MT", "s"), ("MTL", "s"),
        ("IN1", "s"), ("IN2", "s"),
        ("A1N", "s"), ("B1N", "s"), ("A2N", "s"), ("B2N", "s"),
    ],
    # comparator_dut_latch
    "clk": [("MTL", "g"), ("M7", "g"), ("M8", "g"), ("M9", "g"), ("M10", "g")],
    "ltail": [("MTL", "d"), ("M1", "s"), ("M2", "s")],
    "mn": [("M1", "d"), ("M3", "s"), ("M9", "d")],
    "mp": [("M2", "d"), ("M4", "s"), ("M10", "d")],
    "qn": [("M3", "d"), ("M4", "g"), ("M5", "d"), ("M6", "g"), ("M7", "d"),
           ("IP2", "g"), ("IN2", "g")],
    "qp": [("M4", "d"), ("M3", "g"), ("M6", "d"), ("M5", "g"), ("M8", "d"),
           ("IP1", "g"), ("IN1", "g")],
    "sp": [("IP1", "d"), ("IN1", "d"), ("A1P", "g"), ("A1N", "g")],
    "sn": [("IP2", "d"), ("IN2", "d"), ("B1P", "g"), ("B1N", "g")],
    "na": [("A1P", "d"), ("A2P", "s")],
    "nb": [("B1P", "d"), ("B2P", "s")],
    "dout": [("A2P", "d"), ("A1N", "d"), ("A2N", "d"),
              ("B2P", "g"), ("B2N", "g")],
    "doutb": [("B2P", "d"), ("B1N", "d"), ("B2N", "d"),
               ("A2P", "g"), ("A2N", "g")],
}

#: Single-pin nets -- labelled via gen-compose's `pins[]` (nothing to route:
#: each is one gate terminal with no other pin on its net). Every other
#: schematic pin (ibias/vdd/vss/clk/dout/doutb) is a >=2-pin `NETS` entry
#: above and therefore cannot ALSO carry a `pins[]` label (gen-compose
#: rejects a (block, port) used in both) -- those six carry their boundary
#: name from the Metal3 trunk label `route_nets.py` draws on every net
#: instead, which is what `klt extract --pins` then promotes to a top-level
#: pin (see `run_lvs.py`'s `INTERFACE_PINS`).
PIN_LABELS = {
    "vinp": _p("MIP", "g"),
    "vinn": _p("MIN", "g"),
}


def run_klt(*args) -> str:
    cmd = ["klt", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 3):
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"klt {' '.join(args)} failed (exit {proc.returncode})")
    return proc.stdout


def gen_blocks() -> None:
    os.makedirs(GENDIR, exist_ok=True)
    for bid, (generator, params), _devs in BLOCKS:
        gds = os.path.join(GENDIR, f"{bid}.gds")
        out = run_klt(
            "gen", generator,
            "--pdk", PDK,
            "--params", json.dumps(params),
            "--cell-name", bid,
            "-o", gds,
            "--format", "json",
        )
        report = json.loads(out)
        with open(os.path.join(GENDIR, f"{bid}.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
        n = report["device_count"]
        print(f"gen {bid:12s} {generator:10s} device_count={n}")


def build_request() -> dict:
    connectivity = []
    for net, pins in NETS.items():
        connectivity.append({
            "net": net,
            "pins": [_p(dev, term) for dev, term in pins],
        })
    pins_top = [
        {"net": net, "block": entry["block"], "port": entry["port"]}
        for net, entry in PIN_LABELS.items()
    ]
    order = [bid for bid, _, _ in BLOCKS]
    return {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": PDK},
        "blocks": [
            {"id": bid, "generator_report": f"{bid}.json"}
            for bid, _, _ in BLOCKS
        ],
        "placement": {"strategy": "row", "order": order, "spacing_um": 3.0},
        "connectivity": connectivity,
        "pins": pins_top,
        # No `routing` block: this is a declare-only request (klt gen-compose
        # #1188). Every connectivity[] net is still validated against the
        # blocks' own reported ports -- a typo'd or stale port name is still
        # a hard request error -- but no metal is drawn here. `route_nets.py`
        # draws all of it instead, on the vertical/horizontal layer pair this
        # design's non-planar net graph needs and gen-compose's one-plane-per
        # -net router cannot express (see that module's docstring and
        # layout/README.md's "Routing" section).
        "options": {
            "cell_name": "COMPARATOR",
            "output": os.path.join(HERE, "comparator.gds"),
        },
    }


def gen_compose() -> dict:
    request = build_request()
    req_path = os.path.join(GENDIR, "request.json")
    with open(req_path, "w", encoding="utf-8") as fh:
        json.dump(request, fh, indent=2)
        fh.write("\n")
    out = run_klt("gen-compose", req_path, "--format", "json")
    response = json.loads(out)
    with open(os.path.join(HERE, "comparator.gen-compose.json"), "w", encoding="utf-8") as fh:
        json.dump(response, fh, indent=2)
        fh.write("\n")
    return response


def main() -> None:
    gen_blocks()
    response = gen_compose()
    n_mos = sum(len(devs) for bid, gp, devs in BLOCKS if gp[0] != "res_array")
    n_res = sum(len(devs) for bid, gp, devs in BLOCKS if gp[0] == "res_array")
    print(f"\nplaced comparator.gds  transistors={n_mos}  resistors={n_res}")
    print(f"bbox_um (placement only): {response['bbox_um']}")
    print(f"connectivity validated for {len(response['nets'])} nets "
          f"({sum(len(n['pins']) for n in response['nets'])} pins)")

    print("\nrouting every net (layout/route_nets.py)...")
    route_nets.route()
    drc = route_nets.run_drc()
    print(f"klt drc: status={drc['status']} violations={drc['violation_count']}")


if __name__ == "__main__":
    main()
