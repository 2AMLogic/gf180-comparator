#!/usr/bin/env python3
"""Post-process `comparator.gds` to close the `metal1.space.1` violations
`klt gen-compose` leaves behind -- issue #20 (DRC signoff, T1 checklist
item 3).

WHY THIS EXISTS (read `layout/README.md`'s "DRC signoff" section for the
full derivation -- this is the summary)
------------------------------------------------------------------------
`klt gen-compose --deck gf180mcu` routes every net in `gen_comparator.py`'s
`NETS` with `nets[].legs[].routed: true`, but six of those legs land on a
`diff_pair` block's own `Q1_1_G` port -- the interleaved pair's physically
-interior device row, whose gate landing pad sits sandwiched between the
two rows' own S/D metal (unlike `Q2_1_G`'s pad, which sits clear at the
block's outer edge). Reaching it forces the router's approach to thread a
gap that is *narrower than gf180mcu's own `metal1.space.1` minimum*
(0.23um) -- a real DRC violation `gen-compose`'s own routability heuristics
never flag, confirmed independently (six different W/L/flavor
combinations, twelve violations, always the same class) and filed
generically per `CLAUDE.md`'s friction protocol as
[klayout-tools#1904](https://github.com/2AMLogic/klayout-tools/issues/1904).
Direct experiments ruled out every caller-side knob `klt gen-compose`
exposes (`routing.width_um`, `placement.spacing_um`, `diff_pair`'s own
`row_spacing_um`, `connectivity[].legs[].waypoints_um` detours, and
swapping which schematic device maps to Q1 vs Q2) -- see the module
docstring history in this repo's git log and the filed issue's own
"Ruled out" section for the arithmetic (the internal S-to-D gap this
squeezes through is a fixed ~0.66um regardless of route width, and
0.66um cannot fit a legal-width (>=0.23um) wire with legal spacing
(>=0.23um) on both sides -- 3 x 0.23um = 0.69um > 0.66um).

WHAT THIS SCRIPT DOES (a *physical*, not a connectivity, fix)
---------------------------------------------------------------
For every `metal1.space.1` violation `klt drc` reports against
`comparator.gds`, this script edits *only* the Metal1 *geometry* --
identical `NETS`/connectivity to `gen_comparator.py`'s own request, no net
is touched, dropped, or rerouted. Two techniques, chosen per violation:

1. **Corridor bridge** (5 of 6 hops): when the violation is a single net's
   own routed metal squeezed between two *other* nets' plates (a clean,
   single Metal1 polygon touching the violation box), the squeezed segment
   is cut out of Metal1 and re-drawn on Metal2 with a Via1 drop on each
   end, landing on the *same* polygon's own remaining metal -- a standard
   "jump to the layer above" technique free of gf180mcu's Metal1-only
   congestion at that exact spot. Every via placement is verified (not
   assumed) to land fully on the intended polygon before being drawn.
2. **Shave the wider side** (the rest): when the violation is between two
   *different* plates and one side has ample width margin (e.g. a `vdd`/
   `vss`/tail-node plate, not the thin route itself), that wider plate's
   edge is nudged back just enough to restore the legal minimum spacing,
   split proportionally to each side's own safe headroom so neither shave
   alone has to reach far enough to risk the plate's own `metal1.width.1`
   minimum.

**The `a2n_b2n` / `doutb` hop is bespoke** (see `layout/README.md`): its
`diff_pair` sits at the design's own right edge, immediately next to a
contact whose enclosure margin a generic corridor bridge or shave both
clip. The fix here removes the whole tight junction and re-joins it with a
Metal2 jumper landing on two independently-verified-clear Metal1 pads,
well outside the contact's footprint -- confirmed via `klt lvs` /
`klt extract` producing an *identical* connectivity signature to the
unpatched layout (same `category_counts`, same 103 `mismatches[]`,
byte-for-byte) before and after, i.e. this hop's own gate connection is
neither dropped nor accidentally shorted to anything else.

**Verification, not assertion**: this script re-runs `klt drc` on its own
output before returning and raises if it is not `status: clean` -- it does
not claim success it has not just re-checked.

Usage
-----
    python3 layout/fix_metal1_space.py

Called automatically by `gen_comparator.py`'s own `main()` right after
`gen_compose()` writes `comparator.gds` -- this file documents the
technique and can also be re-run standalone against any already-composed
`comparator.gds` (e.g. after a future re-route) as its own regeneration
step. Requires `klt` on `PATH` and `klayout.db`'s Python bindings
importable (same `klayout` package `klt` itself is built on).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
GDS = os.path.join(HERE, "comparator.gds")
DECK = "gf180mcu"
TOP = "COMPARATOR"

METAL1 = (34, 0)
METAL2 = (36, 0)
VIA1 = (35, 0)
CONTACT = (33, 0)

#: gf180mcu's `metal1.space.1` / `metal1.width.1` minimum (0.23um at this
#: deck's 0.0005um/dbu).
SPACE_THRESHOLD_DBU = 460
#: Extra cushion added beyond the bare minimum on every fix, so a
#: subsequent re-run of the (imprecise, floating-point-free) DRC engine
#: doesn't re-flag the same spot on a rounding technicality.
SAFETY_DBU = 20
#: How far a "shave" cut's y-range extends past the violation's own
#: reported y-range -- just enough to fully cover corner effects in the
#: DRC engine's own reported box without reaching into an unrelated
#: feature (a wider pad, a different contact) further along the same net.
SHAVE_Y_PAD_DBU = 20
#: gf180mcu's Via1 is a fixed 0.26um x 0.26um square (only the minimum
#: half of the rule is checked by this deck -- see
#: `klayout_tools/decks/gf180mcu.py`'s own `via1.width.1` provenance note).
VIA_SIZE_DBU = 520
#: `metal2.enclosing.via1.1` needs only 0.01um; doubled for safety margin.
VIA_ENC_M2_DBU = 40
#: How far a corridor bridge's cut extends past the paired violations'
#: own bounding box, so the via search starts from solidly-outside the
#: tight zone rather than right at its edge.
CORRIDOR_MARGIN_DBU = 460
#: Extra clearance the drawn Metal2 patch keeps beyond each via's own
#: footprint, on top of `VIA_ENC_M2_DBU`.
M2_OUTER_MARGIN_DBU = 100

# The `doutb` net's `a1n_b1n.Q2_1_D -> a2n_b2n.Q1_1_G` leg (module
# docstring's "bespoke" case): identified by the pair of violation boxes
# `klt drc` reports for it before any fix is applied.
A2N_B2N_LEFT_X = 648200
A2N_B2N_RIGHT_X = 649220


def run_drc(path: str) -> dict:
    proc = subprocess.run(
        ["klt", "drc", path, "--deck", DECK, "--top", TOP, "--format", "json"],
        capture_output=True, text=True,
    )
    if proc.returncode not in (0, 3):
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"klt drc failed unexpectedly (exit {proc.returncode})")
    return json.loads(proc.stdout)


def _pair_violations(viols: list[dict]) -> list[tuple[dict, dict]]:
    """Pair up the two `metal1.space.1` violations that are the left/right
    flanks of the same squeezed corridor (same y-band, nearest neighbour
    in x)."""
    items = [
        dict(v, cy=(v["bbox"]["bottom"] + v["bbox"]["top"]) / 2,
             cx=(v["bbox"]["left"] + v["bbox"]["right"]) / 2)
        for v in viols
    ]
    items.sort(key=lambda v: (round(v["cy"] / 1000), v["cx"]))
    pairs, used = [], set()
    for i, a in enumerate(items):
        if i in used:
            continue
        best = None
        for j, b in enumerate(items):
            if j <= i or j in used:
                continue
            if abs(a["cy"] - b["cy"]) > 1500:
                continue
            gap = b["cx"] - a["cx"]
            if gap <= 0 or gap > 4000:
                continue
            if best is None or gap < (best["cx"] - a["cx"]):
                best = b
        if best is None:
            raise SystemExit(f"could not pair violation: {a}")
        used.add(i)
        used.add(items.index(best))
        pairs.append((a, best))
    return pairs


def _find_via_center(region, cx, edge_y, direction, x_lo, x_hi):
    """Slide a `VIA_SIZE_DBU` square outward from `edge_y` (in `direction`)
    until it lands fully inside `region` (already isolated to one net's own
    polygon by the caller) -- returns `None` if nothing safe is found."""
    half = VIA_SIZE_DBU // 2
    cx = max(x_lo + half, min(x_hi - half, cx))
    for step in range(0, 3000, 10):
        cy = edge_y + direction * (step + half)
        box = db.Box(cx - half, cy - half, cx + half, cy + half)
        if (db.Region(box) & region).area() == box.width() * box.height():
            return cx, cy
    return None


def _inside_sign(region, x_edge, y0, y1):
    """+1 if `region` lies to the right of the vertical edge at `x_edge`,
    -1 if to the left, `None` if ambiguous (shouldn't happen for a real
    DRC-reported edge)."""
    ym = (y0 + y1) // 2
    right = db.Region(db.Box(x_edge + 2, ym - 2, x_edge + 6, ym + 2))
    left = db.Region(db.Box(x_edge - 6, ym - 2, x_edge - 2, ym + 2))
    in_right = not (region & right).is_empty()
    in_left = not (region & left).is_empty()
    if in_right and not in_left:
        return +1
    if in_left and not in_right:
        return -1
    return None


def _local_width(region, x_edge, y0, y1, s, probe_range=2500):
    ym = (y0 + y1) // 2
    probe = (db.Box(x_edge, ym - 2, x_edge + probe_range, ym + 2) if s > 0
             else db.Box(x_edge - probe_range, ym - 2, x_edge, ym + 2))
    sub = region & db.Region(probe)
    return sub.bbox().width() if not sub.is_empty() else 0


def fix(gds_path: str = GDS) -> None:
    d = run_drc(gds_path)
    if d["status"] == "clean":
        print("klt drc already clean -- nothing to fix")
        return

    viols = [v for v in d["violations"] if v["rule"] == "metal1.space.1"]
    others = [v for v in d["violations"] if v["rule"] != "metal1.space.1"]
    if others:
        raise SystemExit(
            f"fix_metal1_space.py only knows how to fix metal1.space.1 -- "
            f"unexpected violation(s) present: {others}"
        )
    pairs = _pair_violations(viols)
    print(f"{len(viols)} metal1.space.1 violations -> {len(pairs)} corridor hops")

    layout = db.Layout()
    layout.read(gds_path)
    top = layout.top_cell()
    # CRITICAL: `comparator.gds` is a real cell hierarchy (16 `klt gen`
    # blocks, each its own cell), not a flat stream -- `begin_shapes_rec`
    # reads it flattened, but `top.shapes(...).clear()`/`.insert(...)` only
    # ever touch the TOP cell's own shape list. Without flattening first,
    # an edit silently leaves the original (violating) geometry untouched
    # in its child cell while adding new geometry on top of it -- `klt drc`
    # then still reports the original violation, unchanged. Flatten once,
    # up front, before any editing.
    top.flatten(-1, True)

    li_m1 = layout.layer(*METAL1)
    li_m2 = layout.layer(*METAL2)
    li_via = layout.layer(*VIA1)
    li_contact = layout.layer(*CONTACT)

    m1 = db.Region(top.begin_shapes_rec(li_m1))
    m1.merge()
    contacts = db.Region(top.begin_shapes_rec(li_contact))

    add_m2: list[db.Box] = []
    add_via: list[db.Box] = []
    manual_shaves: list[tuple[dict, dict]] = []
    special_case_done = False

    for left_v, right_v in pairs:
        lb, rb = left_v["bbox"], right_v["bbox"]

        if lb["left"] == A2N_B2N_LEFT_X and rb["left"] == A2N_B2N_RIGHT_X:
            # See module docstring's "bespoke" paragraph and
            # layout/README.md for the full derivation of these exact
            # coordinates (independently re-verified against a fresh
            # `klt drc` run of the unpatched GDS before being hardcoded
            # here).
            cut = db.Box(648010, 7251, 649220, 10500)
            m1 = m1 - db.Region(cut)
            m1.merge()
            half = VIA_SIZE_DBU // 2
            via_a = db.Box(647700 - half, 10750 - half, 647700 + half, 10750 + half)
            via_b = db.Box(648760 - half, 6080 - half, 648760 + half, 6080 + half)
            for via, name in ((via_a, "A"), (via_b, "B")):
                if (db.Region(via) & m1).area() != via.width() * via.height():
                    raise SystemExit(f"a2n_b2n special-case via {name} lost its safe landing")
            if not (db.Region(via_a) & contacts).is_empty():
                raise SystemExit("a2n_b2n special-case via A unexpectedly overlaps a contact")
            add_via += [via_a, via_b]
            enc = 20
            add_m2.append(db.Box(
                min(via_a.left, via_b.left) - enc, min(via_a.bottom, via_b.bottom) - enc,
                max(via_a.right, via_b.right) + enc, max(via_a.top, via_b.top) + enc,
            ))
            special_case_done = True
            print("special-case bridge applied: a2n_b2n / doutb hop")
            continue

        cut_x0, cut_x1 = lb["left"], rb["right"]
        cut_y0 = min(lb["bottom"], rb["bottom"]) - CORRIDOR_MARGIN_DBU
        cut_y1 = max(lb["top"], rb["top"]) + CORRIDOR_MARGIN_DBU
        stub_x0, stub_x1 = lb["right"], rb["left"]
        if stub_x1 <= stub_x0:
            raise SystemExit(f"unexpected geometry for hop {lb}/{rb}")

        probe_bbox = db.Box(lb["left"], lb["bottom"], rb["right"], rb["top"])
        stub_candidates = [p for p in m1.each_merged() if p.bbox().overlaps(probe_bbox)]
        if len(stub_candidates) != 1:
            manual_shaves.append((lb, rb))
            continue
        stub_region = db.Region(stub_candidates[0])

        cut_box = db.Box(cut_x0, cut_y0, cut_x1, cut_y1)
        stub_fixed = stub_region - db.Region(cut_box)

        cx = (stub_x0 + stub_x1) // 2
        vb = _find_via_center(stub_fixed, cx, cut_y0, -1, stub_x0, stub_x1)
        vt = _find_via_center(stub_fixed, cx, cut_y1, +1, stub_x0, stub_x1)
        if vb is None or vt is None:
            manual_shaves.append((lb, rb))
            continue
        vx0, vy0 = vb
        vx1, vy1 = vt
        half = VIA_SIZE_DBU // 2
        add_via.append(db.Box(vx0 - half, vy0 - half, vx0 + half, vy0 + half))
        add_via.append(db.Box(vx1 - half, vy1 - half, vx1 + half, vy1 + half))
        add_m2.append(db.Box(
            min(vx0, vx1, stub_x0) - VIA_ENC_M2_DBU,
            vy0 - half - VIA_ENC_M2_DBU - M2_OUTER_MARGIN_DBU,
            max(vx0, vx1, stub_x1) + VIA_ENC_M2_DBU,
            vy1 + half + VIA_ENC_M2_DBU + M2_OUTER_MARGIN_DBU,
        ))
        m1 = (m1 - stub_region) + stub_fixed
        print(f"corridor bridge at x~{cx}: via_bottom=({vx0},{vy0}) via_top=({vx1},{vy1})")

    for lb, rb in manual_shaves:
        for b in (lb, rb):
            x0, y0, x1, y1 = b["left"], b["bottom"], b["right"], b["top"]
            deficit = SPACE_THRESHOLD_DBU - (x1 - x0) + SAFETY_DBU
            s_l = _inside_sign(m1, x0, y0, y1)
            s_r = _inside_sign(m1, x1, y0, y1)
            w_l = _local_width(m1, x0, y0, y1, s_l) if s_l else -1
            w_r = _local_width(m1, x1, y0, y1, s_r) if s_r else -1
            yy0, yy1 = y0 - SHAVE_Y_PAD_DBU, y1 + SHAVE_Y_PAD_DBU
            head_l = max(0, w_l - SPACE_THRESHOLD_DBU - SAFETY_DBU)
            head_r = max(0, w_r - SPACE_THRESHOLD_DBU - SAFETY_DBU)
            total_head = head_l + head_r
            if total_head <= 0:
                shave_l = deficit // 2
                shave_r = deficit - shave_l
            else:
                shave_l = min(head_l, (deficit * head_l) // total_head + 1)
                shave_r = deficit - shave_l
            boxes = []
            if shave_l > 0 and s_l is not None:
                boxes.append(db.Box(x0 + s_l * shave_l, yy0, x0, yy1) if s_l < 0
                             else db.Box(x0, yy0, x0 + s_l * shave_l, yy1))
            if shave_r > 0 and s_r is not None:
                boxes.append(db.Box(x1, yy0, x1 + s_r * shave_r, yy1) if s_r > 0
                             else db.Box(x1 + s_r * shave_r, yy0, x1, yy1))
            m1 = m1 - db.Region(boxes)
            m1.merge()
            print(f"shave at x0={x0}(-{shave_l}) x1={x1}(-{shave_r}) y=({yy0},{yy1})")

    if not special_case_done:
        raise SystemExit(
            "expected to hit the a2n_b2n/doutb special case but never did -- "
            "the composed layout's geometry has changed enough that this "
            "script's hardcoded coordinates no longer apply; re-derive them "
            "(see the module docstring) before trusting this fix"
        )

    top.shapes(li_m1).clear()
    top.shapes(li_m1).insert(db.Region(list(m1.each_merged())))
    m2_region = db.Region(add_m2)
    m2_region.merge()
    top.shapes(li_m2).insert(m2_region)
    for b in add_via:
        top.shapes(li_via).insert(b)

    layout.write(gds_path)
    print(f"wrote {gds_path}")

    d2 = run_drc(gds_path)
    if d2["status"] != "clean":
        raise SystemExit(
            f"fix_metal1_space.py did not reach a clean klt drc result: "
            f"status={d2['status']} violation_count={d2.get('violation_count')} "
            f"violations={d2.get('violations')}"
        )
    print(f"klt drc: status=clean (deck {d2['provenance']['deck']['content_hash']})")


if __name__ == "__main__":
    fix()
