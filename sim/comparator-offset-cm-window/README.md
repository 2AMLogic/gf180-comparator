# `sim/comparator-offset-cm-window/`

**Supplemental, unscored.** Same-draw Monte-Carlo preamp offset and gain at the
three input common modes of the consumer window documented in
[`spec/consumers.md`](../../spec/consumers.md): `dut_vcm` − 100 mV, `dut_vcm`,
`dut_vcm` + 100 mV, i.e. 1.55 / 1.65 / 1.75 V. Issue
[#182](https://github.com/2AMLogic/gf180-comparator/issues/182).

This directory is the **feasibility stage** only. It holds the bench and the
request/report contract for paired common-mode measurement. **No record exists.
Full 45-point coverage is pending**, and the consumer's common-mode rejection
verdict stays **Unknown**. Nothing here adds a CMRR bound or changes the
topology. It is also not a whole-comparator transient result or an
extracted-layout result.

It is a separate bench on purpose. [`comparator-offset-mc/`](../comparator-offset-mc/)
keeps its standalone ±50 mV band, its manifest and all of its records
unchanged. Widening that band in place would blur how its history compares.

## Feasibility outcome: UNSUPPORTED on today's fleet

| Question | Answer | Where to check |
|---|---|---|
| Does the executor run the nested sweep `dc vd 0 2m 2m vcmd -100m 100m 100m`? | **Yes.** `klt sim` writes `analysis.kind`/`args` into the deck verbatim, as one analysis card. | klt v0.5.0 `src/klayout_tools/sim.py` `_write_corner_deck` (`lines.append(f"{analysis['kind']} {analysis['args']}")`); same in v0.7.0. |
| Are the six points one instance and one mismatch draw? | **Yes, by structure.** Each Monte Carlo sample is its own deck with one `.options seed=<rndseed>` card, one netlist instance and one analysis card. It is reported as one `corners[]` entry `<proc>/<T>C/mc<i>` that carries `monte_carlo.sample_index`. ngspice evaluates the `agauss` mismatch parameters once, when it expands that deck, and a `dc` sweep only steps source values. So every point of the sweep shares that draw. | klt v0.5.0 `_write_corner_deck` (the seed card ahead of the `.lib`/`.include`) and `_expand_monte_carlo`; klt `docs/cli/sim.md` "Monte Carlo sampling" (seed contract, unique sample IDs). |
| Can the fleet runner report all six points, each tied to both coordinates? | **No. This is the missing capability.** | See below. |

**The missing capability.** The fleet runner is **klt 0.5.0**. Every batch
record in this repo up to 2026-10-10 reports `runner_klt_version: "0.5.0"` in
`environment.remote`, while the client is 0.7.0. klt 0.5.0 accepts only raw
`.meas` cards. Its request parser refuses any `measurements[]` entry that has
no `spice` key, with `each request.measurements[] entry requires 'name' and
'spice'`. In a nested sweep, a `.meas dc … at=` card searches the scale of the
**inner** source (`vd`). That scale takes the values 0, 2 mV, 0, 2 mV, 0, 2 mV,
so the card cannot name the outer `vcmd` coordinate.

One PDK-free check was run with ngspice-46 on a toy resistor/B-source deck. It
was a semantics check, not design evidence. `.meas dc find … at=0` returned the
**first outer slice** (vcmd = −100 mV), not the midpoint. Through `.meas`, only
two of the six points can be reached, and the midpoint is not one of them.

`measurements[].expr` would close the gap, for example `v(dd)[k]` evaluated
after the analysis in the same `.control` block. It is klt issue #2533 and first
shipped in klt **0.7.0**. The runner does not have it.

**Status of the code.** It refuses explicitly, so no evidence record can be
produced:

- `python3 sim/tools/mk_klt_request.py comparator-offset-cm-window OUT` exits
  with `UNSUPPORTED_EXECUTOR_CAPABILITY: …`. It exits before staging any file,
  so no request set, body or source bundle is written.
- `python3 sim/tools/klt_record.py comparator-offset-cm-window …` exits with
  the same code before any dispatch or ingest. There is no record-minting path
  for this bench yet. Even with a capable runner it refuses, because full
  coverage is pending.

**Next steps** (one of these, in a follow-up):

1. **Preferred.** Move the fleet runner image to klt ≥ 0.7.0. That is a change
   to the fleet/worker spec, not to this repo. Then confirm the version from a
   report's `environment.remote.runner_klt_version` and
   `runner_compatibility: "match"`, and update `FLEET_RUNNER_KLT_OBSERVED` in
   `sim/tools/mk_klt_request.py` with that report as the cited source. Run a
   small nominal probe first. After that, add the record path and the 45-point
   campaign.
2. **Alternative, needs its own review.** Redesign the stimulus as one
   *monotonic* six-step index sweep: one source driving both `vd` and `vcmd`
   through behavioural sources. Then 0.5.0's `.meas dc … at=<k>` names each
   point unambiguously. This changes the stimulus form, so it was not done here.

## The contract (what a supported run must satisfy)

All values below are defined once in `sim/tools/mk_klt_request.py` and checked
by `sim/tools/klt_record.py` (`check_cm_window_request`,
`check_cm_window_executor`, `collect_cm_window`, `derive_cm_window`).

**Stimulus.** This is the fragment
[`testbench/tb_offset_cm_window.spice`](testbench/tb_offset_cm_window.spice).
Its stimulus topology is the same as `tb_offset_mc.spice`: `cm = dut_vcm + vcmd`,
`ap/an = cm ± vd/2`, and the probe `dd = aop − aon` is a high-Z VCVS. One
analysis per draw:

    dc vd 0 2m 2m vcmd -100m 100m 100m

`vd` is the inner (fast) source, so the flattened index is `k = 2·j + i`:

| label | common-mode delta `vcmd` | differential `vd` | index `k` |
|---|---|---|---|
| `dn_0` | −100 mV | 0 | 0 |
| `dn_2m` | −100 mV | +2 mV | 1 |
| `mid_0` | 0 | 0 | 2 |
| `mid_2m` | 0 | +2 mV | 3 |
| `up_0` | +100 mV | 0 | 4 |
| `up_2m` | +100 mV | +2 mV | 5 |

**Request.** There is one request per supply point. Each request has one `dc`
analysis and one `monte_carlo` block,
`{n: 200, seed: 20260909, vary: mismatch}`. There are 18 `expr`
measurements and no `.meas` card. For each label they are:

- `dv_<label> = v(dd)[k]`, the raw differential output;
- `xcm_<label> = v(cm)[k]-v(cmb)[k]`, the common-mode coordinate read back;
- `xvd_<label> = v(vd)[k]`, the differential coordinate read back.

The request also sets `batch.runner_version_check: "enforce"`, so an older
runner refuses before it simulates. With the `warn` mode that other benches use,
skew would only be detected after the run.

**Sample-key schema.** One draw is one report `corners[]` entry. Its key is
`(<proc>_<T>c_<vdd>v, mc<i>)`, and it must carry `monte_carlo.sample_index == i`
and all 18 names exactly once, each a finite number. Both read-backs must match
the label within 1 µV. Draws are joined by identity, never by position.

The following each fail with a named code, and the affected sample is excluded:

- duplicate keys (`DUPLICATE_SAMPLE`)
- missing draws (`MISSING_SAMPLE`)
- extra draws (`UNEXPECTED_SAMPLE`)
- a wrong sample index (`SAMPLE_IDENTITY_MISMATCH`)
- unknown or wrong endpoint labels (`UNEXPECTED_VALUE` / `COORDINATE_MISMATCH`)
- incomplete samples (`INCOMPLETE_SAMPLE`)
- repeated names (`DUPLICATE_VALUE`)
- non-finite values (`NONFINITE_VALUE`)
- a runner that lacks `expr` or does not match the client version
  (`UNSUPPORTED_EXECUTOR_CAPABILITY`)

**Pairing.** All six values of a draw must come from one entry, which means one
analysis of one instance. Values pooled from **separate requests** are refused
(`SEPARATE_REQUEST_PAIRING`) **even when the requests share a seed**. A shared
seed reproduces a sequence of separately randomized decks; it does not make two
decks one instance. Gain scatter (`av_sigma_pct`) is kept only as a diagnostic.
It is not proof of identity.

**Per-draw equations.** For each draw and each `p ∈ {dn, mid, up}`:

    A_p    = (dv_p_2m − dv_p_0) / 0.002          (must be finite and > 0)
    Vos_p  = −dv_p_0 / A_p
    ΔVos_dn = Vos_dn − Vos_mid                     (same draw)
    ΔVos_up = Vos_up − Vos_mid                     (same draw)

The per-PVT-point outputs are the means and **population** standard deviations
over the draws. They are named as in [`testbench/tb.json`](testbench/tb.json)'s
`measure`: `sig_vos_mid_mv`, `mean_vos_mid_uv`, `mean/sig_dvos_dn_uv`,
`mean/sig_dvos_up_uv`, `av_dn/mid/up_mean`, `av_sigma_pct`. Offset changes are
reported in voltage. No rejection ratio is defined. An invalid draw drops its
whole PVT point and names the problem (`INVALID_GAIN`, `NONFINITE_DERIVED`).

**Source-bundle binding.** This works the same way as for every other fleet
bench (issue #151). `stage_sources` copies this `testbench/` directory (the
fragment and `tb.json`) and the selected DUT into the work directory. The body
netlist `.include`s those staged copies and carries one `* source-sha256` line
per staged file. Ingestion re-hashes all of it before anything is published.

**Executor and version.** The executor is `klt sim` on the `batch` backend. The
runner must be klt ≥ 0.7.0, which provides `measurements[].expr`, and its
version must equal the client's (`runner_compatibility: "match"`). Today the
observed runner is 0.5.0.

## What is measured vs. what is only validated

- **Real measured coverage: none.** No simulation of this bench has been run,
  either on the fleet or locally. The local control loop in `tb.json` mirrors
  `comparator-offset-mc`'s validated `dowhile`/`reset` method at ±100 mV, but it
  was not run when it landed.
- **Synthetic contract validation:** the PDK-free tests in
  `sim/harness/tests/test_klt_record.py` (`CmWindowRequestContract`,
  `CmWindowDerivation`). They use hand-chosen, deliberately asymmetric
  fixtures. Those values are test inputs, not simulation evidence, and they
  cannot reach a record.
