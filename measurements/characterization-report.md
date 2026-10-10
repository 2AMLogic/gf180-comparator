# gf180-comparator characterization report

- **Report date**: 2026-09-21
- **Subject**: `comparator-dr0001` — schematic-provenance netlist
  `design/comparator.spice` (sha256 `0df618e73b1f0736`), the topology decided
  by [DR-0001](../spec/decision-records/DR-0001-comparator-topology.md):
  a resistively-loaded NMOS differential preamplifier into a StrongARM latch
  with isolation inverters and a NOR SR output latch, biased at `dut_ib = 10 µA`
  (20 µA preamp tail) and `dut_vcm = 1.65 V` (mid-rail, a standalone choice —
  no CDAC or driving circuit to inherit a common mode from).
- **Simulation context** (per record, not shared): the four original
  schematic records (offset-MC `20260910-124917-4805118`, preamp-noise
  `20260910-125200-4805118`, regeneration `20260910-125206-4805118`, kickback
  `20260910-125341-4805118`) were run locally with gf180mcuD @ open_pdks
  `c6d73a35f524070e85faff4a6a9eef49553ebc2b`, ngspice-46 / Python 3.14.7,
  at commit `4805118`, on the 45-point full-factorial PVT grid (process
  `tt/ff/ss/fs/sf` × −40/27/125 °C × 2.97/3.30/3.63 V). The later records
  cited below differ: the whole-comparator offset records
  (`20261010-013540611508-4a4df37`, `20261010-021500046481-d84e59d`) and the
  both-node kickback record (`20261010-022609774981-bf851ec`) were produced
  by `klt sim` (client 0.7.0, fleet runner klt 0.5.0, ngspice 46, backend
  `batch`, AWS Spot fleet) at their own recorded commits, and the extracted
  (post-layout) records (`20261002-202641-baeffe5`, `20261002-211343-6346fad`)
  were produced locally by the extracted-DUT path at their own commits. Each
  cited record's own header is the authority for its toolchain, commit and
  job ids.
- **Scored against**: the target-specification table as **ratified by
  [DR-0002](../spec/decision-records/DR-0002-target-spec-ratification.md)** —
  the act being the two-key re-ratification on the record's PR
  [#74](https://github.com/2AMLogic/gf180-comparator/pull/74) (non-author EE
  key + market `RATIFY-KEY` reviews and the merge as the record), per the
  operator ruling of 2026-10-02 on
  [issue #3](https://github.com/2AMLogic/gf180-comparator/issues/3), which
  ruled that the original 2026-09-19 flip on PR #27's merge was **not** the
  ratification act (see [`README.md`](../README.md)'s "Ratification status").
  DR-0002's Decision table is the authoritative ratified source here. This
  report follows DR-0002's own Consequences rule: the two rows with gaps are reported **as
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

  That local command surface covers the four original benches on a
  workstation with the pinned PDK. It is **not** to be used for multi-corner or
  Monte Carlo grids on a shared dispatch worker, and it does not cover
  `comparator-offset-tran` (fleet-only). The fleet campaigns are reproduced
  with `KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py <bench>` (see
  [`sim/README.md`](../sim/README.md)); fleet requests support the schematic
  DUT only, so extracted records use the local post-layout path, and noise
  has no fleet expression (single nominal point on a shared worker, full grid
  on a workstation).

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

## Scored summary — five ratified rows

| Ratified row (DR-0002) | Target | Stretch | Measured (nominal `tt_27c_3.30v`) | Measured (45-point grid) | Scored verdict |
|---|---|---|---|---|---|
| Offset sigma | ≤ 15 mV 3σ | ≤ 8 mV 3σ | whole comparator + conservative load-R budget: 3σ ≈ 3.15 mV (`tt_27c_3.30v`, 9-point record); preamp-only DC bench 2.80063 mV | whole comparator (schematic, scored): 2.994–3.795 mV 3σ, binding `ff_125c_3.63v` (`20261010-021500046481-d84e59d`); preamp-only DC bench 2.796–2.807 mV (diagnostic) | **meets target and stretch at 45/45 corners** (schematic, one seed, N = 200 per point) |
| Input-referred noise | ≤ 1.0 mV rms | ≤ 0.6 mV rms | 91.25 µV rms | 66.82–128.83 µV rms | **meets target and stretch at every corner** |
| Decision time (50 mV overdrive) | ≤ 1.5 ns | ≤ 0.8 ns | schematic 0.708 ns; extracted 1.158 ns | schematic 0.464–1.237 ns; extracted 1.553–2.034 ns at the 7 failing corners (`20260910-125206-4805118`, `20261002-202641-baeffe5`) | **schematic: meets target 45/45, misses stretch 16/45** (worst 1.237 ns at `ss_125c_2.97v`); **extracted: misses target at 7/45, stretch at 44/45** (worst 2.034 ns at `ss_125c_2.97v`) |
| Kickback into 1 kΩ | ≤ 5 mV | ≤ 2 mV | schematic 7.60 mV (positive node); extracted 10.03 mV | schematic 4.53–10.01 mV positive node (`20260910-125341-4805118`); both-node schematic aggregate sets at the positive node 45/45 (`20261010-022609774981-bf851ec`); extracted 8.49–14.58 mV (`20261002-211343-6346fad`, positive node only) | **schematic: misses target 44/45 (both-node record: 1/45 within target), stretch 45/45; extracted: misses target 45/45, stretch 45/45** |
| Supply / power | ≤ 1 mW avg, one decision per clock edge at a stated clock rate (TBD) | ≤ 500 µW avg | static current 28.4 µA ≈ 94 µW (diagnostic) | static current 27.7–29.7 µA ≈ 82–108 µW (diagnostic) | **average power UNSCORED** — no clock rate is ratified (TBD, pending [#125](https://github.com/2AMLogic/gf180-comparator/issues/125)); static power is a diagnostic only and is not a pass |

Two rows (offset, noise) clear both bounds at every corner of their
schematic evidence. Two rows carry real, known gaps, and the power row is not
scored at all —
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
Scored on this preamp-only record alone: meets both bounds at every corner;
the row's scored verdict, however, rests on the whole-comparator total below.

**Scope of this DC record.** It excludes the decision stage's own offset
(the latch has no DC operating point) and load-resistor mismatch (this PDK
does not model it at all; the `sig_rpair_uv = 0` control documents the null).
So the 2.80 mV 3σ above is the **preamp-only** offset, a lower bound on the
total; it is retained as the historical/diagnostic figure. The scored offset
is the whole-comparator evidence in the next subsection (full 45-point grid,
2.994–3.795 mV 3σ), where both missing terms are measured or budgeted. Layout-induced systematic offset is not in either record (both are
schematic, `provenance: schematic`).

**Total offset: latch measured, load-R derived (issue #157).** Cited evidence:
[`sim/comparator-offset-tran/records/20261010-013540611508-4a4df37.md`](../sim/comparator-offset-tran/records/20261010-013540611508-4a4df37.md)
(fleet job `klt-sim-816fb60826f4`). Reproduce with
`KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-offset-tran`.

*Method.* [`sim/comparator-offset-tran/`](../sim/comparator-offset-tran/README.md)
clocks the *whole* comparator through a 64-level, ±5.04 mV input staircase
(0.16 mV steps), one decision per level. It uses N = 200 mismatch draws per
PVT point with seed 20260909, the same seed as the DC bench, on a **reduced**
grid for the first record (tt/ss/ff × −40/27/125 °C at 3.3 V); the full grid follows below. The per-draw trip point is the
midpoint of the one-step bracket. The staircase's quantisation variance,
step²/12, is subtracted in quadrature (σ_q = 0.046 mV). On the same draw it also
measures the DC-equivalent preamp offset, so the latch contribution is a
paired measurement. The **derived, not simulated** budget for the
`ppolyf_u_1k` load pair is σ(ΔR/R)_pair = A_R/√(WL) = 0.021 µm/√(1 × 120 µm²)
= 0.19 %. A_R comes from the foundry's commented-out `par_r` for the sibling
`ppolyf_u` device in `sm141064.ngspice`, and the scored variant triples it as
a conservative assumption. The budget is input-referred through the measured
per-corner I_D·R/A_v and added in quadrature.

*Result.* At `tt_27c_3.30v`:

- Whole-comparator σ is 0.966 mV (3σ 2.897 mV), against the DC bench's 0.934 mV.
- **The decision stage (latch) contributes a paired 1σ of 0.333 mV.**
- The load-R term is 0.136 mV 1σ, or 0.409 mV with the conservative A_R.
- The scored total, with the conservative load-R term, is **3.146 mV 3σ**.

Across the 9 points:

- The simulated whole-comparator 3σ spans 2.897–3.439 mV.
- The latch 1σ spans 0.203–0.608 mV. It is largest at `ff_125c`, where the preamp gain is lowest (11.5×), so the gain divides the latch's own offset least.
- The scored total spans 3.146–**3.725 mV** (worst `ff_125c_3.30v`).

Scored against the ratified row, the total **meets the ≤ 15 mV target and the ≤ 8 mV stretch at 9/9 points.** The ratified bound is unchanged.

*Full 45-point grid (issue #200).* Cited evidence:
[`sim/comparator-offset-tran/records/20261010-021500046481-d84e59d.md`](../sim/comparator-offset-tran/records/20261010-021500046481-d84e59d.md)
(fleet jobs `klt-sim-ee7ad68415d2`, `klt-sim-a503009e268a`, `klt-sim-031f74d456a0`; source bundle at
clean commit `d84e59d`; reproduce with
`KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-offset-tran`). Same method,
seed 20260909 and N = 200, extended to tt/ss/ff/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V: 45 of 45
points, 200 valid draws each, no failed unit and no staircase saturation (the mean offset stays within
±0.13 mV of the ±5.04 mV range).

| 3σ input-referred offset, 45 points | range | binding point |
|---|---|---|
| DC bench, preamp only (diagnostic, separate record) | 2.796–2.807 mV | `sf_125c_3.30v` |
| whole comparator, **simulated** | 2.808–3.515 mV | `ff_125c_3.63v` |
| **whole comparator + conservative load-R budget (scored)** | **2.994–3.795 mV** | **`ff_125c_3.63v`** |

The latch's paired 1σ is 0.184–0.659 mV (simulated, largest at `ff_125c_3.63v`); the load-R 1σ is
0.342–0.501 mV at the conservative 3× coefficient (**derived, not simulated**: the PDK models no
`ppolyf_u_1k` mismatch). **The total meets the ≤ 15 mV target and the ≤ 8 mV stretch at 45/45
points** (2.1× margin on the stretch at the binding point), so the offset row now rests on the
whole comparator at every corner rather than on the preamp alone. The ratified bound is unchanged.
Limitations: schematic DUT, one seed, 5 % sigma precision per point, hand-budgeted resistor term.

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
carries the latch time constant `tau_ps` and `td_od1_over_tau` at **every**
PVT point (τ = 38.39–122.93 ps; `td_od1_over_tau` = 13.61–15.17 e-folds of
full clock-to-output delay over τ — recorded under its deprecated alias
`resolve_decades`, which despite the name is an e-fold ratio, not decades;
a report-only diagnostic per DR-0005), so any
metastability statement this repo makes is computed from a measured
worst-corner time constant rather than asserted from a typical-corner delay.

**Result (schematic).** 0.708 ns at nominal; grid 0.464–1.237 ns across all 45 corners.
Scored against the ratified row: **meets the ≤ 1.5 ns target at 45/45
corners; misses the ≤ 0.8 ns stretch at 16/45**.

**Result (extracted, post-layout).** The extracted-DUT record
[`20261002-202641-baeffe5`](../sim/comparator-regeneration/records/20261002-202641-baeffe5.md)
reports 1.158 ns at nominal (+63.6 % over schematic) and 2.034 ns worst case at
`ss_125c_2.97v`: **misses the ≤ 1.5 ns target at 7/45 corners
(1.553–2.034 ns) and the ≤ 0.8 ns stretch at 44/45**, a recorded miss accepted
as known at ratification. Schematic and extracted verdicts are distinct
evidence and are not merged. See
[Known gaps](#known-gaps-scored-as-misses-not-dropped).

**Supply / power: static current is diagnostic; average power is unscored.**
The same record carries the static supply current (`i_static_ua`, 45 points):
28.4 µA at nominal (≈ 94 µW at 3.3 V) and 27.7–29.7 µA (≈ 82–108 µW at
2.97–3.63 V) across the grid. These are **diagnostic values only**. The
ratified row's bound is an *average* power at one decision per clock edge at a
stated clock rate, and that clock rate is still TBD (choosing one needs a
decision record; tracked on
[#125](https://github.com/2AMLogic/gf180-comparator/issues/125)). Static
current times supply is not that quantity, so **no pass or fail verdict is
issued for the supply/power row**; no rate is invented here. The
switching-energy column (`e_dec_fj`) is recorded but deliberately carries
**no** check in this record — the residue of the charge integral is dominated
by numerical artefact, and the record refuses to invent a floor that would
pass for the wrong reason.

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

**Result (schematic).** 7.60 mV peak at nominal (`tt_27c_3.30v`), positive input node only; grid 4.53–10.01 mV.
Scored against the ratified row: **misses the ≤ 5 mV target at 44/45 corners
and the ≤ 2 mV stretch at 45/45**. The later both-node schematic record
[`20261010-022609774981-bf851ec`](../sim/comparator-kickback/records/20261010-022609774981-bf851ec.md)
(fleet) scores the row-facing peak as the maximum of both nodes: the positive
node sets it at 45/45 corners (negative node 4.24–9.91 mV vs positive
4.53–10.01 mV), 1/45 within target, 0/45 within stretch. Which source feeds
item-5 scoring is a separate decision (#204) and is not changed here.

**Result (extracted, post-layout).**
[`20261002-211343-6346fad`](../sim/comparator-kickback/records/20261002-211343-6346fad.md)
reports 10.03 mV at nominal (+32 % over schematic) and 8.49–14.58 mV across the
grid (positive node only; extracted both-node evidence is pending): **misses the target at 45/45 and the stretch at 45/45.** See
[Known gaps](#known-gaps-scored-as-misses-not-dropped). Supply is the
strongest single axis (the peak moves 30–61 % along it): the injected
charge — and with it the peak in mV — scales with the rail, growing
toward the high-supply corners.

## Known gaps (scored as misses, not dropped)

Two ratified rows are missed at some or all corners (shown for schematic and
extracted evidence in the summary table); the power row is unscored, not missed. DR-0002 ratified both
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
   post-layout extraction adds capacitance at the input, and the extracted
   record bears that out: 8.49–14.58 mV, worse than the schematic's
   4.53–10.01 mV at every corner. The extracted-decision-time miss (7/45
   against the target) is likewise recorded above.

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
grid, meets both bounds at every corner). The whole-comparator total (preamp + latch + derived load-R
budget, 2.994–3.795 mV 3σ over the same 45 points, issue #200) is a separate, additive record; it is the
value item-5 scoring uses, and the preamp-only record above remains the item-6 yield source.

## What this report does not claim

- Most numbers above are **schematic-level (`provenance: schematic`, no
  parasitics)**; the extracted decision-time and kickback figures are labelled
  as such and come from their own records. Noise, offset and the whole-comparator
  trip-point have no extracted-DUT record, and extracted kickback covers the
  positive node only. No post-layout signoff beyond what the ledger records is
  claimed.
- **Average power is not scored** (clock rate TBD, #125); static power is
  diagnostic.
- No number here was produced outside `sim/`'s append-only evidence trail —
  an unverifiable figure in a narrative document is worth nothing in this
  repo, which is why every table cell above traces to a committed record.
