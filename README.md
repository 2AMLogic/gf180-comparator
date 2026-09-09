# gf180-comparator

A dynamic latched comparator on GF180MCU on
[GlobalFoundries GF180MCU](https://github.com/google/gf180mcu-pdk), a 180 nm open CMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: just opened.** Nothing is designed yet. The first work is
the offset methodology — gf180mcu ships Monte-Carlo mismatch models, so the first result is the MC offset study at 3.3 V.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using this PDK, not just this repo.

## Why this block, on this PDK

gf180-sar-adc already embeds a comparator that has never been specified
standalone; this repo characterizes the decision element for its own sake —
offset, noise, metastability, kickback — on the catalog's most mature PDK,
as the gf180 twin of sg13g2-comparator (same benches, same spec structure,
opened together).

GF180MCU ships statistical mismatch models, so the offset story here is the
strong version: Monte-Carlo sigma with run counts and seeds committed. The
existing SAR's behavior is context, not a source — this repo derives its own
numbers from the models.

## Verification harness

Every row of the table below has a testbench, a committed PVT corner matrix,
and a one-command way to reproduce it — see [`sim/`](sim/).

```bash
python3 sim/run_corners.py --check-env   # PDK, pinned toolchain, DUT contract
./sim/characterize.sh smoke              # every bench, nominal point, seconds
./sim/characterize.sh characterize       # the full 45-point PVT campaign
./sim/selftest.sh                        # the harness's own acceptance test
```

**No measured result exists for this block's own comparator yet.** The
topology is not decided — that is [`spec/porting-plan.md`](spec/porting-plan.md)
next step 1 — so `sim/dut.json` binds a loudly-labelled *placeholder* DUT and
every committed record carries a banner saying its numbers substantiate the
harness rather than a spec row. Swapping in the real netlist once it exists is
a one-line edit; see [`sim/dut/README.md`](sim/dut/README.md).

## Target specification (DRAFT — engineering to ratify)

No decision record has ratified this table yet — these are original
engineering-judgment bounds for the gf180mcu 3.3 V rail, each row stating its
own basis, not a value inherited from any sibling. See
[`spec/porting-plan.md`](spec/porting-plan.md) for what *does* transfer
(testbench/measurement methodology and same-PDK device-flavor facts, not
topology, sizing, or spec numbers) from
[`gf180-sar-adc`](https://github.com/2AMLogic/gf180-sar-adc)'s embedded
comparator, and [`spec/README.md`](spec/README.md) for when a decision record
is required to move a row out of DRAFT.

| Parameter | Target | Stretch | Basis |
|---|---|---|---|
| Offset sigma | ≤ 15 mV, 3σ (input-referred, post-calibration-free) | ≤ 8 mV, 3σ | Monte Carlo via gf180mcu's `sw_stat_mismatch`-based local-mismatch models (per-instance statistical mismatch, confirmed real and present on this PDK — not just global-process corners — by `gf180-sar-adc`'s [`sim/comparator-offset-mc/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-offset-mc): `setseed <n>` then N = 150 draws per PVT point via a `dowhile` reset loop). This repo has no schematic yet, so no measurement exists; the bound matches the sg13g2-comparator/sky130-comparator twin set so the three PDKs' eventual measured results are directly comparable, not because it was independently re-derived per PDK. `gf180-sar-adc`'s own *embedded* comparator (40/1 µm input-pair sizing, not a target this repo inherits) measured ≈ 3.84 mV 3σ offset at `tt`/27 °C, N = 150 — same-PDK context that this target is achievable at *some* sizing, nothing more. |
| Input-referred noise | ≤ 1.0 mV rms, differential | ≤ 0.6 mV rms, differential | ngspice `.noise` on the preamplifier with the latch held in reset, **total integrated output noise divided by measured DC gain** — the exact methodology of `gf180-sar-adc`'s [`sim/comparator-preamp-noise/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-preamp-noise), whose own record documents a prior 200×-magnitude unit error from reporting ngspice's raw `sqrt(onoise_total)` directly instead of dividing by gain — this repo's future noise testbench applies the same divide-by-gain step and the same units caution. `gf180-sar-adc`'s embedded comparator measured ≈ 0.08–0.13 mV rms at its own sizing — same-PDK context on achievable magnitude, not a ported value. |
| Decision time vs. overdrive | ≤ 1.5 ns at 50 mV overdrive, 3.3 V | ≤ 0.8 ns at 50 mV overdrive | Transient decision-time-vs-overdrive sweep, methodology mirroring `gf180-sar-adc`'s [`sim/comparator-regeneration/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-regeneration) (schematic-level sweep, plus a separate bespoke extracted-netlist script for post-layout margin once layout exists here). No measurement exists yet in this repo; the slow/cold corner is expected to be the binding case, consistent with the topology rationale in `gf180-sar-adc`'s [DR-0015](https://github.com/2AMLogic/gf180-sar-adc/blob/main/spec/decision-records/DR-0015-comparator-topology.md), and is open work here too. |
| Kickback | ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge | ≤ 2 mV | Drive the input nodes from a floating, high-impedance bias through a realistic RC (not an ideal voltage source, which would falsely report ≈ 0 kickback) — the methodology of `gf180-sar-adc`'s [`sim/comparator-kickback/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-kickback). That repo's own preamp-isolated topology (per DR-0015) measured a near-zero kickback residual — same-PDK context that a preamp-ahead-of-latch topology *can* hit this bound, not evidence this repo's own (not-yet-chosen) topology will. |
| Supply / power | 3.3 V ±10% (`nfet_03v3`/`pfet_03v3`); ≤ 1 mW average, one decision per clock edge at a stated clock rate (TBD) | ≤ 500 µW average | Device-flavor axis settled directly against the installed model file: gf180mcu ships exactly `nfet_03v3`/`pfet_03v3`, `nfet_05v0`/`pfet_05v0`, `nfet_06v0`/`pfet_06v0` (plus `_dss`/`_nvt` variants) — no sub-3.3 V core flavor exists in this PDK at all, per `gf180-sar-adc`'s [DR-0004](https://github.com/2AMLogic/gf180-sar-adc/blob/main/spec/decision-records/DR-0004-device-flavor.md), which greps that file directly. This corroborates this repo's own `CLAUDE.md` ("3.3 V primary; 5 V flavor only via decision record," the same rail discipline as `gf180-opamp`) independently. Power bound (≤ 1 mW target, ≤ 500 µW stretch) is first-principles engineering judgment, matching the twin set's convention — no dynamic-latch design exists yet in this repo to measure quiescent/dynamic current. |

**Statistical basis, stated once for the table.** gf180mcu's `sw_stat_mismatch`
local-mismatch models enable real per-instance device-mismatch draws (not a
global-process-only fallback) — the "strong" statistical story this repo's
own `CLAUDE.md` calls the headline result is available on this PDK, confirmed
by `gf180-sar-adc`'s own Monte-Carlo offset methodology
(`sim/comparator-offset-mc/`, N = 150 draws/corner). No Monte Carlo run exists
yet for *this* repo's own (not-yet-designed) comparator; the offset row's
basis column states the methodology this repo commits to using once a
schematic exists.

**Numeric consistency across the twin set.** The Target/Stretch bounds above
match `sg13g2-comparator` and `sky130-comparator` (≤ 15 mV / ≤ 8 mV 3σ offset;
≤ 1.0 / ≤ 0.6 mV rms noise; ≤ 1.5 ns / ≤ 0.8 ns decision time at 50 mV
overdrive; ≤ 5 mV / ≤ 2 mV kickback into 1 kΩ) by deliberate choice, so the
three twins' eventual *measured* results are directly comparable — the whole
point of a twin set. `gf180-sar-adc`'s embedded-comparator numbers cited in
the Basis column are same-PDK context showing these targets are achievable at
*some* sizing, not inherited values; this repo's own sizing and measurement
are original work (see `spec/porting-plan.md`).

**Ratification status.** This table stays **DRAFT** in this pass — no
decision record is filed for it yet. `spec/README.md` documents when a DR is
required (whenever this table is set, changed, or scoped) and how to write
one. See [issue #3](https://github.com/2AMLogic/gf180-comparator/issues/3)
for the honest artifact-presence checklist this table's DRAFT status feeds
(full PVT corner sim vs. a *ratified* spec is blocked on this table's
ratification).

## License

Apache-2.0.
