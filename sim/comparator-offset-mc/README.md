# `sim/comparator-offset-mc/`

**Monte-Carlo input-referred offset** of the comparator front end over the
full PVT grid, plus the part of that offset that moves with input common
mode, plus a null control on resistor mismatch.

Backs [`README.md`'s Offset-σ row](../../README.md#target-specification-draft--engineering-to-ratify)
(≤ 15 mV 3σ input-referred, ≤ 8 mV stretch) — the headline result for this
block, because gf180mcu is one of the open PDKs that actually ships
statistical mismatch models.

```bash
python3 sim/run_corners.py comparator-offset-mc -j 8
```

## Method

`setseed 20260909` once, then **200 draws per PVT point** through a
`dowhile` / `reset` loop — each `reset` re-evaluates the `agauss`
expressions inside the PDK's `fets_mm` subcircuits, which is what makes each
iteration an independent local-mismatch draw.

Per draw, one `dc` sweep produces six operating points: the differential
input at 0 mV and +2 mV, at each of three common modes (`dut_vcm` − 50 mV,
`dut_vcm`, `dut_vcm` + 50 mV). From them:

- **gain** `A_v = (dv(+2 mV) − dv(0))/2 mV`, measured on the *same* draw;
- **offset** `V_os = −dv(0)/A_v`;
- **common-mode-dependent offset** `V_os(V_cm ± 50 mV) − V_os(V_cm)`.

The same seed is used at every PVT point (common random numbers), so movement
of σ across the grid is a real PVT effect rather than sampling noise. N for
statistical-error purposes is 200 — not 200 × 45 — giving 1/√(2N) = **5.0 %**
precision on each reported σ.

Every draw's `voa` / `ddc` / `dde` is printed into the per-corner log, so the
raw sample set is in the evidence trail and not only its summary statistics.

### The two checks that are not design numbers

- **`av_sigma_pct ≤ 5 %`** proves the Monte-Carlo draw is *preserved* across
  the two DC points a gain is taken from. If it were re-rolled, the "gain"
  would be dominated by the difference of two independent offsets and every
  `V_os` in the record would be meaningless. This is the check that makes the
  method valid.
- **`sig_rpair_uv ≤ 0.01 µV`** is a null control on two identical
  `ppolyf_u_1k` loads and is *expected to be zero*: gf180mcu wires
  `*(1+mis_r*sw_stat_mismatch)` into its resistor subcircuits but hard-sets
  `mis_r = 0`. So **this PDK models no resistor local mismatch at all**, the
  reported offset σ contains no load-mismatch term, and that term has to be
  budgeted by hand. Kept live rather than as a comment so a PDK revision that
  turns `mis_r` on fails here instead of silently changing every offset
  record in this repo.

## Provenance

Methodology ported from
[`gf180-sar-adc/sim/comparator-offset-mc/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-offset-mc),
per [`spec/porting-plan.md`](../../spec/porting-plan.md).

**Ported:** the `setseed` + `dowhile`/`reset` draw loop and the fact that it
is the only seeding mechanism that works in ngspice here (`set rndseed` is
silently ignored, `.options seed` freezes the draw); one instance, two DC
points per draw, with `av_sigma_pct` as the draw-preservation self-check; the
resistor null control and the PDK fact behind it; the common-random-numbers
convention across the grid; the "state seed, draw count and σ derivation in
the record" discipline.

**Deliberately NOT ported:**

- **The topology, the sizing, and every number.** That repo's comparator is a
  40/1 µm preamp pair into a StrongARM latch, sized for its ADC's CDAC-driven
  common mode; its ≈ 3.84 mV 3σ result is same-PDK context that the target is
  reachable at *some* sizing, not a value this repo inherits.
- **The CDAC-derived common-mode band.** There is no CDAC here. The ±50 mV
  band is a stated property of this comparator's own input range, swept
  through an auxiliary source so the manifest never has to know what
  `dut_vcm` is.
- **Everything expressed in LSB.** That repo's bounds are in LSB of a 10-bit
  converter (`vos_3sig_lsb`, `sig_dvos_*` against a fraction of an LSB). A
  standalone comparator has no LSB; all bounds here are in volts.
- **`A_Vt` back-extraction** (`avt_back_mv_um`). It needs the input pair's
  effective W and L, which is a property of a design this repo does not have
  yet. It belongs in a device-characterization experiment, not here.
- **N = 150.** Raised to 200: this deck's per-draw cost is a six-point DC
  sweep of a six-device front end rather than a full preamp, so the extra
  precision (5.0 % vs. 5.8 %) is nearly free.

## Records

| record | DUT | grid | verdict |
|---|---|---|---|
| [`20260910-000212-3383e41`](records/20260910-000212-3383e41.md) | `comparator-dr0001` (**schematic**) | 45/45, `mos` × 3 T × 3 V | PASS |
| [`20260909-055500-e2bb637`](records/20260909-055500-e2bb637.md) | `placeholder-v1` (**placeholder**) | 45/45, `mos` × 3 T × 3 V | PASS |

The first row is the current reference: taken against
[DR-0001](../../spec/decision-records/DR-0001-comparator-topology.md)'s
static preamp + StrongARM latch, no placeholder banner, 3σ = 2.80 mV at
nominal (well inside the README ≤ 15 mV target / ≤ 8 mV stretch, reference
against a still-DRAFT row, not a verdict). It is also the record the
`vbias_anchor_mv` per-axis floors are now calibrated from (observed weakest
slices: process 23.55 %, temperature 1.282 %).

**Read the banner on the placeholder row.** It was taken against the
placeholder DUT and substantiates the harness, not the offset row; it stays
committed as append-only evidence but is superseded as the current
reference. It is the record the `vbias_anchor_mv` per-axis floors were
*originally* calibrated from (observed weakest slices: process 27.35 %,
temperature 14.76 %) — the temperature floor did not transfer to the real
schematic's bias node and was recalibrated (see this experiment's `tb.json`
`vbias_anchor_mv` check description).
