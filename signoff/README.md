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

1. **The grader distribution: `klayout-tools==0.5.0`, the PyPI registry
   wheel.** `regenerate.sh` grades with a throwaway venv install of exactly
   that wheel and asserts its identity (`klt version --format json` must
   report `package_version: 0.5.0`, `git_tag: v0.5.0`, `is_release: true`) —
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
   the 0.5.0 release: the wheel still bundles the older 10-item copy and
   without `--tiers-doc` it renders no item-11 row at all and disagrees with
   this report on `t1_item_count`. Every grade here — regenerate, verifier,
   CI — passes `--tiers-doc signoff/design-evidence-tiers.md`; the file is a
   verbatim copy of that commit's `docs/design-evidence-tiers.md` (its
   sha256 above is the human-facing identity pin — the pinned wheel predates
   klayout-tools#2191, so it cannot itself hash the governing doc into the
   report). When a klayout-tools release carrying the 11-item rulebook
   ships, move both pins forward together and re-grade.

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

- **met — item 2 (Layout), item 3 (DRC clean)**
- **unmet, reason `no_evidence` — items 1, 4, 5, 6, 7, 8, 9, 10**
- **unmet, reason `unrecognized_envelope` — item 11** (evidence is now cited;
  the pinned grader predates item-11 recognition — see the item-11 section)

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

### unmet — item 1 (Design sources): present but deliberately uncited

`design/comparator.sch` (+ sub-cells and `.sym`s), `design/xschemrc`,
`design/netlist.sh`, and the generated `design/comparator.spice` are
committed (PRs of issues #12/#18), with the netlist bound in `sim/dut.json`
and the topology + sizing rationale in DR-0001. `klt signoff` cannot check
any of that claim (no verb binds item 1; any passing envelope of any kind
would render it `met`, however unrelated), and the checklist's own guidance
plus the sibling canaries' practice is to leave this row uncited rather than
cite something topically unrelated — an `UNMET`/`no_evidence` row here is
the accurate machine statement, not a claim that the sources are missing.

### unmet — item 4 (LVS clean): the committed report fails, so nothing is cited

`layout/lvs/comparator.lvs.json` (`klayout` engine) reports
`status: "mismatch"` — `error_count: 6`, all `device.property` findings on
the two `ppolyf_u_1k` load resistors (the reference netlist's placeholder-0
`r`/`l_um`/`w_um` values versus the layout's real ones), plus one
`topology.flattened` **warning** row (the compare flattened the reference
netlist's 3 circuits into 1 before comparing, per
`docs/cli/lvs.md` "topology.flattened"). A failing check cannot be cited —
that is exactly what this manifest exists to make visible. The open chain
is issues
[#22](https://github.com/2AMLogic/gf180-comparator/issues/22) →
[#30](https://github.com/2AMLogic/gf180-comparator/issues/30) →
[#40](https://github.com/2AMLogic/gf180-comparator/issues/40)
(the upstream `klt` re-pin / `netgen` install holding the fix). LVS was
never cited here, so nothing here goes stale when that work lands —
re-cite and re-grade then, per the refresh contract below.

### unmet — items 5, 6 (PVT corners vs a ratified spec; Monte Carlo): substance exists, nothing gradeable

The four experiment directories under `sim/` carry committed
schematic-provenance corner records (`sim/comparator-{offset-mc,preamp-noise,
regeneration,kickback}/`, driven by `sim/characterize.sh` +
`sim/run_corners.py`), and item 6's own MC campaign exists (offset MC,
200 draws/corner per the tracker's survey). But (a) the target-spec table
in `README.md` is still **DRAFT** — DR-0002's ratification is proposed, not
completed (the two-key ceremony is unfinished per the tracker's 2026-09-21
note), and verdicts against an unrated spec are provisional by construction;
(b) those records are this repo's harness format, not `klt sim`/`klt yield`
JSON envelopes, so the grader could not read them even if they were scored.
Scoring the MC record against the spec table is exactly issue
[#24](https://github.com/2AMLogic/gf180-comparator/issues/24)'s in-flight
work; when it lands a `klt`-shaped envelope and the table is ratified, cite
and re-grade.

### unmet — item 7 (Post-layout verification): not started

Post-layout re-simulation against the extracted netlist is issue
[#23](https://github.com/2AMLogic/gf180-comparator/issues/23) (blocked on
item 4's chain). Item 7 rejects every evidence kind except a `klt pex`
report for an analog block — a clean DRC, LVS, or pre-layout sim renders
`wrong_kind` — so there is nothing to cite until that work exists.

### unmet — item 8 (Characterization report): in flight

Issue
[#25](https://github.com/2AMLogic/gf180-comparator/issues/25) owns the
one-command narrative characterization report; no aggregated record is
committed yet. Item 8 is the one item a hand-rolled **generic evidence
envelope** (`"kind": "generic"`) may satisfy — wrap the report in one when
it lands, pin its content hash, cite, re-grade.

### unmet — item 9 (Testbenches shipped): present but deliberately uncited

The four committed testbench directories plus the one-command drivers
(`sim/characterize.sh`, `sim/selftest.sh`, whose 2026-09-15 re-run passed
all 9 checks) are the substance of the claim; no `klt` envelope can back a
"testbenches shipped" claim, and citing an unrelated passing envelope would
render a green row the tool never actually checked — the same reasoning as
item 1.

### unmet — item 10 (Repo hygiene): partially true, honestly unchecked

`README.md`, `CLAUDE.md`, `spec/`, a LICENSE, and (with this directory)
the first CI workflow exist; the item also demands CI that keeps the
harness and evidence formats valid, and before this PR there was no CI at
all. `klt signoff --manifest` has no way to grade "CI exists"; the
machine-readable part of this item's hygiene duty is exactly the anti-rot
gate below. The full sweep is issue
[#26](https://github.com/2AMLogic/gf180-comparator/issues/26).

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
items 2/3 cite) — item 4's own LVS leg of the compound entry is *not*
citable yet and is deliberately absent: `comparator.lvs.json`'s
`net_correspondence` still leaves `vdd`/`vss` uncorrelated while item 4's
two `ppolyf_u_1k` property errors hold it open (see the item-4 section
above), so item 11 stays unmet even at the next pin refresh. The reason
the row renders `unrecognized_envelope` and not a graded verdict is the
distribution pin, not the evidence: the pinned 0.5.0 release predates
item 11's grading rules (klayout-tools#1984 and later), so the grader
cannot read the cited ERC envelope at all — a state
[docs/cli/signoff.md](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/signoff.md)
anticipates. When a released `klt` that grades item 11 ships, upgrade the
distribution pin together with this citation (the refresh contract) and
re-grade — the row will then render its real state on this same evidence
(`unmet` until both the `ties[]` blocker klayout-tools#2169 clears and
item 4's LVS carries the supply nets in `net_correspondence`; the
`erc.missing_tie` leg is not computed in the cited run, with the drawn
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
   `provenance.input.content_hash` == the sha256 of the committed artifact's
   current bytes. A manifest citing an artifact that has since changed
   fails rather than rotting — the acceptance criterion this whole directory
   exists for.
3. **The vendored rulebook is what graded.** The fresh
   grade's `source_doc` must be `signoff/design-evidence-tiers.md`; a grade
   that ran against the wheel's bundled 10-item copy instead fails by name.

**Refresh contract.** Any change to a cited evidence envelope or to the
cited artifacts means: re-run the producing flow (e.g.
`layout/run_drc.py`/`layout/run_lvs.py` per `layout/README.md`), re-pin the
hash in `block-manifest.json`, run `./signoff/regenerate.sh`, commit the
fresh report — in one change. A *new* citation means adding the
corresponding pin row to `verify-report.py`'s `PINNED_ARTIFACTS` in the
same change; an unlisted citation fails the verifier by name rather than
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
