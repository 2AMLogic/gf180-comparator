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

- **#323**: Propose a design change that closes the 7 post-layout decision-time misses (T1 item 7)
- **#325**: Deduplicate shared helpers (parse_klt_version, git_state, sha256) across sim/layout tools

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#326**: feat: add device-lever study and proposed DR-0007 for td_od50 misses

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#327**: refactor: reuse shared sha256/klt-version/git_state helpers in preamp-noise and tran-feasibility tools

## Proposed

Issues carrying `loom:curated`.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey *(curated)*
- **#125**: Define and measure the missing average-power operating condition for T1 *(curated)*
- **#209**: Extend paired extracted preamp noise measurement to full PVT coverage *(curated)*

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
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 1 |
| Curated | 3 |
| Architect / Hermit proposals | 0 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
