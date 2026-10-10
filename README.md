# gf180-comparator

A dynamic latched comparator on GF180MCU on
[GlobalFoundries GF180MCU](https://github.com/google/gf180mcu-pdk), a 180 nm open CMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: schematic- and layout-level evidence is committed; the block is not yet T1.**
The design is a static differential preamplifier into a StrongARM latch
([`design/`](design/), decided in
[DR-0001](spec/decision-records/DR-0001-comparator-topology.md)), bound into
`sim/dut.json` as `comparator-dr0001` (`provenance: schematic`) with a
parasitic-extracted layout entry alongside. [`layout/`](layout/) holds the
GDS plus DRC, LVS, ERC and post-layout extraction evidence; the four corner-grid benches
under [`sim/`](sim/) have schematic records, and the regeneration
(decision-time) and kickback benches also have post-layout (extracted-DUT)
records; the
[target-specification table](#target-specification-ratified-via-dr-0002) is
ratified by
[DR-0002](spec/decision-records/DR-0002-target-spec-ratification.md)
(two-key ceremony on its re-ratification PR, per the operator ruling of
2026-10-02 on #3). The machine-graded tier verdict lives in
[`signoff/signoff-report.json`](signoff/signoff-report.json) (see
[`signoff/`](signoff/)) — read it, not this paragraph, for the current T1
state. Integrator data is in [`manifests/integrator.json`](manifests/integrator.json).
[DR-0004](spec/decision-records/DR-0004-preamp-input-cascode-kickback.md)
(status: proposed) would add an input cascode to close the kickback gap and
is not yet ratified; the table below reflects the ratified spec only.

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
numbers from the models. Integrators: [`manifests/integrator.json`](manifests/integrator.json)
publishes what this block takes and exposes (consumer requirement rows:
[`spec/consumers.md`](spec/consumers.md)).

## Verification harness

Every row of the table below has a testbench, a committed PVT corner matrix,
and a documented way to reproduce it — see [`sim/`](sim/). `sim/` holds eight bench directories: four corner-grid benches
(`comparator-offset-mc`, `comparator-preamp-noise`, `comparator-regeneration`,
`comparator-kickback`) that `characterize.sh` runs, the fleet-only
`comparator-offset-tran` (whole-comparator offset evidence), the
supplemental, unscored `comparator-offset-cm-window` (no record yet) and its
monotonic-index variant `comparator-offset-cm-index` (unscored; complete
45-point record, verdict Unknown), and `comparator-offset-tran-extracted-feasibility`
(bounded, unscored, fleet-only feasibility probe; no record).

```bash
python3 sim/run_corners.py --check-env   # PDK, pinned toolchain, DUT contract
./sim/characterize.sh smoke              # the four corner-grid benches, nominal point, seconds
./sim/characterize.sh characterize       # their full 45-point PVT campaign
./sim/selftest.sh                        # the harness's own acceptance test
```

`characterize.sh` does **not** run `comparator-offset-tran`: it is not wired
into `run_corners.py` and is fleet-only. To reproduce its record (the
whole-comparator total-offset evidence), submit it to the Spot batch fleet:

```bash
KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-offset-tran --label "<text>"
```

Details and limits: [`sim/README.md`](sim/README.md#reproducing-one-record).
Do not hand-launch the grid on a shared worker.

**`sim/dut.json` now binds the real schematic** (`design/comparator.spice`,
`id: comparator-dr0001`, `provenance: schematic`) — see
[`spec/decision-records/DR-0001-comparator-topology.md`](spec/decision-records/DR-0001-comparator-topology.md)
for the topology decision and [`sim/dut/README.md`](sim/dut/README.md) for
the binding contract. The four corner-grid benches' new records carry no placeholder
banner; the earlier placeholder-DUT records remain committed (`sim/` is
append-only evidence) but are superseded as the current reference.

## Target specification (ratified via DR-0002)

This table is ratified against the measured results below by
[`spec/decision-records/DR-0002-target-spec-ratification.md`](spec/decision-records/DR-0002-target-spec-ratification.md)
(`Status: ratified`) — no numeric bound was changed by that record; it
ratified the existing bounds against the first measured result against every
row. Ratification is the two-key ceremony on the record's re-ratification
PR (non-author EE + market `RATIFY-KEY` reviews, `loom:auto-merge-ok`, and
the merge as the record), per the operator ruling of 2026-10-02 on #3 —
which also ruled the record's original 2026-09-19 flip (PR #27's merge)
was not the ratification act. These are
original engineering-judgment bounds for the gf180mcu 3.3 V rail, each row
stating its own basis, not a value inherited from any sibling. See
[`spec/porting-plan.md`](spec/porting-plan.md) for what *does* transfer
(testbench/measurement methodology and same-PDK device-flavor facts, not
topology, sizing, or spec numbers) from
[`gf180-sar-adc`](https://github.com/2AMLogic/gf180-sar-adc)'s embedded
comparator, and [`spec/README.md`](spec/README.md) for when a decision record
is required to set, change, or scope a row of this ratified table.

Per-row result narrative (records, per-corner numbers, scoring detail) lives in
[`spec/evidence-ledger.md`](spec/evidence-ledger.md), one section per row; the
Basis column keeps the method and the current verdict.

| Parameter | Target | Stretch | Basis |
|---|---|---|---|
| Offset sigma | ≤ 15 mV, 3σ (input-referred, post-calibration-free) | ≤ 8 mV, 3σ | Monte Carlo via gf180mcu's `sw_stat_mismatch` local-mismatch models: N = 200 mismatch-only draws per corner, `setseed 20260909` common across all 45 corners, 1σ reported alongside 3σ, precision 1/√(2N) = 5.0 %; bound matches the sg13g2/sky130 twin set. **Verdict — meets target and stretch at every corner** (2.796–2.807 mV 3σ; nominal 2.80063 mV). Scope: DC-sweep, preamp-only (a lower bound). **Whole-comparator total** (additive bench `sim/comparator-offset-tran/`, #157): transient MC on the full 45-point PVT grid (tt/ss/ff/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V), N = 200 draws per point, seed 20260909, with the latch measured and a conservative load-R hand budget (derived, not simulated). The scored total is **3.146 mV 3σ at nominal `tt_27c_3.30v` and 2.994–3.795 mV across all 45 points (binding corner `ff_125c_3.63v`); meets target and stretch at 45/45**. The purely simulated whole-comparator mismatch alone is 2.808–3.515 mV 3σ; the load-R term is added on top as a derived budget. The latch adds a paired 0.184–0.659 mV 1σ. Schematic DUT, single seed; no extracted-layout or layout-systematic offset is claimed. The earlier nine-point reduced-grid run (3.146–3.725 mV, 9/9) is history. Record, methodology provenance and negative control: [ledger](spec/evidence-ledger.md#offset-sigma). |
| Input-referred noise | ≤ 1.0 mV rms, differential | ≤ 0.6 mV rms, differential | ngspice `.noise` on the preamplifier with the latch held in reset, total integrated output noise **divided by measured DC gain** (the `gf180-sar-adc` `sim/comparator-preamp-noise/` methodology and units caution). **Verdict — meets target and stretch at every corner** (91.25 µV rms nominal, 128.8 µV rms worst case; worst case clears target 7.8× and stretch 4.7×; scoring pass [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)). Records and provenance: [ledger](spec/evidence-ledger.md#input-referred-noise). |
| Decision time vs. overdrive | ≤ 1.5 ns at 50 mV overdrive, 3.3 V | ≤ 0.8 ns at 50 mV overdrive | Transient decision-time-vs-overdrive sweep mirroring `gf180-sar-adc`'s `sim/comparator-regeneration/` (schematic, plus extracted post-layout). **Verdict — misses the ratified target at 7 of 45 post-layout corners (worst 2.034 ns); recorded miss, accepted as known at ratification** per [DR-0002](spec/decision-records/DR-0002-target-spec-ratification.md) Option A (schematic meets target at all 45 corners, worst 1.237 ns; stretch missed at 16 of 45 schematic and 44 of 45 post-layout corners; scoring pass [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)). Relaxes nothing. Records and delta detail: [ledger](spec/evidence-ledger.md#decision-time-vs-overdrive). |
| Kickback | ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge | ≤ 2 mV | Floating high-impedance bias through a realistic RC, never an ideal source (`gf180-sar-adc` `sim/comparator-kickback/` methodology). **Verdict — misses the ratified target at every post-layout corner (and at 44 of 45 schematic corners); recorded miss, accepted as known at ratification** per [DR-0002](spec/decision-records/DR-0002-target-spec-ratification.md) Option A (post-layout 8.49–14.58 mV, nominal 10.03 mV; schematic 4.53–10.01 mV, nominal 7.60 mV; stretch missed everywhere in both records; scoring pass [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)). Relaxes nothing. Records and delta detail: [ledger](spec/evidence-ledger.md#kickback). |
| Supply / power | 3.3 V ±10% (`nfet_03v3`/`pfet_03v3`); ≤ 1 mW average, one decision per clock edge at a stated clock rate (TBD) | ≤ 500 µW average | Rail settled against the installed model file (only `nfet_03v3`/`pfet_03v3`, `_05v0`, `_06v0` flavors (plus `_dss`/`_nvt` variants) exist; no sub-3.3 V core flavor); power bound is first-principles judgment matching the twin set. **Verdict — static power meets target and stretch at every corner; the average-power bound as written is not fully scored** (28.5 µA mean static current, ≈ 93.9 µW nominal; the clock rate is still TBD and no rate is invented here — choosing one needs a decision record per [`spec/README.md`](spec/README.md); scoring pass [#75](https://github.com/2AMLogic/gf180-comparator/issues/75)). Records and provenance: [ledger](spec/evidence-ledger.md#supply--power). |

**Statistical basis, stated once for the table.** gf180mcu's `sw_stat_mismatch`
local-mismatch models enable real per-instance device-mismatch draws (not a
global-process-only fallback) — the "strong" statistical story this repo's
own `CLAUDE.md` calls the headline result is available on this PDK, confirmed
by `gf180-sar-adc`'s own Monte-Carlo offset methodology
(`sim/comparator-offset-mc/`, N = 150 draws/corner) and now realized by this
repo's own scored run: 200 mismatch-only draws per corner through the full
45-point grid, `setseed 20260909` held common across corners, scoring the
offset row at 2.796–2.807 mV 3σ (meets the ratified target and stretch at
every corner — see the offset row's Basis column, the evidence ledger, and
[#24](https://github.com/2AMLogic/gf180-comparator/issues/24)).

**Numeric consistency across the twin set.** The Target/Stretch bounds above
match `sg13g2-comparator` and `sky130-comparator` (≤ 15 mV / ≤ 8 mV 3σ offset;
≤ 1.0 / ≤ 0.6 mV rms noise; ≤ 1.5 ns / ≤ 0.8 ns decision time at 50 mV
overdrive; ≤ 5 mV / ≤ 2 mV kickback into 1 kΩ) by deliberate choice, so the
three twins' eventual *measured* results are directly comparable — the whole
point of a twin set. `gf180-sar-adc`'s embedded-comparator numbers cited in
the Basis column are same-PDK context showing these targets are achievable at
*some* sizing, not inherited values; this repo's own sizing and measurement
are original work (see `spec/porting-plan.md`).

**Ratification status.** This table is **ratified** by
[DR-0002](spec/decision-records/DR-0002-target-spec-ratification.md) — by
the two-key ceremony on the record's re-ratification PR
[#74](https://github.com/2AMLogic/gf180-comparator/pull/74) (non-author EE
key + market `RATIFY-KEY` reviews, `loom:auto-merge-ok`, and the merge as
the record), per the operator ruling of 2026-10-02 on
[issue #3](https://github.com/2AMLogic/gf180-comparator/issues/3), which
ruled the record's original 2026-09-19 flip on PR #27's merge was **not**
the ratification act. The record ratified every row's
existing bound against the measured results above — including two rows,
decision time and kickback, that carry a known gap at some or all PVT
corners, where approving the record as drafted enacted the "accept the gap,
record it as known" option (a bound revision would have required rejecting
or amending that PR, and no such revision was made). Per-row scored verdicts
have now landed in each row's Basis column (full narrative in the evidence ledger): the offset-sigma row (meets target
and stretch at every corner,
[#24](https://github.com/2AMLogic/gf180-comparator/issues/24)) and the four
remaining rows scored in
[#75](https://github.com/2AMLogic/gf180-comparator/issues/75) — input-referred
noise: meets target and stretch at every corner; decision time: misses the
target at 7 of 45 post-layout corners and the stretch at 44 of 45 (recorded
miss, accepted as known at ratification); kickback: misses the target at every
post-layout corner and the stretch everywhere in both records (recorded miss,
accepted as known at ratification); supply/power: static power meets target and
stretch at every corner, with the average-power bound at its still-TBD clock
rate not fully scored. `spec/README.md` documents when a
DR is required (whenever this table is set, changed, or scoped) and how to
write one. See
[issue #3](https://github.com/2AMLogic/gf180-comparator/issues/3) for the
honest artifact-presence checklist this table's ratification unblocks (full
PVT corner sim vs. a *ratified* spec and Monte Carlo scoring are no longer
blocked on this table's ratification).

## License

Apache-2.0.
