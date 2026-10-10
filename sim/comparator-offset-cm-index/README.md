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
| 45-point PVT x N=200 campaign and append-only record | **Pending. Measured coverage: none.** `klt_record.py` refuses this bench with `RECORD_PATH_PENDING` until a record-minting path exists. |

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

**Conclusion.** The selected executor supports this stimulus and returns all
ingredients. The full campaign was **not** dispatched in this change because it
needs a record-minting path (scoring-free record writer, completeness gate over
all 45 points) that is not written yet. Until a complete append-only record
exists, **measured coverage of the window is none** and the 45-point claim must
not be made.
