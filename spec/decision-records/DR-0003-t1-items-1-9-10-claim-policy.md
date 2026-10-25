# DR-0003: T1 items 1, 9, 10 — claim policy (leave uncited unless topically honest)

- **Status**: proposed
- **Date**: 2026-10-08
- **Decided by**: Builder agent, issue #89
- **Supersedes**: none — first record on the citation policy for ungradeable T1 items
- **Superseded by**: (none while this record stands)
- **Related**: #89, #57, #21, #26, `signoff/design-evidence-tiers.md`,
  [klayout-tools#2844](https://github.com/2AMLogic/klayout-tools/issues/2844)

## Context

T1 items 1 (Design sources), 9 (Testbenches shipped) and 10 (Repo hygiene)
have no `klt` verb; `klt signoff --manifest` grades them on citation presence
only and cannot check relevance. #89 asked which already-committed passing
envelopes, if any, truthfully back them. This is a claim-policy choice, not a
spec change.

## Decision

Cite an envelope for one of these items only if it shows the item's own
claim. Audit of the committed envelopes:

- **Item 1** (schematic sources + derived netlist, regenerated on change):
  no committed envelope shows it. The LVS report's `environment.reference_sha256`
  pins `design/comparator.spice`, but LVS compares layout against that netlist;
  it says nothing about `design/comparator.sch` generating it. The
  `design/netlist.sh --check` staleness check is a script, not an envelope,
  and CI does not run it. **Left uncited.**
- **Item 9** (testbenches + cold-start invocation + pinned PDK): no `klt sim`
  envelope exists. The `sim/*/records/*.json` files are this repo's harness
  format, not `klt sim` envelopes, and `sim/selftest.sh` output is not
  committed as an envelope. Citing the item-8 wrapper or the yield report
  would be citing a different claim. **Left uncited.** `klt sim` corner-sweep
  envelopes for the testbenches are open work under item 5 (#91); such an
  envelope backs item 9 only if it records the cold-start invocation and the
  pinned PDK.
- **Item 10** (README, license, CI keeping harness/evidence formats valid):
  the only CI is `signoff.yml`; it does not run the harness tests
  (`sim/harness/tests`) or `design/netlist.sh --check`, and no CI-produced
  run evidence is committed. **Left uncited.**

## Alternatives considered

- **Cite the LVS envelope for item 1** — it pins the derived netlist but not
  its derivation from the schematic; it would flip the grade on a claim it
  does not show.
- **Wrap the hand-checked claims in generic envelopes** — generic envelopes
  are only accepted for item 8, and a self-asserted pass for items 1/9/10
  would launder #21/#26's hand-checks as tool evidence.

## Consequences

Items 1, 9, 10 stay `unmet`/`no_evidence`; the T1 count does not change. The
README states, per item, what exists and what would make it citable. The gap
is filed upstream as klayout-tools#2844. Follow-ups that would change this
policy: CI running `netlist.sh --check` and the harness tests with a
committed result envelope; `klt sim` corner-sweep envelopes from #91, for
item 9 only if they record the cold-start invocation and the pinned PDK.

## Spec lines affected

none — claim-policy decision for `signoff/`; no `README.md` target-spec row
is set, changed or scoped.

## Addendum (issue #322, 2026-10-17): re-audit against `klt signoff --attest`

klayout-tools#2844 (tool-produced, artifact-anchored attestation envelopes
for items 1, 9, 10) is closed, but no PyPI release carries it: the latest
release is `klayout-tools` 0.7.0 and `klt signoff --help` there lists no
`--attest` or inventory option (checked with
`uvx --from "klayout-tools==0.7.0" klt signoff --help`). The pin stays at
0.6.0 (a git/dev build would break the PyPI-registry-wheel pin discipline).

Per item, "leave uncited" **still holds**: no tool-produced envelope exists.
Hand-written native envelopes remain rejected (see Alternatives).

- **Item 1**: still uncited. Inventory committed: `signoff/inventory/item-1.json`.
- **Item 9**: still uncited. Inventory committed: `signoff/inventory/item-9.json`.
- **Item 10**: still uncited. Inventory committed: `signoff/inventory/item-10.json`.

The inventory schema is written against the #2844 description and is
**unverified against a released klt**. Next step, once a release ships
`--attest`: bump the pin in `signoff/regenerate.sh` and
`.github/workflows/signoff.yml` together, produce the envelopes from the
inventories, pin their hashes in `signoff/block-manifest.json`, regenerate
`signoff/signoff-report.json`, add `--check` steps to `signoff.yml`, and run
the negative control (edit one inventoried file; the row must go
stale/unmet). No missing `--attest` check was found beyond the unreleased
state, so no new upstream issue is filed.

## Addendum 2 (issue #322, 2026-10-25): attestation envelopes, pin 0.8.0

`klayout-tools` 0.8.0 (PyPI) ships `klt signoff --attest` / `--inventory`
(checked with `uvx --from "klayout-tools==0.8.0" klt signoff --help`). The
grader pin moved 0.6.0 -> 0.8.0 (`signoff/regenerate.sh`, `signoff.yml`,
`verify-report.py`); it still grades the 11-item vendored rulebook. The
inventories were rewritten to the tool's real schema.

- **Item 1**: "leave uncited" **no longer holds**. Cited:
  `signoff/envelopes/item-1.json` (13/13 checks). Limit: freshness is the
  PDK-free pin check, not an xschem regeneration (CI has no xschem).
- **Item 10**: "leave uncited" **no longer holds**. Cited:
  `signoff/envelopes/item-10.json` (16/16 checks: the PDK-free verifier steps,
  excluding the circular re-grade).
- **Item 9**: "leave uncited" **still holds**. The cold start needs ngspice
  >= 46 plus the pinned PDK, which the producing host lacked (ngspice 42, no
  PDK); a self-asserted or weakened cold start would not be honest. Open: attest
  on a toolchain host.

The envelopes are `klt`-produced, not hand-written, so the Alternatives above
(wrapping hand-checked claims) still stand rejected. No `--attest` gap was
found that needs filing upstream.

## Addendum 3 (issue #322, 2026-10-25): item 9 attestation attempt on the toolchain host

`selftest.yml` now has an attest-and-upload step (`klt signoff --attest 9`,
klt 0.8.0) so the envelope can be produced where ngspice >= 46 and the pinned
PDK exist. Two findings from the first runs (workflow_dispatch on the issue
branch, runs 40226985190 and 40227065422):

- The workflow had failed on `main` since at least 2026-10-12 because the
  ngspice 46 tarball moved to SourceForge's `old-releases/` path (HTTP 404).
  Fixed in this change; the toolchain now builds.
- With the toolchain present, `./sim/selftest.sh` fails at the nominal
  `comparator-kickback` bench ("no completed points"; every other nominal bench,
  the reverse-polarity controls and all four sabotage controls pass). The cold
  start therefore does not succeed, so `--attest 9` cannot honestly pass and
  produces no envelope.

Decision: item 9 **stays uncited** ("leave uncited" still holds). The cold start
is not weakened or self-asserted to make the row pass. The attest step is
non-gating (it runs after the selftest step, which must pass first), and
`signoff.yml` is unchanged for item 9. Follow-up: diagnose the CI kickback
failure, then download the `item-9-envelope` artifact, commit it as
`signoff/envelopes/item-9.json`, pin it in the manifest and add item 9 to the
`signoff.yml` loop. No `--attest` gap was found that needs filing upstream.

