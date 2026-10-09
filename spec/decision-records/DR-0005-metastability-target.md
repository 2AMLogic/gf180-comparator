# DR-0005: Metastability target — a deterministic small-overdrive resolution-time row, with no probabilistic guarantee

- **Status**: proposed — **not ratified**. Ratification is the DR-0002 two-key
  act only: a non-author EE-key and a non-author market-key `RATIFY-KEY`
  review, plus the release they clear (`loom:auto-merge-ok`), with a merge as
  the record. Ceremony status at the time of drafting: **pending** (see
  "Ratification ceremony status"). Until a valid released ceremony exists,
  this record changes no spec line, and the pending/declined/missing-key
  outcomes all leave it `proposed`.
- **Date**: 2026-10-09
- **Decided by**: Builder agent, issue #134 (drafting only; the author cannot
  supply or count its own keys, and ordinary PR approval is not ratification)
- **Supersedes**: none — first record that proposes a metastability row.
  Changes no bound set by [DR-0002](DR-0002-target-spec-ratification.md).
- **Superseded by**: (none while this record stands)
- **Related**: [#134](https://github.com/2AMLogic/gf180-comparator/issues/134),
  [#3](https://github.com/2AMLogic/gf180-comparator/issues/3),
  [#125](https://github.com/2AMLogic/gf180-comparator/issues/125) (separate
  average-power clock condition; not a dependency),
  [DR-0001](DR-0001-comparator-topology.md), DR-0002,
  [DR-0004](DR-0004-preamp-input-cascode-kickback.md) (proposed cascode
  experiment), `spec/consumers.md`,
  `sim/comparator-regeneration/records/20260910-125206-4805118` (schematic),
  `…/20261002-202641-baeffe5` (post-layout extracted),
  `…/20261008-235219317743-7e61c52` (DR-0004 cascode experiment),
  `sim/comparator-regeneration/testbench/tb.json`,
  `measurements/characterization-report.md` ("Decision time vs. overdrive —
  regeneration bench (and metastability)"),
  `ratification/ee-key/MANIFEST.md`, `ratification/market-key/MANIFEST.md`.

## Context

`CLAUDE.md` says metastability is a first-class row; `README.md`'s ratified
target table (DR-0002) has five rows and no metastability row. The
regeneration bench records `tau_ps` and `resolve_decades` at every one of the
45 PVT points (`sim/comparator-regeneration/testbench/tb.json:35-36`) and
`tb.json:100` calls metastability "a first-class row here, not a note", but no
ratified bound exists, so the recorded numbers can neither pass nor fail.

Two properties of those recorded numbers decide what a defensible row can be:

- `tau_ps = (td_c − td_b)/ln(10)·1e12` with `td_b`, `td_c` the clock-to-output
  delays at 1 mV and 0.1 mV overdrive. It is a **finite difference of two
  deterministic delays**, one decade of overdrive apart.
- `resolve_decades = td_b/((td_c − td_b)/ln(10))` is **`td_od1/τ`, an e-fold
  count (natural log), not decades**, despite its name. It divides the *whole*
  clock-to-output delay (including non-regenerative fixed delay) by τ, and uses
  no application clock phase. It is therefore not "e-folds available in a
  decision phase".

Neither number, alone or together, supplies a calibrated probability that a
decision is unresolved after a stated time: that needs a prefactor, an
input-density assumption and evidence that the exponential tail holds far
below the smallest measured overdrive. The `tb.json` check text ("the
probability of an unresolved decision falls as exp(−t/τ)") and the issue's
first sketch (`P = exp(−t_avail/τ)`) both omit those three things. This
record therefore **does not propose a probability**; it proposes the
deterministic quantity the bench does support, bounded by an application
budget, and states what a probability claim would additionally need.

## Decision

Propose one new row, **"Small-overdrive resolution time"**, to be added to
`README.md`'s target table only if and when this record is ratified. All
numbers below are **proposed**, derived from the application budget, and none
was chosen from an observed worst value.

### Metric, units, convention

| Item | Proposed definition |
|---|---|
| Metric | `td_od01`: delay from the 50 % point of the clock's rising (evaluate) edge to the 0.5·VDD crossing of `dout`, with the input held **0.1 mV above the comparator's own trip point** with the correct polarity. Units: ns. Scored as the **maximum over the 45-point PVT grid** (process tt/ff/ss/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V). |
| Target | `td_od01 ≤ 15.625 ns` at every one of the 45 corners |
| Stretch | `td_od01 ≤ 7.8125 ns` at every one of the 45 corners |
| Also required to count as "resolved" | existing bench checks `dout_od01_end ≥ 0.9` and `dout_od01_first ≤ 0.1` (supply-normalized): the instance must hold the correct answer after the second strobe and the opposite answer after the first, so it provably decided both ways in one run. A corner that fails them is a miss, not a pass-by-delay. |
| Input distribution | **None assumed.** The row is a conditional, worst-case-timing statement at a *fixed* overdrive. It bounds how long a decision with at least 0.1 mV of overdrive takes; it says nothing about how often inputs land closer to the trip point than 0.1 mV. |
| Trip-point / offset convention | Overdrive is measured **above the comparator's own trip point**, not above 0 V. Schematic DUT: mismatch-free (`sw_stat_mismatch` = 0), trip point 0 V, `dut_vos` = 0. Extracted DUT: the trip point is probed per PVT point (`tb_vosprobe.spice`) and the three-rung ladder is centred on it via `dut_vos` (record `…baeffe5`: −1.83 to −21.57 mV across the 45 points, recomputed from its JSON). Mismatch-induced offset (Offset row) and noise are **not** in this row: an input inside the offset band of the trip point is the Offset row's subject. |
| Resolution threshold | `dout` crossing 0.5·(its own supply), supply-normalized (`tb.json` note "TIMING THRESHOLDS ARE SUPPLY-NORMALIZED"), search window opened at 35 ns so only the second-strobe decision is timed. Clock edges 100 ps rise/fall; bench clock `pulse(0 VDD 10n 100p 100p 10n 30n)` (10 ns high, 30 ns period). |
| Scoring DUT | Whichever DUT `sim/dut.json` has `active` when the row releases (today `comparator-dr0001`, schematic; see "Active DUT"). |

### Budget and allocation (where the numbers come from)

The only stated application timing in this repo is `spec/consumers.md`'s
`gf180-sar-adc` row: one decision per decide phase of **31.25 ns at 1 MS/s
(ratified)** and **15.625 ns at 2 MS/s (stretch)** (16× clock, 50 % duty;
`gf180-sar-adc` `spec/comparator-budget-memo.md` §6 at `b8d494f`). The target
tier is set from the ratified-rate phase and the stretch tier from the
stretch-rate phase, mirroring how the repo's other rows pair target and
stretch.

`t_avail` is the part of the phase the *comparator* may spend resolving:

```
t_avail  =  T_phase  −  t_fixed,ext
t_fixed,ext := 0.5 · T_phase          (PROPOSED allocation, see below)
target   :  t_avail = 31.25 ns − 15.625 ns = 15.625 ns
stretch  :  t_avail = 15.625 ns −  7.8125 ns =  7.8125 ns
```

- **Fixed delay inside the metric.** `td_od01` is clock-edge to `dout`, so the
  comparator's own non-regenerative delay (clock buffering, preamp-to-latch
  hand-off, isolation inverters, NOR SR latch) is already inside the measured
  number. This bench does not separate it from the regenerative part, and the
  record does not extract a `t0`.
- **Fixed delay outside the metric (`t_fixed,ext`).** Consumer-side terms the
  bench cannot see: comparator-to-SAR-logic transport, clock skew and edge-rate
  differences, logic setup before the next DAC update, and margin for the
  region below 0.1 mV overdrive. **The 50 % reservation is an engineering
  allocation, not a measurement and not a number taken from the consumer.**
  It is deliberately more conservative than the consumer's own
  `timing-budget-memo.md`, which allocates the whole 62.5 / 31.25 ns bit cycle
  and carries a fixed 0.863 ns comparator delay (their §3.2). The consumer
  owns the true split and should confirm or replace 50 % before ratification;
  if it replaces it, the two bounds scale linearly (`0.5·T_phase → (1−f)·T_phase`).
- **Why a bound at 0.1 mV overdrive and not at 50 mV.** The ratified
  Decision-time row (50 mV) is the large-signal speed; metastability is the
  behavior as the input approaches the trip point. 0.1 mV is the smallest rung
  the bench already measures, so the row needs no new simulation.
- **Dead zone, stated.** The row says nothing about inputs closer than 0.1 mV
  to the trip point. 0.1 mV is 0.031 LSB of the consumer's 10-bit,
  3.3 V ADC (LSB = 3.3 V/1024 = 3.2227 mV) and is comparable to the
  comparator's own front-end noise (66.8–128.8 µV rms, DR-0002 /
  `sim/comparator-preamp-noise/records/20260910-125200-4805118.md`). **Assumption
  the consumer must confirm:** if an unresolved output is read as *some*
  polarity by the logic, a wrong decision inside the dead zone costs at most the
  residue magnitude (≤ 0.1 mV ≈ 0.031 LSB) in a non-redundant SAR; if the logic
  can sample an unresolved node inconsistently, the consequence is larger and
  this row is not sufficient.

### Validity assumptions (the row is void if any fails)

1. Mismatch-free bench for the schematic DUT; offset and metastability are
   budgeted separately (`tb.json`, "MISMATCH-FREE BY CONSTRUCTION").
2. Noise-free transient (no transient-noise sources). The 0.1 mV rung is the
   same order as the front-end noise rms, so it is a deterministic timing probe,
   not a statistical one.
3. Clock edge rates, duty and the 20 ns input-flip settling as in the bench;
   different edge rates or a clock-to-input skew move `t0`.
4. Supply-normalized 0.5 crossing as the resolution criterion; the consumer's
   logic threshold may differ and sits in `t_fixed,ext`.
5. The bench's strobe-high window is 10 ns (`tb_regeneration.spice`, line 82).
   A delay approaching that window would be cut off by the reset edge, so the
   bench can only *demonstrate* resolution inside 10 ns. It cannot, as built,
   score a value between 10 ns and the 15.625 ns target as a pass: such a point
   would also fail the `dout_od01_end` check and be recorded as a miss. This
   does not affect any measured point (largest 3.19 ns) but is a limit on what
   the 15.625 ns tier can ever certify.
6. Extracted-DUT scoring uses the first-order lumped RC extraction recorded in
   `sim/dut.json`; its limits carry over.

## Deterministic evidence versus a statistical model

**What the bench supports (deterministic).** A set of delays at three fixed,
noise-free overdrives per PVT point, plus the polarity pair. The row above uses
only these. `tau_ps` and `resolve_decades` are retained as **report-only
diagnostics** and are not scored.

**Why no exponential-tail probability is proposed.** A regenerative decision
resolves in `t = t0 + τ·ln(V_ref/|ΔV|)`, with `ΔV` the overdrive. If the
overdrive has a density `f0` (per volt) near zero, then

```
P(unresolved at t)  ≈  2 · f0 · V_c(t),     V_c(t) = 1 mV · exp(−(t − td_od1)/τ)
```

(anchored at the measured 1 mV rung so no `t0` is needed). Claiming a number
from this requires all of the following, none of which this repo has:

| Needed | Why it is missing here |
|---|---|
| Prefactor `2·f0·V_c`, i.e. an input/residue density `f0` at the trip point **after** convolution with noise | The bench has no input distribution; it uses fixed, noise-free overdrives. |
| Initial-condition distribution of the latch (reset completeness, kickback memory, kT/C and device noise on the regenerating nodes) | Mismatch and noise are off; reset-state dependence is only checked via the two-way polarity pair. |
| Evidence the log-linear (exponential) tail holds over the extrapolation | `τ` comes from **two** points one decade apart, which fit any line. The extrapolation is far outside the data: see the table below. |
| Per-corner and per-device variability of `τ` | `τ` is a nominal-mismatch value; no Monte-Carlo of `τ`. |
| Independent confirmation by direct counting or importance sampling | A direct count to show `P ≤ 10⁻⁹` at 95 % needs ≳ 3×10⁹ failure-free trials; none exists. |

Illustrative, **proposed, not a claim and not written into any record**
(recomputed from the cited JSON; `t − td_od1` in e-folds, worst-`td_od01`
corner `ss_125c_2.97v` in each record):

| Record (DUT) | `td_od1` | `τ` | e-folds from 1 mV rung to 15.625 ns / 7.8125 ns | equivalent overdrive `V_c` (extrapolated) |
|---|---|---|---|---|
| `…4805118` (schematic) | 1.6730 ns | 122.93 ps | 113.5 / 49.9 | 1 mV·e⁻¹¹³·⁵ ≈ 5×10⁻⁵³ V / 1 mV·e⁻⁴⁹·⁹ ≈ 2×10⁻²⁵ V |
| `…baeffe5` (extracted) | 2.7163 ns | 205.77 ps | 62.7 / 24.8 | ≈ 6×10⁻³¹ V / ≈ 2×10⁻¹⁴ V |

Those equivalent overdrives are far below thermal noise (tens of µV at the
input) and, for most entries, below any physical scale. Quoting them as a
probability would be the unsupported extrapolation this record declines. (The
`gf180-sar-adc` budget memo §6 does quote a per-trial `10⁻³⁰⁹`, from the same
extrapolation; a finding about that consumer memo, if one is warranted, belongs
on that repo per this repo's cross-pollination protocol, not here.)

One bounded, honest use of the tail: it shows the 0.1 mV rung is not
negligible *as a fraction of decisions*. For an **assumed** residue uniform over
±1 LSB (6.4453 mV span), the fraction of decisions within ±0.1 mV of the trip
point is 0.2/6.4453 ≈ 3.1 %. Those take longer than `td_od01`; the row's margin
(below) is what covers them, and it is a margin, not a probability.

**If a probability row is wanted later**, the minimum new evidence is: a
transient-noise Monte-Carlo (seeds and run counts committed) with mismatch on,
over the 45-point grid, with a ladder of at least six overdrives from ≈ 10 mV
to ≈ 1 µV showing a constant fitted `τ` across rungs (or a fitted `τ(ΔV)`), a
stated residue/input density, and a stated `t_avail` allocation — plus a
statistical-convention line (record kind "distribution", not corner-matrix).
That is separate work; this record neither schedules nor presumes it.

## Provisional scoring (proposed; recomputed from cited records; rewrites nothing)

`td_od01_ns` and its margin to each tier, worst of 45 corners. Computed with
`python3 -I` from the records' `points`/`derived` JSON, cross-checked by
recomputing `tau_ps` and `resolve_decades` from `td_od1_ns`/`td_od01_ns` in all
45 points of each record (0 mismatches), and confirming
`td_od50 < td_od1 < td_od01` and the polarity checks at every point.

| DUT / record | `td_od01` range (ns) | worst corner | within 15.625 ns | within 7.8125 ns | worst margin (target / stretch) | `τ` range (ps) | `resolve_decades` (e-folds) |
|---|---|---|---|---|---|---|---|
| Schematic `comparator-dr0001`, sha `0df618e73b1f0736`, `…20260910-125206-4805118` (**active**) | 0.6685 – 1.9560 | `ss_125c_2.97v` | 45/45 | 45/45 | 7.99× / 3.99× | 38.39 – 122.93 | 13.61 – 15.17 |
| Extracted `comparator-dr0001-layout`, `…20261002-202641-baeffe5` | 1.0902 – 3.1901 | `ss_125c_2.97v` | 45/45 | 45/45 | 4.90× / 2.45× | 55.92 – 205.77 | 13.20 – 18.25 |
| DR-0004 cascode **experiment** (non-active), sha `79dcc79fb6a876bc`, `…20261008-235219317743-7e61c52` | 0.6772 – 2.0254 | `ss_125c_2.97v` | 45/45 | 45/45 | 7.71× / 3.86× | 39.04 – 127.04 | 13.64 – 15.09 |

The schematic τ range (38.39–122.93 ps; 13.61–15.17) equals what
`measurements/characterization-report.md` cites. These are provisional
verdict *candidates*; nothing here is a scored verdict until the row is
ratified and scored by the follow-up. A miss at any corner would be recorded,
not relaxed.

The margins are an output, not an input: the bounds were fixed from the
31.25 / 15.625 ns phases and the 50 % allocation *before* looking at the
worst value. The margin of 2.45× at the stretch tier for the extracted DUT is
what remains after the 50 % reservation; it is not a guarantee about inputs
below 0.1 mV.

## Active DUT versus the DR-0004 experiment

- **Active DUT**: `sim/dut.json` `"active": "comparator-dr0001"` — schematic,
  `design/comparator.spice`, sha256 `0df618e73b1f0736…` (checked at drafting
  time). The schematic regeneration evidence for it is
  `…/20260910-125206-4805118`. The post-layout extracted binding
  `comparator-dr0001-layout` is selectable (`--dut`) and its regeneration
  record is `…/20261002-202641-baeffe5`; it is reference evidence for the
  ladder-centred convention, not the active binding.
- **DR-0004 experiment**: `comparator-dr0004-cascode-exp`
  (`sim/dut/experiment_comparator_dr0004_cascode.spice`, sha256
  `79dcc79fb6a876bc…`) is a **non-active, proposed** topology change. Its
  regeneration record `…/20261008-235219317743-7e61c52` stamps DUT id
  `comparator-dr0001` and path `design/comparator.spice` because the cascode
  sat there on the issue branch; its sha256 identifies it (DR-0004, "Where the
  proposed circuit lives"). It is listed above for sensitivity only: the
  cascode shifts the worst `td_od01` by +0.07 ns (+3.5 %) and the worst τ by
  +4.1 ps. It must not be read as evidence for the active DUT. If DR-0004 is
  ratified and becomes active, this row must be re-scored against the then-active
  binding; this record does not pre-decide that.

## Twin comparison (read, not transplanted)

Read at: `sg13g2-comparator` `origin/main` @
`7445379d11a0445f8b45624f6ac97ae5183f8330` and `sky130-comparator`
`origin/main` @ `016b67b886ae621232e8eca55a08fcffb8151977` (read-only local
clones; no files copied), and `gf180-sar-adc` @
`b8d494f121262e8d20b7cf2694d163bac66b0940` for the consumer budget.

| Aspect | `gf180-comparator` (this repo) | `sg13g2-comparator` @ `7445379d` | `sky130-comparator` @ `016b67b8` |
|---|---|---|---|
| Bench | `sim/comparator-regeneration/testbench/tb.json` | Same file, same structure: identical `analyses`, `measure` expressions for `tau_ps` and `resolve_decades`, `tran 5p 60n`, 35 ns `targ` window | **No `tau`/`resolve_decades` bench.** `sim/comparator-decision/run.py regen` sweeps differential input, one reset-to-evaluate edge per point, classifying each point `resolved` / `WRONG-POLARITY` / `NON-DECISION` against a 0.5·VDD differential threshold |
| Quantities | `td_od50/od1/od01`, `tau_ps`, `resolve_decades` at 45 PVT points | Same, 45 points, 1.08/1.20/1.32 V | Delay vs input over a sweep; PVT coverage is seven points (DR-005), not 45; sub-mV points can be UNRESOLVED (e.g. 0.5 mV at `ss`/−40 °C) |
| Metastability scored? | No (this DR proposes) | **Yes**, ratified in its DR-0002 Row 3: `τ ≤ 250 ps` worst point and `≤ 2.0 ns at 0.1 mV`, with a 10 ns strobe (33.3 MHz) | No scored τ or metastability row; its DR-004 Open items list "an explicit metastability-report requirement" as a candidate lever |
| Basis of bound | This record: application phase, 50 % reservation | Strobe width: `τ ≤ 250 ps ⇒ ≥ 40 τ ≈ 17 decades` per decision, plus 1.5× the measured worst τ; `2.0 ns` is 1.2× the measured worst 0.1 mV delay | n/a |
| Probability claim | Declined (above) | "negligible against any realistic input distribution" — a qualitative argument, no stated density or prefactor | none |

Similarities: the gf180 and sg13g2 benches are structurally identical for the
quantities this record uses (the `tb.json` measure expressions and `td=35n`
windowing match; the sg13g2 file says the window was ported from this repo).
Differences that matter: (1) the sky130 twin has no equivalent quantities, so
a definition shared by all three **cannot** exist without new sky130 bench
work; this record does not force one; (2) the sg13g2 twin bounds `τ` and a
0.1 mV delay from a 10 ns strobe, this record bounds the 0.1 mV delay from the
consumer's decide phase and does not score `τ`; (3) supply, strobe width and
device speed differ, so **no numeric bound is transplanted** — sg13g2's
`250 ps` and `2.0 ns` are context only (for comparison, this repo's
measured worst `τ` is 122.93 ps schematic / 205.77 ps extracted, and worst
`td_od01` is 1.956 / 3.190 ns). Keeping the bench structurally identical
across the two-PDK twin is preserved; the *scored* metric is allowed to differ
where the bound's basis differs, and the difference is recorded here.

## Alternatives considered

- **`τ ≤ X` bound (the sg13g2 form).** Not chosen: `τ` is a two-point finite
  difference with no `t0`, so a `τ` bound alone does not say a decision
  finishes in time; and the "≥ 40 τ" argument still needs the prefactor and
  density this repo lacks. Kept as a report-only diagnostic.
- **`P_unresolved = exp(−t_avail/τ)` at the worst corner (the issue's original
  sketch).** Not chosen: dimensionally incomplete (no overdrive scale or
  prefactor), uses `t_avail` in a place the measured `td_od1` would anchor, and
  yields figures such as `exp(−254) ≈ 10⁻¹¹⁰` that no evidence here supports.
- **Score `resolve_decades ≥ N`.** Not chosen: it is `td_od1/τ` in e-folds
  (including fixed delay), not a count of e-folds available in a phase; any N
  would be invented.
- **Bound `td_od01` at the observed worst value plus margin.** Rejected as a
  matter of principle: a bound derived from the result cannot fail.
- **Leave metastability as an unscored bench output.** Rejected: it contradicts
  `CLAUDE.md`'s "first-class" claim and gives integrators nothing to rely on.
- **New transient-noise Monte-Carlo bench now.** Not chosen: outside the
  "reuse existing measurements" scope, expensive on a shared worker, and
  premature before the consumer confirms the allocation. Listed as the route
  to a probability row.
- **A different overdrive rung (e.g. 1 mV, `td_od1`).** Not chosen: the
  consumer's half-LSB basis is 1.61 mV (`spec/consumers.md`), but the point of
  this row is behavior nearest the trip point, where 0.1 mV is the available
  floor.

## Limitations

- Deterministic, noise-free, mismatch-free (schematic) — a timing bound at one
  overdrive, not an error-rate claim. Inputs closer than 0.1 mV to the trip
  point are explicitly outside it.
- The 50 % reservation is an allocation, not a measurement, and is not yet
  confirmed by the consumer. Changing it changes both bounds linearly.
- The bench's 10 ns strobe-high window caps what it can certify (assumption 5).
- Extracted evidence uses a first-order lumped RC extraction and an
  offset-centred ladder; the schematic is the active binding.
- Worst-corner selection is on the 45-point grid only; there is no
  Monte-Carlo spread of τ or delay.
- If DR-0004 is ratified the evidence must be re-minted for the new active
  DUT.
- The bound uses the consumer's decide phase; a consumer with a shorter phase
  or different edge conventions needs its own allocation.

## Consequences

- **Good**: the first-class claim gets a falsifiable, application-derived
  bound that reuses an existing measurement and needs no new simulation; the
  e-fold/decade naming hazard and the unsupported `exp(−t/τ)` shortcut are
  written down before anyone scores against them.
- **Bad**: the row is a timing bound and **not** a probability, so it will not
  satisfy a reader who wants a failure rate. It makes integrators carry the
  dead-zone assumption. Its margin (2.45×–7.99×) is large partly because of the
  strobe and phase conventions, which could be read as a vacuous bound; it is
  not, since it is set from the budget and a 2.5× miss would fail it.
- **Ceremony cost**: adding a row means the DR-0002 two-key ceremony again; if
  it does not release, the row never exists and nothing changes.
- **Follow-up (excluded from this PR; only after a valid released ceremony)**:
  1. Update `README.md`, `spec/evidence-ledger.md` and
     `measurements/characterization-report.md` with per-corner target/stretch
     verdicts, evidence identity, worst corner and limitations, retaining
     misses.
  2. Extend `signoff/make_item5_envelope.py` and
     `signoff/tests/test_item5_envelope.py` for the supported row and its
     coverage semantics, including missing or unsupported evidence. There is no
     standalone metastability item in the eleven-item rulebook; the row belongs
     in item 5 (every-spec-row scoring) and item 8 (characterization summary);
     it does **not** propose a new checklist item or an unconditional T1 pass.
     A statistical claim would additionally need item 6's evidence requirements.
  3. Refresh item 8 with `signoff/make_item8_envelope.py`; preserve old
     evidence, bump the scoring revision where semantics change, and repin
     `signoff/block-manifest.json` and assertions in `signoff/verify-report.py`
     as needed.
  4. Validate with `python3 signoff/make_item5_envelope.py --check`,
     `python3 signoff/make_item8_envelope.py --check`,
     `python3 -m unittest discover -s signoff/tests`,
     `./signoff/regenerate.sh` and `python3 signoff/verify-report.py`, running
     generation in an isolated worktree.
  5. Revise this plan if the ratified statistic needs new simulation; it is not
     permission to manufacture probability evidence from `τ`.
- **Nothing in this PR touches** the README table, the evidence ledger,
  `signoff/`, any `sim/` record or any other decision record.

## Evidence provenance

| Item | Source |
|---|---|
| `tau_ps`, `resolve_decades` definitions | `sim/comparator-regeneration/testbench/tb.json:35-36`; check descriptions at `:56-64`; "first-class" note at `:100` |
| Bench clock and strobe | `sim/comparator-regeneration/testbench/tb_regeneration.spice:82` |
| Schematic per-corner data | `sim/comparator-regeneration/records/20260910-125206-4805118.{md,json}` |
| Extracted per-corner data and `dut_vos_v` | `…/20261002-202641-baeffe5.{md,json}` |
| DR-0004 experiment per-corner data | `…/20261008-235219317743-7e61c52.{md,json}` |
| Characterization narrative (τ 38.39–122.93 ps; 13.61–15.17) | `measurements/characterization-report.md`, "Decision time vs. overdrive — regeneration bench (and metastability)" |
| Noise floor | `sim/comparator-preamp-noise/records/20260910-125200-4805118.md` |
| Application phases | `spec/consumers.md` (decision speed row); `gf180-sar-adc@b8d494f` `spec/comparator-budget-memo.md` §6 |
| Active DUT | `sim/dut.json` (`"active"`), `design/comparator.spice` sha256 |
| Twin definitions | `sg13g2-comparator@7445379d` `sim/comparator-regeneration/testbench/tb.json`, `spec/decision-records/0002-target-spec-ratification.md` Row 3, record `20260916-021945-36773c7`; `sky130-comparator@016b67b8` `sim/comparator-decision/README.md`, `spec/decision-records/DR-004-comparator-preamp-supersession.md` |

All derived numbers above were recomputed from those JSON records and labeled
proposed; no record was edited.

## Ratification ceremony status

Per DR-0002 and the installed reviewer variants
(`ratification/ee-key/MANIFEST.md`, `ratification/market-key/MANIFEST.md`):
ratification is a **non-author EE-key** review (technical soundness) and a
**non-author market-key** review (competitiveness), each posting a
`<!-- RATIFY-KEY: <ee|market> verdict=… -->` marker on the PR, plus the
release (`loom:auto-merge-ok`) those keys clear.

| Key | Status at drafting time (2026-10-09) |
|---|---|
| EE key (non-author) | **pending** — not yet run; no marker exists on this PR |
| Market key (non-author) | **pending** — not yet run; no marker exists on this PR |
| Release (`loom:auto-merge-ok`) | **not released** |

The drafting agent cannot supply keys and treats neither its own review nor
ordinary PR approval as ratification. **Outcomes**: release → ratified claim
may be recorded by the merge; declined, missing or pending → this record stays
`proposed`, objections are recorded here (a proposed record may be revised in
its PR), and the ratified README table, ledger verdicts and signoff evidence
remain unchanged. This section describes status at drafting time; a later
ceremony outcome is recorded by revising this proposed record in the PR, not by
this draft.

## Spec lines affected

- `README.md#target-specification-ratified-via-dr-0002` — Small-overdrive
  resolution time (metastability) row — **new, PROPOSED only; takes effect
  only upon a valid released ceremony. This PR adds no row and changes no
  value.**
- `README.md#target-specification-ratified-via-dr-0002` — the five ratified
  rows (offset, noise, decision time, kickback, supply/power) — unchanged; not
  re-ratified.
