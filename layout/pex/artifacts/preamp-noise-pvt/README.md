# Paired extracted vs schematic preamp noise over 45-point PVT (issue #209)

**Status: STOPPED at the executor-capability gate. No PVT result exists.**
The fleet runner (klt 0.5.0) cannot execute the request. The 45-point grid was
not submitted and was not run locally. Nothing in this directory is a PVT
record, a spec verdict, a signoff input or a T1 promotion.

This directory extends the nominal feasibility probe of issue #202
(`../preamp-noise/`). The tool is `layout/pex/preamp_noise_pvt.py` and its
PDK-free regressions are in `layout/tests/test_preamp_noise_pvt.py`. Evidence is
append-only. Each run has its own `<UTC stamp>-<commit>/` subdirectory.

## Scope (read before quoting anything)

Reset-state `.noise` about the clk-low operating point measures the preamp's
thermal and flicker noise with the real latch gate load, referred to the input
by the measured DC gain. **It excludes the latch's regenerative noise.** It is
not whole-comparator decision noise and cannot complete T1 item 7 by itself.
Every summary that `ingest` writes says so (`scope.excludes`). It also sets
`scope.t1_promotion: false` and `spec_row_verdict: null`, whether or not the
verdict is complete.

## Method expressed as a `klt sim` request

One deck per unit uses `analysis_steps` (klt #2482) and `measurements[].expr`
(klt #2533):

| step | analysis | read |
|---|---|---|
| `op` | `op` | `v(ibn)` bias anchor, both DC outputs |
| `nfull` | `noise v(P,N) vd dec 20 1 1e9` | `onoise_total`, `inoise_total` |
| `nhf` | `noise v(P,N) vd dec 20 1e3 1e9` | `onoise_total` |
| `nwhite` | `noise v(P,N) vd lin 11 0.995e6 1.005e6` | `onoise_total` (10 kHz band at 1 MHz) |
| `ac` | `ac dec 20 1 1e9` | `av_dc = mag(v(P)-v(N))[0]` |

The derived values are `vn_in_uv = nfull.onoise/ac.av_dc*1e6` (the measured-gain
referral), the >1 kHz version, `onoise`, `inoise_band`, white density
(`nwhite.onoise/sqrt(10 kHz)`) and ENBW. A step expression evaluates against
its own totals plot, so the bench's `noise1.onoise_spectrum[120]` cannot be
addressed. That is why white density comes from a narrow band integral. Every
request sets `batch.runner_version_check: enforce`, so a runner that cannot
honour these keys refuses before simulating. It does not drop the keys and
return something else.

The sources are pinned to #202, and the tool refuses on any difference:

* Schematic leg: `design/comparator.spice`, sha256 `0df618e7...`. This is the
  like-for-like case with **no 10 fF allowance**. The bench's 10 fF-allowance
  numbers stay in `sim/comparator-preamp-noise/` records and are not this
  comparison.
* Extracted leg: `../preamp-noise/comparator.dut-layout.cir`, sha256
  `a7ca3c00...`. It is observed at #202's connectivity-derived hub nodes
  `xdut.xlayout_dut.aop/aon`. The extracted capacitance supplies the loading.
* Both legs use the same stimulus lines, sliced from #202's own deck builder,
  the same `dut_ib = 10 uA` and `dut_vcm = 1.65 V`, fnoicor at the PDK default
  and mismatch off.
* Disclosures carried over from #202: the preamp NMOS bulks and the resistor
  substrate resolve to `vss`. The extraction is first-order lumped RC per net,
  with no lateral coupling and `distributed_rc` false.

## Run `20261010-040759-c40d49e` (clean origin commit c40d49e)

### 1. The request expresses the #202 method (`nominal-local/`)

This is one single-unit `klt sim --backend local` run per leg at tt, 27 C,
3.30 V. It is a debug probe, not a grid. Client: klt 0.7.0+g8eec069c7576,
ngspice-46. The documented tolerance is `NOMINAL_TOLERANCE_REL = 1e-4`.

| leg | quantity | request | #202 record | rel |
|---|---|---|---|---|
| schematic | av_dc | 18.012265 | 18.012265 | 2e-11 |
| schematic | vn_in_uv | 102.910075 | 102.910075 | 3e-11 |
| schematic | white_nv_rthz | 250.20574 | 250.20567 | 2.5e-7 |
| schematic | enbw_mhz | 54.88554 | 54.88556 | -5.0e-7 |
| extracted | av_dc | 17.930005 | 17.930005 | 4e-12 |
| extracted | vn_in_uv | 70.896674 | 70.896674 | 7e-12 |
| extracted | white_nv_rthz | 252.11026 | 252.11020 | 2.3e-7 |
| extracted | enbw_mhz | 25.42328 | 25.42329 | -4.6e-7 |

All eight quantities on both legs are in `nominal-local/probe-summary.json`
(`within_tolerance: true`). The only non-round-off differences come from the
band-integrated white density. `nominal-local/paired-summary.json` is the
validator run on this nominal set. Its verdict is **incomplete**: the grid has
1 corner, not 45, and the reports are local with no fleet runner. That is the
intended behaviour: a nominal or local result cannot produce a complete
verdict.

### 2. The fleet runner cannot execute it (`nominal-fleet/`)

One nominal request (extracted leg, one unit) was submitted with
`KLT_SIM_BACKEND=batch`. The runner's preflight rejected it before any
simulation (job `klt-sim-077efa68c737`, exit 87):

```
batch_runner_version_mismatch: ... the fleet runner runs klt 0.5.0 but the
submitting client is 0.7.0+g8eec069c7576 -- the request was not run
```

Even without the version pin, a 0.5.0 runner accepts only `.meas`-card
measurements. It has no `analysis_steps` and no `expr`, and ngspice has no
`.meas noise`. So no request it accepts can read a noise integral or
perform the measured-gain referral (klt #2938, #2948, #2877). Every earlier
batch record in this repository through 2026-10-10 also reports
`runner_klt_version` 0.5.0.

### 3. The campaign refuses (`campaign-refusal.txt`)

`preamp_noise_pvt.py campaign OUT --probe-report nominal-fleet/report-extracted-v3.30.json`
stops with `UNSUPPORTED_EXECUTOR_CAPABILITY` before it stages or submits
anything. No local grid is substituted.

## Resuming once the fleet runner is updated

```
python3 layout/pex/preamp_noise_pvt.py probe  <dir>/nominal-fleet --backend batch
python3 layout/pex/preamp_noise_pvt.py campaign <dir>/pvt --probe-report <dir>/nominal-fleet/report-extracted-v3.30.json
python3 layout/pex/preamp_noise_pvt.py ingest <dir>/pvt   # re-validates; writes paired-summary.json
```

`ingest` reports `complete` only when all of the following hold:

* Each leg has exactly 45 unique expected corners: 5 mos corners x {-40, 27,
  125} C x {2.97, 3.30, 3.63} V.
* Gain and noise are finite and positive, with `av_dc >= 1`.
* Every referral recomputes from the same unit's raw values to within 1e-6.
* The >1 kHz noise does not exceed the full-band noise.
* Every report's simulated-netlist sha256 matches its bundled body.
* The DUT, bias and stimulus identities match #202.
* Every runner is a version-matched klt >= 0.7.0.

Any failure produces `incomplete` with every reason listed. Per-corner deltas
and the binding corners (highest extracted and schematic `vn_in`, largest
`vn_in` and white-density change, lowest extracted gain) cite the request,
report, netlist sha256 and klt corner id of both legs. Gain, noise, white
density and ENBW are always reported together, so a reader cannot mistake a
narrower noise bandwidth from heavier extracted loading for a quieter preamp.
