# Work Plan

This roadmap is generated from the repository's current GitHub label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#145**: fix: correct drifted decision-record enumeration and item-9 klt pin in attested evidence

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073)

## Important

`loom:important`; taken before unlabelled work.

- **#110**: Re-take the full DRC/LVS regression record under the CI-pinned klt 0.9.0

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#137**: a7s_common: gate_contact's v1= parameter now shadows the module-level v1() helper
- **#139**: Docs: ROADMAP.md is on main but nothing links it
- **#154**: normalize_paths CLI: the relative-prefix test is vacuous, and a trailing flag crashes instead of printing usage
- **#156**: `--verify` cannot re-check any committed record: 541 of 581 envelopes drift on nondeterministic and uncommitted derived inputs

## In Progress

Issues currently being built (`loom:building`).

- **#120**: Docs: stale decision-record enumeration in spec/stdcells.md, and the declared 0.8.0 pin in t1-item9-inventory.json
- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073)
- **#129**: Collapse the package.json test/check alias chain onto one gate that runs all six self-test files
- **#142**: Item 9 inventory does not content-hash klt_helper.py (nor check_lef.py / write_lef.py)
- **#144**: Four harness/evidence scripts outside item 9 are unpinned, incl. item 2's own check command

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#143**: build: run all six self-tests as one package.json gate
- **#161**: fix(lef): emit a pin's own net M2 as port geometry, not obstruction

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#145**: fix: correct drifted decision-record enumeration and item-9 klt pin in attested evidence
- **#153**: evidence: pin six unpinned harness/design scripts into T1 item 1 and 10
- **#159**: manifests: content-hash harness helpers in T1 item 9 attestation

## Proposed

Issues carrying `loom:curated`.

- **#120**: Docs: stale decision-record enumeration in spec/stdcells.md, and the declared 0.8.0 pin in t1-item9-inventory.json *(curated)*
- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073) *(curated)*
- **#137**: a7s_common: gate_contact's v1= parameter now shadows the module-level v1() helper *(curated)*
- **#139**: Docs: ROADMAP.md is on main but nothing links it *(curated)*
- **#142**: Item 9 inventory does not content-hash klt_helper.py (nor check_lef.py / write_lef.py) *(curated)*
- **#144**: Four harness/evidence scripts outside item 9 are unpinned, incl. item 2's own check command *(curated)*
- **#149**: integration/run_par.sh records an early-stage OpenROAD refusal as invalid-input (exit 1), not as a recorded refusal (exit 3) *(curated)*
- **#151**: klt_helper.py is not importable: module-level sys.argv indexing blocks unit-testing its pure parts *(curated)*
- **#154**: normalize_paths CLI: the relative-prefix test is vacuous, and a trailing flag crashes instead of printing usage *(curated)*
- **#156**: `--verify` cannot re-check any committed record: 541 of 581 envelopes drift on nondeterministic and uncommitted derived inputs *(curated)*

## Proposed (Architect / Hermit)

- **#133**: Drop the vendored design-evidence-tiers.md: a second, already-stale pin to klayout-tools that the pinned wheel already ships *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`) | 4 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 3 |
| Curated | 10 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
