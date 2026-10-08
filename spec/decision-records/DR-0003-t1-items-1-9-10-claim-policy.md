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
  would be citing a different claim. **Left uncited**; becomes citable when
  #75 lands `klt sim` envelopes for the ratified rows.
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
committed result envelope; `klt sim` envelopes from #75.

## Spec lines affected

none — claim-policy decision for `signoff/`; no `README.md` target-spec row
is set, changed or scoped.
