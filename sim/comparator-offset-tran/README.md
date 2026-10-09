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

## Cold-start invocation

Fleet only. A transient Monte Carlo is a grid (here 9 PVT points x 200
draws = 1800 transients, ~4 s each) and must not run on a dispatch worker:

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

## Grid: reduced, and which reduction

**tt / ss / ff x -40 / 27 / 125 C at the nominal 3.3 V supply (9 PVT
points), N = 200 draws each.** Not the 45-point grid. The reason is cost (a
clocked 1.6 us transient per draw), and the justification is the DC bench's
own record: its 1-sigma moves < 0.4 % across all 45 points (the mismatch
sigma lives in the PDK's `fets_mm` subcircuits, not in a corner section), so
fs/sf and the +/-10 % supply points add cost, not information, for a
*sigma* — they are where the *mean* moves, and the mean is reported here too.
Extending to the full grid is a `tb.json` edit (`corners`, `supply_tolerance`)
and a re-run.

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
