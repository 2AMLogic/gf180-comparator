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
  [#364](https://github.com/2AMLogic/gf180-comparator/issues/364),
  [#373](https://github.com/2AMLogic/gf180-comparator/issues/373),
  [#374](https://github.com/2AMLogic/gf180-comparator/issues/374),
  [#398](https://github.com/2AMLogic/gf180-comparator/issues/398),
  [#452](https://github.com/2AMLogic/gf180-comparator/issues/452)
  (pre-ratification validation of this record),
  [2AMLogic/klayout-tools#6080](https://github.com/2AMLogic/klayout-tools/issues/6080)
  (no request field for control-block commands between the analysis and the
  measurements — why `reset_margin_ns` is fleet-unavailable),
  [2AMLogic/klayout-tools#5651](https://github.com/2AMLogic/klayout-tools/issues/5651)
  (the dry-run-passes, every-corner-errors failure shape that makes shipping
  the `t_rst` card alone wrong),
  [DR-0001](DR-0001-comparator-topology.md), DR-0002,
  [DR-0003](DR-0003-t1-items-1-9-10-claim-policy.md),
  [DR-0004](DR-0004-preamp-input-cascode-kickback.md),
  [DR-0005](DR-0005-metastability-target.md) (separate proposed record; it
  uses a different bench condition and is not coupled to this one),
  `spec/consumers.md`, `spec/evidence-ledger.md#supply--power`,
  `sim/comparator-regeneration/records/20260910-125206-4805118` (schematic),
  `…/20261002-202641-baeffe5` (post-layout extracted),
  `sim/comparator-avg-power/` (this record's own validation bench; see its
  README and the records cited under "Feasibility status"),
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

**Validation status (revised 2026-11-21, issue #452 — items 1–4 measured;
each cites its committed record and that record's sha256)**:

The validation bench is `sim/comparator-avg-power/` (issue #356; fleet path
issues #372/#373/#374, citable re-mint #398). Its two 45-corner records are:

- schematic: `sim/comparator-avg-power/records/20261115-075832478887-79abbcc`
  (sha256 `b33962e622ddc9df37679e8baa7f8cfbdcebbdd1ec92a6cc052042a5bab10ced`)
- post-layout extracted: `sim/comparator-avg-power/records/20261116-203811672880-81544ac`
  (sha256 `cdc0590763c8a56017d6868eebbdd72a2062fdec085eca41c7420317e71e7d38`)

Both cover all 45 points (tt/ff/ss/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V)
and read `citable: true`, `reference: true` (the extracted one under DR-0008's
staged-source provenance class). UNSCORED: both are evidence for the
ratification reviewers, not verdicts.

1. **Every cycle decides correctly at every corner: MEASURED, both
   bindings.** `dec_cycles_correct` = 16/16 at all 45 points on both records,
   including the first post-warm-up cycle, on the alternating ±10 mV
   stimulus about each point's own trip point (the extracted record carries
   the per-corner probed `dut_vos` referral). The hypothesised slow corner
   `ss`/125 °C/2.97 V completed cleanly on both bindings (schematic
   `p_avg_uw` 124.908, extracted 143.760) — and the grid refuted the
   hypothesis that it is the *power* worst corner: the maximum sits at
   `ff_125c_3.63v` on both bindings. **The reset-completion margin itself is
   measured only at the local bring-up point** (`reset_margin_ns` = 30.48 ns
   of the 31.25 ns reset phase at `tt_27c_3.30v`, record
   `20261114-032046866512-d02a882`): the fleet request schema has no field
   for a control-block command between the run and the measurements, which is
   what the threshold's interactive `let` needs — the gap is
   [2AMLogic/klayout-tools#6080](https://github.com/2AMLogic/klayout-tools/issues/6080),
   and shipping the `t_rst` card without its `let` is the
   [2AMLogic/klayout-tools#5651](https://github.com/2AMLogic/klayout-tools/issues/5651)
   dry-run-passes-then-every-corner-errors failure shape, so the pair is
   omitted together. The checked backstop `dec_cycles_correct` = 16 — 16
   alternating decisions cannot happen unless the latch reset between them —
   is what the 45-corner records actually establish. **Open:** a direct
   fleet-path reset-margin number, pending klayout-tools#6080.
2. **Dynamic-power figure: MEASURED, both bindings.** Worst `P_avg` over the
   45 corners: **174.487 µW @ `ff_125c_3.63v`** (schematic; `e_dec_fj`
   10 905 fJ/decision) and **207.376 µW @ `ff_125c_3.63v`** (extracted;
   12 961 fJ/decision), the extracted figure 19 % higher (interconnect
   parasitics — an inference stated by the record, not a cross-measured
   delta). Both are figures for the reviewers, not compliance claims: this
   record is `proposed`, and neither the ≤ 1 mW target nor the ≤ 500 µW
   stretch is scored here. Static power from `i_static_ua` stays partial
   evidence and is not summed with `P_avg`.
3. **Settledness / window adequacy: MEASURED, both bindings.** Worst
   `q_half_mismatch_pct` over the grid: **0.00440 % @ `fs_125c_3.30v`**
   (schematic) and **0.00231 % @ `fs_27c_2.97v`** (extracted) — about 230× /
   430× inside the 1 % criterion at every point, so the proposed 8-cycle
   warm-up and 16-cycle window held; no lengthening and re-record was
   needed. **Open:** none.
4. **Output load, overdrive and clock-pin-charge sensitivities:
   MEASURED.** Three parts, all as unscored SENSITIVITY-ONLY records under
   `sim/comparator-avg-power/records/` (issue #452's closing increment; every
   record carries its override set and its 3-point corner subset —
   `tt_27c_3.30v`, `ff_125c_3.63v`, `ss_125c_2.97v`: the nominal point, the
   nominal campaign's measured power maximum, and this record's hypothesised
   slow corner — in its header and Reproduce line, and is stamped so it can
   never be read as the nominal condition or a scored row):
   - **Load (0 fF and 100 fF against the chosen 20 fF).** Schematic
     `20261121-032749529701-fd2a190` (0 fF, sha256
     `46779f53a919092ad213507db086d2ca96c3a89e1bcb7074c0d708e71430d033`) and
     `20261121-033511010875-fd2a190` (100 fF, sha256
     `6633bfbe72a8004f215d7fc6e13b094e7566bddd50e9ce12a6762e5c18e521af`);
     extracted `20261121-034429183380-fd2a190` (0 fF, sha256
     `9d35ff9942eb071fd05d9ec7232be9c923dc7e24836383da5210e56f894d0955`) and
     `20261121-034303477762-fd2a190` (100 fF, sha256
     `60f48af91b04ad2558e2fa643611b09598f8180a423d4766eb52f6ecaaaa809a`).
     Removing the loads moves `p_avg_uw` by −3.0 … −4.6 µW (schematic) and
     −3.0 … −4.5 µW (extracted; 202.882 µW worst sampled at 0 fF, extracted); 100 fF moves it by +11.7 … +17.9 µW and
     +11.6 … +17.7 µW — ≈ 0.22 µW/fF on both bindings, so the chosen 20 fF
     sits on a gentle slope: even the 5× load leaves the worst sampled point
     at 192.350 µW / 225.079 µW, inside the 500 µW stretch. **No revision to
     the 20 fF choice is proposed.**
   - **Overdrive (1 mV and 50 mV against the chosen 10 mV).** Schematic
     `20261121-033708169651-fd2a190` (1 mV, sha256
     `d05280f12432407d731a0e60ca9c49bcd737558ea431be2c8c1837dd19e9233d`) and
     `20261121-033802179758-fd2a190` (50 mV, sha256
     `37d87a4b1740d9b9b8d922af2b8d0aa2a942d08e7c2a73a6f4f218df6ac2cefc`);
     extracted `20261121-034624876214-fd2a190` (1 mV, sha256
     `4436669b85d711d052d7afcba37940938d60964068365e3e9add05647d0661f5`) and
     `20261121-034303118261-fd2a190` (50 mV, sha256
     `ec1161acf7ce111291cdf6232d5ca7372fc72c933dff773da1fed545af3b432b`).
     `p_avg_uw` RISES as the overdrive shrinks (1 mV: +3.7 … +9.8 µW
     schematic, +6.1 … +15.7 µW extracted — slower regeneration spends longer
     at the static bias) and falls as it grows (50 mV: −5.2 … −1.0 µW and
     −8.5 … −2.6 µW), at every sampled corner on both bindings. The chosen
     10 mV reference stimulus therefore understates power relative to 1 mV
     (by up to 15.7 µW extracted) and overstates it relative to 50 mV; the
     regeneration-dwell mechanism is a hypothesis, and 10 mV is retained on
     its stated engineering basis. All 16 decisions were correct at 1 mV on both bindings (the
     extracted leg overdrive referred to each corner's own probed trip
     point). **No revision to the 10 mV choice is proposed.**
   - **Clock rate (32 MHz, informational per "Alternatives considered").**
     Schematic `20261121-034107310717-fd2a190` (sha256
     `608e87c18b3ca3d23d6860c8bb1030a9f039f93e6f7b2f782397ce8252af453b`);
     extracted `20261121-034523379992-fd2a190` (sha256
     `afbaf1af850bf35f90c7c837cf284ca5a4a04d81dadac70e3e63b32d7aa519f2`).
     Doubling the rate moves the figure by +36.2 … +65.4 µW (schematic,
     +37.5 % at the binding corner) and +59.5 … +104.6 µW (extracted, +50.4 %
     at the binding corner): worst sampled 239.876 µW / 311.937 µW — inside
     the 1 mW target but 62 % of the 500 µW stretch on the extracted
     binding. This supports keeping the ratified 16 MHz as the scored rate
     (the "Alternatives" reasoning stands); it is not a scored condition and
     moves no bound.
   Every one of the 10 records: `dec_cycles_correct` = 16/16 at all 3 points,
   worst `q_half_mismatch_pct` 0.00472 % (≈ 212× inside the 1 % criterion),
   and the highest-power corner **among the sampled points** is
   `ff_125c_3.63v` in every condition on both bindings — the same corner the
   45-point nominal campaigns identify as the grid maximum, so no condition
   moved the binding corner and no full-grid re-run was triggered.
   - **Signed clock-pin charge: computed from the committed records** — see
     `sim/comparator-avg-power/clock-charge-boundary.md` (issue #452). It is
     an informational pin diagnostic only: the signed net charge of a
     capacitive clock load cancels over whole cycles, so it is **not** a
     measure of clock-driver supply cost and no bound on that cost is
     claimed. Adding it to the row's charge integral moves the figure by at
     most +0.1254 µW (schematic, `sf_27c_3.63v`) / +0.0640 µW (extracted,
     `fs_125c_3.63v`); at the binding corner (`ff_125c_3.63v`) by +0.028 /
     +0.045 µW. The same boundary is visible in the sensitivity records
     (100 fF and 32 MHz): the largest fold-in over the sampled points is
     +0.039 µW (schematic) / +0.054 µW (extracted) at 16 MHz conditions and
     +0.056 µW / +0.084 µW at 32 MHz. The binding corner does not change
     under any of them. **Open:** the clock-driver supply cost (needs a
     specified driver or the `-∫ v(clk)·i(vclk) dt` port integral).

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
rate, and the validation status under "Feasibility status" — which since
issue #452 cites, per item, the committed records and their sha256 that
establish it (items 1–3 measured on the nominal 45-corner grid on both bindings,
except that the direct reset margin of 30.484 ns is a single schematic
TT/27 °C/3.30 V measurement; item 4's signed clock-pin charge is an
informational diagnostic, its clock-driver cost and sensitivity sweep records
open until they land).
