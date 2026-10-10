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

- **#209**: Extend paired extracted preamp noise measurement to full PVT coverage
- **#210**: Correct current characterization report ratification and average-power verdicts
- **#212**: Close unclosed file handles in layout scripts and make ResourceWarning fail the PDK-free suite

## In Progress

Issues currently being built (`loom:building`).

- **#177**: Test run_lvs interface-pin and device-geometry contract checks

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#166**: sim(regeneration): reverse-polarity (HIGH->LOW) decision-time ladder across PVT (#158)

## Proposed

Issues carrying `loom:curated`.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey *(curated)*
- **#125**: Define and measure the missing average-power operating condition for T1 *(curated)*
- **#158**: Characterize reverse-polarity comparator delay across PVT *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

_None._

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Operator priority | 1 |
| Ready (`loom:issue`) | 3 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 3 |
| Architect / Hermit proposals | 0 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
