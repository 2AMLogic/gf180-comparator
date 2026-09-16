#!/usr/bin/env python3
"""Draw 100% of `gen_comparator.NETS` into the composed `comparator.gds`
as a two-layer (vertical/horizontal) channel route, plus the well and
substrate ties every device body needs -- issue #30 (LVS signoff).

WHY THIS EXISTS (the short version; `layout/README.md`'s "Routing" section
carries the full derivation)
----------------------------------------------------------------------
`klt gen-compose`'s own router draws each net as a spanning tree of two-pin
legs on **one** routing plane, and rejects any leg that would cross a net
already drawn on that plane (`route-vs-route`, a real short). That makes the
set of nets it can draw in one call exactly the set whose connectivity graph
is *planar in the chosen floorplan* -- for a single-row placement, the set
whose pin intervals along the row never interleave. This comparator's 18
nets interleave heavily in the latch region (their channel density is well
above 4), so no assignment onto the four planes gf180mcu's deck exposes
(`metal`/`metal2`/`metal3`/`metal4`) can draw them all: measured directly,
a greedy three-plane packing leaves 5 of 18 nets undrawable
(`doutb`/`qn`/`qp`/`vss`/`vdd`), and the single-plane runs #18/#22
committed left 35 of 65 spanning-tree legs undrawn.

The classical answer -- and the one this module implements -- is **channel
routing with a dedicated vertical layer and a dedicated horizontal layer**:
every net's trunk runs horizontally on **Metal3** at its own y track, and
every pin reaches its trunk by a vertical riser on **Metal2**. A trunk can
never short against a riser, because the two are never on the same layer;
two trunks never collide, because each net owns its own y track; and two
risers never collide, because `classify()` gives them disjoint columns (see
its docstring). Crossings stop being a constraint at all, so **every** net
routes, by construction, whatever the floorplan. `klt gen-compose` cannot
express that shape: `routing.layer_role` names one plane per request (per
net/leg at most, with issue #1655), and a single L-shaped leg's horizontal
and vertical halves always land on the same layer -- see `layout/README.md`.

WHAT THIS MODULE DRAWS
-----------------------
1. **Body ties** (`plant_taps`). Neither `mos_array` nor `diff_pair` reports
   a body/bulk port, and this PDK's extraction deck resolves an untied PMOS
   body to its own anonymous Nwell net and every NMOS body to the deck's
   global `vsubs` -- against a reference netlist that ties them to `vdd`
   and `vss`, that is a real, unroutable LVS mismatch, not a naming nuance.
   So this module *draws the missing taps*: an Nwell tab extending each
   PMOS block's own well into the free channel beside it, carrying an
   `Nplus`-over-`Comp` tie (the geometry `klt extract` derives a well tap
   from, issue #1084) up to a Metal1 pad; and `Pplus`-over-`Comp` substrate
   ties in two inter-block gaps. Each tap pad then joins `vdd`/`vss` as an
   ordinary router pin.
2. **Risers** -- Metal1 pad -> Via1 -> Metal2 -- run vertically out of every
   pin to its net's own trunk.
3. **Trunks** -- one Metal3 horizontal segment per net per channel, at that
   net's own y track, with a Via2 where each riser meets it, and one
   `kdb.Text` net label so `klt extract` recovers the net by name rather
   than as an anonymous `$N` (and so `klt extract --pins` can promote the
   interface nets to top-level pins -- see `run_lvs.py`).
4. **Channel links** -- a net with pins in both channels gets one vertical
   Metal2 segment in an inter-block gap joining its two trunks.

The one structural rule that makes this safe: **two shapes on the same
layer are only ever drawn within `MIN_SPACE_UM` of each other when they
belong to the same net.** `check_spacing()` asserts it over the whole drawn
result before anything is written, and `klt drc` (issue #20's own signoff
step, re-run by `gen_comparator.py`) re-checks it independently against the
real deck.

Usage
-----
    python3 layout/route_nets.py        # re-route an already-composed GDS

Called automatically by `gen_comparator.py` right after `klt gen-compose`
places the blocks. Requires `klayout.db` importable (the same `klayout`
package `klt` is built on).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))

# --- gf180mcu layers, as the curated klt extraction deck resolves them -----
M1 = (34, 0)
M2 = (36, 0)
M3 = (42, 0)
V1 = (35, 0)
V2 = (38, 0)
M3_LABEL = (42, 10)
NWELL = (21, 0)
COMP = (22, 0)
NPLUS = (32, 0)
PPLUS = (31, 0)
CONTACT = (33, 0)

#: Routing geometry. Every value clears the gf180mcu deck's own minimum by a
#: margin: metal2/3 width & space 0.28, via1/2 size 0.26 and space 0.26,
#: metal enclosure of a via 0.01, comp width 0.22 / space 0.28, contact size
#: 0.22 / space 0.25, comp enclosure of contact 0.07, nwell enclosure of a
#: comp tap 0.12, nwell space 0.60.
W_ROUTE_UM = 0.32
MIN_SPACE_UM = 0.30      # >= metal{2,3}.space.1 (0.28), with margin
MIN_PITCH_UM = W_ROUTE_UM + MIN_SPACE_UM   # legal centre-to-centre pitch
TRACK_PITCH_UM = 0.80    # W_ROUTE + clearance between neighbouring trunks
VIA_UM = 0.26
VIA_PAD_UM = 0.36        # >= VIA + 2 * enclosure, and >= W_ROUTE
STUB_UM = 0.70           # Metal1 escape stub off a too-crowded S/D pad
CHANNEL_GAP_UM = 1.5     # clearance between the block row and the first track

# Tap geometry (well/substrate ties).
TAP_COMP_UM = 0.44       # comp square side (>= comp.width 0.22, holds a contact)
TAP_CONTACT_UM = 0.26    # >= contact.width 0.22
TAP_IMPLANT_MARGIN_UM = 0.23
TAP_WELL_MARGIN_UM = 0.20   # >= nwell.enclosing.comp 0.12
TAP_TAB_OFFSET_UM = 0.60      # well tab kept clear of the block's own stubs

#: Database unit of the composed stream, read from it at `route()` time
#: rather than assumed (`klt gen-compose` writes gf180mcu at 0.0005um).
_DBU = 0.0005


def _dbu(v: float) -> int:
    return int(round(v / _DBU))


def _box(x0, y0, x1, y1) -> db.Box:
    return db.Box(_dbu(x0), _dbu(y0), _dbu(x1), _dbu(y1))


def _square(cx, cy, side) -> db.Box:
    return _box(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


# ---------------------------------------------------------------------------
# Pin collection
# ---------------------------------------------------------------------------

def collect_pins(nets, dev_to_pin, placement, reports):
    """Resolve every (device, terminal) in `nets` to an absolute-frame pin.

    Returns a list of dicts: net, block, port, x/y (um, composed frame),
    direction_deg and the port's own pad width.
    """
    pins = []
    for net, terminals in nets.items():
        for dev, term in terminals:
            entry = dev_to_pin(dev, term)
            bid, port = entry["block"], entry["port"]
            report = reports[bid]
            p = next(pp for pp in report["ports"] if pp["name"] == port)
            off = placement[bid]
            pins.append({
                "net": net,
                "block": bid,
                "port": port,
                "x": p["x_um"] + off["x"],
                "y": p["y_um"] + off["y"],
                "dir": int(p["direction_deg"]),
                "pad_um": float(p["width_um"]),
                "kind": "device",
            })
    return pins


def classify(pins, reports):
    """Give every pin a riser *direction*, and widen the block's own
    too-narrow pin pitch with a Metal1 escape stub where it needs one.

    Two rules, and between them they make same-layer riser collisions
    impossible without any geometric search:

    * **Direction by row.** A `diff_pair` block stacks its two devices in
      two rows *at the same x*: `Q1_1_S` and `Q2_1_S` share a column and
      usually belong to different nets. The lower row therefore escapes
      **downwards**, into a channel below the block row, and the upper row
      escapes upwards -- so two risers that do share a column never share
      any y at all. A single-row block (`mos_array`, `res_array`) escapes
      upwards.
    * **Escape stubs for the gate pitch.** A generated device reports its
      gate column 0.54um from both its source and its drain column. Two
      minimum-width Metal2 wires need 0.56um between centres on this deck
      (0.28um wide, 0.28um apart), so a riser dropped straight onto each
      pad as reported is 0.02um short of legal -- a hard geometric fact
      about the device pitch, not a routing choice. Where a pin has a
      neighbour that close, its source/drain riser is moved `STUB_UM`
      further out along the direction that pin's own port faces, reached
      by a drawn Metal1 stub off the pad; the gate keeps the column to
      itself. Pins whose reported pitch is already legal (the resistor
      array's facing end pads, 0.92um apart) are left exactly where the
      generator put them.
    """
    for pin in pins:
        port = pin["port"]
        pin["stub_um"] = 0.0
        if pin["kind"] != "device":
            pin.setdefault("updown", "up")
            continue
        ports = reports[pin["block"]]["ports"]
        two_row = any(pp["name"].startswith("Q2_") for pp in ports)
        pin["updown"] = "down" if (two_row and port.startswith("Q1_")) else "up"
        if pin["dir"] % 180 == 90:      # a gate: keep its own column
            continue
        own_x = next(pp["x_um"] for pp in ports if pp["name"] == port)
        crowded = any(pp["name"] != port and abs(pp["x_um"] - own_x) < MIN_PITCH_UM
                      for pp in ports)
        if crowded:
            pin["stub_um"] = STUB_UM
    return pins


# ---------------------------------------------------------------------------
# Well / substrate ties
# ---------------------------------------------------------------------------

def _region(layout, cell, layer):
    idx = layout.find_layer(*layer)
    if idx is None:
        return db.Region()
    return db.Region(cell.begin_shapes_rec(idx))


def plant_taps(layout, cell, pfet_blocks, placement, reports, gaps, shapes):
    """Draw the body ties the device generators do not: one Nwell tap per
    PMOS block (on a well tab grown sideways out of that block's own Nwell)
    and two substrate taps in free inter-block gaps.

    Returns the list of new `vdd`/`vss` router pins, one per tap pad.
    """
    nwell = _region(layout, cell, NWELL)
    new_pins = []

    for bid in pfet_blocks:
        off = placement[bid]
        bbox = reports[bid]["bbox_um"]
        search = _box(bbox["x0"] + off["x"] - 1.0, bbox["y0"] + off["y"] - 1.0,
                      bbox["x1"] + off["x"] + 1.0, bbox["y1"] + off["y"] + 1.0)
        own = (nwell & db.Region(search)).bbox()
        if own.empty():
            raise SystemExit(f"no Nwell found for PMOS block {bid!r}")
        wx1 = own.right * _DBU
        wy0 = own.bottom * _DBU
        wy1 = own.top * _DBU
        # A tab wide enough for the comp tap plus its well enclosure, grown
        # to the right of the block's own well, in the inter-block gap.
        tab_w = TAP_COMP_UM + 2 * TAP_WELL_MARGIN_UM
        tab_h = TAP_COMP_UM + 2 * TAP_WELL_MARGIN_UM
        tab_y0 = wy1 - tab_h if (wy1 - wy0) > tab_h else wy0
        # Held clear of the block's own drain-side escape stubs; the tab is
        # still far short of the next block's well (nwell.space.1, 0.60um).
        tab_x0 = wx1 + TAP_TAB_OFFSET_UM
        shapes[NWELL].append(_box(wx1 - 0.10, tab_y0, tab_x0 + tab_w, tab_y0 + tab_h))
        cx = tab_x0 + tab_w / 2
        cy = tab_y0 + tab_h / 2
        _draw_tap(shapes, cx, cy, NPLUS)
        new_pins.append({
            "net": "vdd", "block": bid, "port": "NWELL_TAP",
            "x": cx, "y": cy, "dir": 90, "pad_um": TAP_COMP_UM,
            "kind": "tap", "updown": "up", "layer": "m2",
        })

    # Substrate ties: gf180mcu's deck connects the substrate globally, so a
    # single drawn P+ tie is enough to give *every* NMOS body (and the two
    # poly resistors' bulk) the real `vss` net instead of the deck's
    # synthesized one -- two are drawn, in separate gaps, as ordinary good
    # practice rather than because the netlist needs both.
    for i, (gx0, gx1) in enumerate(gaps[:2]):
        cx = (gx0 + gx1) / 2
        cy = -0.6
        _draw_tap(shapes, cx, cy, PPLUS)
        new_pins.append({
            "net": "vss", "block": f"substrate_tap_{i}", "port": "TAP",
            "x": cx, "y": cy, "dir": 270, "pad_um": TAP_COMP_UM,
            "kind": "tap", "updown": "down", "layer": "m2",
        })
    return new_pins


def _draw_tap(shapes, cx, cy, implant):
    """Comp + implant + contact + Metal1 pad, centred at (cx, cy)."""
    shapes[COMP].append(_square(cx, cy, TAP_COMP_UM))
    shapes[implant].append(_square(cx, cy, TAP_COMP_UM + 2 * TAP_IMPLANT_MARGIN_UM))
    shapes[CONTACT].append(_square(cx, cy, TAP_CONTACT_UM))
    shapes[M1].append(_square(cx, cy, TAP_COMP_UM))


# ---------------------------------------------------------------------------
# Track / link assignment
# ---------------------------------------------------------------------------

def assign_tracks(pins, y_lo, y_hi, net_order):
    """One horizontal track per net per channel it has pins in."""
    up = defaultdict(list)
    down = defaultdict(list)
    for pin in pins:
        (up if pin["updown"] == "up" else down)[pin["net"]].append(pin)

    tracks = {}
    k = 0
    for net in net_order:
        if net in up:
            tracks[(net, "up")] = y_hi + CHANNEL_GAP_UM + k * TRACK_PITCH_UM
            k += 1
    k = 0
    for net in net_order:
        if net in down:
            tracks[(net, "down")] = y_lo - CHANNEL_GAP_UM - k * TRACK_PITCH_UM
            k += 1
    return tracks, up, down


def assign_links(nets_needing, gaps, riser_x):
    """Give every net with pins in both channels its own vertical link x,
    inside an inter-block gap and clear of every riser column."""
    slots = []
    for gx0, gx1 in gaps:
        x = gx0 + MIN_SPACE_UM + W_ROUTE_UM / 2
        while x <= gx1 - MIN_SPACE_UM - W_ROUTE_UM / 2:
            if all(abs(x - rx) >= W_ROUTE_UM + MIN_SPACE_UM for rx in riser_x):
                slots.append(x)
            x += W_ROUTE_UM + MIN_SPACE_UM
    if len(slots) < len(nets_needing):
        raise SystemExit(
            f"only {len(slots)} channel-link slots for {len(nets_needing)} nets")
    # Spread the links out across the row rather than packing them into the
    # first gaps: a link is a full-height wire, and bunching them would make
    # one gap a wall.
    step = len(slots) / len(nets_needing)
    return {net: slots[int(i * step)] for i, net in enumerate(nets_needing)}


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

_OUTWARD = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}


def via_anchor(pin, m1_region, emit=None):
    """Where the Via1 that lifts this pin off Metal1 goes.

    Two cases. A pin the generator already leaves enough room around keeps
    its own pad: the reported port point sits on the pad's *outward* edge,
    so the via steps **inward** until the whole via square lands inside
    real drawn Metal1 -- checked against the composed layout's geometry,
    not assumed from the report. A pin `classify()` marked crowded instead
    gets its via `stub_um` **outward** of the pad, on a Metal1 stub drawn
    here to reach it, which is what buys the gate column the clearance the
    device pitch does not give it.
    """
    ox, oy = _OUTWARD[pin["dir"] % 360]
    if pin["stub_um"]:
        x = pin["x"] + ox * pin["stub_um"]
        y = pin["y"] + oy * pin["stub_um"]
        if emit is not None:
            x0, x1 = sorted((pin["x"], x))
            y0, y1 = sorted((pin["y"], y))
            emit(M1, _box(x0 - W_ROUTE_UM / 2, y0 - W_ROUTE_UM / 2,
                          x1 + W_ROUTE_UM / 2, y1 + W_ROUTE_UM / 2), pin["net"])
        return x, y
    for step in [0.0, 0.10, 0.16, 0.21, 0.26, 0.32, 0.40, 0.50]:
        x = pin["x"] - ox * step
        y = pin["y"] - oy * step
        via = db.Region(_square(x, y, VIA_UM + 0.02))
        if (via - m1_region).is_empty():
            return x, y
    raise SystemExit(f"no Metal1 landing for via at {pin['block']}.{pin['port']}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def check_spacing(net_shapes):
    """Assert the module's one structural invariant: on any single layer, two
    shapes closer than MIN_SPACE_UM belong to the same net."""
    problems = []
    halo = _dbu(MIN_SPACE_UM) - 1      # strictly closer than MIN_SPACE_UM
    for layer, per_net in net_shapes.items():
        nets = sorted(per_net)
        regions = {n: db.Region(per_net[n]).merged() for n in nets}
        for i, a in enumerate(nets):
            for b in nets[i + 1:]:
                ra, rb = regions[a], regions[b]
                if not (ra & rb).is_empty():
                    problems.append(
                        f"layer {layer}: nets {a!r} and {b!r} overlap -- a short")
                elif not (ra.sized(halo) & rb).is_empty():
                    problems.append(
                        f"layer {layer}: nets {a!r} and {b!r} are closer than "
                        f"{MIN_SPACE_UM}um")
    return problems


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def route(gds_path=None, response_path=None, report_path=None, verbose=True):
    import gen_comparator as G

    gds_path = gds_path or os.path.join(HERE, "comparator.gds")
    response_path = response_path or os.path.join(HERE, "comparator.gen-compose.json")
    report_path = report_path or os.path.join(HERE, "comparator.routing.json")

    response = json.load(open(response_path))
    placement = {b["id"]: b["offset_um"] for b in response["blocks"]}
    placed_bbox = {b["id"]: b["bbox_um"] for b in response["blocks"]}
    reports = {bid: json.load(open(os.path.join(HERE, "_gen", f"{bid}.json")))
               for bid, _, _ in G.BLOCKS}

    global _DBU
    layout = db.Layout()
    layout.read(gds_path)
    _DBU = layout.dbu
    cell = layout.top_cell()
    cell.flatten(-1, True)
    m1_region = _region(layout, cell, M1)

    shapes = defaultdict(list)          # layer -> [db.Box]
    net_shapes = defaultdict(lambda: defaultdict(list))   # layer -> net -> [box]

    def emit(layer, box, net):
        shapes[layer].append(box)
        net_shapes[layer][net].append(box)

    pins = collect_pins(G.NETS, G._p, placement, reports)

    # Free vertical corridors between placed blocks, used for substrate taps
    # and for the channel links.
    order = [bid for bid, _, _ in G.BLOCKS]
    gaps = []
    for a, b in zip(order, order[1:]):
        x0 = placed_bbox[a]["x1"]
        x1 = placed_bbox[b]["x0"]
        if x1 - x0 >= 1.0:
            gaps.append((x0, x1))

    pfet_blocks = [bid for bid, (gen, params), _ in G.BLOCKS
                   if params.get("flavor") == "pfet"]
    tap_shapes = defaultdict(list)
    tap_pins = plant_taps(layout, cell, pfet_blocks, placement, reports, gaps,
                          tap_shapes)
    for layer, boxes in tap_shapes.items():
        shapes[layer].extend(boxes)
    # The taps' own Metal1 pads are landing sites for their Via1 too.
    m1_region = (m1_region + db.Region(tap_shapes[M1])).merged()
    pins += tap_pins
    classify(pins, reports)
    for pin in pins:
        pin["vx"], pin["vy"] = via_anchor(pin, m1_region, emit)

    y_lo = min(b["bbox_um"]["y0"] for b in response["blocks"])
    y_hi = max(b["bbox_um"]["y1"] for b in response["blocks"])
    net_order = list(G.NETS)
    tracks, up, down = assign_tracks(pins, y_lo, y_hi, net_order)

    riser_x = sorted({round(p["vx"], 3) for p in pins})
    need_link = [n for n in net_order if n in up and n in down]
    links = assign_links(need_link, gaps, riser_x)

    report = {"schema": "gf180-comparator.routing/1", "nets": [],
              "channel": {"upper_first_track_um": None, "lower_first_track_um": None},
              "totals": {}}

    total_len = 0.0
    for net in net_order:
        net_pins = [p for p in pins if p["net"] == net]
        entry = {"net": net, "pins": len(net_pins), "risers": [], "trunks": [],
                 "link_x_um": links.get(net), "route_length_um": 0.0}
        for side in ("up", "down"):
            side_pins = (up if side == "up" else down).get(net, [])
            if not side_pins:
                continue
            y_track = tracks[(net, side)]
            xs = []
            for pin in side_pins:
                vx, vy = pin["vx"], pin["vy"]
                _stack_and_rise(emit, vx, vy, y_track, net)
                xs.append(vx)
                entry["risers"].append({
                    "block": pin["block"], "port": pin["port"],
                    "x_um": round(vx, 3), "channel": side,
                    "stub_um": pin["stub_um"],
                    "length_um": round(abs(y_track - vy), 3),
                })
                entry["route_length_um"] += abs(y_track - vy)
            if net in links:
                xs.append(links[net])
            x0, x1 = min(xs), max(xs)
            emit(M3, _box(x0 - W_ROUTE_UM / 2, y_track - W_ROUTE_UM / 2,
                          x1 + W_ROUTE_UM / 2, y_track + W_ROUTE_UM / 2), net)
            entry["trunks"].append({"channel": side, "y_um": round(y_track, 3),
                                    "x0_um": round(x0, 3), "x1_um": round(x1, 3)})
            entry["route_length_um"] += x1 - x0
            label = db.Text(net, db.Trans(_dbu((x0 + x1) / 2), _dbu(y_track)))
            cell.shapes(layout.layer(*M3_LABEL)).insert(label)
        if net in links:
            lx = links[net]
            y_a = tracks[(net, "up")]
            y_b = tracks[(net, "down")]
            emit(M2, _box(lx - W_ROUTE_UM / 2, y_b - W_ROUTE_UM / 2,
                          lx + W_ROUTE_UM / 2, y_a + W_ROUTE_UM / 2), net)
            for y in (y_a, y_b):
                emit(V2, _square(lx, y, VIA_UM), net)
                emit(M3, _square(lx, y, VIA_PAD_UM), net)
                emit(M2, _square(lx, y, VIA_PAD_UM), net)
            entry["route_length_um"] += abs(y_a - y_b)
        entry["route_length_um"] = round(entry["route_length_um"], 3)
        total_len += entry["route_length_um"]
        report["nets"].append(entry)

    # Tap geometry belongs to its own net too, for the spacing invariant.
    for pin in tap_pins:
        net_shapes[M1][pin["net"]].append(_square(pin["x"], pin["y"], TAP_COMP_UM))

    problems = check_spacing(net_shapes)
    if problems:
        for p in problems[:20]:
            print("  SPACING:", p)
        raise SystemExit(f"{len(problems)} same-layer spacing/short problems")

    for layer, boxes in shapes.items():
        li = layout.layer(*layer)
        merged = db.Region(boxes).merged()
        cell.shapes(li).insert(merged)

    # `gds2_write_timestamps: False` zeroes the BGNLIB/BGNSTR date fields.
    # Without it the only bytes that differ between two runs of an otherwise
    # fully deterministic pipeline are those clock readings (8 of them), so
    # the committed GDS would show as modified on every regeneration and
    # "re-running reproduces it byte-for-byte" could not be checked with
    # `git status`. With it, that check is real.
    opts = db.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    layout.write(gds_path, opts)

    report["channel"] = {
        "upper_first_track_um": round(y_hi + CHANNEL_GAP_UM, 3),
        "lower_first_track_um": round(y_lo - CHANNEL_GAP_UM, 3),
    }
    report["totals"] = {
        "nets": len(net_order),
        "pins": len(pins),
        "device_pins": sum(1 for p in pins if p["kind"] == "device"),
        "tap_pins": sum(1 for p in pins if p["kind"] == "tap"),
        "route_length_um": round(total_len, 3),
        "channel_links": len(links),
    }
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    if verbose:
        print(f"routed {len(net_order)} nets, {len(pins)} pins "
              f"({report['totals']['tap_pins']} of them drawn body ties), "
              f"{total_len:.1f}um of metal, {len(links)} channel links")
    return report


def _stack_and_rise(emit, vx, vy, y_track, net):
    """Via1 off the Metal1 pad, the Metal2 riser, and the Via2 that lands it
    on this net's own Metal3 trunk."""
    emit(V1, _square(vx, vy, VIA_UM), net)
    emit(M2, _square(vx, vy, VIA_PAD_UM), net)
    y0, y1 = sorted((vy, y_track))
    emit(M2, _box(vx - W_ROUTE_UM / 2, y0, vx + W_ROUTE_UM / 2, y1), net)
    emit(V2, _square(vx, y_track, VIA_UM), net)
    emit(M2, _square(vx, y_track, VIA_PAD_UM), net)
    emit(M3, _square(vx, y_track, VIA_PAD_UM), net)


def run_drc(gds_path=None):
    """Re-check the drawn result against the real deck -- this module's own
    `check_spacing()` only knows about the shapes it drew itself, so the
    rule authority is always `klt drc` (issue #20 keeps the committed
    evidence; this is the inline sanity re-check)."""
    import subprocess

    gds_path = gds_path or os.path.join(HERE, "comparator.gds")
    proc = subprocess.run(
        ["klt", "drc", gds_path, "--deck", "gf180mcu", "--top", "COMPARATOR",
         "--format", "json"],
        capture_output=True, text=True)
    if proc.returncode not in (0, 3):
        raise SystemExit(f"klt drc failed (exit {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    report = route()
    drc = run_drc()
    print(f"klt drc: status={drc['status']} violations={drc['violation_count']}")
