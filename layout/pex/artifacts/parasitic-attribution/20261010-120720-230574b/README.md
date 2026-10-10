# Parasitic attribution of the post-layout `td_od50_ns` misses (issue #229)

**Diagnostic only.** This run does not score a spec row, change the spec, or
promote T1 item 7. Item 7 stays `unmet / check_failed`. The cited report
[`layout/pex/comparator.pex.json`](../../../comparator.pex.json) and its
artifacts under [`../../measure/`](../../measure/) are not modified.

Produced by [`layout/pex/parasitic_attribution.py`](../../../parasitic_attribution.py)
at commit `230574b`. See its docstring for the full method.

```
python3 layout/pex/parasitic_attribution.py run     <this dir> --jobs 2   # batch fleet
python3 layout/pex/parasitic_attribution.py analyze <this dir>
python3 layout/pex/parasitic_attribution.py verify  <this dir>            # PDK-free
```

## What was measured

* **DUT.** The cited extracted DUT. That is the committed
  `layout/pex/artifacts/preamp-noise/comparator.dut-layout.cir`, whose sha256
  (`a7ca3c00…`) equals the cited extracted leg's `dut_netlist_sha256`. No
  re-extraction was done.
* **Variants.** 52 variants, derived from the netlist's own parasitic cards
  (20 nets). Each net gets one variant with its series R removed (star legs
  shorted into the hub) and one with its ground C removed. There are also
  aggregate variants (all R, all ground C, all coupling C, all C, everything),
  a substrate-node tie variant, two device-geometry variants, and the
  controls and centring legs.
* **Corners.** `ss_125c_2.97v` and `tt_125c_2.97v`, the two corners named by
  the issue. They are the worst ss and the only tt failing rows.
* **Harness.** `layout/pex/pex_measure.py`'s own deck and request builders,
  unchanged. Each variant gets its own offset probe and then one overdrive
  ladder per process. The ladder is centred on that variant's probed trip
  point, which is the cited convention.
* **Execution.** Every one of the 154 `klt sim` requests ran on the AWS batch
  fleet (`--backend batch`, Spot). They were submitted by the released klt
  0.6.0 client, the same client as the cited report. Each report's
  `environment.remote.job_id` is kept in the report and collected per
  variant in `attribution.json`. Nothing ran as a local grid. The run was
  started at concurrency 6 and hit the fleet's shared
  `BATCH_MAX_CONCURRENT_INSTANCES=8` cap, so some launches were refused
  before running anything. It was stopped and resumed at concurrency 2 with
  capacity-refusal retry. Reports that had already completed were reused
  only when their `netlist_sha256` matched the regenerated deck.
  `run-log.json` is the resumed run's log. `failed_jobs` is empty.

Generated decks (`*.spice`) are scratch and git-ignored, as for the cited
artifacts. `verify` regenerates every deck and checks that each committed
report ran exactly that deck (sha256), so the decks are reproducible from
the committed inputs.

## Validity: the controls

| control | corner | cited | this run | deck |
|---|---|---|---|---|
| `ctrl` (extracted) | tt_125c_2.97v | 1.58774 ns | 1.58774 ns | byte-identical to the cited ladder deck |
| `ctrl` (extracted) | ss_125c_2.97v | 2.02956 ns | 2.02956 ns | byte-identical to the cited ladder deck |
| `sch` (schematic) | tt_125c_2.97v | 0.986719 ns | 0.986719 ns | byte-identical |
| `sch` (schematic) | ss_125c_2.97v | 1.23747 ns | 1.23747 ns | byte-identical |

The probed trip points also reproduce exactly (-8.9074 mV tt, -5.1865 mV ss).
**The study is valid** (`attribution.json: study_valid = true`).

**Closure.** `devgeom-rc0-all` removes every extracted parasitic and also sets
the MOSFET junction geometry to the schematic's convention. It reproduces
the schematic leg measured under the same probe-centred convention
(`sch-probed`) to every printed digit: 0.986674 / 1.23736 ns for both. It is
within 0.11 ps of the cited schematic rows. So the whole post-layout gap is
explained by two things: the extracted RC, and the extracted S/D junction
geometry. Nothing else contributes, including the flat-vs-hierarchical
netlist, device mapping and models.

## Result

`share` = (td_ctrl - td_variant) / (td_ctrl - td_sch) at the same corner. A
value of 100 % closes the whole gap (0.601 ns tt, 0.792 ns ss). The full
table is [`attribution-table.md`](attribution-table.md) and the data is in
[`attribution.json`](attribution.json).

| contributor | variant | tt | ss |
|---|---|---|---|
| **ground C (all nets)** | `cg0-all` | **82.6 %** | **83.6 %** |
| series R (all nets, star model) | `r0-all` | 5.8 % | 5.3 % |
| vertical-overlap coupling C | `cc0-all` | 0.5 % | 0.5 % |
| all RC together | `rc0-all` | 87.3 % | 87.7 % |
| extracted S/D junction geometry (AS/AD/PS/PD) | `devgeom` | 13.7 % | 14.6 % |
| floating `vsubs` node tied to ground | `vsubs-tied` | -1.4 % | -2.4 % |

Ranked single-net ground C (mean share over both corners). Values in fF are
the extracted ground C, with the mirror net in parentheses:

| net | role | C (mirror) | share |
|---|---|---|---|
| `sn` | inverter output from `qn`; gates the `doutb` side of the SR stage (`nb` pull-up, `doutb` pull-down) | 20.8 (`sp` 7.1) | 21.8 % |
| `doutb` | SR output | 27.3 (`dout` 22.7) | 19.2 % |
| `qn` | regenerating latch node | 30.9 (`qp` 30.1) | 15.2 % |
| `dout` | SR output (the measured node) | 22.7 | 14.7 % |
| `mp` | latch input-pair drain | 16.3 (`mn` 5.3) | 6.7 % |
| `qp` | regenerating latch node | 30.1 | 4.7 % |
| `nb` | SR pull-up stack | 10.5 (`na` 4.5) | 3.8 % |
| `aop` | preamp output | 39.7 (`aon` 34.9) | 3.3 % |
| everything else | | | < 2 % each |

The four nets `sn`, `doutb`, `qn` and `dout` together explain about 71 % of
the gap. Single-net ground-C shares sum to 87 % against 83 % for `cg0-all`,
so the attribution is close to additive. The largest single series R is
`ltail` at 2.6 %. Every other net's R is below 1 %.

Two nets have negative shares. Removing `aon` or `clk` ground C makes the
decision *slower* (-3.2 % and -3.6 %). `aon` is the preamp output mirror of
`aop`, so removing one side's C unbalances the preamp. `clk` is driven by an
ideal source, and its C couples into the floating `vsubs` node. Neither
nets' C is a cause of the slowdown.

The same ground-C asymmetry also produces the extracted leg's systematic
offset. `cg0-all` takes `dut_vos` from -5.2 / -8.9 mV to -0.4 / -0.5 mV,
and `rc0-all` returns the schematic's 32 uV.

### Classification asked by the issue

The gap is **(i) dominated by a few nets' ground C**. It is not (ii) the
star-model series R (about 5.5 % in total) and not (iii) the vertical-overlap
coupling terms (about 0.5 %). There is one further contributor outside RC:
the extracted S/D junction geometry, about 14 %. The extraction reports
AS = AD = 0.5 um x W, while the schematic netlists 0.18 um x W.

### Centring confound (issue step 5)

The confound is ruled out. It does not inflate the delta.

* `ctrl-ctr0` re-runs the extracted leg with the ladder centred at 0 V, the
  schematic's convention, instead of at its probed trip point. This makes
  the extracted leg *faster* by 3.5 % (tt) and 4.5 % (ss) of the gap. With a
  -5 to -9 mV offset, a 0 V-centred +50 mV rung is an effective 55 to 59 mV
  overdrive. So the cited convention (a true 50 mV) is the stricter,
  like-for-like one.
* `sch-probed` re-runs the schematic leg centred at its own probed trip point
  (+32 uV). `td_od50_ns` changes by 0.045 ps (tt) and 0.11 ps (ss), which
  is 0.01 % of the gap.
* None of the +60 % comes from the centring convention.

Aside, not part of the item-7 rows studied here: the 0.1 mV rung is
sensitive to that 32 uV. The schematic `tau_ps` moves from 122.9 to 108.6 (ss)
and from 92.4 to 82.1 (tt) when the schematic is probe-centred.

## What the data points to

**A layout change.** About 71 % of the gap is the routing ground C of four
nets on the decision-to-output path (`sn`, `doutb`, `qn`, `dout`). That C is
layout-controlled, and `sn` carries about 3x the C of its mirror `sp`.
Another 14 % is the drawn S/D diffusion extent. Shared or shorter
diffusions are also a layout lever. A DR-0004-era re-layout would target the
same nets. The data does **not** point to a new decision record. The miss is
a physical loading effect that reproduces bit-for-bit, and the measurement
convention adds no slowdown of its own. No variant here is a proposed fix,
and none was graded against the spec.
