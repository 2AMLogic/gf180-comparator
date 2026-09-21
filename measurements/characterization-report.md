# gf180-comparator characterization report

- **Report date**: 2026-09-21
- **Subject**: `comparator-dr0001` — schematic-provenance netlist
  `design/comparator.spice` (sha256 `0df618e73b1f0736`), the topology decided
  by [DR-0001](../spec/decision-records/DR-0001-comparator-topology.md):
  a resistively-loaded NMOS differential preamplifier into a StrongARM latch
  with isolation inverters and a NOR SR output latch, biased at `dut_ib = 10 µA`
  (20 µA preamp tail) and `dut_vcm = 1.65 V` (mid-rail, a standalone choice —
  no CDAC or driving circuit to inherit a common mode from).
- **Simulation context** (identical in all four cited records): gf180mcuD @
  open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, ngspice-46 /
  Python 3.14.7, evidence committed at `4805118`, 45-point full-factorial PVT
  grid (process `tt/ff/ss/fs/sf` × −40/27/125 °C × 2.97/3.30/3.63 V) per
  campaign.
- **Scored against**: the target-specification table as **ratified by
  [DR-0002](../spec/decision-records/DR-0002-target-spec-ratification.md)** —
  the act being that record's PR (#27) being approved and merged on 2026-09-19
  (the operator's PR approval *is* the ratification act, per
  [2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)). DR-0002's
  Decision table is the authoritative ratified source here. Residual
  pre-ratification wording that still reads "proposed"/"DRAFT" in
  [`README.md`](../README.md)'s target-spec heading and `spec/README.md`'s
  status paragraph is a documentation-sync gap flagged on #25 and #24 and
  handled separately; it does not unmerge DR-0002, and this report follows
  DR-0002's own Consequences rule: the two rows with gaps are reported **as
  misses against a ratified bar, not as "still DRAFT, not a verdict."**

## What this report is, and what `sim/characterize.sh` does (reproducibility)

Per this repo's standing bar
([`spec/README.md`](../spec/README.md) → "Review bar"), every cited result must
be regenerable from a single documented command per experiment. It is, and the
split of labor is:

- **`sim/characterize.sh` does NOT emit this narrative report.** It is the
  one-command **numeric driver**: `smoke` (one nominal point per campaign,
  seconds, writes no evidence), `characterize` (the full 45-point PVT campaign
  per experiment), and `selftest` (the harness's own acceptance test). Each
  campaign it runs goes through `sim/run_corners.py` and mints a **new,
  dated, append-only evidence record** under `sim/<experiment>/records/` — a
  re-run never overwrites a committed record. The full command surface is:

  ```bash
  python3 sim/run_corners.py --check-env   # PDK, pinned toolchain, DUT contract
  ./sim/characterize.sh smoke              # every bench, nominal point, seconds
  ./sim/characterize.sh characterize       # full 45-point PVT campaign per bench
  ./sim/selftest.sh                        # harness acceptance test
  ```

- **This file is a separate, hand-written narrative** that scores those
  committed records against the now-ratified table. Every number below cites
  the specific record file it comes from (append-only evidence with raw
  per-corner ngspice logs committed alongside), never a bare inline restatement.
  A future re-run of `./sim/characterize.sh characterize` mints *new* records
  scoring the same design; it does not regenerate this document, though its
  output can be compared against the records cited here — and does compare
  cleanly: a nominal-point smoke re-run on the tree this report was written
  against reproduced the deterministic rows exactly (`vn_in_uv` = 91.2549 µV,
  `td_od50_ns` = 0.708061 ns, both to all recorded digits; kickback peak
  7.597 vs the recorded 7.599 mV, a solver-tolerance-scale agreement), and
  the Monte-Carlo row within the record's own stated statistical precision
  (1/√(2N) ≈ 5 % on σ at N = 200 draws; observed nominal 3σ 2.725 vs the
  recorded 2.801 mV — the same seeded 200-draw discipline, replayed on this
  host, agreeing well inside the precision the record commits to; both
  figures sit far inside the ratified bounds).

## Scored summary — five ratified rows, four cited records

| Ratified row (DR-0002) | Target | Stretch | Measured (nominal `tt_27c_3.30v`) | Measured (45-point grid) | Scored verdict |
|---|---|---|---|---|---|
| Offset sigma | ≤ 15 mV 3σ | ≤ 8 mV 3σ | 3σ = 2.80063 mV | 2.79617–2.80688 mV 3σ | **meets target and stretch at every corner** |
| Input-referred noise | ≤ 1.0 mV rms | ≤ 0.6 mV rms | 91.25 µV rms | 66.82–128.83 µV rms | **meets target and stretch at every corner** |
| Decision time (50 mV overdrive) | ≤ 1.5 ns | ≤ 0.8 ns | 0.708 ns | 0.464–1.237 ns | **meets target at 45/45; misses stretch at 16/45** (worst 1.237 ns at `ss_125c_2.97v`) |
| Kickback into 1 kΩ | ≤ 5 mV | ≤ 2 mV | 7.60 mV | 4.53–10.01 mV | **misses target at 44/45, stretch at 45/45** (only `ss_-40c_2.97v` clears the target) |
| Supply / power | ≤ 1 mW avg | ≤ 500 µW avg | 28.4 µA ≈ 94 µW | 27.7–29.7 µA ≈ 82–108 µW | **meets target and stretch at every corner** |

Three rows clear both bounds everywhere. Two rows carry real, known gaps —
addressed head-on under [Known gaps](#known-gaps-scored-as-misses-not-dropped)
below rather than absorbed.

## Experiment narratives

### Offset sigma — Monte Carlo on local mismatch

Cited evidence:
[`sim/comparator-offset-mc/records/20260910-124917-4805118.md`](../sim/comparator-offset-mc/records/20260910-124917-4805118.md)
(45-corner table + matched JSON, raw logs under `corners/`). Reproduce with
`python3 sim/run_corners.py comparator-offset-mc`.

**Method, as committed.** The headline statistical story this repo's
`CLAUDE.md` demands: run counts, seeds, and the σ derivation are all in the
record. 200 mismatch draws per PVT point, seeded with `setseed 20260909`, the
same seed at every corner (common random numbers — so σ movement across the
grid is a real PVT effect, not sampling noise); mismatch-only
(`sw_stat_mismatch = 1`, global process variation left to the corner axis so
the two are never confounded); statistical precision on each σ is
1/√(2N) = 5.0 % at N = 200. Offset per draw is −dv(0 mV)/A_v with the gain
A_v measured **on the same draw** from one `dc` sweep — two instances would
have independent mismatch draws and expose the measurement to an offset
difference instead of just the gain. The `av_sigma_pct` column is the check
that the draw really was preserved between the two points.

**Result.** 1σ = 0.933543 mV, 3σ = 2.80063 mV at the nominal
`tt_27c_3.30v` corner; the grid moves 3σ only 2.79617–2.80688 mV —
corner-invariant to within 0.4 %, a direct consequence of the offset being
dominated by the input pair's mismatch physics rather than by the bias point.
Scored against the ratified row: **meets the ≤ 15 mV target and the ≤ 8 mV
stretch at every corner, by more than a factor of two on the stretch.**

**What the record does not claim.** The decision stage's own offset (no DC
operating point — referred to the input it is divided by the measured ≈18×
gain); load-resistor mismatch (this PDK does not model it at all — the
`sig_rpair_uv = 0` control documents the null); and any layout-induced
systematic offset (schematic-level record, `provenance: schematic`).

### Input-referred noise — preamplifier `.noise`

Cited evidence:
[`sim/comparator-preamp-noise/records/20260910-125200-4805118.md`](../sim/comparator-preamp-noise/records/20260910-125200-4805118.md).
Reproduce with `python3 sim/run_corners.py comparator-preamp-noise`.

**Method, as committed.** Total integrated output noise **divided by the
measured DC gain** — not ngspice's `inoise_total`, whose direct use once
produced a 200×-magnitude error in the sibling repo's own record (both the
method and the caution are ported from `gf180-sar-adc`'s equivalent bench and
both quantities sit in the table so a reader can see them agree). Integrated
to 1 GHz, not to an assumed signal bandwidth — a comparator samples its input
noise at the decision instant rather than filtering it, so the band-limited
total is the relevant quantity. The decision stage is instantiated **in
reset** so the front end's noise bandwidth is set by the capacitance it
actually drives (omitting it would over-state bandwidth and noise; inventing a
lumped capacitor instead would make the answer depend on the invention).
Mismatch is off (noise and offset budgeted separately), and `fnoicor` is at
the PDK default 0 (as-extracted) with the flicker fraction recorded at every
corner (0.32–1.14 %) so a reader can rescale the flicker part for the
worst-case setting and see it does not change a verdict.

**Result.** 91.25 µV rms at nominal — an order of magnitude below the
≤ 1.0 mV target; grid 66.82–128.83 µV rms, the worst case at
`ff_125c_3.63v`. Temperature is the dominant axis (noise rises as gain
falls with temperature). Scored against the ratified row:
**meets the ≤ 1.0 mV target and the ≤ 0.6 mV stretch at every corner.**

**What the record does not claim.** The decision stage's own noise — `.noise`
cannot reach a reset-and-regenerate structure at all (no DC operating point);
referred to the input it is divided by the ≈18× gain, which is why the front
end is where the budget is closed.

### Decision time vs. overdrive — regeneration bench (and metastability)

Cited evidence:
[`sim/comparator-regeneration/records/20260910-125206-4805118.md`](../sim/comparator-regeneration/records/20260910-125206-4805118.md).
Reproduce with `python3 sim/run_corners.py comparator-regeneration`.

**Method, as committed.** The delay at 50 mV overdrive (`td_od50_ns`) is
measured on the **second strobe**, where the output must actively flip a latch
holding the opposite answer — every instance is driven by a PWL that changes
sign between the two strobes, and the `dout_*_first`/`dout_*_end` polarity
pair is checked so no delay depends on which state the output started in.
Timing thresholds are supply-normalized (each output crossed at 0.5× its own
supply), so the ±10 % supply axis measures the circuit rather than a fixed
threshold artefact. The `targ` window opens at 35 ns — after the first strobe
and after the 20–21 ns input flip has settled (a real latch's SR output is a
bistable with no defined power-up state; an unwindowed search locks onto that
resolution and can report a **negative** delay — observed −38.2 ns — instead of
the decision under test). Solver tolerances are deliberately tightened
(reltol 1e-4, vntol 1e-9; abstol 1e-13, not the kickback deck's 1e-15 — the
latter stalls six of the 45 points' first transient step) so a
sub-nanosecond delay is resolved rather than smeared; the record states a
re-run changing any of these is not bit-comparable. Mismatch is off —
regeneration time and offset are separable effects, budgeted separately.

**Metastability is a first-class row here, per `CLAUDE.md`.** The same record
carries the latch time constant `tau_ps` and `resolve_decades` at **every**
PVT point (τ = 38.39–122.93 ps; 13.61–15.17 decades of resolution), so any
metastability statement this repo makes is computed from a measured
worst-corner time constant rather than asserted from a typical-corner delay.

**Result.** 0.708 ns at nominal; grid 0.464–1.237 ns across all 45 corners.
Scored against the ratified row: **meets the ≤ 1.5 ns target at 45/45
corners; misses the ≤ 0.8 ns stretch at 16/45** — see
[Known gaps](#known-gaps-scored-as-misses-not-dropped).

**Supply / power rides the same record.** The static supply current
(`i_static_ua`, measured in the same 45-point run) is 28.4 µA at nominal —
≈ 94 µW at 3.3 V — and 27.7–29.7 µA (≈ 82–108 µW at 2.97–3.63 V) across the
grid. Scored against the ratified supply/power row: **meets the ≤ 1 mW
target and the ≤ 500 µW stretch at every corner.** The switching-energy
column (`e_dec_fj`) is recorded but deliberately carries **no** check in this
record — the residue of the charge integral is dominated by numerical
artefact, and the record refuses to invent a floor that would pass for the
wrong reason.

### Kickback — decision-edge disturbance into the input

Cited evidence:
[`sim/comparator-kickback/records/20260910-125341-4805118.md`](../sim/comparator-kickback/records/20260910-125341-4805118.md).
Reproduce with `python3 sim/run_corners.py comparator-kickback`.

**Method, as committed.** Three instances per corner, none driven from an
ideal voltage source — an ideal source restores the injected charge instantly
and reports ≈ 0 kickback however bad the circuit is, which the record calls
the standard way this measurement is faked. Instance A measures the **peak**
disturbance through the 1 kΩ source impedance the ratified row is stated at;
instances B and C sit at 1 pF nodes through 1 GΩ (RC = 1 ms against a ~30 ns
cycle) and measure the **residual**, split so only the signal-dependent part
(`kick_sigdep_nv`) is treated as irreducible — a residue-independent kick is
indistinguishable from offset and is cancelled the same way, which is why B
and C sit at 1 mV and 100 mV residues. The input node is a **lumped
capacitance**: conservative for the residual (no path to restore charge),
optimistic for the peak (no distributed series resistance) — which is why the
peak is reported separately rather than folded into one number. Mismatch is
off, and the resolution floor (~1 µV, ngspice `meas`'s ~6 significant digits)
is documented in the table itself, with `kick_resid_small_nv` measuring the
same quantity through a near-0 V-referenced probe ~1000× finer. The coupling
path is the **input pair's own C_gd** (`XMIP`/`XMIN` of
`comparator_dut_analog`) — a property of the real devices per DR-0001, not
the placeholder DUT's invented `c_fb` stand-in the earlier placeholder-era
records used.

**Result.** 7.60 mV peak at nominal (`tt_27c_3.30v`); grid 4.53–10.01 mV.
Scored against the ratified row: **misses the ≤ 5 mV target at 44/45 corners
and the ≤ 2 mV stretch at 45/45** — see
[Known gaps](#known-gaps-scored-as-misses-not-dropped). Supply is the
strongest single axis (the peak moves 30–61 % along it): the injected
charge — and with it the peak in mV — scales with the rail, growing
toward the high-supply corners.

## Known gaps (scored as misses, not dropped)

Two ratified rows are missed at some or all corners. DR-0002 ratified both
bounds **unchanged** — ratifying a bound is agreeing what to measure against,
not asserting the design meets it — and presented the accept-vs-revise
tradeoff for each; the PR's approval as drafted enacted "accept the gap,
record it as known." Both are stated here exactly as DR-0002's Consequences
require: as misses against a ratified bar.

1. **Decision-time stretch bound — missed at 16/45 corners.** The ≤ 1.5 ns
   target is met at every corner (worst 1.23747 ns at `ss_125c_2.97v`); the
   ≤ 0.8 ns stretch is exceeded at the 16 slow/hot/low-supply corners
   (enumerated exactly as in DR-0002's tradeoff section, re-verified against
   the record's per-corner table): the 125 °C row across
   `tt_125c_2.97v`/`3.30v`/`3.63v`, `ff_125c_2.97v`, `ss_125c_2.97v`/`3.30v`/`3.63v`,
   `fs_125c_2.97v`/`3.30v`, `sf_125c_2.97v`/`3.30v`/`3.63v`, plus
   `ss_-40c_2.97v`, `ss_27c_2.97v`/`3.30v`, and `sf_27c_2.97v`. Worst case is
   the canonical worst PVT slice `ss_125c_2.97v` at 1.237 ns — the strongest
   corner is `ff_-40c_3.63v` at 0.464 ns, so the same silicon spans
   stretch-miss to 2×-inside-stretch purely on PVT.

2. **Kickback target and stretch — missed.** This is the larger of the two
   gaps and the one DR-0001 named as the consequence most likely to need
   revisiting first. Target (≤ 5 mV): missed at 44/45 corners — only
   `ss_-40c_2.97v` clears it, at 4.528 mV. Stretch (≤ 2 mV): missed at
   45/45 — the best-case corner still exceeds the stretch bound by more than
   2×. DR-0002's Consequences additionally record the direction of travel:
   post-layout extraction can only **add** capacitance at the input, so the
   schematic-level miss here is expected to widen, not close, in the layout
   pass — the noise numbers are the conservative ones (parasitics lower
   measured noise), and the kickback numbers are *not*.

A future sizing change (DR-0002's Option B) would go through a follow-on
decision record revising the affected row's bound or the input pair's `C_gd`
contribution; per this repo's rules (`CLAUDE.md`, `sim/README.md`), no bound
is relaxed here to make a result pass.

## Consistency with sibling scoring

The offset-sigma narrative above is deliberately keyed to the same sources
sibling issue #24 (T1 item 6, Monte-Carlo scoring) scores from — DR-0002's
Decision table and the same
[`20260910-124917-4805118`](../sim/comparator-offset-mc/records/20260910-124917-4805118.md)
record — so this report and `README.md`'s offset-sigma row remain numerically
consistent by construction (2.80 mV 3σ nominal, 2.796–2.807 mV 3σ across the
grid, meets both bounds at every corner).

## What this report does not claim

- Every number above is **schematic-level, `provenance: schematic`, no
  parasitics**. Layout, DRC/LVS and post-layout re-simulation are not done;
  the direction each row moves post-layout is recorded (noise improves,
  kickback worsens), not the magnitude.
- No number here was produced outside `sim/`'s append-only evidence trail —
  an unverifiable figure in a narrative document is worth nothing in this
  repo, which is why every table cell above traces to a committed record.
