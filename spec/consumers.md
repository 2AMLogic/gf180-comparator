# Consumers — who consumes this block, and what they require

This repo's consumers are part of its spec. 2am cross-cutting rule 9
([`2AMLogic/2am` `REUSE.md` §"Adopt or record"](https://github.com/2AMLogic/2am/blob/main/REUSE.md),
ratified 2am#899, widened 2026-09-21 to same-PDK sub-blocks) puts it directly:
*"For the primitive repo: its consumers are its spec... Name the consumers,
carry their requirement rows in the spec, and publish what an integrator
takes — the cell, its port list, the netlist and GDS paths, measured area,
maturity rung — as structured data rather than README prose."* This file is
that Consumers section; the structured-data half lives at
[`manifests/integrator.json`](../manifests/integrator.json).

## The mechanism (how rows appear here)

A repo becomes a consumer of this block exactly when
[`2AMLogic/2am` `repos.yml`](https://github.com/2AMLogic/2am/blob/main/repos.yml)
records a `consumes: [gf180-comparator]` edge on it — rule 9's adopt-or-record
trigger is **same-PDK only**, so cross-PDK SAR repos (`sky130-sar-adc`, any
sg13g2 ADC) are never consumers of this block. Each new edge adds a new
section below with one row per requirement the consumer imposes. "Unknown" is
a legitimate row value (the consumer states no bound); an unnamed consumer or
an unstamped row is not.

**Today exactly one repo records that edge** (verified by live API read of
`repos.yml` @ `79b7cc6`, 2026-09-22): `gf180-sar-adc` — entry comment:
*"carries its own in-tree comparator with the SAME port list - adopt-or-record,
see REUSE.md"*. No other repo names this block as a consumption edge.

The adopt-or-record *decision* itself (the `reuse.lock.json` `in_tree` entry,
`status: evaluate` → `adopting`/`kept`) lives in **the consumer's repo**, per
REUSE.md ("the lock file lives in the owning repo"). This section publishes
what makes that evaluation answerable from here; it does not file or edit the
consumer's ledger.

## gf180-sar-adc — gf180mcu 10-bit SAR ADC canary

[`gf180-sar-adc`](https://github.com/2AMLogic/gf180-sar-adc) (same PDK, same
3.3 V rail) embeds its own comparator as a core subblock and is evaluating
this block as a replacement under rule 9. Every consumer fact below was
verified by live read at commit `773f906` on 2026-09-22; this repo's own
values are at `5649686` (the commit this file landed against).

| Requirement | Consumer's value (gf180-sar-adc @ `773f906`) | This block (@ `5649686`) | Verdict |
|---|---|---|---|
| Port list | `.subckt comparator vinp vinn clk ibias dout doutb vdd vss` — [`design/comparator/comparator.spice:111`](https://github.com/2AMLogic/gf180-sar-adc/blob/773f9063900566f6e98edebedc3501c112bdf332/design/comparator/comparator.spice#L111) | `.subckt comparator_dut vinp vinn clk ibias dout doutb vdd vss` — `design/comparator.spice:24` | **Meets** — pin-for-pin identical in name and order (8 pins; only the subckt name differs). Drop-in at the netlist interface; directions/meanings in [`manifests/integrator.json`](../manifests/integrator.json). |
| Rails | `V_DD = 3.3 V ±10 %` (2.97/3.30/3.63 V grid), single supply, 3.3 V devices throughout — top-level README supply row, [DR-0004](https://github.com/2AMLogic/gf180-sar-adc/blob/773f9063900566f6e98edebedc3501c112bdf332/spec/decision-records/DR-0004-device-flavor.md) | Same: 3.3 V ±10 %, `nfet_03v3`/`pfet_03v3`, ratified supply row (`README.md` target-spec table) | **Meets** — identical rail discipline. |
| Input common-mode range | Constant `V_cm = V_REF/2 = 1.65 V` (DR-0006 switching scheme; budget memo §1: "The comparator's input common mode is constant at `V_cm = 1.65 V`"; README `V_CM` row, DR-0026) | Front end specified at `dut_vcm = 1.65 V` (`sim/dut.json` params; DR-0001 — mid-rail standalone, `VDD/2` at nominal) | **Meets at the operating point** — same 1.65 V. This block's CMRR over the consumer's ±100 mV `V_CM` window (their CMRR row) is **Unknown**: no CMRR row exists in this repo's ratified target-spec table. |
| Decision speed / clock rate | One decision per decide phase: **31.25 ns** @ 1 MS/s ratified, **15.625 ns** @ 2 MS/s stretch (16× clock: 16/32 MHz — budget memo §6, DR-0003, README rate/clock rows); their own measured worst decision delay 863 ps @ **half-LSB overdrive (1.61 mV)** | Standalone ratified row (unchanged): ≤ 1.5 ns at 50 mV overdrive; measured 0.708 ns nominal, 1.237 ns worst (`ss_125c_2.97v`). Delay at the **consumer's overdrive basis** is taken from the same regeneration ladder, 45-corner grid: **1 mV** rung, schematic — 0.904 ns nominal, **1.673 ns worst** (`ss_125c_2.97v`), `sim/comparator-regeneration/records/20260910-125206-4805118.md`; post-layout extracted — 1.481 ns nominal, **2.716 ns worst** (`ss_125c_2.97v`), `.../20261002-202641-baeffe5.md` | **Meets on measurement, conditional on the stated basis** (not on the 50 mV row, which alone cannot support a half-LSB verdict). Worst 2.716 ns (extracted) / 1.673 ns (schematic) at 1 mV vs the 15.625 ns binding (stretch-rate) phase: ≥ 5.7× margin. Basis and assumptions: (1) **Inference, not a direct 1.61 mV measurement.** Decision delay is monotone non-increasing in overdrive (regeneration model `t = t0 + τ·ln(V_logic/(A·V_in))`; observed ordered `td_od50 < td_od1 < td_od01` at all 90 corner points of the two records), so `td(1.61 mV) ≤ td(1 mV)` and the 1 mV worst case bounds the consumer's 1.61 mV conservatively. The even-smaller 0.1 mV rung (worst 1.956 ns schematic / 3.190 ns extracted) also fits the phase, so the conclusion is not sensitive to the exact overdrive. (2) **Offset-referred timing.** Each delay is measured at the stated overdrive *above the comparator's own trip point* (schematic: mismatch-free, trip point 0 V; extracted: ladder centred on the per-corner probed `dut_vos`, −1.8 to −21.6 mV). It is the delay after the input has crossed the trip point by 1 mV, **not** a guarantee for a given input code: **no uncalibrated total-error guarantee is made** — an input within the offset band of the trip point (3σ mismatch 2.8 mV measured, plus the extraction's systematic offset) can resolve the wrong way, and that is the Offset row's subject, not this one. A half-LSB overdrive is only realized after the offset is calibrated/trimmed or absorbed by the consumer's error budget. (3) **Scope.** Delay is clock-rise to output 0.5·VDD crossing from the supply-normalized deck; it excludes the consumer's reset/precharge, comparator-to-logic path and phase-allocation of the 15.625 ns, which this repo does not know. (4) The consumer values are as read at `773f906` (2026-09-22), not necessarily its latest state. A direct ~1.61 mV rung was **not** run — the inference above suffices; adding one is a bench change only if (1) is challenged. The DR-0004 cascode experiment record (`20261008-235219317743-7e61c52`) is a non-active experiment netlist and is not used here. |
| Offset | ≤ **2 LSB** untrimmed, 3σ mismatch (README offset-error row @ `773f906`); `LSB_se = V_REF/1024 = 3.2227 mV` → **2 LSB = 6.4453 mV 3σ** (budget memo §1; `V_REF = 3.3 V` per DR-0002) | Ratified target ≤ 15 mV 3σ; **measured 2.796–2.807 mV 3σ at every one of the 45 corners** (`sim/comparator-offset-mc/records/20260910-124917-4805118.md`, scored vs the ratified row per #24) | **Meets on measurement** — 2.807 mV ≤ 6.4453 mV at every corner. The ratified 15 mV *bound* alone would not demonstrate this; the measured corner population does. Scope: that number is the preamp-only (DC-sweep) offset, a lower bound on the total. The **whole-comparator total** includes the latch (measured) and a conservative load-resistor hand budget (derived, not simulated). It is **2.994–3.795 mV 3σ over all 45 PVT points** (`sim/comparator-offset-tran/records/20261010-021500046481-d84e59d.md`, #200; the earlier nine-point record 3.146–3.725 mV stays as history), so it also meets the 6.4453 mV budget, with 1.70× margin at the binding corner `ff_125c_3.63v`. Caveat: the load-resistor term is derived, not simulated; schematic DUT, one seed. |
| Noise | Comparator's allocated share of the total input-referred noise budget: ≤ **0.930 mV rms** (ratified ENOB > 9.0), ≤ **0.537 mV rms** (stretch ENOB > 9.5) — budget memo §1/§2, three-equal-power split of the non-quantization budget | Ratified ≤ 1.0 mV rms differential; measured 91.25 µV rms nominal, 128.8 µV rms worst over the grid — `sim/comparator-preamp-noise/records/20260910-125200-4805118.md` | **Meets on measurement** — worst 128.8 µV rms is inside even the stretch allocation (537 µV), ~4× under the ratified share (930 µV). |
| Area budget | **Unknown** — no comparator-specific area bound is stated anywhere in that repo: `spec/comparator-budget-memo.md` @ `773f906` treats area only qualitatively (offset-vs-area Pelgrom tradeoffs), DR-0015 @ `773f906` states tradeoffs with no µm² bound, and the only stated area budget is the whole-ADC block (`< 0.16 mm²`, DR-0024, proposed) | Measured 20 596 µm² (0.0206 mm²) placed — derivation in [`manifests/integrator.json`](../manifests/integrator.json) | **Unknown** (consumer states no bound; nothing to meet or miss). |

### Same block class, not a different block — stated once, by name

Both comparators are the **same class, same port list, sized twice for
different budgets** — not different shapes. Each is a static differential
preamplifier into a StrongARM latch with isolation inverters and a NOR SR
output latch: this repo's
[DR-0001](decision-records/DR-0001-comparator-topology.md) @ `5649686` and
`gf180-sar-adc`'s
[DR-0015](https://github.com/2AMLogic/gf180-sar-adc/blob/773f9063900566f6e98edebedc3501c112bdf332/spec/decision-records/DR-0015-comparator-topology.md)
@ `773f906` decide the identical topology class independently. The sizing
differs because the budgets differ: theirs is sized for the ADC's
CDAC-driven constant 1.65 V common mode against LSB-referred offset/noise
allocations (40/1 µm pair, 150 kΩ loads, `A_v ≈ 16`); this one is sized
mid-rail standalone against the twin-set target table (which lands on the
same 1.65 V operating point, for a different stated reason). Recorded here
once so no reader re-derives it.

### Findings about the consumer's block

Findings about `gf180-sar-adc`'s embedded comparator are filed **on that
repo**, per this repo's cross-pollination protocol (`CLAUDE.md`; the
`sky130-sar-adc#346` pattern) — this section records *their* requirements,
not defects in their block.
