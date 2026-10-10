# Combined finite ground-C x series-R budget for the post-layout `td_od50_ns` gap (issue #264)

**Diagnostic only.** This does not score a spec row or change the spec,
DR-0004, the DUT or the cited report
([`layout/pex/comparator.pex.json`](../../../comparator.pex.json)). It does not
promote T1 item 7, which stays `unmet / check_failed`. The ratified 1.5 ns bound
is unchanged. Results from scaling netlist cards cannot satisfy item 7.

Produced by [`layout/pex/parasitic_attribution.py`](../../../parasitic_attribution.py)
(`combo-*` subcommands), run from commit `c49a3f1`. `stage.json` records the
script hash at run time.

## Question and method

The #243 study ([`../../ground-c-budget/20261010-154019-b9fff0f/README.md`](../../ground-c-budget/20261010-154019-b9fff0f/README.md))
scaled the ground C of four nets only. It found no finite budget that clears
`ss_125c_2.97v`, and it said another lever must be combined with that one. This
study scales two levers together and **measures** each combination. It does not
add up single-lever shares:

* **every** extracted ground-C card (`C<net> <net> vsubs`, all 20 nets,
  including rails, `ibias` and inputs) is multiplied by f_c, and
* **every** series-R leg card (`R<net>_t<k> <net>__t<k> <net>`, all 114 legs)
  is multiplied by f_r.

Both factors are finite and lie in (0, 1]. Zero, values above 1, NaN, inf,
bools and non-numbers are refused. The scaling leaves the following cards
byte-identical: the 60 coupling-C cards, all device cards (junction
geometry), and the `Rvsubs_dctie` substrate tie. Unit tests check that only
the 20 + 114 intended cards change, that the C and R edits commute, and that
(1.0, 1.0) returns the source netlist object unchanged.

Every variant gets its own offset probe, and its ladder is centred on that
probe's trip point (the cited convention). Corners: `tt_125c_2.97v` and
`ss_125c_2.97v`. One shared (125 C, 2.97 V) probe serves both.

Grid (fixed by the issue's curator): f_c in {0.75, 0.5, 0.25} x f_r in {1.0, 0.5}.
Variant ids are `cgr-<f_c x 1000>-<f_r x 1000>`.

## Validity: controls reproduce the cited results

`ctrl` and `sch` reproduce the cited `td_od50_ns` and trip points exactly
(|diff| = 0):

* extracted: tt 1.58774 ns, ss 2.02956 ns
* schematic: tt 0.986719 ns, ss 1.23747 ns
* trip points: -8.9074 mV (tt), -5.1865 mV (ss)

`study_valid = true` in [`stage1-grid/combo.json`](stage1-grid/combo.json).

## Result (stage 1, the only stage run)

Cells read `td_od50 ns / margin to 1.5 ns / trip-point shift vs ctrl (mV)`.
Every variant has 0 unresolved decisions at both corners: all three overdrive
rungs resolved. The generated tables are in
[`stage1-grid/combo-table.md`](stage1-grid/combo-table.md). They also give
the retained ground C (fF) and leg-R sum (ohm) **per net** for every variant,
read back from the variant netlists.

| variant | f_c | f_r | total ground C fF | total leg R ohm | tt_125c_2.97v | ss_125c_2.97v |
|---|---|---|---|---|---|---|
| `ctrl` | 1 | 1 | 493.51 | 3380.1 | 1.5877 / -0.0877 / +0.00 fail | 2.0296 / -0.5296 / +0.00 fail |
| `cgr-0750-1000` | 0.75 | 1 | 370.13 | 3380.1 | 1.4601 / +0.0399 / +1.50 PASS | 1.8539 / -0.3539 / +0.84 fail |
| `cgr-0500-1000` | 0.5 | 1 | 246.76 | 3380.1 | 1.3348 / +0.1652 / +3.30 PASS | 1.6846 / -0.1846 / +1.86 fail |
| `cgr-0250-1000` | 0.25 | 1 | 123.38 | 3380.1 | 1.2118 / +0.2882 / +5.52 PASS | 1.5220 / -0.0220 / +3.15 fail |
| `cgr-0750-0500` | 0.75 | 0.5 | 370.13 | 1690.1 | 1.4439 / +0.0561 / +1.77 PASS | 1.8347 / -0.3347 / +1.05 fail |
| `cgr-0500-0500` | 0.5 | 0.5 | 246.76 | 1690.1 | 1.3199 / +0.1801 / +3.57 PASS | 1.6671 / -0.1671 / +2.07 fail |
| `cgr-0250-0500` | 0.25 | 0.5 | 123.38 | 1690.1 | 1.1981 / +0.3019 / +5.82 PASS | 1.5062 / -0.0062 / +3.36 fail |

* **No tested cell meets 1.5 ns at both corners.** `ss_125c_2.97v` fails at
  every cell. The smallest miss is `cgr-0250-0500` (75 % of all ground C and
  50 % of all series R removed) at 1.5062 ns, 6.2 ps over the bound.
* **No crossing bracket exists at ss or at both points together.** The only
  measured bracket is at tt, along f_c at f_r = 1.0: `ctrl` fails and
  `cgr-0750-1000` passes. Every cell in that bracket's interval fails ss, so
  refining it cannot produce a candidate. As the issue requires, the study
  **stops after stage 1** (23 requests). The stage-2 refinement (<= 12
  requests) and the stage-3 seven-corner check (<= 29) were **not run**,
  because there was no candidate and no usable bracket. Nothing is
  extrapolated beyond the tested grid or interpolated between tested cells.
* **Interaction (measured, not summed):** halving all series R saves less as
  ground C shrinks:
  * ss: -19.2 / -17.5 / -15.8 ps at f_c = 0.75 / 0.5 / 0.25
  * tt: -16.2 / -14.9 / -13.7 ps at the same f_c

  td fell monotonically along both axes at both corners
  (`non_monotonic_per_point` is false); this was observed, not assumed.
* **Comparison with #243, by measured points only:** at f_c = 0.25 with R
  unscaled, scaling all nets gives ss 1.5220 ns. #243's four-net scaling at
  f = 0.25 gave 1.6338 ns. Even so, the all-net, half-R cell `cgr-0250-0500`
  still misses ss.
* **Offset:** the trip point moves **positive** under all-net scaling, from
  -8.91 / -5.19 mV (tt / ss) at `ctrl` to -3.09 / -1.83 mV at
  `cgr-0250-0500`. That is the opposite direction from #243's four-net
  scaling, which moved it negative. Each variant is centred on its own
  probed value.

What this says for #112: across this grid, combining ground C reduced to 25 %
on every net with series R halved on every net still does not clear ss at
125 C / 2.97 V. Device geometry and coupling C were left at their extracted
values. These are statements about this netlist transform at tested points,
not about what a layout can realize. #229 found the S/D junction geometry
lever to be about 14 % of the gap. It was deliberately not touched here: the
issue forbids synthetic junction-geometry changes as physical evidence.

## Limitations

* Two corners only. With no candidate, the seven-failing-corner check was
  never triggered. The harness supports it
  (`combo-run --kind seven --cells <f_c:f_r>`).
* All ground-C cards are scaled by one factor and all leg cards by another,
  so per-net weighting was not explored. A real reroute would move ground C,
  coupling C and R together and non-uniformly.
* Scaling netlist cards is not re-extraction or physical routing. Whether
  25 % of the extracted ground C, or half of the series R, is achievable is
  unknown. Physical realizability still needs routing and re-extraction.
* Not full-PVT closure. No spec row is scored.

## Fleet provenance and request budget

The declared budget is a hard cap of 64 requests: stage 1 <= 23,
refinement <= 12, seven-corner <= 29. `combo-run` enforces it from the
planned counts that each `stage.json` records. **Used: 23** (7 probes + 16
ladders), all on the AWS Spot batch fleet (`--backend batch`). The client
was the released klt 0.6.0 (`v0.6.0`, `c622e8a`), and `failed_jobs` is
empty. Each report's `environment.remote.job_id` is collected per point in
`combo.json` (`job_ids` for the ladder, `probe_job_ids` for the probe).
Nothing ran locally.

| variant | probe | ladder tt | ladder ss |
|---|---|---|---|
| `ctrl` | klt-sim-15b59ed12c68 | klt-sim-fe58a58e3d0e | klt-sim-5724084d1464 |
| `cgr-0750-1000` | klt-sim-7948d32a58c9 | klt-sim-928b336d7991 | klt-sim-2029a2f79675 |
| `cgr-0500-1000` | klt-sim-0bbf21dc13c6 | klt-sim-1502a6a0861c | klt-sim-b6ba0ff04104 |
| `cgr-0250-1000` | klt-sim-6ece492b4767 | klt-sim-32b43a09b9f0 | klt-sim-a403db1283a9 |
| `cgr-0750-0500` | klt-sim-88424566fed6 | klt-sim-bb754d9e8774 | klt-sim-d03e6825735b |
| `cgr-0500-0500` | klt-sim-65a8ad05bc53 | klt-sim-c884193fb068 | klt-sim-279d9b75047e |
| `cgr-0250-0500` | klt-sim-aa4482646869 | klt-sim-7b8e216656bb | klt-sim-6f66a29f6fec |
| `sch` | (none, centred at 0 V) | klt-sim-0e63ea0f4fd2 | klt-sim-4fa7f476f990 |

## Files

* `stage1-grid/stage.json`: the variant manifest. It records:
  * the stage kind, points, and planned request count;
  * per variant: f_c, f_r, DUT and probe-deck sha256, retained ground C per
    net (fF) and series-R leg sum per net (ohm), and the totals;
  * source hashes: extracted DUT, schematic DUT, cited report, #229
    `attribution.json`, #243 README, tb consumed fields, `pex_measure.py`,
    and the script.
* `stage1-grid/<variant>/`: requests and remote reports. The decks
  (`*.spice`) are git-ignored scratch; `combo-verify` regenerates them and
  checks their hashes.
* `stage1-grid/combo.json` and `combo-table.md`: generated results (controls,
  outcome, brackets, monotonicity, per-point fastest cell, per-variant
  values).
* `stage1-grid/run-log.json`: client identity and timings.

## Reproduce / verify

```
python3 layout/pex/parasitic_attribution.py combo-plan --kind grid
python3 layout/pex/parasitic_attribution.py combo-run     <dir>/stage1-grid --kind grid --jobs 2
python3 layout/pex/parasitic_attribution.py combo-analyze <dir>/stage1-grid
python3 layout/pex/parasitic_attribution.py combo-verify  <dir>/stage1-grid   # PDK-free
python3 layout/tests/test_parasitic_attribution.py
```

`klt` is `uvx --isolated --from klayout-tools==0.6.0 klt` (override with
`PEX_SIM_KLT`). Stage directories are append-only: `combo-run` refuses to
re-plan an existing one. It also refuses any stage over its kind's cap, and
any stage that would take the directory's total past 64 planned requests.
