# DR-0007: Design levers for the post-layout decision-time misses (T1 item 7)

- **Status**: proposed
- **Date**: 2026-10-17
- **Decided by**: builder agent, issue #323 (no ratification claim)
- **Supersedes**: none — first record for this decision
- **Superseded by**: (none while this record stands)
- **Related**: #323, #229, #243, #264, #112, #125; DR-0002, DR-0004;
  `layout/pex/artifacts/design-levers/20261017-192854-fa963e7/`

## Context

T1 item 7 is `unmet / check_failed`: 7 of 675 post-layout delta rows exceed
DR-0002's ratified `td_od50_ns <= 1.5 ns`, worst `ss_125c_2.97v` at 2.03 ns
(schematic 1.24 ns). Parasitic trimming cannot close it: #264 measured that
even 25 % of all ground C with 50 % of all series R leaves ss at 1.5062 ns.
`signoff/README.md` says the row turns `met` only through a design or layout
change, or a new decision record. This record evaluates design levers.

## Decision

**Proposed, not ratified. No lever is adopted and no spec row changes.**
Six device-W levers were measured on the cited extracted netlist at
`tt_125c_2.97v` and `ss_125c_2.97v` (records under
`layout/pex/artifacts/design-levers/20261017-192854-fa963e7/`):

| rank (ss) | lever | tt td ns | ss td ns | independent of DR-0004 cascode? |
|---|---|---|---|---|
| 1 | `pair-x1.5` (latch input pair W x1.5) | 1.5367 | 1.9389 | **no**: loads aop/aon, re-measure after #112 |
| 2 | `tail-x1.5` (latch tail W x1.5) | 1.5558 | 1.9847 | yes (acts after the preamp) |
| 3 | `tail+regen` | 1.6004 | 2.0729 | yes |
| 4 | `tail+regenload` | 1.6541 | 2.1004 | yes |
| 5 | `regen-x1.5` | 1.6384 | 2.1247 | yes |
| 6 | `regenload-x0.7` | 1.6864 | 2.1455 | yes |

Reference: extracted `ctrl` 1.5877 / 2.0296 ns (reproduces the cited rows
exactly), schematic 0.9867 / 1.2375 ns.

**Recommendation:** none of these levers closes item 7 (the result is
negative). Of the measured candidates, `pair-x1.5` is the most effective
(-90.7 ps at ss) and `tail-x1.5` the second (-44.9 ps); they are the only
ones that help. Neither is sufficient alone, and the pair + tail combination
was not run. The recommended next step is a follow-up issue combining the
input-pair lever with the parasitic reduction #264 found necessary,
re-measured after #112 lands. The layout-floorplan lever is bounded by #264's
measured cells and is not re-measured here. DR-0002's 1.5 ns bound stays.

## Alternatives considered

- **Strengthen regeneration** (`regen-x1.5`) — measured slower (+95 ps ss):
  the added gate and junction C on qn/qp outweighs the gain.
- **Reduce regeneration-node load** (`regenload-x0.7`) — measured slower
  (+116 ps ss): weakening the sp/sn drivers costs more than the load saved.
- **Relax or rescope the 1.5 ns bound** — not permitted: agents do not relax
  the ratified spec to make results pass.
- **A global sizing sweep** — unbounded and not tied to a lever.

## Consequences

- Item 7 stays `unmet`; `comparator.pex.json` is not re-cited.
- The result is bounded: one factor per lever, W only, wiring parasitics of
  the wider devices not added (optimistic for upsizing), two corners, and no
  item-5 rows (offset, kickback, noise, power) because no lever passed.
- `pair-x1.5` adds preamp-output load; `tail-x1.5` adds clocked power. Neither
  cost is measured (power: #125).
- The record stays `proposed` until #112 settles the input topology.

## Spec lines affected

- `README.md#target-specification-ratified-via-dr-0002` — `td_od50_ns` row —
  measured against, not set.
