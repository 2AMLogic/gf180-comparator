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
| `regenerate.sh` | re-grades the manifest with the pinned grader distribution and rewrites the committed report |
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
   commit `31a3e3c4` (sha256
   `c7a1e7e10627fae396007e0ff951734f37d95028b8f49f2e21e802e9f552f318`).**
   The checklist grew its **eleventh item** — *Power delivery (structural)*
   — on 2026-09-17 (klayout-tools
   [#2025](https://github.com/2AMLogic/klayout-tools/issues/2025)), *after*
   the 0.5.0 release. The 0.6.0 wheel bundles an 11-item rulebook too (it
   lists `erc: 11` under `klt signoff --describe-grader`), but its bundled
   copy is **not** byte-identical to the vendored one (it is newer: e.g. the
   `partition_boundary` paragraph and `degenerate_well_assertion`), so the
   vendored copy and `--tiers-doc` stay until a deliberate re-vendor. Every grade here — regenerate, verifier,
   CI — passes `--tiers-doc signoff/design-evidence-tiers.md`; the file is a
   verbatim copy of that commit's `docs/design-evidence-tiers.md` (its
   sha256 above is the human-facing identity pin — the pinned wheel predates
   klayout-tools#2191, so it cannot itself hash the governing doc into the
   report). Re-vendoring the doc (dropping `--tiers-doc`) is a separate,
   deliberate step: it changes `source_doc` and the verifier's expectations.

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

- **met — item 2 (Layout), item 3 (DRC clean), item 4 (LVS clean), item 6
  (Monte Carlo; offset row only — see the item 5/6 section), item 8
  (Characterization report; generic envelope — see the item-8 section)**
- **unmet, reason `no_evidence` — items 1, 5, 7, 9, 10**
- **unmet, reason `supply_spec_incomplete` — item 11** (the 0.6.0 grader
  reads the cited ERC + LVS evidence; the ERC run declares no `ties[]` —
  klayout-tools#2169 — see the item-11 section)

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

### unmet — item 5 (PVT corners vs a ratified spec): blocked on #75

The four experiment directories under `sim/` carry committed
schematic-provenance corner records (`sim/comparator-{offset-mc,preamp-noise,
regeneration,kickback}/`, driven by `sim/characterize.sh` +
`sim/run_corners.py`). Item 5 needs **every** ratified spec row evaluated at
its bound corners as a `klt sim` envelope. The target-spec table is ratified
(DR-0002, two-key ceremony on PR #74), but only the offset-sigma row's
scoring pass has landed ([#24](https://github.com/2AMLogic/gf180-comparator/issues/24),
PR #58); the other four rows' scoring is tracked in
[#75](https://github.com/2AMLogic/gf180-comparator/issues/75), and their
records are this repo's harness format, not `klt sim` envelopes. **Item 5
depends on #75** and stays `no_evidence` until that lands; the item-6
citation above does not substitute for it (a Monte Carlo report is not the
`sim` envelope item 5 accepts).

### unmet — item 7 (Post-layout verification): not started

Post-layout re-simulation against the extracted netlist is issue
[#23](https://github.com/2AMLogic/gf180-comparator/issues/23) (blocked on
item 4's chain). Item 7 rejects every evidence kind except a `klt pex`
report for an analog block — a clean DRC, LVS, or pre-layout sim renders
`wrong_kind` — so there is nothing to cite until that work exists.

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
The item-6 yield report and item-8 wrapper show different claims. `klt sim`
corner-sweep envelopes for the testbenches are open work under item 5
([#91](https://github.com/2AMLogic/gf180-comparator/issues/91)). Such an
envelope backs item 9 only if it records the cold-start invocation and the
pinned PDK; one that does not would still leave item 9 uncited.
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

### unmet — item 11 (Power delivery, structural): first supply evidence cited; the grader cannot read it yet

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
graded machine and cross-checks the committed record three ways on every
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
3. **The vendored rulebook is what graded.** The fresh
   grade's `source_doc` must be `signoff/design-evidence-tiers.md`; a grade
   that ran against the wheel's bundled 10-item copy instead fails by name.

**Refresh contract.** Any change to a cited evidence envelope or to the
cited artifacts means: re-run the producing flow (e.g.
`layout/run_drc.py`/`layout/run_lvs.py` per `layout/README.md`;
`signoff/make_item8_envelope.py` for the item-8 wrap), re-pin the
hash in `block-manifest.json`, run `./signoff/regenerate.sh`, commit the
fresh report — in one change. A *new* citation means adding the
corresponding pin row to `verify-report.py`'s `PINNED_ARTIFACTS` in the
same change (item 6's `klt yield` citation is the exception: it pins its
samples document, handled by `verify_yield_pin()`); an unlisted citation fails the verifier by name rather than
passing unverified.

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
