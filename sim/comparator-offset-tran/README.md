# `sim/comparator-offset-tran/`

**Total input-referred offset of the whole comparator**, by transient Monte
Carlo: preamp + StrongARM latch + SR output latch, with the latch's own
mismatch in the trip point. Closes the disclosed gap in
[`sim/comparator-offset-mc/`](../comparator-offset-mc/README.md), whose DC
sweep runs on the analog partition only and therefore cannot see the
decision stage, and which cannot see the `ppolyf_u_1k` load-pair mismatch the
PDK does not model (issue #157).

It is **additive**: the DC bench stays as the preamp-only number and its
records are untouched. This bench does not alter any ratified bound; a miss,
if there is one, is recorded as a miss.

Twin-bench definition: same `tb.json` + `tb_*.spice` + `records/` layout as
the other four benches, same `setseed 20260909` + `reset` draw convention
(seed common to every PVT point, so movement across the grid is a PVT effect).

## Status: measured on the full 45-point grid (record `20261010-021500046481-d84e59d`)

Issue #200 extended the nine-point reference below to the whole PVT grid.
Record [`records/20261010-021500046481-d84e59d.md`](records/20261010-021500046481-d84e59d.md): **45 of 45 PVT points x N = 200
valid draws** (tt/ss/ff/fs/sf x -40/27/125 C x 2.97/3.30/3.63 V; 9,000
transients), no named problem, `reference: true`, source bundle at clean
commit `d84e59d`. Seed 20260909 (common to every point), `vary: mismatch`,
ngspice pinned to one thread per unit.

| quantity | value over the 45 points | worst / binding point |
|---|---|---|
| whole-comparator, simulated 3σ (`vos_3sig_tran_mv`) | 2.808–3.515 mV | `ff_125c_3.63v` |
| latch term, paired 1σ (`sig_latch_mv`, simulated) | 0.184–0.659 mV | `ff_125c_3.63v` |
| load-R hand budget 1σ, 3× conservative (`sig_rload_cons_mv`, **derived, not simulated**) | 0.342–0.501 mV | `ss_125c_2.97v` |
| mean offset (`mean_vos_tran_uv`, simulated) | -126.4 – +118.4 uV | `sf_27c_3.63v` / `ss_-40c_3.63v` |
| **total incl. conservative load-R (`vos_3sig_total_cons_mv`, scored)** | **2.994–3.795 mV** | **`ff_125c_3.63v`** |

**Score: within the ≤ 15 mV target and the ≤ 8 mV stretch at 45/45 points**
(the binding corner has 2.1× margin on the stretch). The ratified bound is
unchanged. Compared with the nine-point record the binding corner moves from
`ff_125c_3.30v` (3.725 mV) to `ff_125c_3.63v` (3.795 mV): +0.07 mV, so the
fs/sf and ±10 % supply points add little to the sigma, and the new extremes
did not saturate the staircase. The mean offset stays within ±0.13 mV, far
inside the ±5.04 mV staircase. What is simulated versus derived: the scored
total adds the derived load-R term (at most 0.50 mV 1σ, conservative) in
quadrature to the simulated sigma; `vos_3sig_tran_mv` is the purely simulated
3σ. The preamp-only DC bench (2.796–2.807 mV) stays as its own diagnostic
record.

Limitations: schematic DUT only (no extracted-layout statistics); single seed
(common random numbers across points, so N is effectively 200, no seed
replication); sigma precision 1/sqrt(2N) = 5 % per point; the resistor term is
a cited-coefficient hand budget; the common-mode convention is held at the
bench's 1.65 V (the common-mode window is issue #182).

**Debug probes before the campaign (not evidence).** One-draw local
`ngspice -b` runs at the newly covered extremes (`fs_-40c_2.97v`,
`sf_-40c_2.97v`, `fs_125c_3.63v`, `sf_125c_3.63v`, `ss_125c_2.97v`,
`ff_-40c_3.63v`) gave finite `.meas` values, positive gain, trip levels
inside 1..63 (levels 28-30) and flips within the evaluate phase. Nothing was
clipped or discarded afterwards: the fleet record has no failed unit.

**Fleet execution (cost and capacity).** 9,000 transients at ~1.5 s
single-threaded is ~3.8 core-hours, split as three requests (one per supply,
3,000 units each). Jobs `klt-sim-ee7ad68415d2` (m7i.4xlarge Spot, 349 s),
`klt-sim-a503009e268a` (m6i.4xlarge Spot, 415 s) and `klt-sim-031f74d456a0`
(m7i.4xlarge Spot, 340 s), runner klt 0.5.0, client klt
0.7.0+g5e5b55992a7f, no capacity refusal, no retry; about 0.3 instance-hours
in total.

Reproduce (fleet only; `klt_record.py` refuses a local backend):

```bash
git checkout d84e59d   # originating commit (clean tree)
KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-offset-tran \
    --label "DR-0001 whole-comparator, transient MC, full 45-point grid"
```

### Nine-point reference (record `20261010-013540611508-4a4df37`, history)


[`records/20261010-013540611508-4a4df37.md`](records/20261010-013540611508-4a4df37.md),
fleet job `klt-sim-816fb60826f4` (c7i.4xlarge Spot, runner klt 0.5.0, 200 s
elapsed). All 9 PVT points x N = 200 draws completed, with no failed unit or
named problem. Commit `4a4df37`, clean.

| quantity (3σ unless noted) | `tt_27c_3.30v` | range over the 9 points |
|---|---|---|
| whole-comparator, simulated (`vos_3sig_tran_mv`) | 2.897 mV | 2.897–3.439 mV |
| DC bench, same corners ([`20260910-124917-4805118`](../comparator-offset-mc/records/20260910-124917-4805118.md)) | 2.801 mV | 2.796–2.807 mV |
| latch term, paired 1σ (`sig_latch_mv`) | 0.333 mV | 0.203–0.608 mV (max `ff_125c`) |
| load-R hand budget 1σ, nominal / 3× conservative (derived) | 0.136 / 0.409 mV | 0.114–0.166 / 0.342–0.499 mV |
| **total incl. conservative load-R (`vos_3sig_total_cons_mv`, scored)** | **3.146 mV** | **3.146–3.725 mV (max `ff_125c`)** |

**Score: within the ≤ 15 mV target and the ≤ 8 mV stretch at 9/9 points**
(the worst point has 2.1× margin on the stretch). The ratified bound is
unchanged. The latch adds a paired 1σ of 0.20–0.61 mV. It grows with
temperature as the preamp gain falls (`av_mean` 26.7 → 11.5) and so divides
the latch's own offset less. The same-draw preamp term `sig_vos_pre_mv`
(0.898–1.040 mV) agrees with the DC bench's 0.932–0.936 mV to within
−4/+12 %. The draws are independent and each sigma has 5 % precision, so
that agreement is within about 1.6σ.

### Fleet history

The first three submissions, made on 2026-10-09 with klt client
0.7.0+g86740f86d44f, produced no result. Per the host rules, none was
replaced by a local grid:

| attempt | outcome |
|---|---|
| 1, 2 | `batch_no_capacity`: "no capacity in any of the 30 pools after 3 attempt(s)". The requests then had no `batch.capacity_wait_s`; `sim/tools/mk_klt_request.py` now sets it (1800 s). |
| 3 (job `klt-sim-8fc6a625dac7`, m7i.4xlarge Spot) | Launched, then hit the fleet's hard 3600 s job limit (exit 124) after about 64 of 1800 units, with an empty `report.json`, so every unit came back as `batch_job_timeout` and `klt_record.py` refused to publish (`EMPTY_RESULT`). The fleet runner (klt 0.5.0) ran about 450 s per unit per worker against about 5 s for the same unit locally. |

**Root cause of the throughput collapse, and the fix (2026-10-10).** The
batch job runs one ngspice per physical core. Each ngspice process also ran
its own OpenMP device-evaluation threads, which oversubscribed the instance.
Two 8-unit fleet probes on the same deck (`tt`, 27 C, one wave) isolate it:

| probe job | ngspice threads | per-unit `runtime_s` | `.meas` values |
|---|---|---|---|
| `klt-sim-165f587b67e9` | default | ~422 s | reference |
| `klt-sim-42cceb7f254f` | `set num_threads=1` | ~1.54 s | bit-identical (same seeds) |

The request has no thread knob: the 0.5.0 runner drops
`options.ngspice_init` (klt #2917). So `sim/tools/mk_klt_request.py` now ends
this bench's generated body netlist with a `.control` / `set num_threads=1` /
`.endc` block (`SINGLE_THREAD_BENCHES`). ngspice runs `.control` blocks in
deck order, and the body is `.include`d ahead of klt's own `.control ... tran`,
so the setting is in place before the analysis reads it. It changes only the
thread count, not the circuit. One local unit drops from ~5 s to ~1.3 s with
it as well. With the pin, the whole 1800-unit grid fits in a single job
(200 s), well inside the 3600 s limit, so #2833's whole-job timeout is
avoided rather than fixed. The finding is posted on
[2AMLogic/klayout-tools#2970](https://github.com/2AMLogic/klayout-tools/issues/2970);
[#2833](https://github.com/2AMLogic/klayout-tools/issues/2833) is still open
on the tool side.

Before the fleet run, the bench was smoke-checked with single local units
(`tt`, 27 C, one draw, `klt sim --backend local`). These were debug probes,
not evidence: every `.meas` ingredient came back finite, the output stepped
cleanly 0 -> 1, and the threaded and single-thread runs gave identical values.

## Cold-start invocation

Fleet only. A transient Monte Carlo is a grid (here 45 PVT points x 200
draws = 9000 transients, ~1.5 s each single-threaded) and must not run on a
dispatch worker:

```bash
KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-offset-tran \
    --label "DR-0001 whole-comparator, transient MC"
```

`klt_record.py` generates the request with `sim/tools/mk_klt_request.py`
(`comparator-offset-tran` has one leg, `main`: `tran` + `monte_carlo`
`{n: 200, seed: 20260909, vary: mismatch}`), submits it with `klt sim`,
verifies the source bundle, derives the quantities below and mints
`records/<id>.{md,json}`, `corners/<id>/` and `netlist-snapshots/<id>.spice`.
`klt_record.py` refuses a local backend for a multi-unit grid. The bench is
not wired into `sim/run_corners.py` / `sim/selftest.sh` (a local hand-run of
this grid is exactly what the host rules forbid).

## Grid

**tt / ss / ff / fs / sf x -40 / 27 / 125 C x 2.97 / 3.30 / 3.63 V (45 PVT
points), N = 200 draws each**, the same grid as the other four benches. The
nine-point record (tt/ss/ff at nominal supply) was the first, reduced run; the
cost argument for reducing it (a clocked 1.6 us transient per draw) was
superseded once the single-thread pin made 1,800 units fit in 200 s. The
`mk_klt_request.py` request is one `klt sim` per supply point (the supply is
baked into each body netlist), each 5 x 3 x 200 = 3,000 units.

## Method

Each draw is one clocked transient. The differential input is a 64-level
staircase, -5.04 mV to +5.04 mV in 0.16 mV steps, one level per clock period
(T = 24 ns, evaluate phase 8 ns), with 2 extra cycles on the first level and 3
on the last; the staircase steps in the reset phase so the preamp has ~15 ns
to settle. The comparator decides once per period and its output holds across
reset (the NOR SR latch keeps state), so `dout/vdd` is a clean 0 -> 1 step at
the first level above that draw's trip point:

| step | quantity |
|---|---|
| `.meas ... when v(dn)=0.5 rise=1 td=71n` | `t_trip`, time of the 0 -> 1 flip |
| `c = floor((t_trip - t0)/T)`, `k = c - 2` | the staircase level that flipped |
| `V_trip = -5.04 mV + 0.16 mV * k - 0.08 mV` | midpoint of the one-step bracket |

**Quantisation.** A uniform +-0.08 mV bracket adds a variance
`step^2/12` (sigma 0.046 mV) to the population. It is **subtracted in
quadrature**, and the uncorrected value is reported as `sig_vos_tran_raw_mv`.

**Same-draw preamp offset (how the latch is quantified).** The preamp
differential output is sampled at the end of the reset phase of the first
cycle (input -5.04 mV) and the last cycle (+5.04 mV) of the *same draw*:

```
A_v      = (dd_end - dd_start) / 10.08 mV
V_os_pre = 5.04 mV - dd_end / A_v          # the DC bench's quantity, same draw
V_lat    = V_trip - V_os_pre               # decision-stage contribution
```

`sig_latch_mv` is the population sigma of `V_lat` (quantisation removed), so
the latch contribution is a **direct measurement on paired draws**, not the
difference of two unrelated sigmas of 5 % precision each. `mean_latch_uv` is
the deterministic (non-random) part: clock feed-through / kickback asymmetry.

**Statistics.** Population standard deviation (`pstdev`), N = 200 draws,
seed `setseed 20260909` common across the PVT points (the klt
`monte_carlo.seed`, `vary: mismatch`; `sw_stat_mismatch=1` is set in the
fragment, `sw_stat_global` left at 0 — global process variation is the corner
axis). Statistical precision on a sigma is 1/sqrt(2N) = 5.0 % at N = 200.
sigma_total (3 sigma is what the README row is stated at) is
`sig_vos_tran_mv`; the DC bench's value for the same quantity at the same
corner is reported beside it in the ledger.

**Range and failure policy.** A draw whose trip point falls outside the
staircase, whose flip lands outside the evaluate phase, or whose endpoint
decisions are wrong is a *named problem* (`TRIP_OUT_OF_RANGE`, `LATE_FLIP`,
`BAD_ENDPOINT_DECISION`) and the record is then an incomplete diagnostic —
nothing is clipped or silently dropped.

**Known systematic.** The 24 ns period leaves a finite preamp settling
residue (tau ~ R_load * C_latch-input, a few ns): a level step is ~e^-2 settled
after the 15 ns reset phase, a *constant* lag of order 0.02 mV of input that
moves the mean (`mean_vos_tran_uv`), not the sigma.

## Resistor-mismatch hand budget (DERIVED, not simulated)

The PDK's `ppolyf_u_1k` subcircuit carries **no** mismatch term at all (the
DC bench's `sig_rpair_uv` null control reads 0), so the load pair
(`XRN`/`XRP`, W = 1 um, L = 120 um) contributes nothing to any Monte-Carlo
number. It is budgeted by hand, and **labelled derived** wherever it appears:

1. **Source for the matching coefficient.** The foundry's own commented-out
   mismatch model for the resistor family in the PDK model file
   (`libs.tech/ngspice/sm141064.ngspice`, the `ppolyf_u` subcircuit, lines
   `* + par_r=0.021`, `* + var_r='0.7071*par_r*1e-06/par_sqrtarea'`):
   per-resistor sigma(dR/R) = 0.7071 * A_R / sqrt(W*L) with
   **A_R = 0.021 um** (2.1 %.um). The `ppolyf_u_1k` subcircuit in that file has
   no such lines; `ppolyf_u` (p+ poly on field oxide, same unsalicided
   p+ poly material) is its closest published coefficient. This is a cited
   foundry figure for the *sibling* device, not a measurement of the 1k flavour
   — hence the conservative variant below.
2. **Pair sigma.** The offset depends on the *difference* of two independent
   resistors, so sigma(dR/R)_pair = sqrt(2) * 0.7071 * A_R / sqrt(W*L) =
   A_R / sqrt(W*L) = 0.021 / sqrt(1 x 120) = **0.192 %**.
3. **Input referral.** A load error dR gives an output offset I_D * dR; dividing
   by the preamp gain A_v:
   `V_os,R = (I_D * R / A_v) * dR/R`. `I_D * R / A_v` is **measured per
   corner** by this bench (`vdrop_over_av_mv`: `vdd - v(aop)` at the first
   reset phase over the same-draw gain), not assumed.
4. **Total.** `sig_total = sqrt(sig_tran^2 + sig_rload^2)` (independent
   terms, added in quadrature). `sig_rload_cons_mv` / `vos_3sig_total_cons_mv`
   repeat it with A_R tripled (0.063 um): a stated conservative assumption
   covering "the 1k flavour is not the family member the coefficient was
   published for" and narrow-width (W = 1 um) effects. **The record scores the
   conservative total.**
