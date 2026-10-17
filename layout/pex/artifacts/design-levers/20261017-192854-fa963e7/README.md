# Design-lever study for the post-layout `td_od50_ns` gap (issue #323)

**Diagnostic only.** This scores no spec row and changes no spec, layout, DUT
or cited report ([`comparator.pex.json`](../../../comparator.pex.json)). T1
item 7 stays `unmet / check_failed`; DR-0002's 1.5 ns bound is unchanged.
Feeds the proposed [DR-0007](../../../../../spec/decision-records/DR-0007-post-layout-decision-time-levers.md).

Produced by [`layout/pex/design_lever_study.py`](../../../design_lever_study.py)
(run from commit `fa963e7`; `stage.json` records the script hashes). Same
harness as #264: cited extracted netlist, own-probe centring,
`klt sim --backend batch` (client `klayout-tools==0.6.0`, see `run-log.json`;
job ids in `levers.json`).

## Method

Each lever rewrites `W` of named extracted MOSFET cards (AS/AD scaled with W,
PS/PD keep their constant part). Wiring parasitics are **not** changed, so an
upsizing result is optimistic on wiring load. Every variant gets its own
offset probe and a ladder centred on that trip point. Corners:
`tt_125c_2.97v`, `ss_125c_2.97v`.

Request budget declared before the run: 23 (7 probed variants x 3 + schematic
control x 2). Used: 23. No retry stage, no local ngspice.

## Validity

`ctrl` and `sch` reproduce the cited `td_od50_ns` exactly (|diff| = 0,
tolerance 1e-4 ns): extracted tt 1.58774 / ss 2.02956 ns, schematic tt
0.986719 / ss 1.23747 ns. `study_valid = true`. `verify` passes.

## Result

[`levers-table.md`](levers-table.md) is generated; cells read
`td_od50 ns / margin to 1.5 ns / trip-point shift vs ctrl (mV) / unresolved`.
All variants have 0 unresolved decisions at both corners.

| lever | change | tt td ns | ss td ns | ss delta vs ctrl |
|---|---|---|---|---|
| `ctrl` | none | 1.5877 | 2.0296 | 0 |
| `pair-x1.5` | M$9, M$13 W 8 -> 12 um | 1.5367 | 1.9389 | -90.7 ps |
| `tail-x1.5` | M$12 W 16 -> 24 um | 1.5558 | 1.9847 | -44.9 ps |
| `tail+regen` | tail x1.5 and 4 regen devices x1.5 | 1.6004 | 2.0729 | +43.3 ps |
| `tail+regenload` | tail x1.5, sp/sn drivers x0.7 | 1.6541 | 2.1004 | +70.8 ps |
| `regen-x1.5` | M$8, M$11, M$20, M$25 W 6 -> 9 um | 1.6384 | 2.1247 | +95.1 ps |
| `regenload-x0.7` | M$1, M$5, M$18, M$24 W x0.7 | 1.6864 | 2.1455 | +116.0 ps |

* **No lever meets 1.5 ns at ss, and none meets it at both corners.** Best:
  `pair-x1.5`, 1.5367 ns (tt) and 1.9389 ns (ss); it misses ss by 439 ps and
  tt by 37 ps. This is a **negative result**; nothing is extrapolated to
  closure.
* Only the latch input pair and the tail reduce td. Strengthening regeneration
  and reducing the sp/sn load both made td **worse** at both corners.
* **Item-5 rows (offset, kickback, noise, power) were not run.** The curated
  plan runs them only for candidates that pass both corners; there are none.
  The only item-5-adjacent datum recorded is the trip-point shift, at most
  1.41 mV (tt) / 0.78 mV (ss) in magnitude.

## Limitations

* One factor per lever, two corners; no sweep and no interpolation.
* Device W only; a re-laid-out wider device adds wiring C/R this study omits.
* `pair-x1.5` loads the preamp outputs (aop/aon) more; that interaction with
  the input cascode (DR-0004, #112) is not measured here.
