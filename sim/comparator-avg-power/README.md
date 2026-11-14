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

## Not run by `characterize.sh`, and not on the fleet path

`sim/characterize.sh`'s `CAMPAIGNS` list is unchanged; this bench is listed in
`scripts/check_bench_inventory.py`'s `NOT_RUN_BY_CHARACTERIZE` with its
reason. `sim/tools/mk_klt_request.py` and `sim/tools/klt_record.py` are
per-bench dispatch tables and carry no branch for it, so the Spot-batch fleet
path does not reach it yet — wiring that up is the 45-corner follow-up's work.
The local runner is generic over `tb.json` and needs no tool change:

```bash
# the committed record's command: ONE PVT point, run locally
python3 sim/run_corners.py comparator-avg-power \
  --corners tt --temps 27 --supply-tolerance 0 -j 1
```

A 45-point grid must **not** be hand-launched on a shared worker
([`CLAUDE.md`](../../CLAUDE.md) host rules); it goes through `klt sim` corner
submission once the fleet path exists.

## Records

| record | coverage | status |
|---|---|---|
| _(minted by the command above; see the table below after the first run)_ | **1 of 45** PVT points (`tt_27c_3.30v`), schematic DUT | bring-up validation probe, unscored |

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
is nonetheless the right scope here is mechanical rather than a judgement
about sufficiency: a second corner of this bench needs the fleet path, the
fleet path needs new per-bench branches in `sim/tools/mk_klt_request.py` and
`sim/tools/klt_record.py`, and that wiring is explicitly out of scope for the
issue that created this bench (#356). **It establishes that the stimulus, the
integral and the settledness criterion work, and what they read at the nominal
point. It establishes nothing about the worst corner** — which is exactly
where DR-0006 expects reset to be slowest (`ss`, 125 °C, 2.97 V is its stated
*hypothesis*, not a result).

## What this bench does **not** do

- It does not score average power, edit the Supply / power row, or touch its
  clock-rate TBD.
- It does not ratify, revise or edit DR-0006. Ratification is the DR-0002
  two-key ceremony.
- It does not run the 45-corner campaign or the extracted
  (`comparator-dr0001-layout`) DUT — DR-0006's feasibility item 1 asks for
  both, and this landing is the bench plus one nominal point.
- It does not run DR-0006's sensitivity sweeps (0/100 fF load, 1/50 mV
  overdrive, 32 MHz, clock-charge boundary), which its feasibility item 4
  requires before ratification. `q_clk_pc` records the clock charge at the
  nominal condition; how much the scored figure would *move* if the boundary
  changed is the sweep, and it is not run here.
