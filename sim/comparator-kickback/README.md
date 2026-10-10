# `sim/comparator-kickback/`

**Charge kicked back into the comparator's own input nodes** by a decision,
over the full PVT grid — measured against two different source impedances,
neither of them ideal.

Backs [`README.md`'s kickback row](../../README.md#target-specification-ratified-via-dr-0002)
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

### Both input nodes (issue #160)

README's kickback row is stated at "the input nodes", but until #160 the
row-facing `kick_1k_peak_mv` came from the **positive** 1 kΩ node alone
(probe `ad` = `v(apa)-v(asp)`). The bench now also probes the **negative**
node against its own source (`adn` = `v(ana)-v(asn)`, same 1 kΩ / 100 fF
loading, same 30 ns-45 ns decision window, same operating point) and reports:

| measurement | meaning |
|---|---|
| `kick_1k_pnode_peak_mv` | positive-node peak (the pre-#160 definition of `kick_1k_peak_mv`) |
| `kick_1k_nnode_peak_mv` | negative-node peak |
| `kick_1k_peak_mv` | **row-facing: the maximum of the two** |
| `kick_1k_nnode_pos_mv` / `kick_1k_nnode_neg_mv` | negative-node extrema |

Layout asymmetry means equal peaks on both nodes cannot be assumed. The 5 mV
target and 2 mV stretch are unchanged; a worse aggregate is a recorded miss,
not a relaxed bound. Records minted before #160 (every record listed below)
carry the positive node only: they are **partial node coverage**, are left
byte-for-byte as committed, and new records state their coverage in the
`Input-node coverage` line and the `input_node_coverage` JSON field.

**Evidence status (honest ledger).** Bench, scoring and regression tests
(`sim/harness/tests/test_klt_record.py`, `KickbackBothNodes`) landed in #160.
The schematic both-node 45-corner record is
[`records/20261010-022609774981-bf851ec.md`](records/20261010-022609774981-bf851ec.md)
(all three supply legs minted through `klt sim` on the batch fleet; coverage
`both`). Result: the aggregate is the maximum of the two node peaks at every
corner; the positive node sets it at 45/45 corners (positive 4.528-10.010 mV,
negative 4.244-9.905 mV; nominal 7.598 mV), so the aggregate equals the earlier
positive-only schematic values to the displayed precision. Verdict unchanged
and not relaxed: within the 5 mV target at 1/45 corners, 0/45 within the 2 mV
stretch. Extracted-DUT both-node evidence is **PENDING** (follow-up, coordinate
with #112); the older records above remain partial node coverage. Reproduce
with `KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-kickback`.

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
| [`20260910-125341-4805118`](records/20260910-125341-4805118.md) | `comparator-dr0001` (**schematic**) | 45/45, `mos` × 3 T × 3 V | PASS |
| [`20260909-055539-e2bb637`](records/20260909-055539-e2bb637.md) | `placeholder-v1` (**placeholder**) | 45/45, `mos` × 3 T × 3 V | PASS |

The first row is the current reference: taken against
[DR-0001](../../spec/decision-records/DR-0001-comparator-topology.md)'s
static preamp + StrongARM latch, no placeholder banner. `kick_1k_peak_mv` is
7.60 mV at nominal, 4.53–10.01 mV across the grid — **misses** the README
≤ 5 mV target at most corners and the ≤ 2 mV stretch everywhere; reference
against the ratified bound, this row's verdict scoring tracked in [#75](https://github.com/2AMLogic/gf180-comparator/issues/75) (DR-0001's Consequences section
names this as the gap most likely to need revisiting first, and it is not
retuned here per `sim/README.md`'s rule against relaxing a check to make a
result pass). It is also the record the `kick_1k_peak_mv` per-axis floors
are now calibrated from (observed weakest slices: process 15.34 %,
temperature 2.461 %, supply 30.1 %).

### Post-layout record (issue #23): `20261002-211343-6346fad`

The second record in `records/` is the **post-layout** one, minted against
the extracted binding (`comparator-dr0001-layout`, `provenance: extracted`)
over the same 45-point grid. What it shows:

- **The kickback peak grows in exactly the direction `design/README.md`'s
  parasitic asymmetry note predicts**: `kick_1k_peak_mv` 7.60 → 10.03 mV at
  nominal (+32 %), 8.49–14.58 mV across the grid (schematic: 4.53–10.01) —
  the input nodes' routing capacitance adds to the charge injected back
  through the input pair. The ≤ 5 mV row (ratified via DR-0002) is now
  missed at every corner; per that note's own instruction the result is
  recorded as data,
  not hidden — this is the gap DR-0001 named "most likely to need
  revisiting first", now with its post-layout magnitude measured.
- The residual/signal-dependent components grow several-fold
  (`kick_sigdep_nv` +13× at nominal) for the same reason.
- The extraction's deterministic trip-point offset (−1.8 to −21.6 mV
  across PVT, same source as the regeneration bench's — see that bench's
  README) means this record's drive sources are **centred on the probed
  trip point** (`dut_vos`, `tb_vosprobe.spice`), so the "1 mV residue"
  rung still probes the near-threshold regime. The schematic record's
  0 V-referenced drives are unchanged and measure byte-identically to
  before.
- The `kick_1k_peak_mv` per-axis floors were recalibrated for the
  extracted grid (see the check's description in `tb.json` and the
  calibration record `20261002-204202-baeffe5`, the first post-layout run
  whose observed weakest slices the recalibration cites): the extracted
  peak is less process/temperature-sensitive because the
  corner-independent routing parasitics dominate the injected charge.
- The record's **Post-layout delta** table carries the full
  nominal + whole-grid-mean comparison against the schematic record cited
  above, and its Reproduce block regenerates the extracted binding first.

**Read the banner on the placeholder row.** It was taken against the
placeholder DUT and substantiates the harness, not the kickback row; it
stays committed as append-only evidence but is superseded as the current
reference. It is the record the `kick_1k_peak_mv` per-axis floors were
*originally* calibrated from (observed weakest slices: process 34.76 %,
temperature 3.34 %, supply 15.25 %) — the process floor did not transfer to
the real schematic's input pair and was recalibrated (see this experiment's
`tb.json` `kick_1k_peak_mv` check description). The coupling from the
placeholder's decision stage back to its front end was an explicit 5 fF/side
stand-in for a real latch input pair's `C_gd`, declared in
[`sim/dut/placeholder_comparator.spice`](../dut/placeholder_comparator.spice);
the schematic row above couples through the real input pair's `C_gd`
(`comparator_dut_analog`'s `XMIP`/`XMIN`) instead.
