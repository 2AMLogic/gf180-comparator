# Work Plan

This roadmap is generated from the repository's current GitHub label state.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

- **#166**: sim(regeneration): reverse-polarity (HIGH->LOW) decision-time ladder across PVT (#158)

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#240**: Quantify solver-tolerance sensitivity of the common-mode offset window
- **#247**: Regenerate the extracted-offset 45x200 campaign from a clean committed source (follow-up to PR #244)
- **#266**: Protect committed parasitic study run archives from evidence rewrites
- **#269**: Enforce the ngspice version floor when ingesting fleet reference records
- **#273**: Publish structured latch decision correctness in fleet records

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#166**: sim(regeneration): reverse-polarity (HIGH->LOW) decision-time ladder across PVT (#158)
- **#271**: fix: match complete numeric tokens in claim drift guard (#268)

## Proposed

Issues carrying `loom:curated`.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey *(curated)*
- **#125**: Define and measure the missing average-power operating condition for T1 *(curated)*
- **#158**: Characterize reverse-polarity comparator delay across PVT *(curated)*
- **#209**: Extend paired extracted preamp noise measurement to full PVT coverage *(curated)*
- **#247**: Regenerate the extracted-offset 45x200 campaign from a clean committed source (follow-up to PR #244) *(curated)*

## Proposed (Architect / Hermit)

- **#275**: Validate the characterization evidence chain before issuing item-8 pass *(architect)*

## Epics

_None._

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Operator priority | 1 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 2 |
| Curated | 5 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
