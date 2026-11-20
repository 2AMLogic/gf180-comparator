# `comparator-avg-power/` — DR-0006's average-power condition, as a bench

**SUPPLEMENTAL AND UNSCORED.** This bench scores no row of
[`README.md`'s target specification](../../README.md#target-specification-ratified-via-dr-0002)
and creates none. It exists to measure the quantities
[`DR-0006`](../../spec/decision-records/DR-0006-average-power-operating-condition.md)
lists under **"Feasibility status"** as *not established*, so that the
reviewers of its ratification ceremony have evidence instead of a proposal.

DR-0006's status is **`proposed` — not ratified**. Nothing here ratifies it,
nothing here edits it, and nothing here changes a bound: the Supply / power
row keeps the `(TBD)` clock rate it was ratified with (DR-0002), its
≤ 1 mW target and ≤ 500 µW stretch are untouched,
[`spec/claim-registry.json`](../../spec/claim-registry.json) still registers
no average-power row ("Average power is deliberately not registered
(UNSCORED)"), and `signoff/make_item5_envelope.py` keeps its
`average_power_clock_rate_tbd` skip reason.

## Why a new bench and not an edit of `comparator-regeneration/`

No committed bench applies a periodic stimulus or integrates supply charge
over a steady state, so none of DR-0006's unestablished items can be measured
today. The closest is [`../comparator-regeneration/`](../comparator-regeneration/)
— the only bench that already clocks the DUT and integrates supply charge —
and this bench reuses its shape. It could not reuse its *deck*: `sim/` is
append-only, and DR-0006 itself rejects that deck's clock as the power
condition ("its 33 % duty and two strobes are a timing rig, not a throughput
condition, and 33 MHz matches no ratified consumer rate").

## The condition, as implemented

Every number below is DR-0006's, transcribed. They live in `tb.json`'s own
`params` map, and `sim/harness/tests/test_avg_power_semantics.py` checks each
one against the record's text and checks every derived `.meas` boundary
against the params.

| DR-0006 clause | Implementation |
|---|---|
| 16 MHz, period 62.5 ns, 50 % duty, 100 ps edges, first rising edge at t = 10 ns | `vclk` `pulse(0 {vdd_val} {t_rise0} {t_edge} {t_edge} {t_hi-t_edge} {t_per})`. The flat top is `t_hi - t_edge`, so the **50 %-crossing** high and low phases are each exactly 31.25 ns. |
| one decision per cycle, evaluated on the rising edge; reset is the low phase | 24 cycles are simulated; the output is read 250 ps before each falling edge. |
| `dut_vcm = 1.65 V` fixed; `dut_ib = 10 µA` | `vcm`, and `iba` from `sim/dut.json`'s `comparator-dr0001` params. |
| alternating sign each cycle, `Vod = 10 mV` about the DUT's own trip point | one `pulse` on the single-ended `s` node, period `2*t_per`, split differentially by `Eap`/`Ean`; centred on `dut_vos` (0 for the schematic binding, the probed trip point for an extracted one). |
| the sign change lands inside the reset phase, ≥ 20 ns before the next rising edge | every transition **completes** exactly `t_setup` = 20 ns before the next rising edge and **begins** 11.15 ns after the preceding falling edge. |
| 20 fF on `dout` and `doutb`, equal, to `vss` | `cld` / `cldb`, both `{c_load}`. |
| bias drawn from the DUT's own rail; no separate `ibias` supply | `iba vdda ibn` — the rail the integral is taken at. |
| mismatch-free, noiseless | PDK default `sw_stat_mismatch = 0`; no `.noise`. |
| 8 warm-up cycles discarded (ends t = 510 ns) | window opens at the rising edge at 510 ns. |
| N = 16 whole cycles, 1.000 µs, edge-to-edge, N even | `q_win` integrates 510 ns → 1510 ns; both ends anchor the **start** of a rising edge, so the interval is an exact integer number of periods. |
| `i_DD(t) = −i(v_supply)(t)`; a negative window integral is invalid, **not** clamped with `abs()` | every charge/energy/power `measure` is `-q_*`; `q_win_pc` carries a `min: 0` **validity floor**, which is the mechanism that makes a negative integral invalid. |
| the two 8-cycle halves must agree within 1 % | `q_half_mismatch_pct`, `max: 1.0`. `abs()` appears on the half-window **difference** only — the one place DR-0006 permits it. |
| `Q_win`, `E_dec = VDD·Q/N`, `P_avg = VDD·Q/(N·T) = E_dec/T = E_dec·f_clk` | `q_win_pc`, `e_dec_fj`, `p_avg_uw`. The three equivalent forms are checked to agree in the PDK-free test, not just stated. |
| "an implementation that integrates `v(vdd)·i_DD` directly must agree with it (a check, not a second definition)" | `p_avg_vi_uw` integrates the instantaneous product through the `pwr` probe; `p_avg_form_delta_pct` is the disagreement, `max: 1.0` %. |
| clock-source and input-source charge: not counted, reported separately | `q_clk_pc`, informational and unchecked; those sources are referenced to ground, outside the boundary. |

### Sign discipline is a real difference from the template

`comparator-regeneration/` reports
`e_dec_fj = abs(q_dec - i_stat*8.1e-9)*vsup_v*1e15`. DR-0006 forbids that
shape here on two counts, and neither is cosmetic:

- **No `abs()` on the window integral.** A wrong-signed integral is a broken
  measurement, and clamping it would turn one into a plausible positive power.
  `q_win_pc`'s `min: 0` floor is what refuses it instead.
- **No static-current subtraction.** DR-0006's `P_avg` is the **total**
  delivered supply power, static part included. `i_static_ua` is reported
  beside it for context and is explicitly *not* summed with `P_avg` (the
  record says so), and it does not replace the regeneration record's
  `i_static_ua`, which is what `signoff/make_item5_envelope.py`'s partial
  static-power evidence still cites.

## What is measured, and what each quantity is *not*

| quantity | what it answers |
|---|---|
| `dout_c08` … `dout_c23`, `doutb_c08`, `doutb_c23` | the decision at the end of every window cycle's evaluate phase, supply-normalized. Checked `≥ 0.9` on even cycles (`+Vod`) and `≤ 0.1` on odd (`−Vod`). Cycle 8 is the **first post-warm-up cycle**, the one DR-0006's feasibility item 1 names. |
| `dec_cycles_correct` | the rollup: how many of the 16 window cycles decided the way the stimulus said, floor 16. Fail-closed — an exactly-0.5 metastable read is non-finite, which the harness rejects as a missing measurement, so the point fails rather than scoring a tie. |
| `reset_margin_ns` | the time left in the last window cycle's reset phase after the supply-current magnitude last exceeded 110 % of the **same run's** quiescent value. **A proxy, and the limitation is real** — see below. Carries no check: DR-0006 proposes no bound on it. |
| `q_win_pc`, `q_half1_pc`, `q_half2_pc`, `q_half_mismatch_pct` | the window charge, its two halves, and DR-0006's required same-run settledness criterion — i.e. whether the proposed warm-up and window are long enough (feasibility item 3). |
| `p_avg_uw`, `e_dec_fj` | average supply power and energy per decision under the proposed condition (feasibility item 2). **Unchecked, deliberately**, because a bound here would score the Supply / power row. |
| `p_avg_vi_uw`, `p_avg_form_delta_pct`, `q_split_delta_pct`, `clk_period_ns` | measurement plumbing: the `v·i` form agrees with the charge form, the halves partition the window, and the clock the simulator produced is the clock every hard-coded `.meas` boundary was derived from. |
| `i_static_ua` | quiescent supply current late in the reset phase, delivered-positive. Floor only (zero would mean the bias never came up). |
| `q_clk_pc` | the ideal clock source's own charge — outside the accounting boundary, recorded for the integrator, never inside the row. |

### The reset-completion margin is a proxy, and here is why

In the DR-0001 topology (StrongARM latch → isolation inverters → NOR SR
output latch) the **SR latch holds `dout` through the reset phase by design**,
so no observable output node resets. What resets is the StrongARM's internal
precharge nodes, whose names exist only in the schematic hierarchy and not in
a flat extracted netlist — probing them would make this bench unusable
against the extracted binding the 45-corner follow-up needs.

`reset_margin_ns` is therefore a **10 %-settling margin on the DUT's supply
current**, not a direct measurement of the latch's internal state. What
directly establishes that reset completed is a different quantity:
`dec_cycles_correct` = 16, i.e. that 16 consecutive cycles each decided
correctly on an *alternating* input, which they cannot do unless the latch
reset between them.

## Not run by `characterize.sh`; fleet path wired (issue #372)

`sim/characterize.sh`'s `CAMPAIGNS` list is unchanged; this bench stays in
`scripts/check_bench_inventory.py`'s `NOT_RUN_BY_CHARACTERIZE` (it scores no
spec row, so it is deliberately outside the characterization campaign). The
Spot-batch fleet path DOES reach it now: `sim/tools/mk_klt_request.py` and
`sim/tools/klt_record.py` carry the per-bench dispatch branches, so PVT
grids go through `klt sim` corner submission and never by hand-launching
ngspice on a shared worker ([`CLAUDE.md`](../../CLAUDE.md) host rules):

```bash
# the committed record's command: ONE PVT point, run locally
python3 sim/run_corners.py comparator-avg-power \
  --corners tt --temps 27 --supply-tolerance 0 -j 1

# the fleet path (requests + ingest; the committed 45-corner campaign record
# is 20261115-075832478887-79abbcc, issue #373).
# The batch capacity wait is baked into every request (batch.capacity_wait_s).
# Against the extracted binding this same command runs the two-phase flow
# (issue #374): phase 1 dispatches the trip-point probe requests, phase 2
# bakes each point's probed dut_vos into its own request -- the committed
# extracted 45-point record was minted this way.
KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-avg-power
```

### The one quantity fleet records omit: `reset_margin_ns`

`tb.json`'s `analyses` end with the adjacent pair
`let i_rst_thr = -1.1*i_q*1e6` / `meas tran t_rst when v(irst)=i_rst_thr ...`:
the 110 % threshold is relative to the SAME run's quiescent current, so it
must be defined interactively between the run and the measurement. The fleet
request schema (one analysis plus `{name, spice}` measurement entries, no
position for an interactive command between the run and the measurements) has
no position for that `let` at any runner version — the missing request field
is tracked upstream as
[2AMLogic/klayout-tools#6080](https://github.com/2AMLogic/klayout-tools/issues/6080)
— and shipping the `t_rst` card without it would be the
[2AMLogic/klayout-tools#5651](https://github.com/2AMLogic/klayout-tools/issues/5651)
failure shape (passes `--dry-run`, then errors every corner). The pair is
therefore omitted from the fleet request together, and fleet records omit
`reset_margin_ns` – its only consumer. The quantity carries **no check** in
`tb.json` (DR-0006 states no bound on it), so a fleet record still answers
every bound quantity DR-0006 asks for; the checked backstop for reset
completion is `dec_cycles_correct` = 16, which IS requested and IS checked.
Every fleet record states the omission under "Not computed by this
executor"; DR-0006's feasibility item 1 names both upstream issues for the
gap. No local workaround is built for the missing field.

## Sensitivity conditions on the fleet path (issue #452)

DR-0006's feasibility item 4 needs records at NON-nominal conditions. The
nominal `tb.json` is never edited (append-only, and the condition stays
exactly what DR-0006 proposes); instead the recorder overrides parameters at
request-build time and stamps the record:

```bash
KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-avg-power \
  --c-load 1e-13 \
  --corner-points tt_27c_3.30v ff_125c_3.63v ss_125c_2.97v
```

- `--v-od V`, `--c-load F`, `--t-per S` override exactly those tb.json
  params. A `--t-per` override is a **clock-rate** override: `t_hi` stays
  half the period, `f_clk = 1/t_per`, `t_setup` scales with the period
  (20 ns at 62.5 ns → 10 ns at 31.25 ns, keeping the input sign change
  inside the reset phase), every period-coupled `.meas` literal is
  re-rendered from the effective schedule, the `clk_period_ns` check bounds
  follow the effective period, and the µW expressions carry the window
  scale their `1e12` factor needs at a non-1 µs window. The renderer is
  refused unless it reproduces the committed nominal cards byte for byte,
  and a nominal-valued override is not an override at all — the request set
  stays byte-identical to the no-flag one
  (`sim/harness/tests/test_avg_power_overrides.py`).
- `--corner-points ID…` declares an explicit, non-cartesian PVT-point
  subset as ratified corner ids; one request per supply point, exactly the
  declared points, never their product.
- The minted record names its overrides and subset in its header **and** its
  Reproduce line, and is marked **SENSITIVITY-ONLY, NON-NOMINAL** (JSON
  `condition` block) so it can never be read as the nominal DR-0006
  condition or as a scored row.

## Records

| record | coverage | status |
|---|---|---|
| [`20261114-032046866512-d02a882`](records/20261114-032046866512-d02a882.md) | **1 of 45** PVT points (`tt_27c_3.30v`), schematic DUT, ngspice-47 / open_pdks `f6eeac7` | bring-up validation probe, unscored |
| [`20261114-222427036313-e00a719`](records/20261114-222427036313-e00a719.md) | **1 of 1** PVT points (`tt_27c_3.30v`), schematic DUT, ngspice-47 / open_pdks `f6eeac7`, fleet path | fleet bring-up (issue #372): proved the `klt sim` dispatch + ingest path and its `cross_run_agreement` against the local probe, unscored |
| [`20261115-075832478887-79abbcc`](records/20261115-075832478887-79abbcc.md) | **45 of 45** PVT points (tt/ff/ss/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V), schematic DUT, ngspice-47 / open_pdks `f6eeac7`, fleet path | the 45-corner campaign (issue #373), unscored — evidence for the DR-0006 ratification reviewers, not a verdict |
| [`20261115-053040016592-a4eca5b`](records/20261115-053040016592-a4eca5b.md) | **5 of 45** PVT points (tt/ff/ss/fs/sf × 27 °C × 3.30 V), **extracted** DUT, ngspice-47 / open_pdks `f6eeac7` | the probe leg's bring-up record (issue #374): first-ever `tb_vosprobe.spice` run (local, via `sim/run_corners.py`), unscored — **not citable as a clean-tree result**: taken against a dirty working tree (`sim/harness/testbench.py` and its test modified), so it is a diagnostic |
| [`20261115-064156694329-8a67cff`](records/20261115-064156694329-8a67cff.md) | **45 of 45** PVT points (tt/ff/ss/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V), **extracted** DUT, ngspice-47 / open_pdks `f6eeac7`, fleet path | the extracted-DUT campaign (issue #374), unscored — **not citable as a clean-tree result**: minted before the staged-source provenance correction (DR-0008), so it grades as a diagnostic; superseded by [`20261116-203811672880-81544ac`](records/20261116-203811672880-81544ac.md), which re-mints the same campaign citable (issue #398) |
| [`20261116-203811672880-81544ac`](records/20261116-203811672880-81544ac.md) | **45 of 45** PVT points (tt/ff/ss/fs/sf × −40/27/125 °C × 2.97/3.30/3.63 V), **extracted** DUT, ngspice-47 / open_pdks `f6eeac7`, fleet path | the extracted-DUT campaign re-minted under DR-0008's staged-source provenance class (issue #398), unscored — `citable` / `reference` hold: the gitignored generation netlist's staged bytes are sha256-pinned by every deck and committed in the record's own corner tree (`origin.pinned_sources`) |

> The record's own **Reproduce** line is the harness's generic template
> (`python3 sim/run_corners.py comparator-avg-power`), which would run the full
> 45-point grid rather than the one point this record covers. The command that
> produced it is the single-point one above. (`sim/harness/report.py` does not
> stamp the corner selection into that line for any bench; filed separately.)

### What the schematic 45-corner campaign measured (record `20261115-075832478887-79abbcc`)

All 45 points of the 5 × 3 × 3 grid ran on the Spot batch fleet through the
`klt sim` path (three requests, one per supply point, as
`mk_klt_request.py` emits them), ngspice-47 / open_pdks `f6eeac7`, job ids
`klt-sim-c79b26d8fa2f` / `klt-sim-4e1b9c841920` / `klt-sim-e9410e5a5fb4`
(`environment.remote` in the record). The bench is check-guarded
(`CHECK_GUARDED_BENCHES`), so the record's **Corner matrix** line reading
**45 of 45** is itself the evidence that every manifest check passed at every
point — no corner was dropped at ingest.

- **`P_avg` is the maximum over all 45 corners**: **174.487 µW at
  `ff_125c_3.63v`** (the hot fast corner at the high rail, not DR-0006's
  hypothesised slow corner). Against README.md's ≤ 1 mW target this is
  **evidence for the ratification reviewers, not a verdict** — this bench
  scores no spec row, DR-0006 stays `proposed — not ratified`, and the ≤ 500 µW
  stretch is likewise not claimed here.
- **Worst `q_half_mismatch_pct`**: **0.00440 % at `fs_125c_3.30v`** — about
  230× inside DR-0006's 1 % settledness criterion at every point, so the
  8-cycle warm-up / 16-cycle window held across the grid; no lengthening and
  re-record was needed.
- **`reset_margin_ns` is unavailable on the fleet path**, by design of the
  request schema: its `t_rst` `.meas` needs the interactive `let i_rst_thr`
  defined between the run and the measurements, and the pair is omitted
  together (`FLEET_OMITTED_MEASURES`, klayout-tools#5651). The checked
  backstop for reset completion, `dec_cycles_correct` = 16, **was met at every
  one of the 45 points** — the answer DR-0006 item 1 asks for, not a gap.
- **The hypothesised slow corner `ss` / 125 °C / 2.97 V completed cleanly**:
  16/16 decisions, `i_static_ua` = 30.108 µA, `p_avg_uw` = 124.908 µW,
  `q_half_mismatch_pct` = 0.0004 %. DR-0006's hypothesis that this is the
  *power* worst corner is refuted by the grid — the maximum sits at
  `ff_125c_3.63v` — while as a *decision-speed* corner it shows no anomaly.
- **Cross-run agreement** at the shared `tt_27c_3.30v` point against the
  committed local probe (`--compare-local …/20261114-032046866512-d02a882.json`):
  all four headline quantities **`within_band`** under
  `AVG_POWER_CROSS_RUN` (1 % relative on `p_avg_uw` / `e_dec_fj` /
  `i_static_ua`, 0.05 pp absolute on `q_half_mismatch_pct`); largest move
  −6.5 × 10⁻⁶ relative. The other 44 corners are listed in the record as
  "not compared" — the local probe covers one point, so the block's
  `INCOMPLETE_COMPARISON` status states exactly that, and claims no agreement
  it cannot see.

### What the extracted-DUT campaign measured (record `20261116-203811672880-81544ac`)

DR-0006 feasibility item 1 asks for the 45 points on **both** bindings, and
the two campaigns are kept **separate on purpose**: the figures below are the
post-layout `comparator-dr0001-layout` DUT's own and are never merged with the
schematic grid's. This is the campaign's **citable** mint (issue #398), re-run
under DR-0008's staged-source provenance class from the diagnostic first mint
[`20261115-064156694329-8a67cff`](records/20261115-064156694329-8a67cff.md);
every figure below is bit-identical between the two (same netlist bytes, same
pinned executor toolchain). The run went through the two-phase flow (issue
#374). The deck's first-ever run was the local bring-up committed as the
5-point record
[`20261115-053040016592-a4eca5b`](records/20261115-053040016592-a4eca5b.md)
(five process corners at 27 °C / 3.30 V, via `sim/run_corners.py`). Phase 1
itself then ran as three fleet probe requests (`probe-v2.97` / `probe-v3.30` /
`probe-v3.63`, one per supply point), measuring **all 45 points'** trip times
with [`tb_vosprobe.spice`](testbench/tb_vosprobe.spice) — that probe output is
not committed as a record; it survives as the three `probe_reports` sha256s in
the campaign record's `dut_vos_referral`. Phase 2 baked each point's probed
`dut_vos` (−21.4 mV … −1.8 mV across the
grid) into 45 main requests, one per PVT point, ngspice-47 / open_pdks
`f6eeac7`.

- **Worst `P_avg`, extracted DUT**: **207.376 µW at `ff_125c_3.63v`**
  (`e_dec_fj` = 12961 fJ) — the same corner that maximises the schematic grid,
  19 % higher (attributed to interconnect parasitics — an inference, not a
  cross-measured delta; the record applies no cross-binding comparison), and
  still a figure for
  the ratification reviewers, **not a verdict**: DR-0006 stays `proposed —
  not ratified` and neither the ≤ 1 mW target nor the ≤ 500 µW stretch is
  claimed here.
- **Worst `q_half_mismatch_pct`, extracted DUT**: **0.002306 % at
  `fs_27c_2.97v`** — about 430× inside DR-0006's 1 % settledness criterion at
  every point; no lengthening of warm-up/window was needed on this binding
  either.
- **`dec_cycles_correct` = 16/16 at all 45 points** — every window cycle
  decided correctly on alternating ±10 mV about each point's own probed trip
  point, including the first post-warm-up cycle; this is the checked backstop
  that reset completed, as on the schematic grid.
- **`reset_margin_ns` is unavailable on the fleet path here too**, for the
  same request-schema reason stated above; the omission is stated in the
  record itself.
- **The hypothesised slow corner `ss` / 125 °C / 2.97 V** completed cleanly on
  the extracted DUT as well: 16/16 decisions, `p_avg_uw` = 143.760 µW,
  `q_half_mismatch_pct` = 0.000605 %.
- **Citability (DR-0008), stated up front**: the DUT netlist is gitignored
  generation scratch, but its staged bytes are sha256-pinned by every request
  deck and committed in this record's own corner tree
  (`origin.pinned_sources`), which DR-0008's staged-source provenance class
  treats as pinned provenance — the record reads `citable: true`,
  `reference: true`, `dirty: false`. The earlier mint
  [`20261115-064156694329-8a67cff`](records/20261115-064156694329-8a67cff.md)
  of the same campaign predates the correction and grades `citable: false`;
  it stays on file as the diagnostic, and this re-mint reproduces its figures
  bit-for-bit.

### What the probe measured, and against which DR-0006 item

At `tt_27c_3.30v` only. Each row below says what it does *not* settle, because
one corner settles no corner question.

| DR-0006 "Feasibility status" item | measured | reading |
|---|---|---|
| **1.** reset time unmeasured; "show every cycle decides correctly, including the first post-warm-up cycle" | `dec_cycles_correct` = **16 / 16**; `dout_c08` … `dout_c23` read 1.000 on even cycles and 7.4 × 10⁻¹⁰ on odd, with `doutb` complementary | every window cycle decided the way the alternating ±10 mV stimulus said, the first post-warm-up cycle included. **Not settled:** the worst corner — DR-0006 expects `ss`/125 °C/2.97 V to be slowest and that is its hypothesis, not a result. |
| | `reset_margin_ns` = **30.48 ns** of the 31.25 ns reset phase | the precharge transient settled to within 10 % of the same run's quiescent current **0.77 ns** after the falling edge. **Not settled:** this is the supply-current proxy described above, not the latch's internal state, and it is one corner. |
| **2.** no dynamic-power figure exists | `q_win_pc` = **43.905 pC** over 16 cycles → `p_avg_uw` = **144.9 µW**, `e_dec_fj` = **9055 fJ** per decision | the first figure of any kind for this row's dynamic component. Static is 30.28 µA × 3.3 V = **99.9 µW** of it (≈ 69 %), leaving ≈ 45 µW — **2.81 pJ per decision** — dynamic. **Not a compliance statement:** `P_avg` is scored as the *maximum over all 45 corners* and 44 of them are unrun, so nothing here says the ≤ 1 mW target or the ≤ 500 µW stretch is met. |
| **3.** the proposed 8-cycle warm-up and 16-cycle window are not shown adequate | `q_half_mismatch_pct` = **0.00228 %** against DR-0006's 1 % criterion — a 440× margin | the window is in steady state at this point: the two 8-cycle halves integrate to 21.9524 pC and 21.9529 pC. **Not settled:** at a slow/hot corner the settling time is longer, and that is where the criterion earns its keep. |
| **4.** output load, overdrive and clock-charge boundary are judgment choices whose sensitivities must be run | `q_clk_pc` = **0.00707 pC**, i.e. the ideal clock source draws **0.016 %** of the DUT's supply charge at this condition | records the boundary line DR-0006 asks for. **Computed since issue #452:** the clock-charge boundary at all 45 corners on both DUTs is reported in [`clock-charge-boundary.md`](clock-charge-boundary.md) (from the committed records, no new simulation). **Not run:** the load/overdrive/32 MHz sensitivity sweeps themselves — how much the figure *moves* — are a follow-up. |
| — (implementation, not a record item) | `p_avg_form_delta_pct` = **1.9 × 10⁻⁵ %**; `q_split_delta_pct` = **4.1 × 10⁻⁴ %**; `clk_period_ns` = **62.5**, `t_win_start_ns` = **510.05** | the `v·i` form agrees with the charge form, the halves partition the window, and the clock the simulator produced is the one every hard-coded `.meas` boundary was derived from. |

**No number DR-0006 chose came out unworkable at this point**, so this probe
gives the ratification reviewers no reason to revise the record — and, equally,
no basis to conclude the condition holds at the corners that matter. The
45-corner campaign has since run ([record
`20261115-075832478887-79abbcc`](records/20261115-075832478887-79abbcc.md),
section above), and so has the extracted-DUT one (record
[`20261115-064156694329-8a67cff`](records/20261115-064156694329-8a67cff.md),
its own section above) — with the citability caveat stated there.

**`e_dec_fj` here is not comparable with `comparator-regeneration/`'s
`e_dec_fj`.** The names collide; the quantities do not. That bench reports
823–1788 fJ for a *single event* with a hard-coded static term subtracted; this
one reports the *total* periodic energy per decision, static included, with
20 fF loads attached. The ≈ 2.81 pJ dynamic part here is the quantity of the
same kind, and it sits just above the "about 1–2 pJ per decision"
order-of-magnitude hint DR-0006 flags as unvalidated — which is what adding an
explicit output load would be expected to do.

### Why one point, and what the repo's own rule says about it

[`sim/README.md`](../README.md) § Rules says "**PVT corners on every recorded
result.** A single-corner run is a smoke test and writes no evidence", and
`CLAUDE.md` repeats it. That rule is why this record is committed as an
explicitly bounded **probe**, not as a result — the same disposition
`sim/comparator-offset-cm-index/records/20261011-091529310543-f16ddbe-tolerance-probe.md`
already has: it states its own coverage limit in its first lines and claims
nothing beyond it.

The probe is less coverage than that precedent, which is a **2-point** record
(`tt_27c_3.30v` + `ss_125c_2.97v` by its hot-point rule). The reason one point
was nonetheless the right scope here is mechanical rather than a judgement
about sufficiency: at the time, a second corner of this bench needed the fleet
path, the fleet path needed new per-bench branches in `sim/tools/mk_klt_request.py`
and `sim/tools/klt_record.py`, and that wiring was explicitly out of scope for
the issue that created this bench (#356). **It established that the stimulus,
the integral and the settledness criterion work, and what they read at the
nominal point. It established nothing about the worst corner** — which is
exactly where DR-0006 expected reset to be slowest (`ss`, 125 °C, 2.97 V is its
stated *hypothesis*, not a result). The fleet wiring has since landed (#372)
and the full-grid campaign has run (record `20261115-075832478887-79abbcc`,
above); this section records why the probe was scoped as it was, not the
current coverage state.

## What this bench does **not** do

- It does not score average power, edit the Supply / power row, or touch its
  clock-rate TBD. The campaign's worst-corner `P_avg` (174.487 µW at
  `ff_125c_3.63v`) is reported as evidence for the ratification reviewers,
  not as a verdict.
- It does not ratify, revise or edit DR-0006. Ratification is the DR-0002
  two-key ceremony.
- The 45-corner schematic-DUT campaign **has run** (record
  `20261115-075832478887-79abbcc`) and so has the extracted
  (`comparator-dr0001-layout`) one — record `20261116-203811672880-81544ac`
  (issue #398), re-minted **citable** under DR-0008's staged-source
  provenance class from the diagnostic first mint
  `20261115-064156694329-8a67cff` (issue #374). The extracted leg's evidence
  is citable reference-grade (unscored); the figures did not move.
- It does not run DR-0006's load/overdrive/32 MHz sensitivity sweeps (0/100 fF
  load, 1/50 mV overdrive, 32 MHz), which its feasibility item 4 requires
  before ratification; the recorder's sensitivity mechanism for them landed
  with issue #452 and their records are that issue's remaining work. The
  clock-charge boundary half of item 4 IS reported, at every corner on both
  DUTs, in [`clock-charge-boundary.md`](clock-charge-boundary.md) — computed
  from the committed records' `q_clk_pc`/`q_win_pc` columns, no new
  simulation; how much the scored figure would *move* under the load,
  overdrive and clock-rate sweeps is still the open part.
