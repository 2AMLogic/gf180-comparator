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

- **#405**: docs: sim/README.md:30 still calls klt 0.5.0 'the fleet runner' (cm-window refusal floor)
- **#414**: corners: parse_corner_id's "accepts exactly what corner_id emits" docstring is still an overstatement at :g's exponent boundary
- **#415**: Replace importlib path-loading in 16 test files with #368's sys.path + plain import idiom

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#417**: docs: narrow parse_corner_id's strictness claim to the ratified temp range
- **#420**: docs: identify klt 0.5.0 as the pinned pre-launch floor, not the fleet runner

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey *(curated)*
- **#125**: Define and measure the missing average-power operating condition for T1 *(curated)*
- **#323**: Propose a design change that closes the 7 post-layout decision-time misses (T1 item 7) *(curated)*
- **#405**: docs: sim/README.md:30 still calls klt 0.5.0 'the fleet runner' (cm-window refusal floor) *(curated)*
- **#414**: corners: parse_corner_id's "accepts exactly what corner_id emits" docstring is still an overstatement at :g's exponent boundary *(curated)*
- **#415**: Replace importlib path-loading in 16 test files with #368's sys.path + plain import idiom *(curated)*

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
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 0 |
| Curated | 6 |
| Architect / Hermit proposals | 0 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
