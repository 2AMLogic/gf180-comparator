# `sim/harness/` — corner-runner reference

Stdlib-only Python. No virtualenv, no dependencies. One entry point:
[`sim/run_corners.py`](../run_corners.py).

```
python3 sim/run_corners.py --check-env          # PDK, tools, pins, DUT contract
python3 sim/run_corners.py --list               # known experiments + grid size
python3 sim/run_corners.py <experiment> -j 8    # run the grid, mint a record
python3 sim/run_corners.py <experiment> --no-write    # run, print, record nothing
python3 sim/run_corners.py <experiment> --sabotage-corners   # negative control
```

## Modules

| module | responsibility |
|---|---|
| `pdk.py` | Locate the gf180mcu install. No PDK path is ever hardcoded in a netlist. |
| `toolchain.py` | Check `sim/toolchain.json`'s pins **before** simulating anything. |
| `dut.py` | Bind and validate the device under test from `sim/dut.json`. |
| `corners.py` | The corner grid: `.lib`-section bundles, PVT axes, and `sabotage()`. |
| `testbench.py` | Load and validate `tb.json` manifests and their netlist fragments. |
| `runner.py` | Compose one self-contained deck per PVT point and run ngspice. |
| `report.py` | Evaluate checks, render the evidence record, write logs + snapshot. |
| `cli.py` | Argument surface and console summary. |

## Ownership boundary (why fragments look incomplete)

A testbench `.spice` file is a **fragment**, not a deck. The harness owns the
model includes, the corner `.lib` sections, `.temp`, the DUT netlist, the
`.control` block and `.end` — so that *one* netlist sweeps the whole PVT grid
without being edited. `testbench.validate_netlist()` refuses a fragment that
tries to own any of them, because a hardcoded `.temp 27` silently pins every
corner to room temperature and nothing downstream would notice.

The fragment gets these `.param`s, in this order:

1. `vdd_nom`, `vdd_val`, `temp_c` — the PVT point.
2. `sim/dut.json`'s `params` (`dut_ib`, `dut_vcm`) — the DUT's own operating
   point, stated once for all four benches.
3. the manifest's own `params`.

Then the models, then `.temp`, then `.options`, then the DUT netlist, then
the fragment.

**One consequence worth knowing.** Anything that must override a value set by
`design.ngspice` — `sw_stat_mismatch` is the case that matters — has to be a
`.param` **in the fragment**, not in the manifest's `params` map, because
manifest params are emitted *before* the model includes. Getting this wrong
collapses a Monte Carlo to σ = 0 while everything still looks like it ran;
`sim/comparator-offset-mc/` says so in its own header for that reason.

## Checks, and what they are for

A `checks` entry names a measurement and bounds it. The vocabulary:

| key | meaning |
|---|---|
| `min` / `max` | bound the value at every completed point |
| `min_spread_pct` / `max_spread_pct` | bound the peak-to-peak spread across the whole grid, as a % of the mean magnitude |
| `min_spread_pct_by_axis` / `max_spread_pct_by_axis` | the same, per axis (`process` / `temperature` / `supply`), evaluated on every slice where the other two axes are fixed — reported weakest → strongest |

An unknown key is a hard load error, not a warning: a silently-ignored
`min_spread_pct` is exactly the failure this vocabulary exists to prevent.

**The per-axis floors are the load-bearing ones.** A
`min_spread_pct_by_axis[process]` entry is not a design claim — it asserts
that the measurement *moves* when the process axis alone is swept, which is
the only automatic proof that the corner runner is really switching models.
`sim/selftest.sh` runs every bench under `--sabotage-corners` (every corner
bundle forced to typical, names kept) and **requires the run to fail**. If a
sabotaged run passes, corner switching is not taking effect and every
downstream record is worthless.

Every run prints the observed per-axis weakest → strongest spread for every
measurement, so a floor can be calibrated the first time a check is authored
rather than only after a record exists.

## The corner grid this block adopts

`corners.py` defines the bundles. gf180mcu has no single global process
switch: each device family carries its own `.lib` section, so a named corner
is a bundle of exactly one section per family, always with `design.ngspice`
included ahead of them (it defines `sw_stat_global`, `sw_stat_mismatch`,
`mc_skew`, … that the sections reference).

| set | corners |
|---|---|
| `tt` | `tt` — smoke only, **not a valid evidence matrix** |
| `mos` *(default)* | `tt`, `ff`, `ss`, `fs`, `sf` |
| `full` | the above plus `res_ff`, `res_ss` |

Axes: **−40 / 27 / 125 °C** and **3.3 V ±10 %** (2.97 / 3.30 / 3.63 V). The
`mos` set is therefore a **45-point** full-factorial grid, and the corner-id
convention is `<process>_<temp>c_<supply>v` (e.g. `ss_-40c_2.97v`).

## Deliberate divergences from `gf180-sar-adc`'s harness

The structure is ported from `2AMLogic/gf180-sar-adc`'s `sim/harness/`. What
changed, and why:

| change | why |
|---|---|
| **`dut.py` / `sim/dut.json` added.** The DUT is bound once and included by the harness. | Over there each testbench fragment carries a verbatim copy of the comparator netlist, kept in step by a bespoke sync script. That works when the topology is settled; here it is not, so the harness has to run before a design exists and accept the real one without editing four benches. It also lets every record stamp `dut_provenance`, so a placeholder measurement can never be quoted as a design measurement. |
| **Capacitor corners dropped** (`cap_ff`/`cap_ss`/`mim_*`/`moscap_*`). | Those exist because a SAR ADC's accuracy rides on its CDAC. A standalone comparator has no capacitor array; carrying them would put seven never-load-bearing points in every matrix and imply an accuracy story this block does not have. |
| **Resistor corners kept and promoted.** | The comparator's front-end gain is (transconductance × load resistance), so the poly sheet-rho skew is a first-order gain axis here in a way it never was for a CDAC. |
| **`mim_wrapper_subckts()` / `MIM_STACK_BY_VARIANT` dropped.** | Same reason: no capacitor array, so binding a MIM subckt to the variant's metal stack would be dead code a future reader could mistake for a requirement. |
| **`netlist_provenance` (per-testbench) dropped.** | Its job — schematic vs. extracted — now belongs to `sim/dut.json`'s `provenance`, because the DUT is bound once for all four experiments instead of copied into each. A third value, `placeholder`, is added. |
| **`scipy_min` pin dropped.** | Nothing here needs scipy; the harness and all four benches are stdlib-only. |
| **Per-axis spreads printed on every run.** | Calibrating a `min_spread_pct_by_axis` floor from a committed record only works once a record exists. |

BJT and diode sections are pinned to typical in every bundle. This block
instantiates neither; they are included only so that `ff`/`ss` here means the
same thing it means in the sibling repo's records.

## Known measurement floors

**The `meas` result-precision floor is ~1 µV, and it is not a solver
setting.** ngspice's `meas` returns roughly six significant digits, so
differencing two ~1.2 V node levels quantizes the answer at ~1 µV before any
`measure` expression touches it. Tightening `reltol`/`vntol`/`abstol` buys
solver accuracy but does **not** move this floor. The way past it is to
measure a quantity that is *already* small — a behavioural node referenced
near 0 V — which is what `sim/comparator-kickback/` does, and it resolves the
same physical quantity about a thousand times finer. Both forms are in that
bench's record so the floor is visible rather than asserted.
