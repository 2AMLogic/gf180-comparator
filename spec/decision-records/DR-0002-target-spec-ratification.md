# DR-0002: Target-specification table — ratification as measured

- **Status**: proposed — ratification is the act of this record's PR being
  approved and merged, not the act of drafting it (2AMLogic/2am#357); do not
  hand-set `ratified` before merge.
- **Date**: 2026-09-15
- **Decided by**: Builder agent, issue #17
- **Supersedes**: none — first record that ratifies (or proposes to ratify)
  `README.md`'s target-specification table itself. `DR-0001-comparator-topology.md`
  ratifies the comparator's topology and sizing but explicitly declines to
  ratify any spec-table row ("None ratified. `README.md`'s target-specification
  table remains DRAFT").
- **Superseded by**: (none while this record stands)
- **Related**: [#3](https://github.com/2AMLogic/gf180-comparator/issues/3)
  (gap-to-T1 tracker, item 5, which this record closes); #17 (this issue);
  [2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357) ("Class 1 —
  canary spec/DR ratification questions" — the standing policy authorizing a
  builder to draft this record and open it as a PR, with the operator's PR
  approval constituting the ratification act); `spec/README.md` ("Decision
  records" — a DR is required whenever a target-spec row is set, changed, or
  scoped); [`DR-0001-comparator-topology.md`](DR-0001-comparator-topology.md)
  (topology/sizing decision and the schematic all four cited records measure
  against); `sim/comparator-offset-mc/records/20260910-124917-4805118.md`;
  `sim/comparator-preamp-noise/records/20260910-125200-4805118.md`;
  `sim/comparator-regeneration/records/20260910-125206-4805118.md`;
  `sim/comparator-kickback/records/20260910-125341-4805118.md`.

## Context

`README.md`'s target-specification table has carried the same five rows,
unchanged, since issue #2: original engineering-judgment bounds chosen to
match the `sg13g2-comparator`/`sky130-comparator` twin set for cross-PDK
comparability, not independently re-derived per PDK. `spec/README.md` states
plainly that "a decision record is required whenever a value or approach in
the top-level README's target-spec table is set, changed, or scoped" — but no
such record has ever been filed, so the table has sat headed "DRAFT —
engineering to ratify" through every subsequent measurement pass.

That gap is now the only thing blocking two downstream gap-to-T1 items ([#3]'s
2026-09-15 status update): item 6 (Monte Carlo scoring) and item 8 (the
narrative characterization report) both need a ratified bar to score against,
and neither can proceed against a table still labeled DRAFT.

Every row already has a first measured result to score against, all four
landed against the same schematic-level design
(`design/comparator.spice`, `id: comparator-dr0001`, `provenance: schematic`,
per [DR-0001](DR-0001-comparator-topology.md)):

- `sim/comparator-offset-mc/records/20260910-124917-4805118.md` — offset
- `sim/comparator-preamp-noise/records/20260910-125200-4805118.md` — noise
- `sim/comparator-regeneration/records/20260910-125206-4805118.md` —
  decision time *and* static power (both measured in the same 45-point run)
- `sim/comparator-kickback/records/20260910-125341-4805118.md` — kickback

Each record's own **Claim** field already states the same fact this record
formalizes: "REFERENCE, NOT VERDICT... that row is still DRAFT — no decision
record ratifies it — so a measured pass or miss here is same-PDK/same-design
context for the eventual ratification, not a pass/fail claim against a
ratified spec." This record is that ratification.

**Standing policy governing this record**
([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)): "a builder
drafts the ratification/DR as a PR on the evidence, and the operator's PR
approval is the ratification act. Values are proposed on their merits with
sources shown — never relaxed to make results pass... Failing-spec cases (a
measured result missing a ratified target) present the tradeoff options in
the DR draft; the operator rules at PR review." Concretely: this record
proposes ratification with `Status: proposed`; the operator's approval of the
PR that carries it is what flips it to `ratified`, not any action taken here.

Two of the five rows have a measured result that misses a bound at some or
all corners of the 45-point PVT grid (re-derived directly from the two cited
records' per-corner tables, not merely restated from `README.md`'s summary —
see "Tradeoff: decision time and kickback" under Consequences for the exact
corner counts, which are more precise than the "at `ss_125c_2.97v`" /
"at most corners" phrasing `README.md` currently uses). Per 2am#357, this
record presents both options for each — accept the gap as a known,
documented miss, or revise the row — without picking one.

## Decision

**Ratify `README.md`'s target-specification table at its existing bounds,
unchanged, as measured against the schematic-level design of
[DR-0001](DR-0001-comparator-topology.md).** No numeric target or stretch
value in any row is set, loosened, or tightened by this record — every bound
below is exactly what `README.md` already states; this record's only
contribution is the ratifying citation. Per this repo's `CLAUDE.md` ("agents
do not relax the ratified spec to make results pass") and per
`spec/decision-records/TEMPLATE.md`'s own instruction, no bound is adjusted
to make a result pass.

| Row | Target | Stretch | Measured (nominal `tt_27c_3.30v`) | Measured (45-point grid) | Verdict |
|---|---|---|---|---|---|
| Offset sigma | ≤ 15 mV 3σ | ≤ 8 mV 3σ | 3σ = 2.80 mV | 2.796–2.807 mV 3σ across all 45 corners | **meets target and stretch at every corner** |
| Input-referred noise | ≤ 1.0 mV rms | ≤ 0.6 mV rms | 91.25 µV rms (0.0913 mV) | 66.8–128.8 µV rms (0.0668–0.1288 mV) across all 45 corners | **meets target and stretch at every corner** |
| Decision time (50 mV overdrive) | ≤ 1.5 ns | ≤ 0.8 ns | 0.708 ns | 0.498–1.237 ns across all 45 corners | **meets target at every corner (45/45); misses stretch at 16/45 corners**, worst case 1.237 ns at `ss_125c_2.97v` |
| Kickback into 1 kΩ | ≤ 5 mV | ≤ 2 mV | 7.60 mV | 4.53–10.01 mV across all 45 corners | **misses target at 44/45 corners** (only `ss_-40c_2.97v` at 4.528 mV clears ≤ 5 mV); **misses stretch at 45/45 corners** (best case 4.528 mV still exceeds 2 mV) |
| Supply / power | ≤ 1 mW avg | ≤ 500 µW avg | 28.4 µA → ≈ 94 µW | 27.7–29.7 µA → ≈ 82–108 µW across all 45 corners | **meets target and stretch at every corner** |

Three of five rows (offset, noise, power) are ratified cleanly — the measured
result clears both target and stretch at every corner of the grid, so there
is no tradeoff to present for those rows. The remaining two rows (decision
time, kickback) each carry a genuine gap; see "Tradeoff: decision time and
kickback" below. **This record ratifies all five rows' numeric bounds as
they stand, including the two with a known gap** — ratifying a bound does not
assert the design meets it, only that the bound itself is now the agreed
target to measure against, with any miss recorded rather than hidden. If the
operator instead wants to revise either bound, see "Alternatives considered."

## Alternatives considered

- **Defer ratification until decision time and kickback close their gaps by
  resizing.** Not chosen. 2am#357 is explicit that failing-spec cases are
  *why* a DR is owed now, not a reason to wait — "a measured result missing a
  ratified target" is exactly the case the policy exists to handle, by
  presenting the tradeoff rather than by delaying ratification until the
  tradeoff disappears. Waiting would also stall gap-to-T1 items 6 and 8,
  which need a ratified bar regardless of whether every row currently clears
  it.
- **Ratify only the three passing rows (offset, noise, power) now and leave
  decision time / kickback DRAFT.** Not chosen. `spec/README.md`'s trigger for
  a decision record is the table as a whole, and a partially-ratified table
  (three ratified rows, two still headed DRAFT) would leave gap-to-T1 items 6
  and 8 unable to score two of five rows at all — worse than ratifying all
  five with two flagged gaps, which lets scoring proceed and states the two
  misses explicitly instead of leaving them unscored.
- **Revise the decision-time stretch bound (currently ≤ 0.8 ns) to a value
  the current sizing meets everywhere** (worst case 1.237 ns → a bound of,
  say, ≤ 1.25 ns, or accept meeting only the ≤ 1.5 ns target and drop the
  stretch tier for this row). Not chosen here — this is one branch of the
  tradeoff presented below, left for the operator to select instead of this
  record's proposed "accept and record" branch.
- **Revise the kickback target and stretch bounds (currently ≤ 5 mV /
  ≤ 2 mV) to match the measured 4.53–10.01 mV range**, e.g. loosening the
  target to something like ≤ 10 mV. Not chosen here for the same reason: this
  is the other row where a tradeoff is presented rather than resolved by this
  record.

## Consequences

- **Gap-to-T1 tracker item 5 closes.** `README.md`'s table stops reading
  "DRAFT — engineering to ratify" and points at this record instead (see
  "Spec lines affected"). Items 6 (Monte Carlo scoring) and 8 (narrative
  characterization report) become unblocked once this record is ratified —
  both can now score against agreed bounds instead of a DRAFT table.
- **No design work is invalidated.** This record changes no numeric bound and
  no testbench; every cited record stays exactly as committed. Nothing needs
  to be re-run as a consequence of ratification itself.
- **Two rows carry a ratified-but-missed gap forward, on the record, rather
  than being silently absorbed.** Any future characterization report (item 8)
  must report these as misses against a ratified bar, not as "still DRAFT, not
  a verdict" the way `README.md` currently frames them.
- **Post-layout parasitics can only make the kickback gap worse, not better**
  — `design/README.md` ("What is here and what is not") already states that
  layout extraction can only add capacitance at the input, and DR-0001's own
  Consequences section names kickback as "the consequence this decision most
  directly creates and should be revisited first." Ratifying the row as-is
  now means a future layout pass inherits an already-known, already-missed
  bound rather than discovering the miss for the first time post-layout.

### Tradeoff: decision time and kickback

Both rows have a real, re-derived (not merely restated) gap. Two options are
presented for each; this record does not choose between them — per 2am#357,
that choice belongs to the operator at PR review. **Approving this record's
Decision section as drafted (no bound touched) enacts Option A by default**
for both rows, because Option B (revising a bound) requires a numeric spec
change this record does not make; selecting Option B for either row means
rejecting or amending this PR rather than accepting it as drafted.

**Decision time (≤ 1.5 ns target / ≤ 0.8 ns stretch).** Measured worst case is
1.237 ns at `ss_125c_2.97v` — the target is met at all 45/45 corners; the
stretch bound is missed at 16/45 corners (all slow-process and/or
high-temperature/low-supply: `tt_125c_*`, `ff_125c_2.97v`, `ss_-40c_2.97v`,
`ss_27c_2.97v`/`3.30v`, `ss_125c_*`, `fs_125c_*`, `sf_27c_2.97v`,
`sf_125c_*` — see `sim/comparator-regeneration/records/20260910-125206-4805118.md`
for the full per-corner table).
- **Option A — accept the gap, record it as known.** Ratify ≤ 1.5 ns / ≤ 0.8 ns
  unchanged; the table's Basis column (already updated by this record, see
  below) states the target is met everywhere and the stretch is met at 29/45
  corners, missed at the 16 named above. No further action required by this
  record.
- **Option B — revise the row.** Loosen the stretch bound (e.g., to something
  at or above 1.24 ns, comfortably clearing the measured worst case) or drop
  the stretch tier for this row entirely, in a follow-on decision record.
  Not enacted here.

**Kickback (≤ 5 mV target / ≤ 2 mV stretch).** Measured range is
4.53–10.01 mV — the target is missed at 44/45 corners (only `ss_-40c_2.97v`
at 4.528 mV clears ≤ 5 mV); the stretch is missed at all 45/45 corners (even
the best-case corner exceeds 2 mV by more than 2×). This is the larger of the
two gaps, and the one DR-0001 already flagged as most likely to need
revisiting first.
- **Option A — accept the gap, record it as known.** Ratify ≤ 5 mV / ≤ 2 mV
  unchanged; the table's Basis column states the row is missed at 44/45
  (target) and 45/45 (stretch) corners at this sizing, and that post-layout
  parasitics can only widen the gap further (see Consequences). No further
  action required by this record.
- **Option B — revise the row.** Loosen the target/stretch bounds to reflect
  what a preamp-isolated topology at *this* sizing actually achieves (e.g., a
  target nearer the measured 7.6 mV nominal / 10.0 mV worst case), in a
  follow-on decision record — likely paired with a sizing change to the input
  pair's `C_gd` contribution, since the coupling path is the real device
  capacitance, not an invented component (DR-0001, "Consequences").
  Not enacted here.

## Spec lines affected

- `README.md#target-specification` — Offset sigma row (≤ 15 mV 3σ target /
  ≤ 8 mV 3σ stretch) — ratified as measured (no value change):
  `sim/comparator-offset-mc/records/20260910-124917-4805118.md` reports
  3σ = 2.80 mV at the nominal `tt_27c_3.30v` corner, 2.796–2.807 mV 3σ across
  the full 45-point PVT grid — meets target and stretch at every corner.
- `README.md#target-specification` — Input-referred noise row (≤ 1.0 mV rms
  target / ≤ 0.6 mV rms stretch) — ratified as measured (no value change):
  `sim/comparator-preamp-noise/records/20260910-125200-4805118.md` reports
  91.25 µV rms at nominal, 66.8–128.8 µV rms across the 45-point grid — meets
  target and stretch at every corner.
- `README.md#target-specification` — Decision time vs. overdrive row
  (≤ 1.5 ns target / ≤ 0.8 ns stretch at 50 mV overdrive) — ratified as
  measured (no value change), **with a known gap**:
  `sim/comparator-regeneration/records/20260910-125206-4805118.md` reports
  0.708 ns at nominal, 0.498–1.237 ns across the 45-point grid — meets target
  at 45/45 corners, misses stretch at 16/45 corners (worst case 1.237 ns at
  `ss_125c_2.97v`). See "Tradeoff: decision time and kickback" for the two
  options the operator may choose between.
- `README.md#target-specification` — Kickback row (≤ 5 mV target / ≤ 2 mV
  stretch into 1 kΩ) — ratified as measured (no value change), **with a known
  gap**: `sim/comparator-kickback/records/20260910-125341-4805118.md` reports
  7.60 mV at nominal, 4.53–10.01 mV across the 45-point grid — misses target
  at 44/45 corners and stretch at 45/45 corners. See "Tradeoff: decision time
  and kickback" for the two options the operator may choose between.
- `README.md#target-specification` — Supply / power row (≤ 1 mW avg target /
  ≤ 500 µW avg stretch) — ratified as measured (no value change):
  `sim/comparator-regeneration/records/20260910-125206-4805118.md` (same
  record as the decision-time row; static current is measured in the same
  45-point run) reports 28.4 µA mean at nominal (≈ 94 µW at 3.3 V), 27.7–29.7
  µA across the grid (≈ 82–108 µW at 2.97–3.63 V) — meets target and stretch
  at every corner.
- `README.md#target-specification` — table heading and "no decision record
  has ratified this table yet" sentence — changed from DRAFT framing to
  reference this record as **proposed** (this PR), flipping to ratified only
  once the PR merges.
