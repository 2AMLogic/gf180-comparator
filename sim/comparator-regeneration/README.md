# `sim/comparator-regeneration/`

**Decision time versus input overdrive** over the full PVT grid, the
regeneration time constant **τ** extracted from it, near-metastable
behaviour, and the switching energy per decision.

Backs [`README.md`'s decision-time row](../../README.md#target-specification-draft--engineering-to-ratify)
(≤ 1.5 ns at 50 mV overdrive, 3.3 V; ≤ 0.8 ns stretch), and supplies the τ
that **every metastability statement in this repo is computed from** —
metastability is a first-class row here, per [`CLAUDE.md`](../../CLAUDE.md),
not a footnote.

```bash
python3 sim/run_corners.py comparator-regeneration -j 8
```

## Method

Three comparator instances, driven in parallel at three overdrives:

| rung | overdrive | why |
|---|---|---|
| `td_od50_ns` | 50 mV | the overdrive the spec row is stated at; large-signal, sets `t0` |
| `td_od1_ns` | 1 mV | inside the logarithmic region |
| `td_od01_ns` | 0.1 mV | one decade smaller again — the τ lever arm and a near-metastable probe |

A regenerative decision resolves in `t = t0 + τ·ln(V_logic /(A·V_in))`, so
the delay difference between two *known* overdrives gives τ directly:

```
tau = (t(0.1 mV) - t(1 mV)) / ln(10)
```

τ is extracted from the two small rungs because both sit inside the
logarithmic region. `resolve_decades = t(1 mV)/τ` is reported alongside it:
it is the exponent that any `exp(-t/τ)` metastability probability is taken
to, so it is the number that decides whether a metastability claim means
anything at this corner.

Two design decisions make the measurement robust:

- **Every instance decides both ways in one run.** Each input is a PWL that
  is negative for the first strobe and positive for the second, and the delay
  is taken on the *second* — where the output must actively flip a latch
  holding the opposite answer. So no delay depends on which state the output
  happened to power up in. The `dout_*_first` / `dout_*_end` check pairs are
  the proof that this actually happened.
- **Every timing threshold is supply-normalized** (each output divided by its
  own supply, crossed at 0.5). A fixed absolute threshold would turn the
  ±10 % supply axis into a measurement artefact.

Mismatch is off (PDK default). Regeneration time and offset are separable and
are budgeted separately: offset moves the input at which the decision flips
(that is `sim/comparator-offset-mc/`), τ sets how fast a given overdrive
resolves. Combining them here would make neither attributable.

## Provenance

Methodology ported from
[`gf180-sar-adc/sim/comparator-regeneration/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-regeneration),
per [`spec/porting-plan.md`](../../spec/porting-plan.md).

**Ported:** τ extracted from a two-overdrive delay difference rather than
assumed; the both-polarities-in-one-run stimulus and the reason it exists
(that repo's earlier `.nodeset`-hinted static-input deck failed at every cold
corner because the operating point sometimes converged to the answer the
decision was meant to produce); supply-normalized timing thresholds; parallel
instances so one transient run covers the whole ladder; reporting static
current and switching energy from the same deck.

**Deliberately NOT ported:**

- **The topology and its sizing**, and every delay/τ/energy number from it.
- **The LSB-derived overdrive ladder.** That repo's rungs are 100 mV,
  half an LSB (1.6113 mV) and 0.1 mV, where the LSB comes from its
  converter's reference. There is no converter here: the primary rung is
  50 mV because that is what this repo's own spec row is stated at, and the
  small rungs are a clean decade apart to make the τ arithmetic exact.
- **The 62.5 ns bit-cycle timing and its `margin_ns` measurement.** Those are
  a SAR bit-trial budget. A standalone comparator has no bit cycle to have
  margin against; the strobe period here is chosen only to give the front end
  more than ten time constants to settle before the decision.
- **The `--netlist ... extracted` post-layout variant** and its bespoke
  driver script. No layout exists in this repo yet; when one does, the DUT
  binding takes an `extracted` netlist and this same manifest runs unchanged
  (see [`sim/dut/README.md`](../dut/README.md)).
- **The glitch-window delay search.** That repo needs a search window because
  its NOR SR latch pulses transiently when both StrongARM outputs fall
  together — a property of its specific output stage. Whether this repo's
  eventual output stage has the same behaviour is unknown until the topology
  is chosen; if it does, the window comes back and gets documented then
  rather than being carried in speculatively.

## Records

| record | DUT | grid | verdict |
|---|---|---|---|
| [`20260909-055028-b930f65`](records/20260909-055028-b930f65.md) | `placeholder-v1` (**placeholder**) | 45/45, `mos` × 3 T × 3 V | PASS |

**Read the banner on that record.** It was taken against the placeholder DUT
and substantiates the harness, not the decision-time row. It is also the
record the `td_od50_ns` per-axis floors are calibrated from (observed weakest
slices: process 15.16 %, temperature 20.05 %).

### Two placeholder-specific caveats on that record

- `e_dec_fj` **carries no check and is not a figure.** The placeholder's
  decision stage is behavioural and draws no supply current at all, so what
  is measured is the front end's switching energy plus numerical residue of
  the charge integral. A check belongs here the moment a transistor-level
  decision stage is bound.
- **Solver tolerances are load-bearing on this deck.** `abstol` is `1e-13`,
  not the `1e-15` the kickback deck uses: at `1e-15`, six of the 45 points
  fail to take their first transient step at all (`Timestep too small …
  trouble with node eanc#branch`, at t < 10⁻¹³ s), because the three
  PWL-driven controlled sources present branch currents far below that floor
  at t = 0. A re-run that changes `reltol`, `vntol` or `abstol` is not
  bit-comparable with this record.
