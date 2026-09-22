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
| Decision speed / clock rate | One decision per decide phase: **31.25 ns** @ 1 MS/s ratified, **15.625 ns** @ 2 MS/s stretch (16× clock: 16/32 MHz — budget memo §6, DR-0003, README rate/clock rows); their own measured worst decision delay 863 ps @ half-LSB overdrive | Ratified ≤ 1.5 ns at 50 mV overdrive; measured 0.708 ns nominal, 1.237 ns worst (`ss_125c_2.97v`) over the 45-corner grid — `sim/comparator-regeneration/records/20260910-125206-4805118.md` | **Meets** — worst measured 1.237 ns ≪ 15.625 ns binding (stretch-rate) phase. Overdrive bases differ (theirs ½ LSB = 1.61 mV, ours 50 mV), so per-overdrive margins are not directly comparable; the phase-budget comparison is the binding fact. |
| Offset | ≤ **2 LSB** untrimmed, 3σ mismatch (README offset-error row @ `773f906`); `LSB_se = V_REF/1024 = 3.2227 mV` → **2 LSB = 6.4453 mV 3σ** (budget memo §1; `V_REF = 3.3 V` per DR-0002) | Ratified target ≤ 15 mV 3σ; **measured 2.796–2.807 mV 3σ at every one of the 45 corners** (`sim/comparator-offset-mc/records/20260910-124917-4805118.md`, scored vs the ratified row per #24) | **Meets on measurement** — 2.807 mV ≤ 6.4453 mV at every corner. The ratified 15 mV *bound* alone would not demonstrate this; the measured corner population does. |
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
