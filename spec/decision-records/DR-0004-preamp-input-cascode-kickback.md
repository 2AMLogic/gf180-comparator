# DR-0004: Cascode the preamp input pair to close the kickback gap (schematic level)

- **Status**: proposed
- **Date**: 2026-10-08
- **Decided by**: Builder agent, issue #102 (operator ratification required — see "Decision")
- **Supersedes**: none. Amends the preamp topology of
  [DR-0001](DR-0001-comparator-topology.md) by one added device group; does not
  supersede it.
- **Superseded by**: (none while this record stands)
- **Related**: #102, DR-0001, DR-0002 (kickback miss accepted at ratification),
  `signoff/README.md` item 5, `sim/comparator-kickback/records/20261008-222136257394-926e792`
  (cascoded), `…/20261008-224115765170-7e61c52` (control, un-cascoded),
  `sim/comparator-regeneration/records/20261008-235219317743-7e61c52`,
  `sim/comparator-offset-mc/records/20261008-235432688892-7e61c52`,
  `sim/comparator-preamp-noise/records/20261008-235224548630-7e61c52`,
  [klayout-tools#2894](https://github.com/2AMLogic/klayout-tools/issues/2894)

## Context

DR-0002 ratified the target table unchanged and accepted kickback as a known
miss: 1/45 corners within ≤ 5 mV, 0/45 within ≤ 2 mV, worst 10.01 mV
(`sf_-40c_3.63v`), the sole blocker of T1 item 5. DR-0001 named the input-pair
C_gd path as the dominant injection route: the clocked latch swings the preamp
output nodes `aop`/`aon` rail to rail, and that swing reaches `vinp`/`vinn`
through the input pair's gate-drain capacitance. Issue #102 asked for one
bounded schematic-level experiment against the **unchanged** bounds.

## Decision

Add an nfet cascode between each input-pair drain and its poly load
(`MCP`/`MCN`, `nfet_03v3`, L = 0.5 µ, W = 20 µ), so the input-pair drains
(`xcp`/`xcn`) no longer follow the swinging `aop`/`aon`. The cascode gate
`vcas` is a fixed internal divider off `vdd` (`XRCT` 240 µ / `XRCB` 360 µ
`ppolyf_u_1k`, w = 1 µ ⇒ `vcas` = 0.6·`vdd`) with a 20 µ × 20 µ NMOS gate-cap
decoupler (`XMCC`). Nothing else in DR-0001 changes: input pair, tail,
loads, latch and bias are untouched.

**This record proposes, it does not ratify.** The measured result (below)
meets the kickback target and stretch at 45/45 schematic corners, but the
schematic is not what T1 item 5 is graded on post-layout, and the topology
change obliges layout, DRC, LVS and extraction re-runs that are explicitly out
of scope of #102. The operator ratifies this record (or declines it) before
the layout follow-up is built. No row of the README target table is edited.

## Sizing rationale

- **Cascode on the input pair, not input downsizing.** Downsizing trades
  directly against the offset-σ and noise rows (DR-0001 sized the pair from
  `sim/comparator-offset-mc/records/20260909-055500-e2bb637`); the cascode adds
  isolation without touching either.
- **L = 0.5 µ, W = 20 µ.** Short cascode, wide enough that its V_gs stays low
  (V_ds,sat headroom for the input pair at `ss_125c_2.97v`: the decision-time
  record shows every one of the 45 corners still resolves correctly,
  `dout_*_end` ≥ 0.9, so headroom held everywhere simulated). Not optimised;
  v1 was run once and not swept.
- **`vcas` = 0.6·`vdd`.** A ratio picked by hand to keep `xcp` (≈ `vcas` − V_gs,casc)
  above the input pair's saturation edge at the low-supply corners; 5.5 µA of
  static divider current at 3.3 V. Per-device operating points were not
  extracted, so headroom is evidenced only by every corner still deciding
  correctly. One bias ratio was tried; it
  was not tuned and is not claimed optimal.
- **Input-pair and load sizes**: unchanged from DR-0001.

## Measured result (schematic, 45 PVT corners, ratified bounds unchanged)

All rows below are `klt sim` batch-fleet runs (c7i.8xlarge Spot, fleet runner
klt 0.5.0, client klt 0.7.0, ngspice 46). One request per supply point; process
tt/ff/ss/fs/sf × −40/27/125 °C per request. Baselines are the DR-0002 numbers
(local harness) except kickback, which was re-measured through the *same*
`klt sim` path as a control.

| Row (bound) | Un-cascoded (DR-0002 / control) | Cascoded (this record) | Corners within target / stretch |
|---|---|---|---|
| Kickback into 1 kΩ (≤ 5 / ≤ 2 mV) | 4.528–10.008 mV, target 1/45, stretch 0/45 (control record `…224115765170-7e61c52` reproduces DR-0002's 4.53–10.01) | **0.0488–0.0849 mV** (min `ss_-40c_2.97v`, max `sf_-40c_3.63v`), decisions still correct 45/45 | **45/45 / 45/45** |
| Offset 3σ (≤ 15 / ≤ 8 mV) | 2.796–2.807 mV | 2.684–3.136 mV (min `fs_-40c_2.97v`, max `ss_-40c_2.97v`); nominal 2.769 mV | 45/45 / 45/45 |
| Decision time @ 50 mV (≤ 1.5 / ≤ 0.8 ns) | 0.464–1.237 ns; stretch missed at 16/45 | 0.469–1.274 ns (max `ss_125c_2.97v`); stretch missed at 17/45 | 45/45 / 28/45 |
| Static power (≤ 1 mW / ≤ 500 µW) | ≈ 82–108 µW | 98.4–131.7 µW | 45/45 / 45/45 |
| Input-referred noise (≤ 1.0 / ≤ 0.6 mV rms) | 91.25 µV nominal (66.8–128.8 µV over 45) | **99.5 µV at nominal only** (ngspice 42, see below); A_v 18.01 → 18.49 | nominal only: yes / yes |

Caveats, stated plainly:

- **Noise is nominal-point only.** The fleet runner's klt (0.5.0) has no
  `noise` analysis, so the 45-corner noise grid could not be sent to the
  batch fleet, and hand-running a grid on the shared worker is not allowed. The
  nominal point was run locally (one corner, `--allow-toolchain-drift`,
  ngspice 42 versus the pinned floor of 46). To keep that honest the
  un-cascoded netlist was run through the *same* local engine: 91.25 → 99.46 µV
  (+9 %). Extrapolating +9 % to the DR-0002 worst corner (128.8 µV) gives ≈ 140 µV, still
  7× inside the 1.0 mV target — **an extrapolation, not a measurement**.
- **Offset sigma statistics.** n = 200 draws per corner, seed 20260909 (common
  random numbers, as in the original bench), so the sigma has a 1/√(2N) = 5 %
  statistical error. The cascode did not measurably change offset: the spread
  of 2.68–3.14 mV is of the order of that error plus real PVT movement.
  This run measures the vcm = 1.65 V offset point only (`voa`); the bench's
  ±50 mV common-mode-step points and rpair null control were not requested (the
  0.5.0 runner cannot express the nested sweep), see the records' "Not computed" lines.
- **Decision time stretch.** Stretch (≤ 0.8 ns) was already missed at 16/45; it
  is now missed at 17/45. The cascode costs ≈ 3 % of decision time at the worst
  corner and does not move the stretch gap in any meaningful way.
- **Power** rises ≈ 16–24 µW (the `vcas` divider plus the cascode leakage); the
  row retains > 3.7× margin to the 500 µW stretch.
- **Mechanism**: a 60–120× reduction (10.01 → 0.085 mV worst case) is large.
  It is consistent with the injection path being almost entirely the Miller
  C_gd route from the swinging `aon`/`aop` through the input pair (cascode
  isolation ≈ g_m,c·r_o,c), as DR-0001 predicted; it is *not* independently
  confirmed by a per-path decomposition. The control run through the same
  tooling rules out a measurement artefact for the cascoded number (the
  un-cascoded netlist gives the known 4.53–10.01 mV).

## Post-layout prediction (stated before any re-extraction)

The schematic-to-extracted delta of the un-cascoded design is +32 % at nominal
(7.60 → 10.03 mV) and +3.96 mV / +4.57 mV absolute at the best / worst corner
(4.53 → 8.49, 10.01 → 14.58 mV). That increment is routing coupling onto the
input nets, which the cascode does not isolate (it isolates the
*device* C_gd path, not wire-to-wire coupling). Two bounding cases:

- If the layout-added term scales with the (now removed) Miller path:
  post-layout ≈ 0.1–1 mV.
- If the layout-added term is independent of the topology change (the
  conservative case): post-layout ≈ schematic + 4.0 … 4.6 mV ⇒
  **≈ 4.0–4.7 mV, a worst-case margin of only ≈ 0.3 mV to the 5 mV target**, and
  the 2 mV stretch would be missed.

So: the schematic-level gap is closed with a large margin, but "post-layout
headroom" is *not established* by this record; whether the residual wire
coupling is the dominant term is the first thing the extracted re-run must
show, and a routing change (shielding / symmetric input routing) may be
needed even with the cascode. The prediction is falsifiable by the follow-up
`sim/characterize.sh postlayout` run.

## Alternatives considered

- **Revise the kickback bound** — rejected: agents do not relax the ratified spec.
- **Downsize the input pair only** — rejected in the issue and by DR-0001's sizing:
  directly trades offset-σ and noise margin.
- **Latch-side reset / clock-edge changes** — not tried: the dominant path
  is through the input pair, so the cascode targets it directly; held as the
  next lever if post-layout shows a residual.
- **Retune the cascode (L, W, `vcas` ratio, bias source)** — not done; v1 met
  the bound by > 50× so further tuning is optimisation, not need. A fixed
  divider is also supply- and process-proportional rather than a
  tracking bias; it worked across the 45-corner grid and was not further
  investigated.
- **Defer indefinitely** — leaves item 5 `check_failed`.

## Consequences

- **Good**: kickback closes at schematic level at 45/45 corners with both
  offset and noise rows undamaged and power and decision-time target intact.
- **Bad / costs**: +16–24 µW static power; +≈ 3 % worst-case decision time
  (stretch gap 16 → 17/45 corners); +1 resistive divider (≈ 600 kΩ of poly), a
  20 µ × 20 µ decoupler and two cascode devices of layout area; a fixed-ratio
  bias that is not process-tracking; one more node (`vcas`) to wire and
  decouple in layout.
- **Invalidated**: `layout/` (GDS, LVS reference, PEX), DRC/LVS/PEX evidence and
  the post-layout `sim/` records were produced for the un-cascoded netlist, and
  T1 items 2–4, 6, 8 pins are stale against `design/comparator.spice` once this
  record is accepted. Re-generation (`layout/gen_comparator.py`), DRC, LVS,
  extraction and the post-layout campaign are follow-ups (not done in #102).
- **Not run**: 44 of 45 noise corners (tool gap, above); the 45-corner
  post-layout kickback.
- `design/comparator.spice` was edited consistently with the `.sch` edits; the
  committed netlist has the same circuit but a different line-wrapping from this
  host's xschem, so `design/netlist.sh --check` reports it stale — as it does for
  the pre-change netlist on this host (a pre-existing xschem-version formatting
  difference; the committed netlist was not regenerated, to keep its sha256 pin).
- Cross-pollination: the same isolation applies to the SAR ADC's embedded
  comparator; filed on that repo, not edited here.

## Spec lines affected

- `README.md#target-specification-ratified-via-dr-0002` — Kickback row —
  measured against, not set (schematic result 0.049–0.085 mV vs ≤ 5 / ≤ 2 mV).
- `README.md#target-specification-ratified-via-dr-0002` — Offset, Noise,
  Decision time, Supply/power rows — measured against, not set.
- `spec/decision-records/DR-0001-comparator-topology.md` — preamp topology —
  amended by this proposed record (cascode added); DR-0001 itself is not edited.
