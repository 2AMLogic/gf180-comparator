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

- **#362**: Record Reproduce line omits the run's corner-selection flags, so a subset record tells the reader to run the full grid
- **#366**: run_stage's append-only check hardcodes one code-hash exemption, so resuming a lever stage after a source edit aborts
- **#368**: Remove 7 hand-rolled importlib path-import blocks: the repo's own sys.path idiom already does this
- **#371**: Deduplicate the stage source_sha256 core hand-typed in all three parasitic-study manifest builders
- **#373**: sim: run and commit the 45-corner comparator-avg-power campaign on the schematic DUT
- **#374**: sim: extracted-DUT comparator-avg-power coverage — fleet probe leg, first tb_vosprobe run, and the 45-corner extracted record
- **#384**: sim: cross_run_agreement cites its local record by basename, with no content hash

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#380**: refactor: replace importlib path-import blocks with the repo's sys.path import idiom
- **#386**: harness: echo restricting flags in the record Reproduce line
- **#389**: feat(sim): extracted-binding two-phase dut_vos referral + the 45-point extracted fleet record
- **#390**: sim: commit 45-corner avg-power PVT fleet campaign record

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#381**: refactor: deduplicate the stage source_sha256 core behind one helper
- **#388**: fix(pex): derive run_stage resume exemption from generated_by, not a hardcoded key

## Proposed

Issues carrying `loom:curated`.

- **#3**: Gap-to-T1 tracker: gf180-comparator artifact-presence survey *(curated)*
- **#125**: Define and measure the missing average-power operating condition for T1 *(curated)*
- **#323**: Propose a design change that closes the 7 post-layout decision-time misses (T1 item 7) *(curated)*
- **#362**: Record Reproduce line omits the run's corner-selection flags, so a subset record tells the reader to run the full grid *(curated)*
- **#366**: run_stage's append-only check hardcodes one code-hash exemption, so resuming a lever stage after a source edit aborts *(curated)*
- **#367**: signoff item 9: add four omitted harness files to the inventory and refresh the envelope from a green selftest run *(curated)*
- **#373**: sim: run and commit the 45-corner comparator-avg-power campaign on the schematic DUT *(curated)*
- **#374**: sim: extracted-DUT comparator-avg-power coverage — fleet probe leg, first tb_vosprobe run, and the 45-corner extracted record *(curated)*
- **#379**: ROADMAP.md's per-issue queue-label claims go stale within hours and nothing re-verifies them *(curated)*
- **#384**: sim: cross_run_agreement cites its local record by basename, with no content hash *(curated)*
- **#385**: docs: comparator-avg-power README attributes the fleet `let` gap to klt 0.5.0, but the runner is 0.9.0 *(curated)*

## Proposed (Architect / Hermit)

- **#375**: Consolidate the five hand-copied corner-id formatters and three divergent parsers onto sim/harness/corners.py *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 7 |
| PRs awaiting review | 4 |
| Approved PRs awaiting merge | 2 |
| Curated | 11 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
