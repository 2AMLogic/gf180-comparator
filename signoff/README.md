# signoff/ — the machine-graded T1 verdict of record

This directory carries this block's `klt signoff` block manifest (the
klayout-tools [design-evidence
tiers](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md)
T1 checklist), the graded report it produces, and the verifier that keeps
both honest. **The gap-to-T1 tracker (issue
[#3](https://github.com/2AMLogic/gf180-comparator/issues/3)) points here as
the verdict of record** — the hand-maintained checkbox list it used to carry
is retired: "what is this block's T1 state" is now answered by re-running a
grader, not by re-reading prose written against whatever the checklist said
that day (issue
[#57](https://github.com/2AMLogic/gf180-comparator/issues/57) landed this
directory for exactly that reason).

## Contents

| file | what it is |
|---|---|
| `block-manifest.json` | the block manifest `klt signoff --manifest` grades: `block`, `kind`, and per-T1-item evidence citations with pinned `content_hash` |
| `signoff-report.json` | the committed output of the grading run — the graded T1 item table, per item `met`/`unmet` + machine-readable `reason` |
| `design-evidence-tiers.md` | the vendored, verbatim copy of the **11-item** T1 rulebook the report is graded under (see "The two pins" below) |
| `verify-report.py` | the anti-rot verifier CI runs on every push and PR (see below) |
| `design-evidence-tiers.md.sha256` | the machine-readable sha256 pin of the vendored rulebook (`sha256sum` format); the single expected value `check_rulebook_pin.py` enforces |
| `check_rulebook_pin.py` | the shared rulebook byte-identity check run by `regenerate.sh`, `verify-report.py` and the PDK-free test entrypoint (`tests/test_check_rulebook_pin.py` covers it) |
| `regenerate.sh` | re-grades the manifest with the pinned grader distribution and rewrites the committed report |
| `make_item5_envelope.py` | wraps the four committed corner records into the `klt sim`-shaped item-5 corner-matrix envelope under `sim/corner-matrix/` (`--check` detects drift); see the item-5 section |
| `tests/test_item5_envelope.py` | PDK-free regressions for the item-5 wrapper: all-measured-targets-pass fixture must still grade item 5 `unmet` (`partial_coverage`) under the pinned `klt`; append-only identity; historical bytes (`python3 signoff/tests/test_item5_envelope.py`, run in CI) |
| `make_item8_envelope.py` | writes the item-8 generic evidence envelope from the characterization report (`--check` detects drift); see the item-8 section |

## Block kind: `analog`

Confirmed against the block, not taken from the filing issue: the DUT is a
static differential preamplifier + StrongARM latch comparator
(`design/comparator.sch` + `design/comparator.spice`, decision record
`spec/decision-records/DR-0001-comparator-topology.md`), captured as
transistor-level SPICE on gf180mcu and verified by SPICE sweeps. There is no
RTL, no synthesis step, no standard-cell library, and no place-and-route
anywhere in the flow; the spec rows (`README.md`'s target-spec table:
input offset σ, input-referred noise, metastability/decision time, kickback)
are all analog measurements. There is no digital partition to declare, so
`mixed-signal` (which demands an explicit partition boundary and both
columns' evidence) would assert a partition that does not exist — `analog`
is the honest declaration, the same one the SG13G2 twin's manifest
(`sg13g2-comparator/manifests/sg13g2-comparator.json`, its issue #37) makes
for the same topology.

## The two pins

Grading this report reproducibly depends on two pinned things, and
`verify-report.py` refuses a grade that does not match either:

1. **The grader distribution: `klayout-tools==0.6.0`, the PyPI registry
   wheel.** `regenerate.sh` grades with a throwaway venv install of exactly
   that wheel and asserts its identity (`klt version --format json` must
   report `package_version: 0.6.0`, `git_tag: v0.6.0`, `is_release: true`) —
   same-version builds are *not* the same code (a git snapshot or
   full-checkout install under the same version string can grade a different
   item table than the released wheel), which is why neither regenerate nor
   CI ever grades with whatever `klt` happens to be on PATH. CI installs the
   same pin (`.github/workflows/signoff.yml`); keep the two pins in sync.
2. **The rulebook: `design-evidence-tiers.md`, vendored at klayout-tools
   commit `31a3e3c4` (sha256 pinned in `design-evidence-tiers.md.sha256`).**
   The checklist grew its **eleventh item** — *Power delivery (structural)*
   — on 2026-09-17 (klayout-tools
   [#2025](https://github.com/2AMLogic/klayout-tools/issues/2025)), *after*
   the 0.5.0 release. The 0.6.0 wheel bundles an 11-item rulebook too (it
   lists `erc: 11` under `klt signoff --describe-grader`), but its bundled
   copy is **not** byte-identical to the vendored one (it is newer: e.g. the
   `partition_boundary` paragraph and `degenerate_well_assertion`), so the
   vendored copy and `--tiers-doc` stay until a deliberate re-vendor. Every grade here — regenerate, verifier,
   CI — passes `--tiers-doc signoff/design-evidence-tiers.md`; the file is a
   verbatim copy of that commit's `docs/design-evidence-tiers.md`. Its
   byte identity is machine-enforced (issue
   [#168](https://github.com/2AMLogic/gf180-comparator/issues/168)):
   `design-evidence-tiers.md.sha256` (`sha256sum` format) is the **only**
   place the expected hash lives, and `check_rulebook_pin.py` is the one
   shared check — `regenerate.sh` runs it before installing or grading,
   `verify-report.py` runs it before anything else (check 0), and
   `scripts/run-pdk-free-tests.sh` runs it as the `rulebook-pin` step. The
   grade-drift comparison only sees the rendered item table, so without
   this a prose-only rulebook edit that leaves item ids, counts, statuses
   and reasons unchanged would pass; with it, it fails as a named
   `rulebook hash mismatch`. A missing rulebook or pin file fails too —
   nothing falls back to the wheel's bundled copy. Where a report carries
   `source_doc_content_hash`, the verifier also requires it to equal the pin.

   **Re-vendoring the rulebook** is deliberate and lands as one change:
   (1) copy the new verbatim `docs/design-evidence-tiers.md` in and review
   its diff; (2) refresh the pin with
   `sha256sum signoff/design-evidence-tiers.md > signoff/design-evidence-tiers.md.sha256`;
   (3) re-grade with `./signoff/regenerate.sh`; (4) run
   `python3 signoff/verify-report.py` (the grade-drift checks still apply);
   (5) commit rulebook, pin and report together. Dropping `--tiers-doc` in
   favour of the wheel's bundled copy is a further separate step: it changes
   `source_doc` and the verifier's expectations.

## How to re-run the grading

`klt signoff --manifest` is PDK-free — it grades the committed JSON
envelopes, it never runs DRC/LVS/sim gates — so grading can run anywhere
(the same discipline as the sibling canaries' signoff flows):

```bash
./signoff/regenerate.sh        # re-grade -> signoff/signoff-report.json
python3 signoff/verify-report.py   # CI runs exactly this
```

The report is committed with the exact form `klt` emits; regenerate it rather
than editing it by hand. `klt signoff` exits `3` when the block grades below
T1 — that exit code is **data** ("some items are unmet"), not failure; exit
1 (bad manifest / unparseable rulebook) and exit 2 (usage error) are real
errors.

## Current verdict, and the claims behind each row

Today the machine grades this block (see `signoff-report.json`, regenerated
by `./signoff/regenerate.sh`):

- **met — item 2 (Layout), item 3 (DRC clean), item 4 (LVS clean), item 11
  (Power delivery, structural; see the item-11 section), item 6
  (Monte Carlo; offset row only — see the item 5/6 section), item 8
  (Characterization report; generic envelope — see the item-8 section)**
- **unmet, reason `check_failed` — items 5, 7** (item 5 cited; the cited corner matrix honestly fails the ratified kickback bound, and also records the average-power row as incomplete coverage (clock rate TBD), so it would grade `partial_coverage`, not `met`, even with kickback closed — see the item-5 section. Item 7 cited; the `klt pex` report honestly fails the ratified decision-time target at 7 of 675 delta rows — see the item-7 section)
- **unmet, reason `no_evidence` — items 1, 9, 10**

`no_evidence` means exactly what it says mechanically: the manifest names no
citation for that item. It is **not** an assertion that the underlying work
is absent — for several items the substance exists but no `klt` envelope
backs it (the grader's own design: it only reads the evidence shapes named
in [docs/cli/signoff.md](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/signoff.md)).
What exists, per item, is stated below — the claim side the grader cannot
grade, stated precisely so nobody has to guess whether an `unmet` row means
"missing" or "present but ungradeable". The two-tier honesty rule from the
tiers doc cuts both ways: **`met` rows are weaker than they look** (their
coverage gaps are disclosed below) and **`unmet` rows may be stronger than
they look** (the substance noted below) — the machine verdict is the
starting point for each read, not the whole of it.

### met — item 2 (Layout): `layout/lvs/comparator.extract.json`

The extraction report is the documented-provenance statement of the
committed GDS: it pins `layout/comparator.gds` by content hash
(`provenance.input.content_hash`, mirrored in the manifest pin), and records
the extracted inventory — 29 devices (15 nfet, 12 pfet, 2 `ppolyf_u_1k`
load resistors), 20 nets, 8 pins, top cell `COMPARATOR` — from the layout
`layout/gen_comparator.py` generates. A present `klt extract` envelope is
definitionally a successful extraction, so a passing citation here states:
the committed GDS exists, parses, extracts, and its bytes are the exact ones
the pinned hash names. Disclosure, since the citation itself cannot say it:
the extraction recorded **no parasitics** (`parasitics: null`, a plain
`klt extract` run) and one warning — 12 internal nets not in the declared
pin set (`aon`, `aop`, `atail`, `ltail`, `mn`, `mp`, `na`, `nb`, `qn`, `qp`,
`sn`, `sp` — klayout-tools#514). `unbiased_pmos_body_nets` is empty.

### met — item 3 (DRC clean): `layout/drc/comparator.drc.json`

`status: clean`, 0 violations, deck `gf180mcu`, pinned to the same GDS hash
as item 2. **Coverage disclosure (the part the grader does not grade —
quoted from the cited envelope's own `coverage` block, not from memory):**

- `layers_in_stream_without_rules` — 7 layers drawn in this stream the deck
  has no rule for: `31/0`, `32/0`, `34/10`, `42/10`, `49/0`, `62/0`, `110/5`
- `rules_skipped` — 21 rules the deck carries but this run did not evaluate:
  `bjt.separation.comp.1`, `comp.space.mv.1`, `comp.width.mv.1`,
  `metal3.enclosing.via3.1`, `metal4.enclosing.via3.1`,
  `metal4.enclosing.via4.1`, `metal4.space.1`, `metal4.width.1`,
  `metal5.enclosing.via4.1`, `metal5.space.1`, `metal5.width.1`,
  `metaltop.space.1`, `metaltop.width.1`, `mim.enclosing.fusetop.1`,
  `mim.enclosing.via4.1`, `mim.space.1`, `pad.enclosing.metal5.1`,
  `via3.space.1`, `via3.width.1`, `via4.space.1`, `via4.width.1`
- `deck_scope` — which DRM chapters the deck transcribes at all:
  `10.4.2 MIM Option B`, `10.7 DRC_BJT Mark Layer`, `7.12 Contact`,
  `7.13 Metaln`, `7.14 Vian`, `7.15 MetalTop`, `7.4 Nwell`, `7.5 Comp`,
  `7.7 Poly2`, `9.1 Bond Pad`

"Clean" therefore means *clean within that scope* — a defect class outside
it (for instance on a rule-free drawn layer, or in a skipped metal4/via3
enclosure rule) is not excluded by this verdict.

### unmet — item 1 (Design sources): present, no envelope shows it

**Re-audited in [#89](https://github.com/2AMLogic/gf180-comparator/issues/89)
(policy: DR-0003); still deliberately uncited.** `design/comparator.sch`
(+ sub-cells and `.sym`s), `design/xschemrc`, `design/netlist.sh`, and the
generated `design/comparator.spice` are committed, with the netlist bound in
`sim/dut.json`. The item's claim is "sources plus the netlist derived from
them, regenerated on change". The only candidate, the item-4 LVS envelope,
pins `design/comparator.spice` (`environment.reference_sha256`) but shows
layout-vs-netlist equivalence, not that the netlist derives from the
schematic. `./design/netlist.sh --check` does check that, but it is a script
whose result is not an envelope and CI does not run it. Citing the LVS report
would flip the grade on a claim it does not show, so the row stays
`no_evidence`. Tool gap filed:
[klayout-tools#2844](https://github.com/2AMLogic/klayout-tools/issues/2844).

**PDK-free source pins (issue
[#120](https://github.com/2AMLogic/gf180-comparator/issues/120)) — what they
do and do not show.** CI now runs `python3 design/verify-netlist-pins.py
--check` (step "Netlist source-pin check (PDK-free)" in
`.github/workflows/signoff.yml`). It re-hashes the schematic hierarchy
(`design/comparator.sch` + the in-repo sub-cell `.sch`/`.sym` files) and
`design/comparator.spice`, plus the generation inputs `design/xschemrc` and
`design/netlist.sh`, against `design/comparator.sources.json`, which
`./design/netlist.sh` writes after each successful netlist, and fails on any
mismatch or a missing pin file. That proves the sch→spice step was re-run
after the last edit to either side. It does **not** prove the netlist is the
correct xschem output (the pin file is plain JSON and the check never runs
xschem; PDK resolution scripts, installed PDK symbols and the xschem version
are not pinned). It is not an envelope, and this change does not cite
it: whether it is enough for item 1 is a separate DR-0003 policy call, so the
row above is unchanged. Details: `design/README.md`, "Source pins".

### met — item 4 (LVS clean): `layout/lvs/comparator.lvs.json`

**Cited and graded `met` as of
[#68](https://github.com/2AMLogic/gf180-comparator/issues/68).** The
citation is the `klayout`-engine LVS report issue
[#40](https://github.com/2AMLogic/gf180-comparator/issues/40) landed:
`status: "match"` with `error_count: 0`, 29/29 devices, 20/20 nets and
8/8 pins matched — including `VDD <-> VDD` and `VSS <-> VSS`, both
`"pin": true` (part of all 20 nets matching). The three remaining
`mismatches[]` rows are all `severity: "warning"` disclosures, not findings
against the layout: `device.placeholder_value` and
`device.geometry_not_compared` (the reference-side placeholder-`0` resistor
value, and the resistor geometry parameters KLayout declares secondary —
neither took part in the compare, and the report says so) plus
`topology.flattened` (the compare flattened the reference netlist's 3
circuits into 1 first, per `docs/cli/lvs.md` "topology.flattened"). What
closed the check was upstream — klayout-tools#1907/#1927/#1928 — not a
change to this block; the full read of exactly what that `match` covers and
what it deliberately does not is `layout/README.md`'s "LVS" section.

**The pin names the netlist, not the GDS — a deliberate difference from
items 2/3.** The manifest entry pins the LVS envelope's own
`provenance.input.content_hash`, whose `role` is `"netlist"`: the sha256 of
the *extracted* layout netlist (`layout/lvs/comparator.extracted.spice`), a
derived scratch file the repo deliberately never commits (see `.gitignore`
and `layout/run_lvs.py`'s header). It cannot pin the GDS hash items 2/3 pin:
`klt signoff`'s staleness gate compares the manifest pin against
`provenance.input.content_hash`, and a GDS pin there would render this row
`stale_evidence`, not `met`. Since no committed artifact hashes to the pin,
`verify-report.py`'s item-4 row instead re-verifies the run's *committed*
inputs: the reference netlist `design/comparator.spice` against the
envelope's `environment.reference_sha256`, while the GDS bytes the
extraction consumed stay pinned by item 2's own citation (rows 2/3/11
re-hash those same bytes). Both checks run on every push and PR.

### met — item 6 (Monte Carlo): `klt yield` report for the offset row

**Cited and graded `met` as of
[#82](https://github.com/2AMLogic/gf180-comparator/issues/82).** The citation
is `sim/comparator-offset-mc/yield/yield-20260910-124917-4805118-target.json`,
a `klt yield` report over the committed offset-MC record
`20260910-124917-4805118` (45 PVT points x 200 draws), scored against the
ratified offset-sigma row's +/-15 mV limit (the +/-8 mV stretch report sits
beside it, uncited). The manifest pin is the sha256 of the **samples
document** the report names (a `klt yield` report carries no `provenance`
block, so `klt signoff` pins the samples it was computed from);
`verify-report.py` re-hashes that document. Nothing was re-simulated: an
adapter (`adapt_samples.py`) re-reads the per-draw `voa` values from the
committed logs and cross-checks them against the record's mean/sigma. Result:
200/200 inside the limits at every point, worst `sigma_to_spec` 15.9
(target) / 8.5 (stretch), `sample_size.verdict: sufficient` and the negative
control `detected` at all 45 points.

**Item-6 support for the total-offset metric (issue #200 assessment).** The
citation above remains the **preamp-only** DC samples; it has not been
relabelled and is not evidence for the whole-comparator total. The
whole-comparator record has per-draw simulated trip points (raw `.meas` in
`sim/comparator-offset-tran/corners/20261010-021500046481-d84e59d/report-main-v*.json`),
but (a) the scored total adds a *derived* load-resistor allowance that is not a
per-draw sample, so it cannot be presented as simulated samples to `klt yield`;
(b) only the simulated whole-comparator part could be wrapped, in a separate,
explicitly labelled yield report with its own adapter, which this change does
not add. Item 6 therefore stays on preamp-only evidence; a total-offset yield
report is a candidate follow-up, not claimed here.

**"Met" is weaker than it looks.** The pinned 0.6.0 grader reads the report's
`status` (`reported`: no `target_yield` is declared, so it cannot fail); it
does not grade the checklist's prose sub-requirements. The disclosed gaps,
in full in `sim/comparator-offset-mc/yield/README.md`: one seed (`20260909`)
with common random numbers across all points, so N is effectively 200 and
there is no seed replication; the `sufficient` verdict certifies yield >=
98.17 % (95 % CI), not a literal 3-sigma 99.73 %, the 3-sigma claim resting
on `sigma_to_spec` and a normal fit; the negative control is a synthetic
+20 mV shift of the same draws (it exercises the statistic, not the
circuit); MC is mismatch-only at deterministic process corners (no global
process MC); schematic DUT only. The seed has no field in the `klt yield`
report format (klayout-tools#2840). The report was produced with
`klayout-tools==0.6.0` plus a locally built `klt_yield_native` extension
(no published wheel — upstream klayout-tools#2531); grading it needs no
extension.

### unmet — item 5 (PVT corners vs a ratified spec): cited, `check_failed`

**Cited as of [#91](https://github.com/2AMLogic/gf180-comparator/issues/91),
scoring revision 2 as of [#108](https://github.com/2AMLogic/gf180-comparator/issues/108);
graded `unmet`, reason `check_failed` — the evidence is read and it fails.**
Item 5 accepts only a `klt sim` envelope (`measurements` + `corner_count`;
generic and every other kind render `wrong_kind`). The committed corner
records are this repo's harness format, so
`signoff/make_item5_envelope.py` **wraps them without re-simulating**:
`sim/corner-matrix/item5-corner-matrix-<four record ids>-r2.json` (revision 3, below, appends the whole-comparator record id), the 45-point
PVT grid of the four records DR-0002 ratified
(`20260910-{124917,125200,125206,125341}-4805118`), every value copied
verbatim, each source record pinned by sha256 in `source_records`. The
envelope's `wrapper` field states plainly that it is **not** `klt sim` output
(an off-host `klt sim` re-run was not needed; none was launched).

**Numerical compliance and coverage are separate, and both are required.**
The envelope's `eligibility` block carries `numerical` (`pass` only if every
corner meets every *measured* ratified *target* bound, DR-0002), `coverage`
(`complete` only if every ratified spec row is actually scored), and
`eligible` (both). The ratified supply/power row is **average** power, one
decision per clock edge, at a stated clock rate — and that rate is still TBD
(root `README.md` target-spec table). So the row cannot be scored, and the
wrapper says so instead of standing static power in for it:

- `spec_rows[]` entry `supply_avg_power_uw` keeps the ratified 1000 uW
  target / 500 uW stretch, `coverage: "incomplete"`,
  `coverage_reason: "average_power_clock_rate_tbd"`, `clock_rate: null`, and
  `corners_within_target`/`corners_within_stretch` `null` (unknown, not a
  fake 0). No clock rate is chosen here; that is a spec change needing a
  decision record (`spec/README.md`).
- Static power is kept per corner as `static_power_uw` = `i_static_ua` x
  corner `vdd`, marked `partial_of: "supply_avg_power_uw"`, and summarised
  under that row's `partial_evidence` (45/45 within target and stretch,
  84-105 uW, the exact product, tighter than the report's loose 82-108 uW
  range). It is scored against the same 1 mW bound because static power is a
  lower bound on average power: a static value over the bound would be a real
  failure, but a static pass does **not** score the average-power row.
  (`e_dec_fj` is recorded by the regeneration bench but deliberately carries
  no check there, so it is not combined into anything.)
- The envelope's `coverage` block (the `klayout_tools.coverage` v1 shape the
  pinned grader validates) lists every measured (corner, row) pair as
  `checked` and the average-power row at all 45 corners as `skipped`.

**`status` is derived, never asserted**, with the grader's own common rollup
rule (failure precedes coverage): `fail` if any measured target misses; else
`pass_partial` while any ratified row is unscored; `pass` only when both
hold. `pass_partial` is the `sim` kind's partial token in the pinned
`klayout-tools==0.6.0` grader, which grades it `unmet` with reason
**`partial_coverage`** — distinct from `check_failed`, so incomplete coverage
is never presented as a measured limit violation. Per-corner `status` follows
the same rule (`fail` / `pass_partial`). Consequence: **closing the kickback
miss alone cannot turn item 5 `met`** while average power is unscored — it
moves the item from `check_failed` to `partial_coverage`.
`signoff/tests/test_item5_envelope.py` pins exactly that with a synthetic
all-measured-targets-pass fixture graded by the pinned `klt`.

Result today: `status: fail`, 0/45 corners passing unconditionally, 1/45
`pass_partial`, 44/45 `fail`. Per row (`spec_rows`): offset 3-sigma 45/45
within target and stretch; noise 45/45 and 45/45; decision time 45/45 target,
29/45 stretch (worst `ss_125c_2.97v`, 1.237 ns); **kickback 1/45 within
target (only `ss_-40c_2.97v`), 0/45 within stretch, worst 10.01 mV at
`sf_-40c_3.63v`**; average power incomplete (static partial evidence as
above). These match the characterization report's scoring. No bound is
relaxed; item 5 turns `met` only when kickback closes (a follow-on decision
record or design change, re-wrapped from a new record set) **and** the
average-power row is scored (a decision record stating the clock rate, plus
a measured per-decision energy the bench actually checks). The manifest pin is
the DUT netlist (`provenance.input`, role `netlist`, `design/comparator.spice`),
which `verify-report.py` re-hashes; `python3 signoff/make_item5_envelope.py
--check` re-derives the envelope from the four records and fails on drift.

**Revision 3 (issue #200): the offset row is scored on the whole-comparator
record.** `item5-corner-matrix-<four ids>-<offset-tran id>-r3.json` scores
`offset_3sigma_mv` on `sim/comparator-offset-tran/records/20261010-021500046481-d84e59d`
(45 PVT points x N = 200, fleet jobs `klt-sim-ee7ad68415d2`,
`klt-sim-a503009e268a`, `klt-sim-031f74d456a0`), value `vos_3sig_total_cons_mv`
= simulated whole-comparator mismatch (latch included) plus a **derived, not
simulated** conservative load-resistor budget (the PDK models none). Result:
2.994-3.795 mV, 45/45 within target and stretch, binding corner
`ff_125c_3.63v`. The record is used **only** if `validate_offset_tran` finds
complete supported coverage and valid provenance (`complete`, no named problem
such as `TRIP_OUT_OF_RANGE`, 45 expected corners, exactly 200 finite draws per
point, `citable` + `reference` + clean source bundle, DUT netlist hash = current,
unchanged 15 / 8 mV bounds). Otherwise the offset row falls back to the
preamp-only DC value, is marked `coverage: incomplete` (reason
`offset_whole_comparator_not_substantiated`, problems listed), is added to
`coverage.skipped` and the corners' `unscored_rows`, and the envelope cannot
exceed `pass_partial`. Each offset measurement discloses `simulated` and
`derived_not_simulated` terms; the preamp-only value rides along as
`diagnostic_preamp_only_3sigma_mv` (per corner) and `preamp_only_diagnostic`
(row). Unrelated unmet items are unchanged: kickback still fails (44/45
corners `fail`) and average power stays unscored, so item 5 remains `unmet`
(`check_failed`). Regression fixtures in `signoff/tests/test_item5_envelope.py`
cover an omitted corner, missing draws, a saturation/incomplete record,
non-finite derivation, dirty/uncitable provenance, stale DUT, a relaxed bound
and a missing record. The r2 file stays committed unchanged.

**Revision 4 (issue #204): the kickback row is scored on the both-node
record.** `item5-corner-matrix-<offset-mc id>-<noise id>-<regen id>-<kickback id>-<offset-tran id>-r4.json`
scores `kickback_1k_peak_mv` on
`sim/comparator-kickback/records/20261010-022609774981-bf851ec` (klt-record
format, `input_node_coverage` = `both`) instead of the positive-node-only
`20260910-125341-4805118`. The record is used **only** if
`validate_kickback_both` passes (45 points, complete, citable + reference,
clean tree, DUT netlist hash = current, unchanged 5 / 2 mV bounds, coverage
`both`, finite `kick_1k_peak_mv` everywhere); otherwise the row falls back to
the older record and says so (`partial_node_coverage`, reason
`kickback_partial_node_coverage`, problems listed). Values shift by at most
2.22 uV (worst `sf_-40c_3.63v`: 10.00758 -> 10.00980 mV); verdicts are
unchanged: 1/45 within target, 0/45 within stretch. Bounds untouched; the
r1/r2/r3 files stay committed unchanged. Extracted-DUT both-node evidence is
out of scope (#112).

**Append-only identity.** The file name is the four record ids plus
`-r<SCORING_REVISION>`: a new record set *or* a new scoring revision mints a
new file, and an existing file with different content is never overwritten.
Revision 1 (`item5-corner-matrix-<four record ids>.json`, no suffix, #91)
stays committed byte-for-byte as historical evidence — it scored
`i_static_ua` x `vdd` as if it were the average-power row
(`supply_power_uw`, "avg static"). It was written by the script as of commit
`1cdd5cb`; the current script does not regenerate it. Refresh after a
scoring change: bump `SCORING_REVISION`, run
`python3 signoff/make_item5_envelope.py`, repoint the item-5 `file` in
`block-manifest.json` and the item-5 `PINNED_ARTIFACTS` path in
`verify-report.py` (the manifest `content_hash` stays the netlist pin, never
the envelope's own hash), run `./signoff/regenerate.sh`, then
`python3 signoff/verify-report.py` and
`python3 signoff/tests/test_item5_envelope.py`.

Disclosure: schematic-provenance records only (no post-layout), and the
item-6 citation does not substitute for this one. A native `klt sim`
re-run of the grid (batch fleet) would replace the wrapper; the harness's
bench decks are not `klt sim` requests, so that is a re-expression, not a
re-run, and is not done here.

### unmet — item 7 (Post-layout verification): `check_failed`, 7 of 675 delta rows miss the decision-time target

**Evidence cited and graded as of
[#81](https://github.com/2AMLogic/gf180-comparator/issues/81); the item is
`unmet / check_failed`, no longer `no_evidence`.** Item 7 accepts only a
`klt pex` report (any other kind renders `wrong_kind`), so the citation is
[`layout/pex/comparator.pex.json`](../layout/pex/comparator.pex.json): the
per-corner, per-spec-row schematic-vs-extracted delta over the same 45-point
PVT grid as the regeneration bench (5 process x 3 temperature x 3 supply),
15 spec rows each, 675 delta rows. Regenerate with
`python3 layout/pex/run_pex.py`. The manifest pin is the report's
`provenance.input.content_hash` (the `layout/comparator.gds` stream, same
convention as items 2/3/11), which `verify-report.py` re-checks.

**Result, not relaxed:** 668 rows pass, 7 FAIL, 0 error. All 7 are
`td_od50_ns` (decision time at 50 mV overdrive) above DR-0002's ratified
<= 1.5 ns target, post-layout, at slow/hot/low-supply points: `tt_125c_2.97v`
(1.59 ns), `ss_27c_2.97v` (1.70), `ss_125c_2.97v` (2.03), `ss_125c_3.30v`
(1.74), `ss_125c_3.63v` (1.55), `fs_125c_2.97v` (1.55), `sf_125c_2.97v`
(1.65), against 0.95-1.24 ns on the schematic leg (about +60 to +69 %). The
spec is not touched; the item turns `met` only through a layout/design change
or a new decision record, tracked on the parent tracker.

How it was produced:

* `klt pex` is `klayout-tools==0.7.0` (`uvx --isolated`, never the host
  `klt`): the first release with `--measure-command`, which this flow needs
  because the extracted leg is a two-stage measurement (offset probe, then an
  overdrive ladder centred on the probed trip point, as in #23) that a plain
  `klt sim` testbench set cannot express. The repo's *grading* pin stays
  `0.6.0` and grades this 0.7.0-written report without trouble.
* `layout/pex/pex_measure.py` re-expresses the committed regeneration bench
  as `klt sim` requests (exact-match, hash-pinned rewrites; see its
  docstring) and every PVT grid goes to the batch fleet; nothing was run as a
  local ngspice grid. The fleet runner is older than 0.7.0, so the requests
  are submitted by a `klt` 0.6.0 client. Each side's requests, reports and a
  `summary.json` are committed under `layout/pex/artifacts/measure/`; the
  generated decks are scratch (git-ignored).
* The existing `sim/` records were not touched or re-run; this is a new,
  separate post-layout measurement (not a re-use of the 45-corner campaign
  record, which is not in `klt pex` shape).

Disclosures (the report's own `extraction.model` limits, stated, not hidden):

* **Capacitance:** net-to-ground from each net's own area/perimeter, plus
  net-to-net only for *vertical-overlap* coupling.
* **Lateral coupling:** modelled only for nets named `--critical-net`; none
  were named, so same-layer sidewall coupling and fringe shielding are
  **not modelled**.
* **Resistance:** a single lumped series R per net as a star across the net's
  device terminals; **no distributed RC** (`--distributed-rc` not used).
* **Frequency:** quasi-static, one frequency-independent R and C per net; no
  skin effect or transmission-line behaviour.
* The report carries `model_mismatch` (the schematic reference is
  hierarchical, the extraction is flat) and the DUT is measured through the
  harness's flat-DUT wrapper (`layout/run_extract_sim.py` adaptation onto PDK
  primitives). `body_bias` is `biased` (no unbiased device bodies).
* The schematic leg's ladder is centred at 0 V and the extracted leg's at its
  probed trip point (the harness's `dut_vos` convention); the offset itself
  is its own `dut_vos_v` delta row.
* Mismatch is off (deterministic corners); this is not a Monte-Carlo
  post-layout claim.

Findings: parasitic attribution of the misses
([#229](https://github.com/2AMLogic/gf180-comparator/issues/229); diagnostic
only, **item 7 stays `unmet`**, the citation above is unchanged):

* **What was run.** The cited extracted DUT was re-measured at
  `ss_125c_2.97v` and `tt_125c_2.97v`, using `pex_measure.py`'s own decks
  with 52 netlist variants. Each of the 20 extracted nets gets one variant
  with its series R removed and one with its ground C removed. There are
  also aggregate R/C/coupling variants, a device-geometry variant, and
  centring legs. All 154 `klt sim` requests went to the batch fleet. Evidence:
  [`layout/pex/artifacts/parasitic-attribution/20261010-120720-230574b/`](../layout/pex/artifacts/parasitic-attribution/20261010-120720-230574b/README.md),
  produced by `layout/pex/parasitic_attribution.py`.
* **Controls.** The control decks are byte-identical to the cited decks. Both
  the extracted and the schematic control reproduce the cited rows exactly
  (1.58774 / 2.02956 ns and 0.986719 / 1.23747 ns). Removing every parasitic
  *and* setting the schematic's S/D junction geometry reproduces the schematic
  leg. So the gap has exactly two sources: extracted RC and extracted
  junction geometry.
* **Dominant contributor: ground C on a few nets.** Removing all ground C
  closes 83 % of the gap (tt 82.6 %, ss 83.6 %). The star-model series R
  accounts for about 5.5 % (largest single net: `ltail`, 2.6 %). The
  vertical-overlap coupling C accounts for about 0.5 %. Four nets on the
  decision-to-output path explain about 71 % together: `sn` 21.8 %, `doutb`
  19.2 %, `qn` 15.2 % and `dout` 14.7 %. `sn` carries about 3x the ground C
  of its mirror `sp` (20.8 vs 7.1 fF). The remaining ~14 % is the extracted
  S/D junction geometry (AS/AD = 0.5 um x W against the schematic's 0.18 um
  x W). Tying the extraction's floating `vsubs` node to ground slows the
  decision slightly (-2 %), so it is not a contributor.
* **Centring confound: ruled out.** Centring the extracted ladder at 0 V
  (the schematic's convention) would make the extracted leg *faster* by about
  4 % of the gap, because 0 V centring over-drives by |dut_vos|. Centring
  the schematic at its own probed trip point (+32 uV) moves `td_od50_ns` by
  at most 0.11 ps. None of the +60 % comes from the convention.
* **What the data points to: a layout change.** The data points to reducing
  routing ground C on `sn`, `doutb`, `qn` and `dout`, and to shorter or
  shared S/D diffusions. A DR-0004-era re-layout would target the same nets.
  The data does not point to a new decision record: the miss is a physical
  loading effect, not a measurement artefact. Any layout change or decision
  record is a separate issue. No variant here was graded against the spec,
  and nothing here relaxes it.

### met — item 8 (Characterization report): generic envelope around the narrative report

**Cited and graded `met` as of
[#80](https://github.com/2AMLogic/gf180-comparator/issues/80).** The
citation is `measurements/characterization-report.item8.json`, a hand-rolled
**generic evidence envelope** (`"kind": "generic"`, klayout-tools#1152 — the
one T1 item that may cite one; every other item renders `wrong_kind` on a
generic citation). `signoff/make_item8_envelope.py` writes it
deterministically (stdlib only) from
[`measurements/characterization-report.md`](../measurements/characterization-report.md):
it pins the report's sha256 in the envelope's
`provenance.input.content_hash` — the exact field the grader's staleness
gate compares against the manifest's own `content_hash` pin, and the field
`verify-report.py`'s item-8 `PINNED_ARTIFACTS` row re-checks against the
current report bytes. Without that `provenance` block a pinned generic
citation can only ever grade `stale_evidence`, never a false pass — the
wrapper is deliberately un-provable if the report it names rots.

**What the `pass` asserts, and what it does not.** `status` in a generic
envelope is the caller-asserted verdict for *item 8's claim* — that one
aggregated, current characterization record, scored against the ratified
DR-0002 table with every verdict citing its committed evidence record,
exists — not a claim that every spec row meets its target. The report itself
scores two rows as misses against the ratified bar (decision-time stretch at
`ss_125c_2.97v`; kickback target and stretch), and those misses are named in
the envelope's `summary` so they travel with the citation instead of being
laundered into a bare `pass`. The full per-row story, with each verdict's
evidence record, is the report's own
[Known gaps](../measurements/characterization-report.md) section; the
narrative report and its evidence chain are unchanged by this citation
(read-only wrap, per #80's scope).

Refresh contract for this citation: the report is the artifact — if it
changes, re-run `python3 signoff/make_item8_envelope.py` (or its `--check`
mode to detect drift), re-pin the item-8 `content_hash` in
`block-manifest.json`, and re-grade via `./signoff/regenerate.sh` in one
change.

### unmet — item 9 (Testbenches shipped): present, no `klt sim` envelope

**Re-audited in #89 (DR-0003); still deliberately uncited.** The four
committed testbench directories (`sim/comparator-*/testbench/`), the
cold-start drivers (`sim/characterize.sh`, `sim/selftest.sh`; selftest passed
all 9 checks on 2026-09-15) and the pinned PDK variant (`sim/pdk.json`,
`gf180mcuD`) are the substance. But no `klt sim` envelope exists: the
`sim/*/records/*.json` files are this repo's harness format, which the grader
does not read, and no selftest/characterize run is committed as an envelope.
The item-6 yield report and item-8 wrapper show different claims. The
item-5 corner-matrix wrapper
([#91](https://github.com/2AMLogic/gf180-comparator/issues/91)) is derived
from records, not a run of the testbenches, and records neither the
cold-start invocation nor the pinned PDK, so it does not back item 9.
Tool gap: klayout-tools#2844.

### unmet — item 10 (Repo hygiene): partially true, no CI-produced evidence

**Re-audited in #89 (DR-0003); still deliberately uncited.** `README.md`
(with the target-spec table and reproduction commands), `CLAUDE.md`, `spec/`
and a LICENSE exist. The item also demands CI that keeps the harness and
evidence formats valid. The only CI is `signoff.yml` (anti-rot on the signoff
evidence); it does not run the harness tests (`sim/harness/tests`) or
`design/netlist.sh --check`, and no CI run evidence is committed. So the CI
leg is only partly met and unevidenced; the row stays `no_evidence`. Adding
those CI steps is the path to a citable claim. Tool gap: klayout-tools#2844.

### met — item 11 (Power delivery, structural): ties[] declared (#103)

The 11-item rulebook renders the row (that is why the rulebook is pinned at
the vendored 11-item revision). Issue
[#56](https://github.com/2AMLogic/gf180-comparator/issues/56) has now
landed the first `klt erc` supply evidence, and this manifest cites the
compound analog entry the rulebook's item 11 names: the ERC supply report
`layout/erc/comparator.erc.json` (spec
`layout/erc-supply-spec.json`; run `klt erc ... --deck gf180mcu`;
`erc_status: "clean"`, zero findings, one electrical island per declared
supply, `provenance.input.content_hash` pinning the same committed GDS
items 2/3 cite).

**Update (#103): `ties[]` is now declared and the row grades `met`.** The
upstream blocker (klayout-tools#2169, `ties[]` collapsing a routed design to
one island) is closed, as are the follow-ups for implant-free streams (#2234),
native-substrate ties (#2255) and well-side selectors (#2339, #2540). The
spec declares two ties and the re-run at the released `klayout-tools==0.6.0`
wheel reports `erc_status: "clean"`, zero findings (no false
`erc.supply_short`), one island per supply, and `erc.missing_tie` *checked*
for both: `nwell_vdd` (Nwell 21/0, Nplus-narrowed Comp taps, to `vdd`) and
`substrate_vss` (no pwell is drawn, so `well_layer: null` with asserted
`well_boxes` covering the die outside the Nwell footprint; Pplus-narrowed
Comp taps, to `vss`). The substrate tie is graded under
`erc_coverage.checked_by_well_assertion`: its which-region half is the
spec author's assertion, not a derived result; the tie is non-degenerate and
no row is skipped or inapplicable. Because 0.6.0 rejects unknown top-level
spec keys, the spec's old `_comment` moved to
`layout/erc-supply-spec.notes.md`. The manifest pin is unchanged (it is the
GDS hash, which this change did not touch). The history below is superseded.

**Update (#90): the pin moved to `klayout-tools==0.6.0`, which recognizes
item 11.** Item 11's manifest entry is now the compound list the grader
requires (the ERC report plus item 4's LVS report, same pin), because a lone
`erc` citation grades `wrong_kind`. The row now renders `unmet`, reason
`supply_spec_incomplete`: the cited `klt erc` run declares no `ties[]`, so
`erc.missing_tie` is not computed (blocker klayout-tools#2169, below). The
paragraph below is the historical #68 state under 0.5.0.

**Re-checked in [#68](https://github.com/2AMLogic/gf180-comparator/issues/68)'s
pass (the same re-grade that cites item 4): the row still renders `unmet`,
reason `unrecognized_envelope` — and the premises this section used to state
as holding it open have both cleared as of #40.** The regenerated LVS
report's `net_correspondence` pairs `VDD <-> VDD` and `VSS <-> VSS` (both
`"pin": true`, part of all 20 nets matching), and the two `ppolyf_u_1k`
property findings survive only as `severity: "warning"` disclosures of the
passing LVS report — they no longer hold anything open. What still holds the
row at `unmet` is, first, the distribution pin: the pinned 0.5.0 release
predates item 11's grading rules (klayout-tools#1984 and later), so the
grader cannot read the cited ERC envelope at all — a state
[docs/cli/signoff.md](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/signoff.md)
anticipates. Moving that pin is deliberately out of #68's scope (see "The
two pins"); when a released `klt` that grades item 11 ships, upgrade the
distribution pin together with this citation (the refresh contract) and
re-grade. Second — even then, the row will render its real state on this
same evidence: `unmet` until the `ties[]` blocker klayout-tools#2169 clears
(the `erc.missing_tie` leg is not computed in the cited run, with the drawn
tap evidence the report's `erc_coverage.inapplicable` /
`provenance.devices` blocks record mechanically). The full claim-side
write-up, including exactly what stands in for the not-computed
`missing_tie`, is `layout/README.md`'s "ERC (T1 item 11)" section.

## The anti-rot gate (`verify-report.py`, what CI runs)

Grading `met` once proves nothing about next month. The verifier re-runs the
graded machine and cross-checks the committed record four ways on every
push and PR (`.github/workflows/signoff.yml`):

1. **Fresh grade == committed report.** `klt signoff --manifest` runs again
   against the pinned distribution and vendored rulebook; block-level
   fields and every per-item row (id/title/status/reason) must match
   `signoff-report.json` byte-for-byte. An envelope, manifest pin, or
   rulebook that changed without a re-grade + re-commit fails here.
2. **Every pin re-verified against current bytes.** For each citation:
   manifest `content_hash` == the cited envelope's recorded
   `provenance.input.content_hash` — the same staleness gate `klt signoff`
   applies at grade time — and the committed artifact the citation's
   `PINNED_ARTIFACTS` row names still hashes to the value the envelope
   records for it. For items 2/3/11 all three are the same sha256 (the
   GDS). Item 4 is the exception the row documents: its envelope's
   `provenance.input` pins the *extracted* netlist — derived scratch the
   repo deliberately never commits, so no committed artifact can hash to
   the pin — and its row instead re-hashes the run's committed reference
   netlist (`design/comparator.spice`) against the envelope's
   `environment.reference_sha256`, while the GDS the extraction consumed
   stays pinned by item 2's row. A manifest citing an artifact that has
   since changed fails rather than rotting — the acceptance criterion this
   whole directory exists for.
3. **Derived wrappers match their source records.** The verifier runs
   `signoff/make_item5_envelope.py --check` and
   `signoff/make_item8_envelope.py --check` (read-only, PDK-free). Each
   rebuilds its envelope deterministically from the cited records
   (item 5: the netlist plus four `sim/*/records`; item 8: the narrative
   report) and fails on any difference, so an edited source record or a
   hand-edited envelope fails even though the netlist pin is unchanged.
4. **The vendored rulebook is what graded.** The fresh
   grade's `source_doc` must be `signoff/design-evidence-tiers.md`; a grade
   that ran against the wheel's bundled 10-item copy instead fails by name.
   Before any of the above, the rulebook's bytes must match
   `design-evidence-tiers.md.sha256` (`check_rulebook_pin.py`, see "The two
   pins"), so a prose-only rulebook edit cannot pass.

**Refresh contract.** Any change to a cited evidence envelope or to the
cited artifacts means: re-run the producing flow (e.g.
`layout/run_drc.py`/`layout/run_lvs.py` per `layout/README.md`;
`signoff/make_item8_envelope.py` for the item-8 wrap;
`signoff/make_item5_envelope.py` for item 5, see its section), re-pin the
hash in `block-manifest.json`, run `./signoff/regenerate.sh`, commit the
fresh report — in one change. A *new* citation means adding the
corresponding pin row to `verify-report.py`'s `PINNED_ARTIFACTS` in the
same change (item 6's `klt yield` citation is the exception: it pins its
samples document, handled by `verify_yield_pin()`); an unlisted citation fails the verifier by name rather than
passing unverified.

**Wrapper drift vs grade drift.** Read the failing line to see which kind
you have:

- `... wrapper drift: python3 signoff/make_itemN_envelope.py --check exited 1`
  is *wrapper drift*: the committed envelope is not what the builder would
  write from its current source records. Fix the cause (restore the edited
  record/envelope, or deliberately produce the successor envelope with the
  wrapper; item-5 `sim/` evidence is append-only, so a changed record gets a
  new revision rather than an overwrite), then re-pin and re-grade.
- `fresh grade ... differs from committed` or a pin mismatch is *grade
  drift*: the envelopes are self-consistent but the manifest pin or committed
  `signoff-report.json` is stale. Re-pin `block-manifest.json` and run
  `./signoff/regenerate.sh`.

Wrapper drift usually causes grade drift too, so fix the wrapper first. CI
never regenerates anything; the author refreshes citations and grade together.
The regressions live in `signoff/tests/test_verify_wrappers.py` (temporary
fixtures only).

## Where this sits in the fleet

The fleet roll-up (2AMLogic/2am#956) consumes exactly this manifest —
`block: "gf180-comparator"` is this block's row identity in
`klt signoff --fleet`, and the roll-up reduces this directory's report to
one line (block, PDK, tier, blocking item). Its file-backed evidence paths
resolve against the invoking process's working directory — grade from this
repo's root, not from inside `signoff/`.

The two-PDK twin's counterpart is
[`sg13g2-comparator/manifests/`](https://github.com/2AMLogic/sg13g2-comparator/tree/main/manifests)
(its issue #37) — the same verdict-of-record mechanism with an
all-uncited manifest (the twin graded before it had any evidence worth
citing); the same-PDK-family canaries
`gf180-rcosc/signoff/` and `gf180-sram/signoff/` follow the same directory
convention used here.
