# DR-0009: Pre-cascode decision-time budget for latch sizing and extracted RC

- **Status**: proposed
- **Date**: 2026-11-21
- **Author**: Builder for #453
- **Supersedes**: none
- **Related**: DR-0002, DR-0004, DR-0007, #112, #229, #264, #323, #453

## Decision

**Withhold the layout budget.** The control run produced no timing measurements.
The input was the pre-cascode extracted comparator used in DR-0007. S3 input
upload failed before launch for the extracted probe and both schematic
ladders because the worker lacked the `batch-runner-submit` profile. The two
extracted ladders need measured trip points and could not start. Three client
requests were attempted, zero fleet jobs launched, and the candidate stages
were skipped. The [run log](../../layout/pex/artifacts/design-levers-combined/20261121-011230-45f12a5/controls/run-log.json)
records the upload errors and the [campaign summary](../../layout/pex/artifacts/design-levers-combined/20261121-011230-45f12a5/timing.json)
records the validity failure.

| Control at 125 °C, 2.97 V | Cited tt (ns) | Cited ss (ns) | Rerun |
|---|---:|---:|---|
| Extracted, centred at its own trip point | 1.58774 | 2.02956 | Missing both |
| Schematic, centred at 0 V | 0.986719 | 1.23747 | Missing both |

The qualification tolerance is ±0.0001 ns (`CONTROL_TOL_NS`). The cited
values come from the [post-layout report](../../layout/pex/comparator.pex.json).
Ranking the combinations, selecting a largest passing global residue, or
concluding that every candidate misses requires a qualified rerun. #453
tracks that run and its candidate-specific kickback, offset and noise evidence.

## Consequences for the next layout

| Lever | Interaction with the DR-0004 input cascode |
|---|---|
| Tail ×1.5 | Changes the clocked latch tail, downstream of the preamp. Its device-width lever is independent of the input cascode. |
| Pair ×1.5, pair+tail ×1.5, conditional pair ×2 | Each changes the load at aop/aon. Repeat any measurements on the post-#112 extraction. |

The grid applies global fractions to all ground capacitances and series
resistances. It supplies no per-net allocation. The width transform changes
junction area and perimeter. It omits routing load introduced by widening,
which makes any future passing result optimistic until layout re-extraction.
The proposed experiment and its conditional request counts are in the
[committed plan](../../layout/pex/artifacts/design-levers-combined/PLAN.md).

## Alternatives considered

Combining DR-0007's single-lever timing improvements arithmetically with
#264's parasitic-only result would assume that changing input load, latch
current and interconnect delay leaves their interactions negligible. Neither
study measured that interaction. The two-phase kickback bench accepts a
by-path extracted DUT and can measure the deterministic offset and the
both-input kickback of a passing candidate. The extracted preamp-noise
recorder checks its DUT hash against #202 and rejects a widened DUT with
`SOURCE_IDENTITY_MISMATCH`.

## Spec lines affected

The DR-0002 decision-time limit is 1.5 ns. T1 item 7 retains its
`unmet / check_failed` grade from the cited layout.
