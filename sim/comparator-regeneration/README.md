# `sim/comparator-regeneration/`

**Decision time versus input overdrive** over the full PVT grid, the
regeneration time constant **τ** extracted from it, near-metastable
behaviour, and the switching energy per decision.

Backs [`README.md`'s decision-time row](../../README.md#target-specification-ratified-via-dr-0002)
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
logarithmic region. `td_od1_over_tau = t(1 mV)/τ` is reported alongside it:
the **e-folds of full clock-to-output delay over τ** (natural-log units, not
decades — divide by ln(10) ≈ 2.303 for decades). It is a report-only
diagnostic (DR-0005), not the number of e-folds of regeneration available in
a decision phase: `t(1 mV)` includes the fixed, non-regenerative delay `t0`,
so the ratio overstates the regenerative lever arm. Records written before
issue #141 carry the same quantity under the misleading name
`resolve_decades`; `tb.json` keeps that key as a deprecated alias (identical
expression) for one release so old and new records stay comparable.

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

The three rungs above time the **LOW→HIGH** output decision only. Since issue
#158 the same deck also carries a **mirrored, supplemental reverse-polarity
ladder** (HIGH→LOW). See
[Reverse-polarity decision time](#reverse-polarity-decision-time-issue-158--supplemental-not-scored)
below. It changes no forward card, expression, check or name.

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
| [`20261009-194212777873-3617a0b`](records/20261009-194212777873-3617a0b.md) | `comparator-dr0001` (**schematic**, same netlist as the next row) | 45/45, `mos` × 3 T × 3 V (klt sim fleet) | REFERENCE: `td_od50_ns` within target 45/45; adds the **supplemental, unscored** reverse-polarity columns ([#158](#reverse-polarity-decision-time-issue-158--supplemental-not-scored)) |
| [`20260910-125206-4805118`](records/20260910-125206-4805118.md) | `comparator-dr0001` (**schematic**) | 45/45, `mos` × 3 T × 3 V | PASS |
| [`20260909-055524-e2bb637`](records/20260909-055524-e2bb637.md) | `placeholder-v1` (**placeholder**) | 45/45, `mos` × 3 T × 3 V | PASS |

The `20260910-125206-4805118` row is the current reference (the #158 row
above re-measures the same netlist's forward ladder to within 5×10⁻⁶ and
adds only supplemental columns): taken against
[DR-0001](../../spec/decision-records/DR-0001-comparator-topology.md)'s
static preamp + StrongARM latch, no placeholder banner. `td_od50_ns` is
0.708 ns at nominal, 1.237 ns worst-case at `ss_125c_2.97v` — meets the
README ≤ 1.5 ns target at every corner, misses the ≤ 0.8 ns stretch at the
slow/hot/low-supply corner; reference against the ratified bound, this
row's verdict scoring tracked in [#75](https://github.com/2AMLogic/gf180-comparator/issues/75) (not retuned here). The `td_od50_ns` per-axis floors (calibrated
against the placeholder DUT, below) held on the real schematic with margin
and were not recalibrated.

**Read the banner on the placeholder row.** It was taken against the
placeholder DUT and substantiates the harness, not the decision-time row; it
stays committed as append-only evidence but is superseded as the current
reference. It is also the record the `td_od50_ns` per-axis floors are
calibrated from (observed weakest slices: process 15.16 %, temperature
20.05 %).

### Post-layout record (issue #23): `20261002-202641-baeffe5`

The second record in `records/` is the **post-layout** one, minted against
the extracted binding (`comparator-dr0001-layout`, `provenance: extracted`)
over the same 45-point grid. What it shows:

- **The layout parasitics roughly double the decision time**: `td_od50_ns`
  0.708 → 1.158 ns at nominal (+63.6 %), 1.237 → 2.034 ns worst-case, and
  `tau_ps` +59 % at nominal — the routing RC on the preamplifier output
  nodes (`aop`/`aon` each gain ~35–40 fF and ~200–250 Ω against a 120 kΩ
  load) sits directly on the regeneration pole.
- **The extraction carries a deterministic systematic input-referred
  offset** the schematic cannot have: `dut_vos_v` measures −1.8 mV
  (`ss_-40c_2.97v`) to −21.6 mV (`ff_125c_3.63v`) across PVT, from the
  ~10 % R / ~14 % C routing asymmetry between the two preamp output nets
  (per-net numbers in `layout/lvs/comparator.extract-rc.json`). This is
  larger than the Monte-Carlo 3σ offset of the same design
  (2.8 mV) — a layout finding, not a simulation artefact: the no-parasitics
  extraction of the same GDS runs this bench clean (see the control note in
  `layout/README.md`'s post-layout section).
- Because of that offset, this record's ladder is **referred to the probed
  trip point** (`dut_vos`, per the `tb_vosprobe.spice` probe; the
  gf180-sar-adc post-layout convention) — each rung is a true 50 mV / 1 mV /
  0.1 mV overdrive above the comparator's own trip point at that corner.
  The schematic record's 0 V-referenced ladder is unchanged and measures
  byte-identically to before (`dut_vos` = 0 there).
- The record's **Post-layout delta** table (rendered by the harness)
  carries the full nominal + whole-grid-mean comparison against the
  schematic record cited above, and its Reproduce block regenerates the
  extracted binding first (`python3 layout/run_extract_sim.py`).

### Consumer half-LSB use of the 1 mV rung (issue #109)

`spec/consumers.md` compares the delay at the consumer's half-LSB overdrive
(1.61 mV) to the 15.625 ns stretch-rate phase budget. No separate 1.61 mV
rung exists or was added: delay is monotone non-increasing in overdrive, so
the existing **1 mV** rung bounds it from above, per corner. Worst `td_od1_ns`
over the 45 corners: 1.673 ns schematic (`20260910-125206-4805118`), 2.716 ns
extracted (`20261002-202641-baeffe5`), both at `ss_125c_2.97v`. These are
offset-referred to the trip point (extracted ladder centred on `dut_vos`);
they are not a total-error guarantee. To re-derive the numbers, read the
`td_od1_ns` column of those two records (no new simulation). If a direct
~1.61 mV rung is ever wanted, add a fourth instance with `dv_cons=1.61m` to
`tb_regeneration.spice`, matching `td_d`/`dout_*` measures in `tb.json`, and
run it through `klt sim` (batch backend) to mint a new record; do not edit the
existing ones.

### Reverse-polarity decision time (issue #158) — supplemental, not scored

Every row above times the **LOW→HIGH** output decision: `td_a/b/c` are
`targ ... rise=1 td=35n`. The `dout_*_first` samples prove that the forward
ladder decided both ways. They do **not** time the HIGH→LOW direction. Since
#158 the deck carries a **mirrored ladder** to measure it:

| instances | stimulus | timed edge | columns |
|---|---|---|---|
| `Xa/Xb/Xc` (unchanged) | −dv on strobe 1, **+dv** on strobe 2 | output **rise**, 2nd strobe | `td_od*_ns`, `tau_ps`, `dout_*_first/_end` |
| `Xra/Xrb/Xrc` (new) | +dv on strobe 1, **−dv** on strobe 2 | output **fall**, 2nd strobe | `td_od*_rev_ns`, `tau_rev_ps`, `dout_*_rev_first/_end` |

- **Same method, mirrored.** The reverse ladder uses the same rungs (50 mV,
  1 mV and 0.1 mV), the same `t_flip`, the same `trig v(clkn) rise=2`, the
  same supply-normalized 0.5 threshold and the same `td=35n` window. The
  window opens after the power-up resolution and after the first decision, so
  neither can be timed (`sim/harness/tests/test_regeneration_reverse.py` pins
  this against the fragment's own clock).
- **The sequence is proved per point.** `dout_*_rev_first >= 0.9` (HIGH after
  the first strobe) and `dout_*_rev_end <= 0.1` (LOW after the second) are
  checks. A point where the mirrored instance never went HIGH has no
  HIGH→LOW transition to time. That point **fails**: no delay is inferred.
- **Direction deltas** come from the same transient at each point:
  `dtd_od*_rev_ps` = reverse − forward, and `dtau_rev_ps` = τ_rev − τ.
- **Not scored.** `td_od50_ns`, `tau_ps` and `td_od1_over_tau` keep their
  names, expressions and meaning. Signoff's item-5 envelope
  (`signoff/make_item5_envelope.py`), the ratified decision-time row and
  [DR-0005](../../spec/decision-records/DR-0005-metastability-target.md)'s
  metric read only those forward quantities. `klt_record.py` prints the
  reverse columns in a separate "Supplemental … NOT SCORED" section and as
  `supplemental_reverse_polarity` in the JSON record. Changing the scoring
  scope would need its own decision record.

**Records (measured direction coverage):**

| record | DUT | grid | forward (scored) | reverse (supplemental) |
|---|---|---|---|---|
| [`20261009-194212777873-3617a0b`](records/20261009-194212777873-3617a0b.md) | `comparator-dr0001` **schematic** (`design/comparator.spice`, sha256 `0df618e73b1f0736`, the same netlist as `20260910-125206-4805118`) | 45/45, `mos` × 3 T × 3 V, klt sim batch fleet | `td_od50_ns` within target 45/45 | measured at 45/45, polarity proof passes at 45/45 |
| *(none: blocker)* | `comparator-dr0001-layout` **extracted** | — | `20261002-202641-baeffe5` (pre-#158 deck) | **not measured**, see below |

What the schematic record shows:

- **HIGH→LOW is faster at every PVT point and every rung.** `dtd_od*_rev_ps`
  runs from −105 ps (`ff_-40c_3.63v`) to −262 ps (`ss_125c_2.97v`). Both
  directions bind at `ss_125c_2.97v`: 50 mV forward 1.237 ns vs reverse
  0.975 ns; 0.1 mV forward 1.956 ns vs reverse 1.694 ns. The forward
  (scored) direction is therefore the slower one.
- **The asymmetry is in the fixed delay, not in regeneration.** At each point
  the delta is the same at all three rungs to within 0.26 ps, and
  `dtau_rev_ps` lies between −0.075 and +0.022 ps. τ_rev equals τ (worst 122.9 ps at
  `ss_125c_2.97v`). On the schematic the reverse direction does not widen any
  metastability statement computed from `tau_ps`.
- **The added instances do not disturb the forward ladder.** Against
  `20260910-125206-4805118`, which used the same DUT netlist and the pre-#158
  deck, the forward delays agree within 5×10⁻⁶ relative at all 45 points and
  `tau_ps` agrees within 5×10⁻⁵.
- **Fleet note.** The v3.63 supply request was refused twice with
  `batch_no_capacity` (Spot capacity). The identical staged request was then
  resubmitted and completed (`klt-sim-7445eb6cdf17`). The record was ingested
  with `--from-report`. Its source-bundle and linkage checks verify that the
  three reports belong to the bundled requests.

**Extracted (post-layout) coverage is a blocker, not a substitution.** No
extracted reverse record exists. The schematic record above does **not**
stand in for it, for two reasons:

1. **No fleet path exists for an offset-referred extracted ladder.**
   `mk_klt_request.py`/`klt_record.py` support the schematic binding only, and
   the `dut_vos` probe leg is not implemented. A `klt sim` request cannot carry
   a per-corner parameter (klayout-tools#2725). The only fleet route that
   chains the probe into the ladder is `layout/pex/pex_measure.py`. Its bench
   sha256 pins have been stale since #141, so it refuses to run. Running the
   45-point extracted grid locally with `run_corners.py` is not allowed on the
   shared dispatch workers.
2. **The trip-point convention does not establish the 0.1 mV reverse rung on
   the extracted DUT.** This was a single-point local check:
   `python3 sim/tools/regen_reverse_control.py --dut comparator-dr0001-layout`
   at `tt_27c_3.30v`, on the extracted netlist regenerated with the pinned
   klt 0.6.0 (sha256 `8ffe4ec2…`, the same netlist as `20261002-202641-baeffe5`),
   under host ngspice 42 against the pinned floor of 46, so it is scratch and
   not evidence. The 50 mV and 1 mV mirrored instances decided HIGH then LOW
   (0.811 ns and 1.129 ns reverse). The 0.1 mV instance, at +0.1 mV over the
   probed trip point (−8.218 mV), decided **LOW** on the first strobe. It
   therefore had no HIGH→LOW transition to time, and the point fails
   (`tdr_c` out of interval, `dout_od01_rev_first` ≈ 0). The probe does not
   show hysteresis: up-ramp and down-ramp trip points agree to 3.5 µV, inside
   its ~30 µV quantisation. The first strobe after the DC operating point
   appears to carry an effective offset of more than 0.1 mV relative to the
   steady-state probed trip point. The forward ladder's `dout_od01_first`
   check cannot detect this, because a LOW first decision is what that check
   expects. Per the issue, this is disclosed rather than read as symmetry.

Reproduce:

```bash
# schematic, 45-point grid on the batch fleet (never a local grid on a dispatch worker)
KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-regeneration
# single-point edge-semantics controls (local; positive must pass, suppressed
# second reverse decision must fail) -- also step 2b of sim/selftest.sh
python3 sim/tools/regen_reverse_control.py [--corner tt_27c_3.30v] [--dut <id>]
```

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
