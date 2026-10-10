# Finite ground-C budget for the post-layout `td_od50_ns` gap (issue #243)

**Diagnostic only.** This does not score a spec row, change the spec, DR-0004,
the DUT or the cited report ([`layout/pex/comparator.pex.json`](../../../comparator.pex.json)),
and it does not promote T1 item 7 (stays `unmet / check_failed`). The 1.5 ns
bound is unchanged. Synthetic-netlist results cannot satisfy item 7.

Produced by [`layout/pex/parasitic_attribution.py`](../../../parasitic_attribution.py)
(`budget-*` subcommands), run from commit `b9fff0f`. Later edits to the script
only add probe job ids to the analysis output and reword the outcome string;
`stage.json` records the script hash at run time.

## Question and method

#229 showed ground C is ~83 % of the gap, but its endpoints remove C
entirely. Here the ground-C cards of `sn`, `doutb`, `qn` and `dout` are
scaled **jointly** by one retained fraction f. Series R, coupling C, device
geometry and all other nets are untouched. Each variant gets its own offset
probe and its ladder is centred on that probe's trip point (the cited
convention). Corners: `ss_125c_2.97v`, `tt_125c_2.97v`.

**Starting set verified** against
[`../../parasitic-attribution/20261010-120720-230574b/attribution.json`](../../parasitic-attribution/20261010-120720-230574b/attribution.json):
the four highest single-net ground-C shares are `sn` 21.8 %, `doutb` 19.2 %,
`qn` 15.2 %, `dout` 14.7 %; their sum is 70.99 % (README: "about 71 %"). The
sum of single-net shares is a #229 diagnostic, not a prediction here.

f = 1.0 is the unchanged `ctrl` (the scaling function returns the netlist
byte-identically for 1.0; unit-tested). f = 0 is the #229 `cg0` endpoint
applied to the four nets (cards dropped).

## Validity: controls reproduce the cited results

In both stages `ctrl` and `sch` reproduce the cited `td_od50_ns` and the
cited trip points exactly (|diff| = 0): extracted tt 1.58774, ss 2.02956 ns;
schematic tt 0.986719, ss 1.23747 ns. `study_valid = true` in both
`budget.json` files. Each stage reruns the controls independently.

## Result

Cells are `td_od50 ns / margin to 1.5 ns / offset shift vs ctrl (mV)`.

Stage 1 ([`stage1-two-corner`](stage1-two-corner/budget-table.md)):

| variant | retained C fF (sn, doutb, qn, dout) | tt_125c_2.97v | ss_125c_2.97v |
|---|---|---|---|
| `ctrl` (f=1) | 20.83, 27.31, 30.95, 22.66 | 1.5877 / -0.0877 / +0.00 fail | 2.0296 / -0.5296 / +0.00 fail |
| `cgs-0750` (f=0.75) | 15.62, 20.48, 23.21, 16.99 | 1.4853 / +0.0147 / -2.85 PASS | 1.8987 / -0.3987 / -1.71 fail |
| `cgs-0500` (f=0.5) | 10.42, 13.65, 15.47, 11.33 | 1.3824 / +0.1176 / -5.85 PASS | 1.7668 / -0.2668 / -3.54 fail |
| `cgs-0250` (f=0.25) | 5.21, 6.83, 7.74, 5.66 | 1.2789 / +0.2211 / -9.09 PASS | 1.6338 / -0.1338 / -5.52 fail |
| `cgs-0000` (f=0) | 0.00, 0.00, 0.00, 0.00 | 1.1744 / +0.3256 / -12.48 PASS | 1.4992 / +0.0008 / -7.65 PASS |

Stage 2 ([`stage2-bracket`](stage2-bracket/budget-table.md)), refining the
only open bracket (ss: f = 0.25 fails, f = 0 passes):

| variant | retained C fF (sn, doutb, qn, dout) | tt_125c_2.97v | ss_125c_2.97v |
|---|---|---|---|
| `cgs-0125` (f=0.125) | 2.60, 3.41, 3.87, 2.83 | 1.2268 / +0.2732 / -10.77 PASS | 1.5667 / -0.0667 / -6.57 fail |
| `cgs-0062` (f=0.0625) | 1.30, 1.71, 1.93, 1.42 | 1.2007 / +0.2993 / -11.61 PASS | 1.5331 / -0.0331 / -7.11 fail |
| `cgs-0031` (f=0.03125) | 0.65, 0.85, 0.97, 0.71 | 1.1876 / +0.3124 / -12.06 PASS | 1.5162 / -0.0162 / -7.38 fail |
| `cgs-0016` (f=0.015625) | 0.33, 0.43, 0.48, 0.35 | 1.1810 / +0.3190 / -12.27 PASS | 1.5078 / -0.0078 / -7.53 fail |

(Variant ids round f to thousandths: `cgs-0062` is f = 0.0625, `cgs-0031` is
0.03125, `cgs-0016` is 0.015625; the exact f is in `stage.json`.)

* **tt_125c_2.97v** crosses: f = 0.75 is the largest tested fraction that
  meets 1.5 ns (margin +14.7 ps); f = 1.0 fails. The tt crossing lies
  somewhere in (0.75, 1.0); it was not refined because tt is not the binding
  corner.
* **ss_125c_2.97v** does **not** cross at any finite tested fraction. Its
  td_od50 is 1.5078 ns at f = 0.015625 (7.8 ps over) and meets the bound only
  at f = 0 (1.4992 ns, +0.8 ps margin), where all four nets have zero ground C.
* Therefore **no finite tested budget clears both corners**. The recorded
  outcome: no finite passing budget for this four-net lever; only the
  unrealizable zero-C endpoint passes ss, by 0.8 ps. Nothing is extrapolated
  or interpolated from these points. No monotonicity was assumed (td happened
  to be monotone in f at both corners).
* Offset: the probed trip point moves from -8.91 / -5.19 mV (tt / ss) at f = 1
  to -12.5 / -7.7 mV at f = 0; each variant is centred on its own value.
* No decision is unresolved: all three overdrive rungs resolved at every point.
* Because no candidate budget exists, the seven-failing-corner check required
  of a candidate was **not run** (nothing to check). The harness supports it
  (`budget-run --points seven`, which also reruns the controls at all seven
  cited failing corners); it is not measured here.

What this says for #112: reducing only these four nets' ground C cannot,
even driven to a physically unreachable ~0 fF, clear the ss corner by a
meaningful margin (0.8 ps). Another lever must be combined with it (the
remaining ground C, series R, coupling C, and the S/D junction geometry,
which #229 found to be ~14 % of the gap); that combination is **not measured
here**. This is a statement about this netlist transform, not about what a
layout can realize.

## Limitations

* Two corners only; ss fails at every finite fraction, so the seven-corner
  check was never triggered.
* Synthetic scaling of extracted ground-C cards; not a re-extraction and not
  physical routing. Real routing changes would also move coupling C and R.
* One jointly scaled net set; other subsets and combined levers were not
  explored (out of scope for the issue).
* Not full-PVT closure; no spec row is scored.

## Fleet provenance

All 34 `klt sim` requests (17 per stage: 5 probes + 12 ladders) ran on the
batch fleet with the released klt 0.6.0 client; every report carries
`environment.remote.job_id`, collected per point in each `budget.json`
(`job_ids` for the ladder, `probe_job_ids` for the probe). `run-log.json`
has client identity and timings; `failed_jobs` is empty in both stages.
Stage 1 was started once, stopped after a few requests and resumed
(completed reports are reused only when the deck sha256 matches), so its
run-log covers the resumed run. Nothing ran as a local grid.

## Files

* `stage.json` - variant manifest: nets, points, per-variant deck/probe
  hashes, per-net retained fF, source hashes (extracted DUT, schematic DUT,
  cited report, #229 attribution.json, tb consumed fields, pex_measure.py,
  the script).
* `<variant>/` - requests and remote reports (decks `*.spice` are git-ignored
  scratch, regenerated and hash-checked by `budget-verify`).
* `budget.json`, `budget-table.md` - numerical results, generated.

## Reproduce

```
python3 layout/pex/parasitic_attribution.py budget-plan --points two
python3 layout/pex/parasitic_attribution.py budget-run     <dir>/stage1-two-corner --points two --jobs 2
python3 layout/pex/parasitic_attribution.py budget-run     <dir>/stage2-bracket --points two --jobs 2 \
    --fractions 0.125,0.0625,0.03125,0.015625
python3 layout/pex/parasitic_attribution.py budget-analyze <stage dir>
python3 layout/pex/parasitic_attribution.py budget-verify  <stage dir>   # PDK-free
python3 layout/tests/test_parasitic_attribution.py
```

`klt` is `uvx --isolated --from klayout-tools==0.6.0 klt` (override with
`PEX_SIM_KLT`); `--backend batch` (the default) submits to the Spot fleet. A
stage directory is append-only: `budget-run` refuses to re-plan an existing one.
