# `sim/comparator-kickback/`

**Charge kicked back into the comparator's own input nodes** by a decision,
over the full PVT grid — measured against two different source impedances,
neither of them ideal.

Backs [`README.md`'s kickback row](../../README.md#target-specification-draft--engineering-to-ratify)
(≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single
decision edge; ≤ 2 mV stretch). Kickback is a first-class row here, per
[`CLAUDE.md`](../../CLAUDE.md).

```bash
python3 sim/run_corners.py comparator-kickback -j 8
```

## Method

**The source impedance is the entire measurement.** Biasing the inputs from
ideal voltage sources restores the injected charge instantly and reports
≈ 0 kickback no matter how bad it is — the standard way this measurement gets
faked. Three instances, two independent drives, and both are in the record:

| instance | drive | reports |
|---|---|---|
| **A** | 1 kΩ series source, 100 fF input-node capacitance | `kick_1k_peak_mv` — **peak** disturbance of the node relative to its own driving source. This is the exact condition the spec row states. |
| **B** | 1 pF node through 1 GΩ, 1 mV residue | `kick_resid_small_nv` — **residual** charge left after the decision. RC = 1 ms against a ~30 ns cycle: the bias sets the operating point and then does nothing. |
| **C** | same, 100 mV residue | the same, at a large residue |

**Only the signal-dependent part is irreducible.** A residue-*independent*
kick is indistinguishable from comparator offset and is removed the same way;
`kick_sigdep_nv = |kick(100 mV) − kick(1 mV)|` isolates the part that is not.

Every instance's decision is checked (`dout_*_end`), because a comparator
whose own kickback pushed its input past the decision point would fail in a
way the displacement numbers alone cannot show.

### Beating the `meas` resolution floor

ngspice's `meas` returns roughly six significant digits, so differencing two
~1.2 V node levels quantizes the answer at **~1 µV** — which for a
well-isolated input stage is coarser than the quantity being measured. That
floor is a property of the tool, and tightening `reltol`/`vntol`/`abstol`
does not move it.

The sibling repo's own kickback record documents this floor and states the
way past it: measure a quantity that is *already* small. This bench does
that. `Bbd`/`Bcd`/`Bbc` compute the differential (and common-mode-referred)
input voltages as behavioural nodes sitting near 0 V, so `meas` returns six
digits **of the small quantity** and the floor drops to ~1 nV.

Both forms are reported, deliberately:

| measurement | resolution |
|---|---|
| `kick_resid_raw_uv` | the naive node difference — quantized at ~1 µV, every value an exact integer number of µV |
| `kick_resid_small_nv` | the same physical quantity, near-zero-referenced — ~1000× finer |

So the floor is *visible in the record* rather than asserted in prose.

Mismatch is off (PDK default): kickback and offset are separable and are
budgeted separately.

## Provenance

Methodology ported from
[`gf180-sar-adc/sim/comparator-kickback/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-kickback),
per [`spec/porting-plan.md`](../../spec/porting-plan.md).

**Ported:** the floating high-impedance drive and the explicit reason for it
(an ideal source reports ≈ 0 kickback however bad the circuit is); separating
the signal-dependent component from the absolute one, and the argument that
only the former is irreducible; reporting the peak transient excursion
separately from the residual displacement; quoting the residual as charge as
well as voltage so a reader with a different input capacitance can rescale
it; checking that every instance still decides correctly while being
disturbed; the tightened solver tolerances, and the `meas` result-precision
floor — including **acting on** that record's own stated remedy rather than
merely restating it.

**Deliberately NOT ported:**

- **The topology and its sizing**, and its near-zero residual result.
- **The 8.83 pF CDAC top plate.** That capacitance is that ADC's `C_side`
  from its own CDAC sizing memo. There is no CDAC here: the floating node is
  a stated 1 pF, and the *primary* drive is the 1 kΩ source impedance this
  repo's own spec row names — which that repo's bench does not have at all,
  because its comparator is never driven from a resistive source.
- **Everything expressed in LSB** (`kick_sigdep_lsb`, `kick_diff_small_lsb`).
  A standalone comparator has no LSB; all bounds here are in volts (or
  attocoulombs).
- **The bit-cycle timing** (62.5 ns, decisions at 9.5 ns/72 ns). Those are SAR
  bit-trial instants. The strobe here is placed only to leave every node
  settled before the decision.
- **The `dout` correctness check phrased as "must still decide with the CDAC
  floating"**, retained in substance but re-anchored: here it is "must still
  decide while its own kickback disturbs a 1 kΩ-driven input", which is the
  condition this repo's row is written against.

## Records

| record | DUT | grid | verdict |
|---|---|---|---|
| [`20260909-055043-b930f65`](records/20260909-055043-b930f65.md) | `placeholder-v1` (**placeholder**) | 45/45, `mos` × 3 T × 3 V | PASS |

**Read the banner on that record.** It was taken against the placeholder DUT
and substantiates the harness, not the kickback row. It is also the record
the `kick_1k_peak_mv` per-axis floors are calibrated from (observed weakest
slices: process 34.76 %, temperature 3.34 %, supply 15.25 %).

**Placeholder caveat.** The coupling from the placeholder's decision stage
back to its front end is an explicit 5 fF/side stand-in for a real latch
input pair's `C_gd`, declared in
[`sim/dut/placeholder_comparator.spice`](../dut/placeholder_comparator.spice),
not an extracted capacitance. The numbers exercise the measurement path end
to end; they characterise no real topology.
