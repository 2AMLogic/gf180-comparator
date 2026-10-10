# `sim/comparator-offset-cm-index/`

**Supplemental, unscored.** The monotonic-index stimulus variant of
[`comparator-offset-cm-window/`](../comparator-offset-cm-window/): same-draw
Monte-Carlo preamp offset and gain at the consumer's three input common modes,
`dut_vcm` - 100 mV / `dut_vcm` / `dut_vcm` + 100 mV (1.55 / 1.65 / 1.75 V),
documented in [`spec/consumers.md`](../../spec/consumers.md). Issue
[#218](https://github.com/2AMLogic/gf180-comparator/issues/218); it implements
the alternative that `comparator-offset-cm-window/README.md` deferred.

Nothing here adds a CMRR bound or changes the topology, and the consumer's
common-mode rejection verdict stays **Unknown**. This is schematic preamp DC
characterization: not a whole-comparator transient result, not an
extracted-layout result.

## Status

| Stage | State |
|---|---|
| Stimulus bench, request generation, ingest checks | Done (this directory, `sim/tools/mk_klt_request.py`, `sim/tools/klt_record.py`) |
| PDK-free asymmetric semantics fixture and unit tests | Done (`sim/harness/tests/test_cm_index_semantics.py`) |
| Bounded nominal fleet probe | **Done, executor supports the stimulus** ([`probes/20261010-nominal-fleet-probe/`](probes/20261010-nominal-fleet-probe/)) |
| 45-point PVT x N=200 campaign and append-only record | **Done: 45 of 45 points, 200 of 200 draws each** ([`records/20261010-130605300890-d8e9253.md`](records/20261010-130605300890-d8e9253.md)). Unscored; verdict stays Unknown. |

## Stimulus

One source `vidx` is swept `dc vidx 0 5 1`. Behavioural sources (`Bcmd`, `Bvd`
in [`testbench/tb_offset_cm_index.spice`](testbench/tb_offset_cm_index.spice))
map each index to the same pairs as the nested bench; thresholds sit at
half-integers so the mapping does not depend on float equality:

| index `k` | label | `vcmd` | `vd` |
|---|---|---|---|
| 0 | `dn_0` | -100 mV | 0 |
| 1 | `dn_2m` | -100 mV | +2 mV |
| 2 | `mid_0` | 0 | 0 |
| 3 | `mid_2m` | 0 | +2 mV |
| 4 | `up_0` | +100 mV | 0 |
| 5 | `up_2m` | +100 mV | +2 mV |

Because the analysis scale is the monotonic index, a raw
`.meas dc <name> find <node> at=<k>` names exactly one point, which a klt 0.5.0
runner can evaluate (the nested bench cannot be addressed that way). Per label
the request carries three cards: `dv_<label>` (`v(dd)`), and two coordinate
read-backs from the same solve, `xcm_<label>` (`v(xcm)` = `v(cm) - v(cmb)`, a
high-Z probe node) and `xvd_<label>` (`v(vd)`): 18 cards, no `expr` entries.

Request: one `dc vidx 0 5 1` analysis per draw, `monte_carlo {n: 200, seed:
20260909, vary: mismatch}`, one request per supply point. Select the bench
explicitly; the nested bench keeps its own refused contract and is not touched:

    python3 sim/tools/mk_klt_request.py comparator-offset-cm-index OUTDIR

(`--corners tt --temps 27 --supply-tolerance 0 --mc-n 3` produces the probe.)
The source-bundle and completeness machinery is the one the other fleet benches
use (#151, #152). Equal seeds across independent requests are never accepted as
pairing (`SEPARATE_REQUEST_PAIRING`); a draw is one `corners[]` entry, joined by
identity (`monte_carlo.sample_index`), with both coordinate read-backs checked
within 1 uV (`COORDINATE_MISMATCH`). Derived quantities (population sigma,
`Vos_p = -dv_p_0 / A_p`, endpoint-minus-midpoint offset change in voltage,
gain per common mode) are those of the nested bench: `derive_cm_window`.

## Evidence so far

**Semantics fixture (local, PDK-free, not design evidence).** The unit test
extracts the real stimulus block from the fragment and the real `.meas` cards
from `cm_index_measurements()`, drives a toy DUT whose output
`dd = 100*vd + 3*x + 40*x^2 - 3*x*vd` (`x = v(cm) - v(cmb)`) is deliberately
asymmetric, and compares all 18 values with expectations computed
independently of the bench's index table. Unit tests also reject swapped
coordinates, duplicate and missing draws, non-finite and missing values,
invalid gains, wrong sample identities and cross-request pairing.

**Nominal fleet probe (design simulation, 3 draws, one point, not a result).**
Fleet job `klt-sim-a04c0e729586`, executor `aws-batch-fleet`, runner klt
**0.5.0** (client 0.7.0+g8eec069c7576, `runner_compatibility: "mismatch"`,
which is the warn-mode skew the request tolerates because it uses no `expr`),
`c7i.8xlarge` spot, `tt` / 27 C / 3.30 V, `n=3`, seed 20260909, three distinct
per-draw seeds, 3 of 3 draws `pass`. Every draw returned all 18 values, finite,
with all coordinate read-backs exactly `vcmd` in {-0.1, 0, 0.1} and `vd` in
{0, 0.002}. Request, body netlist (sha256
`6fc5854d435026474e8e72517b216db300418f70574d62a0967b7217ff2c2121`, equal to
the report's `netlist_sha256`), source bundle (commit `e58b632`, clean) and
report are under `probes/20261010-nominal-fleet-probe/`. Ingest via
`collect_cm_index` accepted it with no issues. With three draws no statistic
here characterizes the window; the per-point outputs are plumbing only.

## Full-grid record (measured coverage: complete, 45 of 45 points)

Record [`20261010-130605300890-d8e9253`](records/20261010-130605300890-d8e9253.md) (JSON beside it), minted by
`python3 sim/tools/klt_record.py comparator-offset-cm-index` at clean commit
`d8e9253` (`mint_cm_index`: scoring-free, append-only). Three requests, one per
supply (2.97 / 3.30 / 3.63 V), each 5 processes x 3 temperatures x 200 draws =
3000 units; `monte_carlo {n: 200, seed: 20260909, vary: mismatch}`. Every
point returned 200 of 200 draws, all 18 finite values per draw, coordinate
read-backs within 1 uV, identity by `monte_carlo.sample_index`. Fleet jobs
`klt-sim-2abdda80958b` (2.97 V), `klt-sim-bfc397ed478e` (3.30 V),
`klt-sim-b86615e15b95` (3.63 V); executor `aws-batch-fleet` spot `c7i.4xlarge`,
runner klt 0.5.0 (client 0.7.0, warn-mode `mismatch`, harmless: no `expr`).
DUT `comparator-dr0001` (`design/comparator.spice`, sha256 `0df618e7...`),
source bundle and request/report/body files are under `corners/20261010-130605300890-d8e9253/`.

What it shows (schematic preamp DC, `dut_vcm` = 1.65 V, window 1.55/1.65/1.75 V):

| quantity (over all 45 points) | range |
|---|---|
| midpoint offset sigma `sig_vos_mid_mv` | 0.895 .. 1.043 mV |
| endpoint-minus-midpoint offset change, mean (`mean_dvos_dn_uv`, `mean_dvos_up_uv`) | -0.24 .. +0.21 uV |
| endpoint-minus-midpoint offset change, sigma (`sig_dvos_dn_uv`, `sig_dvos_up_uv`) | 0.26 .. 1.13 uV |
| gain at 1.55 / 1.65 / 1.75 V (`av_dn/mid/up_mean`) | 11.5 .. 26.5 V/V, rising 0.03-0.29 % per +100 mV |
| gain spread `av_sigma_pct` | 0.40 .. 0.72 % |

Limitations, stated plainly:

- **Unscored.** No ratified bound exists for common-mode offset change or
  rejection, so the consumer's rejection verdict stays **Unknown**. No CMRR
  figure is defined or claimed.
- **Resolution.** The offset changes are sub-microvolt to ~1 uV, against a ~1 mV
  midpoint sigma. They come from differences of two 12-digit `.meas` reads of
  ~1 uV deltas on a dc solve, so solver tolerance may be a visible fraction of
  them. The 125 C points show larger sigmas and means that change sign between
  supplies (for example `tt_125c`); read those as noise-floor, not as a trend.
  The result is that the preamp's *systematic* offset shift across the window is
  at most of order a microvolt, small beside its random offset; it is not a
  precision measurement of that shift.
- **Scope.** Schematic preamp DC characterization only. Not whole-comparator
  transient, not extracted-layout, no load-resistor mismatch (the PDK models none).
- **Draws shared across supplies.** All three requests use seed 20260909, so
  draw `mcN` is the same random sequence at each supply; the 45 points are not
  independent samples. Pairing inside a draw is by single report/analysis, never
  by seed.
- **Operational.** The first dispatch was lost client-side (the foreground
  wrapper timed out and killed the clients for 2.97 V and 3.30 V; their fleet jobs
  were orphaned, never ingested). A re-submit then hit
  `BATCH_MAX_CONCURRENT_INSTANCES=8` ("11 instance(s) already running") and was
  retried until accepted; neither case fell back to local simulation.

**Conclusion.** The selected executor supports this stimulus and returns all
ingredients. The full campaign was dispatched after the record-minting path (`mint_cm_index`) was added; see the section above.
