# DR-0006: Average-power operating condition — 16 MHz, one decision per cycle, integer-cycle supply-charge integral

- **Status**: proposed — **not ratified**. Ratification is the DR-0002
  two-key act only: a non-author EE-key and a non-author market-key
  `RATIFY-KEY` review on the ratification PR, plus that PR's merge as the
  record (`spec/README.md`). Merging this proposed draft is not that act.
  Until a valid ceremony exists, this record changes no spec line, no bound,
  no scoring and no manifest.
- **Date**: 2026-10-09
- **Decided by**: Builder agent, issue #125 (drafting only; the author cannot
  supply or count its own keys)
- **Supersedes**: none — first record to set the average-power clock rate.
  Changes no numeric bound set by [DR-0002](DR-0002-target-spec-ratification.md).
- **Superseded by**: (none while this record stands)
- **Related**: [#125](https://github.com/2AMLogic/gf180-comparator/issues/125),
  [#3](https://github.com/2AMLogic/gf180-comparator/issues/3),
  [#75](https://github.com/2AMLogic/gf180-comparator/issues/75) (scoring
  pass), [#112](https://github.com/2AMLogic/gf180-comparator/issues/112)
  (cascode adoption / layout refresh; not a dependency of this draft),
  [DR-0001](DR-0001-comparator-topology.md), DR-0002,
  [DR-0003](DR-0003-t1-items-1-9-10-claim-policy.md),
  [DR-0004](DR-0004-preamp-input-cascode-kickback.md),
  [DR-0005](DR-0005-metastability-target.md) (separate proposed record; it
  uses a different bench condition and is not coupled to this one),
  `spec/consumers.md`, `spec/evidence-ledger.md#supply--power`,
  `sim/comparator-regeneration/records/20260910-125206-4805118` (schematic),
  `…/20261002-202641-baeffe5` (post-layout extracted),
  `sim/comparator-regeneration/testbench/tb.json` and
  `tb_regeneration.spice`, `signoff/make_item5_envelope.py`,
  `sim/characterize.sh`.

## Context

The ratified Supply / power row (`README.md`, target table, DR-0002) reads
"3.3 V ±10% (`nfet_03v3`/`pfet_03v3`); ≤ 1 mW average, one decision per clock
edge at a stated clock rate (TBD)", stretch "≤ 500 µW average". The clock rate
is TBD, so the row cannot be scored. Today only a **static** quantity is
recorded: `i_static_ua` is the mean of `i(vsupa)` over `25n..29n` of the
regeneration deck, a window inside the clock-low phase
(`tb.json` `meas tran i_stat`). Record `20260910-125206-4805118` gives 28.5 µA
mean (27.7–29.7 µA across the grid; 28.447 µA ≈ 93.9 µW at tt/27 °C/3.30 V).
`signoff/make_item5_envelope.py` accordingly carries static power only as
partial evidence (`partial_of: supply_avg_power_uw`) and records the row as
skipped work with reason `average_power_clock_rate_tbd`. No clock rate was
invented there, and choosing one needs a decision record (`spec/README.md`).

The regeneration deck also integrates a charge `q_dec` over `39.9n..48n` and
reports `e_dec_fj` (823–1788 fJ across the grid in the schematic record), but
that quantity is **not usable as evidence for this row**: it is a single
event, not a periodic steady state; it subtracts a hard-coded `8.1e-9 s ×
i_stat`; its window ends 8 ns after the edge; and `tb.json` states it
"CARRIES NO CHECK, DELIBERATELY". It is cited here only as an unvalidated
order-of-magnitude hint (about 1–2 pJ per decision, versus the 62.5 pJ the
proposed target would allow; see "Feasibility status").

The existing regeneration clock is `pulse(0 VDD 10n 100p 100p 10n 30n)`
(`tb_regeneration.spice`): 30 ns period (≈ 33 MHz), 10 ns high, 33 % duty,
two strobes. It was built to time one decision, not to be a throughput
operating condition, and is **not** proposed as the power condition.

## Decision

Propose one operating condition, to be written into the Supply / power row
**only if and when this record is ratified**. All numbers below are
**proposed**.

### Clock rate and its engineering basis

| Item | Proposed value |
|---|---|
| Clock rate | **16 MHz** (period 62.5 ns), applied identically at all 45 corners and to target and stretch |
| Duty | 50 %: 31.25 ns evaluate (clk high), 31.25 ns reset (clk low); 100 ps rise/fall as in the existing deck |
| Decisions | Exactly **one decision per clock cycle**, evaluated on the rising edge; reset is the low phase |

Basis (consumer snapshot versus current requirement kept separate):

- **Historical consumer snapshot** (`spec/consumers.md`, `gf180-sar-adc` @
  `773f906`, read 2026-09-22): one decision per decide phase of **31.25 ns at
  1 MS/s** (the ratified rate; 16× clock, 16 MHz) and **15.625 ns at 2 MS/s**
  (stretch rate, 32 MHz). That is dated third-party data, not a requirement of
  this repo, and must be re-read live before ratification.
- Choosing the **ratified** 1 MS/s rate (16 MHz) rather than the 32 MHz
  stretch rate keeps the power row tied to the consumer's ratified, not
  aspirational, rate. The 32 MHz condition is not proposed as a scored
  condition here (see Alternatives).
- Time margin in the evaluate phase, from committed evidence: worst
  clock-to-output delay at the 1 mV rung is 1.673 ns schematic / 2.716 ns
  extracted, and at the 0.1 mV rung 1.956 ns / 3.190 ns, all at
  `ss_125c_2.97v` (records `…4805118`, `…baeffe5`; see `spec/consumers.md`).
  That is ≥ 9.8× inside the proposed 31.25 ns evaluate phase and ≥ 4.9×
  inside even the 15.625 ns stretch-rate phase. This is evidence about
  **evaluate**, not about reset.
- The consumer needs 10 decisions per 16 clock cycles for a 10-bit
  conversion (per `consumers.md` rates). Charging a decision every cycle is
  therefore a **conservative upper bound** on its duty, not a claim about
  how the consumer gates the comparator.

### Stimulus

| Item | Proposed definition |
|---|---|
| Input common mode | `dut_vcm = 1.65 V` held fixed at every corner (the DUT's `sim/dut.json` operating point; equal to the consumer's constant `V_cm`). |
| Differential input | Alternating sign each cycle: `+Vod` on even cycles, `−Vod` on odd cycles, **`Vod = 10 mV` above/below the DUT's own trip point** (schematic: trip point 0 V; extracted: the per-corner probed `dut_vos`, as the existing `tb_vosprobe.spice` flow does). Alternation forces a real flip of the SR latch on every cycle, i.e. the worst-case output toggling, not a repeat of the same answer. |
| Input timing | The sign change is applied inside the reset (clk-low) phase, ≥ 20 ns before the next rising edge, matching the existing deck's settling argument (`tb.json`: ">10 time constants" for the front-end output pole), so every decision is on a settled overdrive. |
| Overdrive rationale | 10 mV is large enough that every cycle completes a full decision (worst 1 mV-rung delay is 2.7 ns of a 31.25 ns phase), and small enough not to be an unrealistic rail-to-rail input. It is engineering judgment, not a derived value. Power sensitivity to `Vod` at 1 mV and 50 mV is to be reported alongside (informational, not scored). |
| Output loads | `dout` and `doutb` each loaded with **20 fF to `vss`**, the same on both. Engineering judgment for an adjacent SR-logic gate plus routing in this PDK; the existing regeneration deck has **no** explicit output load, and this repo does not know the consumer's real load. Sensitivity at 0 fF and 100 fF to be reported (informational). The scored figure uses 20 fF. |
| Bias | `ibias` driven by the DUT's `dut_ib` current source (10 µA, `sim/dut.json`), drawn **from the DUT's own `vdd` rail** as in the existing deck's `iba vdda ibna`. |
| Mismatch / noise | Mismatch-free (`sw_stat_mismatch` = 0) and noiseless; this is a PVT-corner row, not a distribution row. |

### Accounting boundary: what counts as DUT energy

- **Counted**: all charge delivered from the DUT's `vdd` source, which
  includes the bias reference current (`ibias` returns through the DUT, and
  its source is referenced to the same rail so its charge appears in the
  supply current) and the charge that charges the output loads through the
  DUT's output stages. A DUT on its own supply source (like the existing
  deck's `vsupa`) avoids any other instance's current in the integral.
- **Not counted, reported separately (informational)**: charge drawn by the
  ideal clock source (`vclk`) and by the ideal input and common-mode
  sources. These are testbench or consumer energy, not DUT supply energy.
  The clock-input charge is a legitimate consumer cost; it is recorded for
  the integrator but is outside the row, which is defined as the DUT's
  supply power. If reviewers want it inside the row, that is a boundary
  change needing re-decision (see Alternatives).
- **No double counting**: the load capacitors are on the output side of the
  DUT and recharge from the DUT supply, so their energy is counted once, in
  the supply charge, and never added again as a `C·V²` term. No separate
  `ibias` supply is permitted; if a bench used one, its charge must be added
  once and the rail must not also be integrated at the pin.

### Warm-up, window, and quantities

- **Warm-up**: the first **8 cycles (500 ns)** are discarded. Cycle 0 begins
  with the rising edge at t = 10 ns (as in the existing deck), so warm-up
  ends at t = 510 ns.
- **Integration window**: **N = 16** whole clock cycles (1.000 µs),
  from the rising edge at t = 510 ns to the rising edge at t = 1510 ns,
  edge-to-edge. N is even, so the window holds a whole number of the
  two-cycle input-polarity period.
- **Settledness check (required, same run)**: the same integral over the
  window's two 8-cycle halves must agree within 1 %; otherwise the corner
  is a **miss** (not-settled), not a pass, and the warm-up and window must be
  lengthened (and re-recorded) rather than the tolerance widened. A run that
  does not complete, whose decisions do not follow the stimulus sign in every
  window cycle (output read at the end of each evaluate phase, supply-
  normalized), or whose integral is missing or non-finite is
  **invalid**, never a pass.
- **Sign convention**: ngspice reports `i(vsupX)` as the current flowing
  *into the positive terminal* of the source, i.e. **negative when the source
  delivers power**. Define the delivered DUT supply current
  `i_DD(t) = −i(v_supply)(t)` (positive when delivering). Charge, energy and
  power are then positive for delivered energy; a negative window integral is
  invalid, not clamped with `abs()`.
- **Definitions** (units in brackets), with `T = 62.5 ns`, `N = 16`, `t0` the
  window-start rising edge, `VDD` the corner supply voltage (2.97/3.30/3.63 V),
  and `i_DD` in A:
  - `Q_win = ∫[t0, t0+N·T] i_DD(t) dt` [C]
  - `E_dec = VDD · Q_win / N` [J per decision]
  - `P_avg = VDD · Q_win / (N · T)` = `E_dec / T` = `E_dec · f_clk` [W]
  - `P_avg` is scored in µW as the **maximum over all 45 corners** against
    the unchanged **1 mW target** and **500 µW stretch**.
  Because `VDD` is constant within a corner, `v·i` integration reduces to the
  charge form above; an implementation that integrates `v(vdd)·i_DD`
  directly must agree with it (a check, not a second definition).

### What stays unchanged

- The **3.3 V ±10 % 45-point PVT grid** (tt/ff/ss/fs/sf × −40/27/125 °C ×
  2.97/3.30/3.63 V) is unchanged and fully required; no corner may be
  dropped or substituted by a typical-only estimate.
- The **1 mW target** and **500 µW stretch** are unchanged and are not
  relaxed by anything above; this record only chooses the condition they are
  evaluated under.
- Static power from `i_static_ua` is **not** average power and remains
  partial evidence; it is not summed with `P_avg`.

## Feasibility status (what is established and what is not)

Established from committed evidence, with its limits:

- Static current alone is ≈ 10× inside the target and ≈ 5× inside the
  stretch at every corner (worst 29.7 µA × 3.63 V ≈ 108 µW;
  `spec/evidence-ledger.md#supply--power`). The static window is in the
  reset phase only; it does not show the evaluate-phase current.
- Evaluate-phase time is sufficient by large margin (see Basis).
- Both regeneration records pass at 45/45 corners including the paired
  `dout_*_first`/`dout_*_end` checks, i.e. the output held the opposite answer
  after the first strobe and the correct one after the second, with a
  **20 ns** low phase between strobes. That is weak, indirect evidence that
  reset can complete in some time ≤ 20 ns at the 33 MHz bench, but it was
  not designed as a reset measurement.

**Not established — validation required before ratification**:

1. **Reset time is unmeasured.** No committed record measures how long the
   latch, isolation and SR-latch nodes take to reach their reset state, nor
   at which corner (expected slowest at `ss`, 125 °C, 2.97 V is a
   hypothesis, not a result). The 31.25 ns reset phase at 16 MHz is longer
   than the 20 ns the existing bench already survived, but "longer than a
   passing bench" is not a measurement. The validation is: run the proposed
   periodic stimulus at all 45 corners on the schematic and on the
   post-layout extracted DUT and show every cycle decides correctly,
   including the first post-warm-up cycle and including at the worst corners
   found, with a reset-completion margin recorded.
2. **Steady-state feasibility of ≤ 1 mW / ≤ 500 µW at 16 MHz is unmeasured.**
   No dynamic-power figure exists. The `e_dec_fj` hint above is not
   evidence (see Context), and the post-layout run is expected to differ
   (the extracted record shows +58 % on that same hint).
3. **Settledness and window length** (8-cycle warm-up, 16-cycle window, 1 %
   half-window agreement) are proposed, not yet shown adequate; the
   validation run must show them adequate or the numbers change in a revised
   record.
4. **Output load, overdrive and clock-charge boundary** are judgment
   choices; the sensitivities listed above must be run so reviewers can see
   how much the scored figure depends on them.

These items validate the *condition*; they are not a compliance claim. A
ratified condition with a measured miss is a miss, and no bound moves to
make it pass.

## Alternatives considered

- **32 MHz (the consumer's 2 MS/s stretch rate).** Doubles the dynamic
  component, is the consumer's stretch not its ratified rate, and leaves only
  a 15.625 ns phase with ≥ 4.9× delay margin. Not chosen as the scored
  condition because tying the *target* to a stretch rate would silently
  tighten the ratified row. It is a natural informational sensitivity run.
- **Keep the existing 30 ns / 10 ns-high regeneration clock (≈ 33 MHz).**
  Convenient (no new clock), but its 33 % duty and two strobes are a timing
  rig, not a throughput condition, and 33 MHz matches no ratified consumer
  rate.
- **Leave the rate TBD and score static power only.** This is the status quo
  and leaves the row permanently partial (`average_power_clock_rate_tbd`);
  the dynamic component is exactly what the row names.
- **Single-event energy (the existing `e_dec_fj`) × a rate.** Cheap, but
  one event is neither periodic steady state nor free of the hard-coded
  static subtraction, and it is already marked unusable by its own bench.
- **Fixed-sign (same-answer) input every cycle.** Under-counts the SR-latch
  and output-load toggling; alternating sign is the worse, more honest case.
- **Include the clock-source charge in the row.** Counts a consumer cost, but
  it depends on the clock buffer and routing outside this block, and it would
  conflate DUT and driver energy. Kept as an informational line instead.
- **A rail-to-rail or random input pattern.** More realistic for a particular
  consumer, but non-reproducible or unrelated to this block; a deterministic
  alternating pattern is repeatable and bounds toggling.

## Consequences

- Makes the row scoreable: the row's "(TBD)" gets a single stated rate and a
  definite integral, so the item-5 envelope's `average_power_clock_rate_tbd`
  skip reason can later be retired.
- **Harder**: it requires a new transient-power bench, not an edit of the
  regeneration deck, and a full 45-corner run (plus a post-layout run). Each
  corner is a ≥ 24-cycle transient; per `CLAUDE.md` host rules, a campaign
  must go through `klt sim` corner/batch submission, not a hand-launched
  ngspice grid.
- **Bad outcomes are possible**: measured average power could miss the 1 mW
  target or the 500 µW stretch at some corner, or reset could fail to
  complete at 31.25 ns at the slowest corner. Either is a legitimate finding,
  not a reason to change the condition after the fact.
- **Moving evidence**: the cascode experiment (DR-0004) and the layout/PEX
  refresh in #112 may change dynamic power. Any final-DUT figure must be
  (re)measured after that adoption; none is implied here.
- The consumer's rates are a dated snapshot; if `gf180-sar-adc` changes its
  rate or comparator duty, this record should be superseded, not edited.
- Later stages (not part of this draft, to be landed separately after
  ratification with their own acceptance criteria): the transient-power
  bench and 45-corner campaign with append-only records; extending
  `signoff/make_item5_envelope.py` and its tests, including regression
  coverage for missing, invalid and incomplete power data, target misses and
  full-grid success; new scoring evidence minted rather than historical
  records rewritten.

## Spec lines affected

None change in this proposed draft. **After ratification only**, the rows
below would be edited by the ratifying change, not by this PR:

- `README.md#target-specification-ratified-via-dr-0002` — the
  **"Supply / power"** row (the table row beginning `| Supply / power |`,
  target column text "≤ 1 mW average, one decision per clock edge at a stated
  clock rate (TBD)") — scoped (`at a stated clock rate (TBD)` -> `at
  16 MHz, one decision per clock cycle, under the DR-0006 operating
  condition`); the 3.3 V ±10 % supply, ≤ 1 mW target and ≤ 500 µW stretch
  numbers are unchanged. Reword "per clock edge" to "per clock cycle
  (evaluated on the rising edge)" is a clarification (no value change).
- `spec/evidence-ledger.md#supply--power` — its mirrored target text and
  verdict narrative would be updated in the same later change, not here.

This record does not change `sim/dut.json`, the DUT selection, the manifests,
scoring, or any historical `sim/` record. Until ratified, the active
README table is unchanged and the row stays "clock rate TBD, average power not
fully scored".

## Ratification ceremony status

**Pending.** No EE-key or market-key review exists for this record. Ordinary
PR approval is not ratification. Pending, declined and missing-key outcomes
all leave this record `proposed` and the README row unchanged. Before the
ceremony the reviewers should be given: a live re-read of the consumer's
rate, and the validation list under "Feasibility status".
