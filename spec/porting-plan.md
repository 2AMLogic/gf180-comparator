# Porting / design plan

**Status**: DRAFT. This plan names what transfers from the nearest mature
sibling and what this repo designs fresh. It ratifies nothing and is not
itself a decision record — see [`spec/README.md`](README.md) for when a DR
is required.

## Primary port source: `2AMLogic/gf180-sar-adc`

[`gf180-sar-adc`](https://github.com/2AMLogic/gf180-sar-adc) is the nearest
mature sibling for this block: same PDK (gf180mcu), same 3.3 V rail, and its
comparator is not a peripheral testbench — it is a **core subblock** of that
ADC's own design. That repo's own top-level README states this directly:
*"gf180-sar-adc already embeds a comparator that has never been specified
standalone... The existing SAR's behavior is context, not a source — this
repo derives its own numbers from the models."* This is the same
topology-vs-methodology split `sg13g2-comparator`'s and `sky130-comparator`'s
porting plans already apply, restated here for this repo's own primary
source: **port testbench/measurement methodology and same-PDK device-model
facts; do not port `gf180-sar-adc`'s topology, sizing, or spec numbers.**
That comparator is sized for the ADC's own CDAC-driven common mode and
residue/LSB budget, not for a standalone block.

### What is inventoried there (confirmed present, contents read 2026-09-06)

- [`design/comparator/comparator.spice`](https://github.com/2AMLogic/gf180-sar-adc/blob/main/design/comparator/comparator.spice)
  — the netlist for a static NMOS-input preamp (40/1 µm pair, 150 kΩ load,
  10 µA tail) into a StrongARM latch (8/0.5 µm pair) into isolation
  inverters and a NOR SR output latch, all `nfet_03v3`/`pfet_03v3`.
- [`spec/decision-records/DR-0015-comparator-topology.md`](https://github.com/2AMLogic/gf180-sar-adc/blob/main/spec/decision-records/DR-0015-comparator-topology.md)
  — status: proposed, not yet ratified in that repo either. Documents *why*
  a static preamp precedes the latch (makes the kickback-sensitive input
  stage unidirectional and isolates the full-swing regeneration nodes from
  the input) and the measured tradeoffs (offset, noise-verification cost,
  kickback, static power) that drove that choice for the ADC's own
  comparator. Cited here for the *rationale class*, not as a sizing to copy.
- [`spec/decision-records/DR-0004-device-flavor.md`](https://github.com/2AMLogic/gf180-sar-adc/blob/main/spec/decision-records/DR-0004-device-flavor.md)
  — greps the installed gf180mcuD model file directly and confirms gf180mcu
  ships exactly `nfet_03v3`/`pfet_03v3`, `nfet_05v0`/`pfet_05v0`,
  `nfet_06v0`/`pfet_06v0` (plus `_dss`/`_nvt` variants) — **no sub-3.3 V
  core flavor exists in this PDK.** This independently corroborates this
  repo's own `CLAUDE.md` ("3.3 V primary; 5 V flavor only via decision
  record" — the same rail discipline as `gf180-opamp`).
- Four separate `sim/` experiment directories (that repo's harness-based
  `sim/run_corners.py` convention, distinct from `sky130-sar-adc`'s single
  bespoke `run.py` driver):
  - [`sim/comparator-offset-mc/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-offset-mc)
    — the Monte-Carlo offset methodology this repo's `CLAUDE.md` calls "the
    headline": `setseed <n>` then N = 150 draws per PVT point via a
    `dowhile` reset loop. Confirms `sw_stat_mismatch`-based local-mismatch
    models are real and present on this PDK, not just global-process
    corners — this repo's own offset row states the same statistical basis
    (see `README.md`'s target-spec table). The seed/draw-count/
    negative-control convention is documented in that repo's
    `sim/comparator-offset-mc/records/20260816-050001-d002e66.md`.
  - [`sim/comparator-regeneration/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-regeneration)
    — decision-time-vs-overdrive methodology (schematic-level sweep, plus a
    separate bespoke extracted-netlist script for post-layout margin).
  - [`sim/comparator-preamp-noise/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-preamp-noise)
    — `.noise` on the preamp with the latch held in reset, **total
    integrated output noise divided by measured DC gain** (not ngspice's
    own input-referred integral — that repo's own record documents a prior
    200×-magnitude error from reporting `sqrt(onoise_total)` directly as
    the answer). This repo's future noise testbench applies the same
    divide-by-gain methodology and the same units caution.
  - [`sim/comparator-kickback/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-kickback)
    — drives the input nodes from a floating, high-impedance bias (not an
    ideal voltage source, which would falsely report ≈ 0 kickback) through
    a realistic RC. Same methodology this repo's kickback row adopts.
- Klayout-tools friction already filed for this PDK (concrete precedent for
  this repo's own future friction-protocol filings, per this repo's
  `CLAUDE.md`):
  [`klayout-tools#595`](https://github.com/2AMLogic/klayout-tools/issues/595)
  (extraction deck can only select `ppolyf_u_1k` sheet-rho, not `_2k`/`_3k`,
  forcing a geometry correction in `gf180-sar-adc`'s own comparator
  resistor) and
  [`klayout-tools#555`](https://github.com/2AMLogic/klayout-tools/issues/555)
  (PMOS body-to-`vdd` remediation needed on extracted netlists, no
  tap/well-label layer for a realistic body bias). Both are cited in
  `gf180-sar-adc`'s own DR-0015 and extraction records; this repo's future
  layout work should expect the same class of gaps on the same PDK deck.

### What transfers directly (methodology and device-flavor facts)

- The four-experiment `sim/` shape above (offset-MC, decision-time-vs-
  overdrive, preamp noise, kickback), including the specific measurement
  techniques (divide-integrated-noise-by-gain; floating high-impedance
  kickback drive; `setseed`/`dowhile` Monte-Carlo offset loop with a
  same-seed negative control).
- The `sw_stat_mismatch`-based Monte-Carlo statistical basis for offset
  claims — confirmed real on this PDK, not assumed.
- The device-flavor fact set from DR-0004 (exactly which `nfet_*`/`pfet_*`
  flavors gf180mcu ships) — a PDK fact, not a design choice.
- The klayout-tools friction precedent (`#595`, `#555`) as an expectation
  for this repo's own future layout work on the same PDK deck.

### What is designed fresh, not ported

- **All numeric target-spec bounds are original engineering judgment**, not
  inherited. `gf180-sar-adc`'s embedded-comparator numbers (≈ 3.84 mV 3σ
  offset at `tt`/27 °C, N = 150; ≈ 0.08–0.13 mV rms noise; near-zero
  kickback residual — all at that repo's own 40/1 µm preamp-pair sizing)
  are same-PDK context showing these targets are achievable at *some*
  sizing, never a value this repo's own (not-yet-designed) comparator
  inherits.
- **The topology and its sizing.** `gf180-sar-adc`'s comparator (static
  preamp + StrongARM, per DR-0015) is sized for that ADC's own CDAC-driven
  common mode and residue/LSB budget — a different design problem from a
  standalone comparator with its own stimulus and no driving CDAC. This
  repo's `design/` work (out of scope for this bootstrap issue) re-derives
  its own topology and sizing from first principles against gf180mcu device
  models, using DR-0015's rationale as context on the tradeoff space, not a
  netlist to copy.
- **A standalone stimulus.** `gf180-sar-adc`'s testbenches assume the
  surrounding ADC's driving CDAC and SAR sequencer where relevant; a
  standalone comparator bench here needs its own ideal differential
  DC/pulse/noise/kickback stimulus with no CDAC or sequencer dependency.
- **Layout.** `gf180-sar-adc`'s comparator subblock's layout maturity is
  out of scope for this survey — this repo's `layout/` work is independent
  per-PDK physical design regardless of that repo's state.

## Other siblings consulted (not primary port sources)

- [`sg13g2-comparator`](https://github.com/2AMLogic/sg13g2-comparator) and
  [`sky130-comparator`](https://github.com/2AMLogic/sky130-comparator) are
  this block's own twins (identical bench structure, per this repo's
  `CLAUDE.md`) — both completed the identical bootstrap task already
  (`sg13g2-comparator` issue #2, merged; `sky130-comparator` issue #2 → PR
  #5, merged). Their porting plans and `README.md` target-spec tables are
  the source of the twin-set numeric-consistency convention this repo's own
  table follows (see `README.md`), and their `spec/README.md` files are the
  precedent for this repo's own `spec/README.md` (target-spec table lives
  in the top-level README, not a separate `spec/target-spec.md` file).
  Neither has same-PDK comparator prior art relevant to gf180mcu beyond that
  structural precedent.
- `sky130-sar-adc` is the campaign-shape precedent the original issue named
  (per `sky130-comparator`'s own porting plan, which used it as its primary
  port source in the same role `gf180-sar-adc` fills here) — not consulted
  directly for this repo's own numbers, since `gf180-sar-adc` is the
  same-PDK sibling and takes precedence.

## Next steps (not part of this bootstrap issue's scope)

1. Design `design/comparator.sch` (or equivalent) from first principles
   against gf180mcu device models, documenting the topology decision as a
   decision record (mirroring `gf180-sar-adc`'s DR-0015 shape: context,
   decision, sizing rationale, alternatives considered, spec lines
   affected, consequences), using DR-0015's rationale as context, not a
   netlist to copy.
2. Stand up this repo's own `sim/` harness plumbing, porting the
   `sim/comparator-offset-mc/` / `sim/comparator-regeneration/` /
   `sim/comparator-preamp-noise/` / `sim/comparator-kickback/`
   *methodology* (not topology or numbers) into this repo's own
   experiment directories.
3. Design a standalone stimulus (no CDAC/sequencer dependency) for each
   experiment.
4. Once real measurements exist, revisit `README.md`'s target-spec table's
   DRAFT bounds and file a ratification decision record if/when the table
   is set, changed, or scoped (see `spec/README.md`).
5. Expect klayout-tools friction of the same class as `#595`/`#555` once
   layout work begins on this PDK deck; file generically-scoped tool-gap
   issues per this repo's `CLAUDE.md` friction protocol.
