# `sim/comparator-offset-mc/yield/`

`klt yield` evidence for the **Offset sigma** row of the ratified
target-spec table (`README.md`, DR-0002: <= 15 mV 3-sigma input-referred,
<= 8 mV stretch), built from the committed offset Monte Carlo record
[`20260910-124917-4805118`](../records/20260910-124917-4805118.md)
(issue [#82](https://github.com/2AMLogic/gf180-comparator/issues/82)). This
is what `signoff/block-manifest.json` cites under T1 item 6.

**Nothing was re-simulated.** The harness prints every draw's `voa` into the
per-corner ngspice log, so the raw samples were already committed. The
existing `sim/` records and logs are untouched (append-only); this directory
only adds files beside them.

| file | what it is |
|---|---|
| `adapt_samples.py` | reads the record + its 45 committed logs, writes the sample-set document. Refuses unless every point has `n_samples` draws and the re-computed mean/sigma reproduce the record's `mean_vos_uv` / `sig_vos_mv` to 1e-6 (they do, at all 45 points). |
| `samples-20260910-124917-4805118.json` | the `klt yield` sample-set document: 45 measurements (`vos_v@<corner>`, volts), 200 draws each, each with a deterministic negative control. **This file's sha256 is the item-6 manifest pin.** |
| `spec-limits-target.json` | per-draw limits `-15 mV <= Vos <= +15 mV` (the ratified target) |
| `spec-limits-stretch.json` | the same at `+/-8 mV` (the ratified stretch) |
| `yield-20260910-124917-4805118-target.json` | `klt yield` report against the target limits -- **the cited evidence** |
| `yield-20260910-124917-4805118-stretch.json` | the same against the stretch limits (supplementary, not cited) |

## Reproduce

```bash
python3 sim/comparator-offset-mc/yield/adapt_samples.py \
    sim/comparator-offset-mc/records/20260910-124917-4805118.json \
    sim/comparator-offset-mc/yield/samples-20260910-124917-4805118.json
klt yield sim/comparator-offset-mc/yield/samples-20260910-124917-4805118.json \
    --limits sim/comparator-offset-mc/yield/spec-limits-target.json --format json
```

(run from the repo root; the report records these repo-relative paths.)

## Result

All 45 PVT points (5 process corners x 3 T x 3 V), each its own population of
200 draws:

| | target (+/-15 mV) | stretch (+/-8 mV) |
|---|---|---|
| empirical yield | 200/200 at every point; Clopper-Pearson 95 % lower bound 98.17 % | same |
| worst `sigma_to_spec` | 15.92 (95 % CI 14.35-17.49) at `sf_125c_3.30v` | 8.45 (CI 7.61-9.29) at `sf_125c_3.30v` |
| worst `Cpk` | 5.31 | 2.82 |
| `sample_size.verdict` | `sufficient` at all 45 | `sufficient` at all 45 |
| `negative_control.verdict` | `detected` at all 45 | `detected` at all 45 |
| normality (Anderson-Darling, 5 %) | `consistent` at all 45 | same |

Reading against the row: "3-sigma offset <= X" is the statement
`sigma_to_spec >= 3` for limit X (`sigma_to_spec` = distance from the mean to
the limit in sigma, so the mean offset counts against the budget too). It
holds with a wide margin at every point on both limits; the lowest-margin
point is the one the record's own prose already names as worst
(`sf_125c_3.30v`). No new pass/fail is claimed beyond what the README row
already scored.

## Disclosed gaps (what this evidence does not show)

Item 6 asks for a recorded seed, a sample count, a deterministic negative
control, and MC combined with process corners. Stated precisely:

1. **Seed.** One seed, `setseed 20260909`, recorded in the record's
   `tb.json` and README. It is *common random numbers*: the same seed at all
   45 points. So the 45 measurements are strongly correlated views of **one**
   200-draw realization, not 45 independent trials; the independent sample
   count behind the whole claim is 200, and there is no second seed to show
   the result is not seed-specific. The seed is not carried in the `klt
   yield` report itself (the sample-set format has no field for it; filed as
   [klayout-tools#2840](https://github.com/2AMLogic/klayout-tools/issues/2840));
   it lives in the record this directory is derived from and in the
   `description` key of the samples document.
2. **Sample count.** N = 200 per point. The `sufficient` verdict is the
   zero-failure bound (n >= 183 for a +/-1 pt half-width): it certifies
   "yield >= 98.17 % at 95 % confidence", **not** the 99.73 % a literal 3-sigma
   yield would be. The 3-sigma statement rests on `sigma_to_spec` and the
   normal fit (tail behaviour beyond ~3 sigma of 200 draws is extrapolated,
   not observed). The margin (15.9 sigma to the 15 mV limit) is what makes
   that safe in practice, but it is an inference, and no `target_yield` is
   declared (the ratified row states none), so the report's status is
   `reported` and can never fail.
3. **Negative control.** The control is **synthetic and post-hoc**: the same
   200 draws with a forced +20 mV offset added (deterministic, no RNG). It
   proves the `klt yield` statistic separates a degraded distribution from
   this one; it does **not** prove the *circuit/bench* can detect a bad
   design. The bench's own circuit-level checks (`av_sigma_pct`,
   `sig_rpair_uv` null control, `mean_vos_sem`) and `sim/selftest.sh`'s
   `--sabotage-corners` loop are cited in the record README, but those are
   not `klt yield` inputs and are not what the verdict above was computed
   from. A real defect-injection MC re-run would be a `klt sim`
   `monte_carlo` request (batch fleet) and was not done here.
4. **MC x process corners.** Combined, but only as *mismatch-only MC at each
   deterministic corner*: `sw_stat_mismatch = 1`, `sw_stat_global` left at
   the PDK default 0, so there is no global-process Monte Carlo and no
   global x local joint distribution. Corners are never pooled (each point is
   its own population, per `klt yield`'s own caveat). The PDK models no
   resistor local mismatch (`mis_r = 0`), so no load-mismatch term is in
   these samples.
5. **Limits mapping.** The row is a 3-sigma statement; the report scores
   per-draw offset against +/-X. These are tied by `sigma_to_spec >= 3` as
   above, which is this directory's reading, not a DR-0002 clause.
6. **Scope of the DUT.** Schematic provenance (`comparator-dr0001`); the
   post-layout offset is not measured here. The other four spec rows are not
   covered ([#75](https://github.com/2AMLogic/gf180-comparator/issues/75)).

## Toolchain note

`klt yield` needs the `klt_yield_native` Rust extension, which no published
`klayout-tools` release ships as a wheel (upstream klayout-tools#2531). The
reports here were produced with `klayout-tools==0.6.0` in a **scratch venv
outside the repo** plus the extension built from a klayout-tools checkout's
`native/yield` (`cargo build --release`, rustc 1.99.0, the resulting
`libklt_yield_native.so` copied into the venv as `klt_yield_native.so`; the
host-wide `klt` and `~/.local` were not touched). `klt signoff` itself needs
no extension to *read* the report, so CI and `signoff/regenerate.sh` are
unaffected. The report does not carry a build identity (`klt yield` emits no
`provenance`), so this paragraph is the record of how it was made.
