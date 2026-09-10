# DR-0001: Comparator topology — static differential preamplifier + StrongARM latch

- **Status**: proposed — requires operator sign-off (this repo's spec
  ratification authority has not yet been delegated to a decision record, so
  this record documents the topology and sizing but does not itself ratify
  any `README.md` row)
- **Date**: 2026-09-09
- **Decided by**: Builder agent, issue #12
- **Supersedes**: none — first record for this decision
- **Superseded by**: (none while this record stands)
- **Related**: #3 (Gap-to-T1 tracker), #12;
  `spec/porting-plan.md` next step 1; `sim/dut/README.md` "Why the DUT is
  split into three subckts"; `design/comparator.spice`; `sim/dut.json`;
  `gf180-opamp/sim/gm-id-characterization/records/20260909-052956-79c6a45.md`
  (same-PDK gm/ID device data, cited throughout the Sizing rationale below);
  `gf180-sar-adc/spec/decision-records/DR-0015-comparator-topology.md`
  (context for the topology-class choice, not a netlist copied from —
  different target-spec numbers, different sizing, no CDAC-derived common
  mode); `sim/comparator-offset-mc/records/20260910-124917-4805118.md`,
  `sim/comparator-preamp-noise/records/20260910-125200-4805118.md`,
  `sim/comparator-regeneration/records/20260910-125206-4805118.md`,
  `sim/comparator-kickback/records/20260910-125341-4805118.md` (the four
  45-point records minted against this decision).

## Context

`spec/porting-plan.md` "Next steps" item 1 is the last engineering step
before this block can make any measurement that counts: design
`design/comparator.sch` from first principles against gf180mcu device models
and document the topology as a decision record, using `gf180-sar-adc`'s
DR-0015 as context rather than a netlist to copy. Items 2 and 3 (the PVT
harness, the four experiment directories, and their hardening) are done —
`sim/dut.json` has bound a deliberately crude placeholder DUT since #6, and
every record committed against it carries a banner saying so.

Two things are available that make this a design decision rather than a
re-measurement:

1. **Same-PDK device data is already citable.**
   `gf180-opamp/sim/gm-id-characterization/records/20260909-052956-79c6a45.md`
   tabulates gm/ID, gm/gds and fT vs `Vov` for `nfet_03v3`/`pfet_03v3` at
   `L = 0.28/0.5/1/2/4 µm` across `typical/ff/ss/fs/sf` × −40/27/125 °C — the
   exact devices and rail this block uses. Every sizing choice below cites a
   specific row of that table.
2. **The harness already encodes one architectural constraint.**
   `sim/dut/README.md` "Why the DUT is split into three subckts, not one"
   states that `comparator-offset-mc` and `comparator-preamp-noise` are
   `dc`/`.noise` benches and therefore assume a DC-resolvable front end
   (`comparator_dut_analog`); a bare dynamic latch with no such front end
   would force both benches onto transient Monte Carlo / transient noise
   instead — thousands of trials per corner rather than one deterministic
   analysis per corner. That is a named, weighable consequence, not a
   discovery to make after the fact.

Unlike `gf180-sar-adc`'s DR-0015, this repo has **no CDAC and no ratified
spec** to inherit a common mode or an offset budget from — `README.md`'s
target-specification table is explicitly DRAFT (≤ 15 mV 3σ offset, ≤ 8 mV
stretch; ≤ 1.0 mV rms noise, ≤ 0.6 mV stretch; ≤ 1.5 ns / ≤ 0.8 ns decision
time at 50 mV overdrive; ≤ 5 mV / ≤ 2 mV kickback into 1 kΩ). DR-0015's own
numbers are cited here only as same-PDK context that a static-preamp +
StrongARM topology is achievable at *some* sizing — this record's sizing and
measurements are original.

## Decision

**The comparator is a static differential preamplifier (resistively loaded
NMOS pair) followed by a StrongARM latch, a pair of isolation inverters, and
a NOR SR output latch.** This mirrors the topology *class* DR-0015 chose for
the identical PDK and rail — not because its numbers transfer, but because
the choice is re-derived independently below and lands in the same place for
reasons specific to this repo's own harness contract (Alternatives
considered). The netlist is `design/comparator.spice`, generated from
`design/comparator.sch` (+ `comparator_dut.sch`, `comparator_dut_analog.sch`,
`comparator_dut_latch.sch`) by `design/netlist.sh`. All devices are 3.3 V
flavor (`nfet_03v3`/`pfet_03v3`) — no 5 V flavor is used, consistent with
`CLAUDE.md`'s rail discipline.

- **Preamplifier chosen over a bare latch.** A static differential front end
  is inserted ahead of the latch specifically so `comparator_dut_analog` has
  a DC operating point, which is what lets `comparator-offset-mc` stay a
  `dc`-sweep Monte Carlo (200 draws/point, ~1 minute/corner measured) and
  `comparator-preamp-noise` stay a `.noise` run, instead of forcing both onto
  a transient Monte Carlo / transient noise campaign of 10³–10⁴ runs per
  corner. See Alternatives considered for the quantified trade.
- **Front-end load: `ppolyf_u_1k`**, not `ppolyf_u_2k`/`_3k`. This carries
  forward DR-0015's reasoning rather than re-deriving it: the pinned `klt`
  extraction deck can only select the PDK's `ppolyf_u_1k` sheet-rho flavor
  for a resistor mark, not `_2k`/`_3k` (`2AMLogic/klayout-tools#595`, open).
  Layout is out of scope for this issue, but choosing `_1k` now means a
  future layout effort does not walk into that wall having to re-derive a
  different resistor geometry for the same target resistance.
- **Latch: StrongARM, single clock phase, precharged high on `clk` low,**
  with isolation inverters between the StrongARM's regeneration nodes and a
  NOR SR output latch. The isolation-inverter + NOR-SR-latch structure is
  carried forward from DR-0015 for a documented reason, not by default: that
  record measured ~10 mV of hysteresis from a NAND SR latch wired directly to
  a StrongARM's regeneration nodes (asymmetric Miller loading of whichever
  node is driving a LOW output), and fixed it with isolation inverters plus a
  NOR SR latch, both inverters identical and both inputs precharging to
  `V_DD` so neither loading depends on the held state. This repo's
  `comparator-regeneration` bench inherits the same defect-catching
  methodology: `sim/comparator-regeneration/testbench/tb.json`'s `td=35n`
  windowing note states explicitly that every instance is driven by a PWL
  that flips sign between two strobes, so every measured decision has to flip
  a latch holding the opposite answer — the same two-way test that found the
  defect in DR-0015 is running here from the first schematic-provenance
  record, not added after a defect is found.
- **Input polarity and common mode.** NMOS input pair, matched to
  `dut_vcm = 1.65 V` — mid-rail (`V_DD` / 2 at the nominal 3.3 V supply).
  Unlike DR-0015's ADC context, there is no CDAC or reference to inherit a
  common mode from; mid-rail is the natural standalone choice for a block
  with no driving circuit of its own, and it is recorded in `sim/dut.json`'s
  `params.dut_vcm` (not in any one testbench) per `sim/dut/README.md`.
- **Bias**: a 10 µA current forced into the `ibias` pin (`sim/dut.json`'s
  `params.dut_ib`) is the block's contract, mirrored 1:2 (`XMB` 5/4 µm :
  `XMT` 10/4 µm, both `nfet_03v3`) into a 20 µA preamp tail. Bias generation
  is out of scope here, as in DR-0015.
- **Offset cancellation**: none is designed in. The offset row is still
  DRAFT and unratified, and the measured 3σ offset (Consequences, below)
  comfortably fits both the target and stretch bounds at this sizing without
  any cancellation, so none is added.

## Sizing rationale

Every device size below is either traced to a cited row of
`gf180-opamp`'s gm/ID record or to a PDK model-file parameter, and checked
against what this repo's own new records actually measured.

### Preamplifier (`comparator_dut_analog`)

| Device | Role | L | W | nf | Device flavor |
|---|---|---|---|---|---|
| `XMB` | bias-mirror diode | 4 µm | 5 µm | 1 | `nfet_03v3` |
| `XMT` | tail | 4 µm | 10 µm | 1 | `nfet_03v3` |
| `XMIP`/`XMIN` | input pair | 2 µm | 30 µm | 1 | `nfet_03v3` |
| `XRN`/`XRP` | load | — | `r_width=1 µm`, `r_length=120 µm` | — | `ppolyf_u_1k` |

- **Tail current.** `XMT`/`XMB` share `L = 4 µm`, so the mirror ratio is the
  bare width ratio `W_T/W_B = 10/5 = 2`; a forced `dut_ib = 10 µA` therefore
  sets a **20 µA tail**, i.e. **10 µA per input-pair leg** at balance.
- **Load resistance.** gf180mcu's model file
  (`libs.tech/ngspice/sm141064.ngspice`, `.LIB typical` parameter block)
  sets `rsh_ppolyf_u_1k = 1000` (Ω/sq). At `r_width = 1 µm`, `r_length =
  120 µm`, `R_load = 1000 Ω/sq × (120 µm / 1 µm) = 120 kΩ`.
- **Input-pair overdrive and predicted gain.** At 10 µA/leg and `L = 2 µm`,
  `gf180-opamp`'s gm/ID record (`nfet_03v3`, `typical` corner, 27 °C, "gm/ID
  (1/V) at representative Vov" table, `L = 2 µm` row) gives **gm/ID = 14.96
  1/V at Vov = 50 mV** — i.e. this device sits in moderate/weak inversion at
  this current density, not at a textbook 200 mV overdrive. Using that row:
  `gm = 14.96 × 10 µA = 149.6 µA/V`, and the single-ended-to-differential
  gain of a resistively loaded pair is `A_v ≈ gm × R_load = 149.6 µA/V ×
  120 kΩ = 17.95`.
- **Measured vs. predicted gain.** `sim/comparator-offset-mc/records/20260910-124917-4805118.md`
  measures `av_mean = 18.0026` and `sim/comparator-preamp-noise/records/20260910-125200-4805118.md`
  measures `av_dc = 18.0123`, both at the nominal `tt_27c_3.30v` corner — a
  **0.3 % match** to the 17.95 prediction from the cited gm/ID row. This is
  the load-bearing citation this record makes: the input pair's operating
  point (`Vov ≈ 50 mV`, `L = 2 µm`) is not asserted, it is derived from a
  cited row and then checked against an independent circuit-level
  measurement.
- **Why `L = 2 µm` and not minimum length.** Per DR-0015's precedent on the
  same PDK, the input pair is sized for area (Pelgrom matching), not for
  speed — it is the dominant offset and noise source in this topology. A
  longer channel buys matching at the direct cost of gm/ID (and hence gain)
  at a given current, which is why the tail current and load resistor above
  are sized together with `L = 2 µm` rather than independently.

### Latch (`comparator_dut_latch`)

| Device group | L | W | Role |
|---|---|---|---|
| `XMTL` | 0.5 µm | 16 µm | tail switch, gated by `clk` |
| `XM1`/`XM2` | 0.5 µm | 8 µm | StrongARM input pair |
| `XM3`/`XM4` | 0.5 µm | 6 µm | cross-coupled NMOS |
| `XM5`/`XM6` | 0.5 µm | 6 µm | cross-coupled PMOS |
| `XM7`–`XM10` | 0.5 µm | 2–4 µm | precharge PMOS, gated by `clk` |
| isolation inverters, NOR SR latch | 0.5 µm | 2–10 µm | output stage |

- **Near-minimum length, not minimum.** `L = 0.5 µm` (not `0.28 µm`) is
  chosen for the whole latch. `gf180-opamp`'s gm/ID record's fT table (`nfet_03v3`,
  `typical`, 27 °C, `Vov = 200 mV`) gives **fT = 4.72 GHz at L = 0.5 µm**
  against **17.08 GHz at L = 0.28 µm** and **1.09 GHz at L = 1 µm** — an
  order of magnitude of intrinsic speed is available at `0.28 µm`, but the
  regeneration bench's own measured worst-case `tau_ps` (Consequences, below)
  shows `0.5 µm` already resolves the input in under a nanosecond at every
  PVT corner, so the extra intrinsic bandwidth of `0.28 µm` is not needed and
  is not spent — `0.5 µm` keeps more matching margin on the cross-coupled
  pair for the same reason the preamp avoids minimum length.
- **Sizing pattern mirrors DR-0015's shape** (8/0.5 µm input pair, 6/0.5 µm
  cross-coupled pairs) because that shape is already proven on this exact PDK
  and rail — it is not re-derived from the gm/ID table device-by-device the
  way the preamp is, because the latch's own noise and offset are divided by
  the preamp's measured gain (`A_v ≈ 18`) when referred to the input, so it
  is sized for speed and correct regeneration behavior, not for matching.

## Alternatives considered

- **Bare StrongARM latch, no preamplifier.** Not chosen. This repo's own
  offset target (≤ 15 mV 3σ, ≤ 8 mV stretch) is looser than DR-0015's ADC
  context (≤ 2 LSB), so a bare latch might well fit the *offset* budget on
  its own — but that is not the reason a preamp was kept. The reason is the
  harness contract named in `sim/dut/README.md`: without a DC-resolvable
  front end, both `comparator-offset-mc` and `comparator-preamp-noise` would
  have to be re-founded on transient Monte Carlo / transient noise
  (thousands of trials per corner instead of one `dc` sweep or one `.noise`
  run). `CLAUDE.md` also asks this repo's benches to stay structurally
  identical to the `sg13g2-comparator`/`sky130-comparator` twin set; keeping
  the same three-subckt split keeps that comparison meaningful across all
  three PDKs. Reconsider only if a future PDK twin or spec revision removes
  the DC-resolvable-front-end requirement from the harness contract itself.
- **Double-tail latch-type sense amplifier.** Not chosen, for the same
  reason DR-0015 rejected it: it remains a reset-and-regenerate structure
  with no DC operating point, so it does not solve the harness-contract
  problem above, while costing a second clock phase or an internally derived
  delay and roughly 1.5–2× the area.
- **Dynamic / integrating preamplifier.** Not chosen. It would keep
  zero static preamp power, but its gain would be set by an integration
  window rather than a bias point, so — like the bare latch — it has no DC
  operating point and forces the same expensive verification path back onto
  two of the four benches.
- **`ppolyf_u_2k`/`ppolyf_u_3k` front-end load.** Not chosen; layout is out
  of scope for this issue, but `2AMLogic/klayout-tools#595` is a known,
  already-filed dead end for those flavors on this exact extraction deck, so
  `ppolyf_u_1k` is chosen now to avoid re-deriving the load geometry later.

## Consequences

- **The harness's DC-resolvable-front-end assumption holds, and is now
  measured, not just designed for.** `comparator-offset-mc` and
  `comparator-preamp-noise` both ran as `dc`/`.noise` benches against the
  real schematic without any change to their analysis type — only two
  self-check floors needed recalibration (below), both because they were
  originally tuned against the placeholder DUT's very different bias/kickback
  behavior, not because the DC-resolvable-front-end assumption failed.
- **Two harness self-checks were recalibrated for this DUT, not relaxed
  against any spec row.** `sim/comparator-offset-mc/testbench/tb.json`'s
  `vbias_anchor_mv` temperature-axis floor (a corner-sensitivity anchor
  guarding against `--sabotage-corners`, not a spec check) was calibrated
  against the placeholder DUT's bias node and required 8 % spread; this
  schematic's bias-mirror node is far less temperature-sensitive at this
  sizing (measured weakest slice 1.282 %), so the floor is now 0.7 % (~45 %
  margin below the measured weakest slice, matching the sibling repos'
  calibrate-from-a-cited-clean-tree-record convention). Likewise
  `sim/comparator-kickback/testbench/tb.json`'s `kick_1k_peak_mv`
  process-axis floor dropped from 18 % to 8 % (measured weakest slice
  15.34 %, vs. the placeholder's 34.76 %). Neither check encodes a
  `README.md` target-spec bound; both still fail under `--sabotage-corners`.
- **Kickback now couples through the real input pair, not a stand-in.** The
  placeholder DUT's kickback path was an explicit `c_fb` component invented
  for the plumbing test. In this schematic, the coupling path into the input
  nodes is the input pair's own `C_gd` (`XMIP`/`XMIN` in
  `comparator_dut_analog`) — a property of the real devices, not an
  invented capacitor.
- **Measured results, reported as reference against the DRAFT table, not a
  verdict** (no decision record ratifies `README.md`'s target-specification
  table yet):
  - **Offset**: 1σ = 0.9335 mV, 3σ = **2.801 mV** at the nominal `tt_27c_3.30v`
    corner, corner-invariant to within 0.4 % across the 45-point grid
    (grid mean 1σ = 0.9338 mV, 3σ = 2.801 mV; `comparator-offset-mc`,
    `sig_vos_mv`/`vos_3sig_mv`) — comfortably inside both the ≤ 15 mV target
    and the ≤ 8 mV stretch.
  - **Input-referred noise**: 91.25 µV rms at nominal, worst case 128.8 µV
    rms at `ff_125c_3.63v` (`comparator-preamp-noise`, `vn_in_uv`) —
    comfortably inside both the ≤ 1.0 mV target and the ≤ 0.6 mV stretch.
  - **Decision time at 50 mV overdrive**: 0.708 ns at nominal, worst case
    1.237 ns at `ss_125c_2.97v` (`comparator-regeneration`, `td_od50_ns`) —
    **meets** the ≤ 1.5 ns target at every corner, **misses** the ≤ 0.8 ns
    stretch at the slow/hot/low-supply corner. This is recorded as a miss,
    not retuned — out of scope for this issue.
  - **Kickback into 1 kΩ**: 7.599 mV at nominal, range 4.53–10.01 mV across
    the grid (`comparator-kickback`, `kick_1k_peak_mv`) — **misses** the
    ≤ 5 mV target at most corners and the ≤ 2 mV stretch everywhere. This is
    the largest gap to the DRAFT table this record surfaces, and — per
    `sim/README.md`'s rule against relaxing a check to make a result pass —
    it is fed to the spec step as a named miss, not designed around here.
  - **Static power**: 28.5 µA mean (27.7–29.7 µA across the grid,
    `comparator-regeneration`, `i_static_ua`) × 3.3 V ≈ **94 µW nominal**
    (up to ≈ 108 µW at 3.63 V) — comfortably inside both the ≤ 1 mW target
    and the ≤ 500 µW stretch.
- **Kickback is the consequence this decision most directly creates and
  should be revisited first**, both because the miss above is real and
  because — as `design/README.md` "What is here and what is not" already
  states — post-layout extraction can only add capacitance at the input,
  which raises measured kickback further; the schematic-level number here is
  not conservative in that direction the way the noise number is.
- **This is a schematic-level design with no parasitics.** Every number
  above carries `Netlist provenance: schematic`. Layout, DRC/LVS and
  post-layout re-simulation are out of scope for this issue.

## Spec lines affected

None ratified. `README.md`'s target-specification table remains **DRAFT**;
this record supplies the first measured data point against every row but
does not itself change or ratify any bound (`spec/porting-plan.md` next step
4, out of scope here). `README.md`'s Basis column is updated to point at the
four records named above as evidence, not as a pass/fail claim.
