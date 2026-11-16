# Work Plan

This roadmap is generated from the repository's current GitHub label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey
- **#112**: layout/PEX/signoff re-run for the DR-0004 input-cascode netlist (follow-up to #102)
- **#125**: Define and measure the missing average-power operating condition for T1

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#416**: Provenance guard: one title edit on any WORK_PLAN-referenced item reddens signoff CI on every open PR, and only a Guide tick can clear it
- **#419**: Provenance guard checks row titles but not section membership: an uncurated issue renders under 'Proposed' and CI stays green
- **#421**: sim/tools: accept a staged-and-committed sha256-matched source as pinned provenance (#398 ruling, option a)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#423**: fix: provenance guard checks the region's own shape, not just row titles
- **#426**: chore(loom): resync installed Loom to v0.19.1302
- **#427**: fix: classify gitignored staged sources as pinned provenance (DR-0008)

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#424**: fix: name stale-pin and foreign causes in provenance row mismatch

## Proposed

Issues carrying `loom:curated`.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey *(curated)*
- **#125**: Define and measure the missing average-power operating condition for T1 *(curated)*
- **#323**: Propose a design change that closes the 7 post-layout decision-time misses (T1 item 7) *(curated)*
- **#416**: Provenance guard: one title edit on any WORK_PLAN-referenced item reddens signoff CI on every open PR, and only a Guide tick can clear it *(curated)*
- **#419**: Provenance guard checks row titles but not section membership: an uncurated issue renders under 'Proposed' and CI stays green *(curated)*
- **#421**: sim/tools: accept a staged-and-committed sha256-matched source as pinned provenance (#398 ruling, option a) *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 3 |
| Approved PRs awaiting merge | 1 |
| Curated | 6 |
| Architect / Hermit proposals | 0 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
