# Evidence ledger for the target-specification table

Per-row result narrative relocated **verbatim** from the `Basis` column of the
[target-specification table](../README.md#target-specification-ratified-via-dr-0002)
(issue #130; pure relocation, no bound, stretch or verdict meaning changed).
Only relative link prefixes were adjusted for this file's location. The table
keeps the bound, stretch, method and a short current verdict per row. `sim/`
records stay append-only; this ledger summarizes them, it does not replace them.

## Offset sigma

Target: ≤ 15 mV, 3σ (input-referred, post-calibration-free) — Stretch: ≤ 8 mV, 3σ

Monte Carlo via gf180mcu's `sw_stat_mismatch`-based local-mismatch models (per-instance statistical mismatch, confirmed real and present on this PDK — not just global-process corners — by `gf180-sar-adc`'s [`sim/comparator-offset-mc/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-offset-mc): `setseed <n>` then N = 150 draws per PVT point via a `dowhile` reset loop); the bound matches the sg13g2-comparator/sky130-comparator twin set so the three PDKs' eventual measured results are directly comparable, not because it was independently re-derived per PDK. `gf180-sar-adc`'s own *embedded* comparator (40/1 µm input-pair sizing, not a target this repo inherits) measured ≈ 3.84 mV 3σ offset at `tt`/27 °C, N = 150 — same-PDK context that this target is achievable at *some* sizing, nothing more. **Verdict — meets target and stretch at every corner** (scored against the ratified bound per [DR-0002](decision-records/DR-0002-target-spec-ratification.md), scoring pass tracked as [#24](https://github.com/2AMLogic/gf180-comparator/issues/24); static preamp + StrongARM latch per [DR-0001](decision-records/DR-0001-comparator-topology.md)): [`sim/comparator-offset-mc/records/20260910-124917-4805118.md`](../sim/comparator-offset-mc/records/20260910-124917-4805118.md) reports nominal 3σ = 2.80063 mV at `tt_27c_3.30v`, and 2.796–2.807 mV 3σ at every one of the 45 corners of the PVT grid — best case `fs_-40c_2.97v` at 2.79617 mV, worst case `sf_125c_3.30v` at 2.80688 mV, corner-invariant to within 0.4% — so every corner clears the ≤ 15 mV target and the ≤ 8 mV stretch. Method per this repo's evidence rules: N = 200 mismatch-only draws per corner (`sw_stat_mismatch` models, global process swept by the corner axis), `setseed 20260909` held common across all corners (common random numbers), 1-sigma of input-referred offset reported alongside the 3-sigma value, statistical precision 1/√(2N) = 5.0 % at N = 200, run counts/seed/derivation committed in the record; the campaign's negative control is `sim/selftest.sh`'s `--sabotage-corners` loop.

**Scope of the number above (issue #157).** The DC-sweep bench measures the analog
partition only, so 2.80 mV 3σ is the preamplifier's offset and a **lower bound** on
total input-referred offset. It excludes the StrongARM decision stage, which has no DC
operating point, and the `ppolyf_u_1k` load-pair mismatch (the PDK hard-sets `mis_r = 0`).
The additive bench that closes both,
[`sim/comparator-offset-tran/`](../sim/comparator-offset-tran/README.md), is a
whole-comparator transient Monte Carlo (preamp + StrongARM latch + SR latch) with
N = 200 draws per PVT point and seed 20260909 (the same seed as the DC bench). Its first
record ran a **reduced grid** (tt/ss/ff × −40/27/125 °C at 3.3 V, 9 points, kept as history); the
full 45-point grid is now measured and is the **current reference** (below). The
latch term is paired, measured on the same draw. On top of that it adds a
**derived, not simulated** load-R hand budget: σ(ΔR/R)_pair = A_R/√(WL) = 0.19 %,
from the foundry's commented-out `ppolyf_u` `par_r = 0.021 µm`. The scored variant
uses a 3× conservative A_R.

**Earlier campaign (historical, superseded by the full 45-point grid below): nine-point measured total** ([`sim/comparator-offset-tran/records/20261010-013540611508-4a4df37.md`](../sim/comparator-offset-tran/records/20261010-013540611508-4a4df37.md), fleet job `klt-sim-816fb60826f4`):

| 3σ input-referred offset (earlier nine-point run) | `tt_27c_3.30v` | 9-point range |
|---|---|---|
| DC bench, preamp only (record above) | 2.801 mV | 2.796–2.807 mV |
| whole comparator, simulated | 2.897 mV | 2.897–3.439 mV |
| **whole comparator + conservative load-R budget (scored)** | **3.146 mV** | **3.146–3.725 mV** (worst `ff_125c_3.30v`) |

The latch contribution, as a paired 1σ, is 0.333 mV at nominal and
0.203–0.608 mV across the grid. It is largest hot and fast, where the preamp gain
is lowest. The load-R term is 0.136 mV 1σ at nominal (0.409 mV conservative).
**The total is within the ≤ 15 mV target and the ≤ 8 mV stretch at 9/9 points**, so
the verdict above stands with the latch and load-R terms included. Not covered by that nine-point record:
fs/sf and the ±10 % supply points (now covered, below), and
layout-induced systematic offset (schematic DUT). The ratified bound is unchanged.

**Current reference: full 45-point grid** (issue #200;
[`sim/comparator-offset-tran/records/20261010-021500046481-d84e59d.md`](../sim/comparator-offset-tran/records/20261010-021500046481-d84e59d.md),
fleet jobs `klt-sim-ee7ad68415d2`, `klt-sim-a503009e268a`, `klt-sim-031f74d456a0`;
tt/ss/ff/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V, 45 points × N = 200, no failed unit):
the scored total (simulated whole-comparator mismatch **plus the derived, not simulated,
conservative load-R budget**) is **2.994–3.795 mV 3σ, worst `ff_125c_3.63v`**, within the ≤ 15 mV
target and the ≤ 8 mV stretch at **45/45** points; the purely simulated whole-comparator 3σ
is 2.808–3.515 mV, the paired latch 1σ 0.184–0.659 mV, the derived load-R 1σ (3×) 0.342–0.501 mV.
The ratified bound is unchanged. Item-5 scoring now uses this record for the offset row
(the preamp-only DC value stays as a separate diagnostic); the item-6 yield citation is
still the preamp-only DC samples (see `signoff/README.md`).

## Input-referred noise

Target: ≤ 1.0 mV rms, differential — Stretch: ≤ 0.6 mV rms, differential

ngspice `.noise` on the preamplifier with the latch held in reset, **total integrated output noise divided by measured DC gain** — the exact methodology of `gf180-sar-adc`'s [`sim/comparator-preamp-noise/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-preamp-noise), whose own record documents a prior 200×-magnitude unit error from reporting ngspice's raw `sqrt(onoise_total)` directly instead of dividing by gain — this repo's future noise testbench applies the same divide-by-gain step and the same units caution. `gf180-sar-adc`'s embedded comparator measured ≈ 0.08–0.13 mV rms at its own sizing — same-PDK context on achievable magnitude, not a ported value. **First measurement of this repo's own design** ([DR-0001](decision-records/DR-0001-comparator-topology.md)): [`sim/comparator-preamp-noise/records/20260910-125200-4805118.md`](../sim/comparator-preamp-noise/records/20260910-125200-4805118.md) reports 91.25 µV rms at nominal, 128.8 µV rms worst-case across the grid (66.82 µV best-case `ss_-40c_2.97v` to 128.83 µV worst-case `ff_125c_3.63v`; the record's pass/fail column is PASS at all 45 corners). **Verdict — meets target and stretch at every corner** (scored against the ratified bound per [DR-0002](decision-records/DR-0002-target-spec-ratification.md), scoring pass tracked as [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)): the worst-case corner clears the ≤ 1.0 mV rms target 7.8× and the ≤ 0.6 mV rms stretch 4.7×.

## Decision time vs. overdrive

Target: ≤ 1.5 ns at 50 mV overdrive, 3.3 V — Stretch: ≤ 0.8 ns at 50 mV overdrive

Transient decision-time-vs-overdrive sweep, methodology mirroring `gf180-sar-adc`'s [`sim/comparator-regeneration/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-regeneration) (schematic-level sweep, plus a separate bespoke extracted-netlist script for post-layout margin once layout exists here). `gf180-sar-adc`'s DR-0015 provided the topology-class rationale this repo's own [DR-0001](decision-records/DR-0001-comparator-topology.md) re-derives independently. **First measurement of this repo's own design**: [`sim/comparator-regeneration/records/20260910-125206-4805118.md`](../sim/comparator-regeneration/records/20260910-125206-4805118.md) reports 0.708 ns at nominal (`tt_27c_3.30v` 0.708061 ns), 0.464–1.237 ns across the grid (worst-case `ss_125c_2.97v`) — meets the target at every corner, misses the ≤ 0.8 ns stretch at 16 of 45 corners (slow/hot/low-supply slices of the grid). **Post-layout measurement** (#23): [`sim/comparator-regeneration/records/20261002-202641-baeffe5.md`](../sim/comparator-regeneration/records/20261002-202641-baeffe5.md) — the parasitic-extracted DUT (offset-referred ladder, per the methodology mirroring noted above) reports 1.158 ns at nominal (+63.6 % over schematic) and 2.034 ns worst-case at `ss_125c_2.97v` — the post-layout decision time MISSES this row's 1.5 ns target at 7 of 45 corners (1.553–2.034 ns, all slow/hot/low-supply; nominal 1.15807 ns stays inside), and the record's delta table documents the systematic layout trip-point offset (−1.8 to −21.6 mV across PVT) the extraction's routing asymmetry introduces. **Verdict — misses the ratified target at 7 of 45 post-layout corners; recorded miss, accepted as known at ratification** (scored against the ratified bound per [DR-0002](decision-records/DR-0002-target-spec-ratification.md), scoring pass tracked as [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)): the schematic record meets the ≤ 1.5 ns target at all 45 corners (worst 1.237 ns) but misses the ≤ 0.8 ns stretch at 16 of 45; the post-layout record misses the ≤ 1.5 ns target at 7 of 45 corners (worst 2.034 ns) and the ≤ 0.8 ns stretch at 44 of 45 — the known gap DR-0002's Option A accepted at ratification ("accept the gap, record it as known", per that record's Consequences); this verdict records the miss against the ratified bound and relaxes nothing.

## Kickback

Target: ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge — Stretch: ≤ 2 mV

Drive the input nodes from a floating, high-impedance bias through a realistic RC (not an ideal voltage source, which would falsely report ≈ 0 kickback) — the methodology of `gf180-sar-adc`'s [`sim/comparator-kickback/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-kickback). That repo's own preamp-isolated topology (per DR-0015) measured a near-zero kickback residual — same-PDK context that a preamp-ahead-of-latch topology *can* hit this bound, not evidence this repo's own topology will at its own sizing. **First measurement of this repo's own design** ([DR-0001](decision-records/DR-0001-comparator-topology.md)): [`sim/comparator-kickback/records/20260910-125341-4805118.md`](../sim/comparator-kickback/records/20260910-125341-4805118.md) reports 7.60 mV at nominal (`tt_27c_3.30v` 7.59853 mV), 4.53–10.01 mV across the grid (`kick_1k_peak_mv`, best `ss_-40c_2.97v`, worst `sf_-40c_3.63v`) — misses the ≤ 5 mV target at 44 of 45 corners and the ≤ 2 mV stretch at every corner; named in DR-0001 as the gap most likely to need revisiting first. **Post-layout measurement** (#23): [`sim/comparator-kickback/records/20261002-211343-6346fad.md`](../sim/comparator-kickback/records/20261002-211343-6346fad.md) — the parasitic-extracted DUT reports 10.03 mV at nominal (+32 % over schematic) and 8.49–14.58 mV across the grid: exactly the worsening-not-improving direction `design/README.md`'s parasitic asymmetry note predicts (input-node routing capacitance adds to the injected charge). Recorded as data per that note's own instruction — the record's delta table carries the full schematic-vs-extracted comparison. **Verdict — misses the ratified target at every post-layout corner (and at 44 of 45 schematic corners); recorded miss, accepted as known at ratification** (scored against the ratified bound per [DR-0002](decision-records/DR-0002-target-spec-ratification.md), scoring pass tracked as [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)): post-layout `kick_1k_peak_mv` spans 8.49–14.58 mV (nominal 10.03 mV, +32 % over schematic), so all 45 post-layout corners exceed the ≤ 5 mV target and every corner of both records exceeds the ≤ 2 mV stretch — the known gap DR-0002's Option A accepted at ratification ("accept the gap, record it as known", per that record's Consequences); this verdict records the miss against the ratified bound and relaxes nothing. **Node coverage (#160)**: every kickback record cited above measures the positive 1 kohm input node only (partial node coverage). The bench now also measures the negative node and scores the row-facing peak as the maximum of both (see `sim/comparator-kickback/README.md`); the both-node schematic 45-corner record is [`sim/comparator-kickback/records/20261010-022609774981-bf851ec.md`](../sim/comparator-kickback/records/20261010-022609774981-bf851ec.md) (positive node sets the aggregate at 45/45 corners, negative node 4.24-9.91 mV vs positive 4.53-10.01 mV; 1/45 within target, 0/45 within stretch; no bound changed), and extracted both-node evidence remains PENDING as a further follow-up. No cited number above is reinterpreted.

## Supply / power

Target: 3.3 V ±10% (`nfet_03v3`/`pfet_03v3`); ≤ 1 mW average, one decision per clock edge at a stated clock rate (TBD) — Stretch: ≤ 500 µW average

Device-flavor axis settled directly against the installed model file: gf180mcu ships exactly `nfet_03v3`/`pfet_03v3`, `nfet_05v0`/`pfet_05v0`, `nfet_06v0`/`pfet_06v0` (plus `_dss`/`_nvt` variants) — no sub-3.3 V core flavor exists in this PDK at all, per `gf180-sar-adc`'s [DR-0004](https://github.com/2AMLogic/gf180-sar-adc/blob/main/spec/decision-records/DR-0004-device-flavor.md), which greps that file directly. This corroborates this repo's own `CLAUDE.md` ("3.3 V primary; 5 V flavor only via decision record," the same rail discipline as `gf180-opamp`) independently. Power bound (≤ 1 mW target, ≤ 500 µW stretch) is first-principles engineering judgment, matching the twin set's convention. **First measurement of this repo's own design** ([DR-0001](decision-records/DR-0001-comparator-topology.md)): [`sim/comparator-regeneration/records/20260910-125206-4805118.md`](../sim/comparator-regeneration/records/20260910-125206-4805118.md) reports a 28.5 µA mean static current (27.7–29.7 µA across the grid; nominal `tt_27c_3.30v` 28.447 µA ≈ 93.9 µW at 3.3 V). **Verdict — static power meets target and stretch at every corner; the average-power bound as written is not fully scored** (scored against the ratified bound per [DR-0002](decision-records/DR-0002-target-spec-ratification.md), scoring pass tracked as [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)): the measured static current alone sits ≈ 10× inside the ≤ 1 mW target and ≈ 5× inside the ≤ 500 µW stretch at every corner, but the ratified bound is *average* power for one decision per clock edge at a stated clock rate — that rate is still TBD in this row, so the dynamic (per-decision switching) component is not covered by this static measurement and no clock rate is invented here; choosing one is a spec change requiring a decision record per [`spec/README.md`](README.md).
