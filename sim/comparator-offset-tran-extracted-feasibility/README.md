# `sim/comparator-offset-tran-extracted-feasibility/`

**Feasibility only (issue #219).** Can the whole-comparator staircase transient
Monte Carlo of [`comparator-offset-tran`](../comparator-offset-tran/README.md) be
run against the **extracted** binding with a valid measurement contract? This
directory answers that for two PVT points at N = 20 draws. It is **not** a
campaign, **not** signoff item 7, mints **no** record under any `records/`
directory, and changes no ratified bound, active topology or verdict. The
schematic bench, its records and the production refusal in
`sim/tools/mk_klt_request.py` (`supports the schematic binding only`) are
untouched.

Tool: [`sim/tools/extracted_tran_feasibility.py`](../tools/extracted_tran_feasibility.py)
(`contract`, `probe`, `mc`, `evaluate`); tests:
`sim/harness/tests/test_extracted_tran_feasibility.py` (28 synthetic fixtures).

## Result in one paragraph

The extracted binding **as `layout/run_extract_sim.py` adapts it cannot support
the measurement**: it writes the 27 MOS devices as bare `M... nfet_03v3`
instances of the PDK `.model`, which bypass the `nfet_03v3`/`pfet_03v3`
*subckt* whose body is the only place `sw_stat_mismatch` scales `delvto`/`mulu0`.
Fleet probe `probes/20261010-standard-adapter-negative-control/` confirms it
empirically: 20 draws at each of two points, 20 different mismatch seeds,
**bit-identical** results, and the tool refuses
(`MISMATCH_NOT_EXERCISED`; `refusal-*.json`). With a **feasibility-only**
re-adaptation (`mismatch_capable()`: `M<n>` -> `X<n>`, nothing else changed;
the committed adapter and the `comparator-dr0001-layout` binding are not
modified) the measurement is feasible, and both fleet probes pass every gate
(`probes/20261010-mismatch-capable-feasibility/`). Making the committed adapter
emit subckt calls is a separate change (it re-pins the binding's netlist hash
and every extracted record's provenance) and needs its own decision; this issue
does not make it.

## Feasibility artifact (the contract, and where each item is checked)

`probes/20261010-mismatch-capable-feasibility/contract.json`.

| item | contract | result |
|---|---|---|
| extraction identity | `layout/comparator.gds` sha256 `d668ccb5...` (= the report's input hash); raw netlist re-made with the klt the committed report names (**0.6.0**, via `uvx --from klayout-tools==0.6.0`) so its sha256 equals the report's `netlist_sha256` `50e5dbf0...`; adapted by `run_extract_sim._adapt_netlist` unchanged | match. The host's klt 0.7.0 extracts a *different* netlist (`dc52d612...`; total poly R 3380 ohm vs 4120.8 ohm), so the identity check is load-bearing: an extraction by the wrong klt is refused (`EXTRACTION_IDENTITY`) |
| device mismatch support | every MOS card calls the PDK subckt (one `.subckt nfet_03v3`/`pfet_03v3`, body has `agauss` x `sw_stat_mismatch`); (model, L, W) multiset equals `design/comparator.spice`'s (29 devices incl. the two 120u/1u loads) | standard adapter: **REFUSED** `ADAPTED_MOS_BYPASS_MISMATCH`; variant: pass |
| body bias | NMOS bulk resolves to the `vss` hub, PMOS bulk to the `vdd` hub (through the extraction's series-R legs); report lists no `unbiased_pmos_body_nets` / `missing_flavour_markers` | pass (both card forms) |
| observation nodes | `layout/pex/preamp_nodes.py` structural derivation (labels and the report cross-checked) -> hubs `xa.xlayout_dut.aop` / `.aon`, generated into the body netlist, never frozen in a fragment | pass; missing/ambiguous/swapped -> `OBSERVATION_NODES` refusal |
| trip convention | trip = differential input (vinp-vinn) at which the decision flips; **absolute**: `centre + v0 + k*step - step/2`; input-referred offset = -trip. Mean and sigma are reported as two numbers; the centre is never subtracted | see below |
| executor/source | probe: single-unit `klt sim --backend local`; Monte Carlo: `klt sim` batch fleet (runner klt 0.5.0), one thread per unit; source bundle per request set; no local fallback | see below |

## Method

1. `tb_trip_probe.spice`: mismatch **disabled** (`sw_stat_mismatch=0`, no
   `monte_carlo`), slow +-40 mV symmetric ramp, one self-contained
   `.meas ... find v(rmp) when v(dn)=0.5 rise=1 td=8u` (the klt-generated deck
   cannot reference `t_flip` from a second card;
   [klayout-tools#3038](https://github.com/2AMLogic/klayout-tools/issues/3038)).
   Quantisation ~30 uV. Its trip point, rounded to 0.01 mV, is the staircase centre.
2. `tb_offset_tran_extracted.spice` + a generated `vsd`: the schematic bench's
   64 x 0.16 mV staircase (the generator reproduces the committed schematic
   PWL exactly at centre 0, tested), shifted so its start is centred on the
   probe; preserved across the point's whole population. `Eddprobe`/`Eapo`
   are generated from the derived hubs.
3. Per-draw validation reuses `klt_record.derive_offset_tran` on an
   absolute-level view (endpoint decisions, trip bracket `1..63`, evaluate-phase
   flip, gain sign, finite ingredients, `collect_checked` coverage), then:
   mismatch actually exercised (sigma > 0), >= 3 steps of edge margin, and the
   mismatch-free probe trip inside the population's bracket (+- one step).
   Any failure refuses the whole point (`refusal-<point>.json`).

## Probes (limited grid, never full-grid statistics)

Seed 20260909 (the schematic bench's), `vary: mismatch`, **N = 20**, one
process corner x one temperature x one supply per request. Sigma precision at
N = 20 is ~16 %; **no comparison with the schematic's sigma is claimed**.

| point | probe trip | centre | N valid | **absolute mean trip** | random sigma (quantisation-corrected) | population bracket | fleet job |
|---|---|---|---|---|---|---|---|
| `tt_27c_3.30v` (nominal) | -8.218 mV | -8.22 mV | 20/20 | **-8.108 mV** | 1.164 mV | [-9.98, -5.66] mV, levels 21..48 of 1..63 | `klt-sim-9f0281ca60b2` |
| `ff_125c_3.63v` (largest systematic offset in the committed extracted regeneration record, -21.57 mV) | -21.538 mV | -21.54 mV | 20/20 | **-21.332 mV** | 1.328 mV | [-23.14, -18.50] mV, levels 22..51 of 1..63 | `klt-sim-1002b3587cf6` |

The staircase brackets every draw's actual trip point at both points, and the
mismatch-free probe lies inside each population's bracket. The deterministic
layout offset (-8.1 mV nominal, -21.3 mV at the binding point) is carried by
the absolute mean and is not removed by the centring; centring only places the
+-5.04 mV range. The probe's nominal trip (-8.21805 mV) reproduces the
regeneration record's `dut_vos_v` (-8.21806 mV) with the mismatch-capable
netlist; at `ff_125c_3.63v` the two probes differ by 30 uV (-21.538 vs -21.568
mV, one probe quantum).

Executor notes: the first tt batch submit (attempt 1, rc=1) failed with
`batch backend failed: batch-fleet-provision.sh launch failed (exit 1): error:
8 instance(s) already running + 1 requested exceeds
BATCH_MAX_CONCURRENT_INSTANCES=8` (`err-mc-tt.attempt1.txt`); it was resubmitted
to the **same** batch backend (no local fallback) and succeeded on attempt 2
(rc=0). Reports carry `runner_compatibility: mismatch` (fleet runner klt 0.5.0,
client 0.7.0), as every batch record in this repository does. Probe-leg
reports are local single-unit runs (klt 0.7.0 client; no job id). The source
bundles are marked dirty because the runs preceded the commit of this tool and
testbench, and the freshly extracted netlist lives outside the repository tree
(`extract/` here is its committed copy); these are feasibility probes, not
reference evidence.

## Withheld

* **Same-draw preamp/latch decomposition (`Vos_pre`, latch term): withheld.**
  It needs the preamp gain linearised across the layout's systematic offset on
  series-R hub nodes; that has not been validated for the extracted netlist.
  `dd_start`/`dd_end` are measured only as the gain-sign validity gate and are
  not published as a preamp offset.
* **Resistor hand-budget term: withheld.** The extracted loads were checked
  (two `ppolyf_u_1k`, `r_length=120u`, `r_width=1u`, equal to the schematic's)
  but the budget's `vdrop/Av` term depends on the withheld gain. Nothing from
  the schematic bench's `rmis_*` arithmetic is transplanted.
* Any item-7 repinning needs a later proposal; this probe sets no
  ratified-row verdict. (The 45-point x 200-draw experiment is the separate
  section below, issue #231.)

Tool gaps filed: [klayout-tools#3038](https://github.com/2AMLogic/klayout-tools/issues/3038)
(dependent `.meas` cards), [klayout-tools#3039](https://github.com/2AMLogic/klayout-tools/issues/3039)
(no MOS subckt-wrapper emission); cross-pollination pointer
[gf180-sar-adc#499](https://github.com/2AMLogic/gf180-sar-adc/issues/499).

## Reproduce

    python3 sim/tools/extracted_tran_feasibility.py contract OUT
    python3 sim/tools/extracted_tran_feasibility.py probe    OUT --point P
    klt sim OUT/request-probe-P.json --backend local --format json -o OUT/out > OUT/report-probe-raw.json
    python3 sim/tools/extracted_tran_feasibility.py mc       OUT --point P --probe-report OUT/report-probe-raw.json --mc-n 20
    klt sim OUT/request-mc-P.json --format json -o OUT/out-mc > OUT/report-mc-P.json   # KLT_SIM_BACKEND=batch
    python3 sim/tools/extracted_tran_feasibility.py evaluate OUT --point P

`contract` needs `uvx` (a throwaway environment; no host tool is changed).

## Experimental 45-point campaign (issue #231) -- STATUS: RUN, 45/45 valid (experimental)

**Results: `campaign/20261010/`** (`campaign-summary.json`, per-point
`campaign-<point>.json`, probe reports, requests, contract, extract copy).
All 45 corners returned exactly 200 valid draws (`complete: true`, no failed or
missing points). Across the grid: absolute systematic offset 1.75 .. 21.38 mV
(worst `ff_125c_3.63v`), random sigma 0.884 .. 1.192 mV (worst `ff_125c_3.63v`);
|systematic| + 3 sigma worst 24.96 mV is **informational only** (no ratified
total-offset verdict). Provenance caveats: the source bundle is marked dirty
only because the campaign inputs were untracked when run; the fleet runner is
klt 0.5.0 vs client 0.7.0 (`runner_compatibility: mismatch`, as for every batch
record here). The 45 raw Monte Carlo reports are committed losslessly as
`campaign/20261010/report-mc.tar.gz` (1.2 MB; `out*/` scratch artifacts are
not committed; fleet job ids are in each `campaign-<point>.json`). Replay
(PDK-free, on a scratch copy so the committed evidence stays untouched):

```
S=$(mktemp -d); cp -r campaign/20261010/. "$S"; tar xzf "$S/report-mc.tar.gz" -C "$S"
for p in <point> ...; do python3 -I ../tools/extracted_tran_feasibility.py evaluate "$S" --point "$p" --campaign; done
python3 -I ../tools/extracted_tran_feasibility.py summary "$S"
```

`evaluate` checks the report's netlist sha256 against the submitted body,
draw coverage and the population gates, then re-derives every statistic; the
output matches the committed `campaign-<point>.json` (verified for
`tt_27c_3.30v` and `ff_125c_3.63v`).

The tool, PDK-free tests and fleet reproduction recipe below were delivered
first (#236). This is an additive, experimental extension:
it mints no record, repins no signoff item, and leaves the production adapter,
the `comparator-dr0001-layout` binding, the committed extracted records and
every ratified bound untouched. The mismatch-capable netlist is still the
feasibility-only variant staged under the campaign output directory.

Scope: the schematic offset-tran bench's 45-point grid (5 process corners x
3 temperatures x 3 supplies), **N = 200 mismatch-only draws per corner**, seed
20260909, one request per point. `--campaign` refuses any other N or point.

Gates (all reused or extended from the feasibility path): contract identity
pinned to the committed extraction report (layout sha256 = report input hash,
raw netlist sha256 = `netlist_sha256`, klt version = the report's, via `uvx`);
mismatch-capable subckt-call form with the schematic's (model, L, W) multiset;
per-corner mismatch-free trip probe before centring; finite-value, coverage,
endpoint-decision, trip-bracket, mismatch-exercised (sigma > 0), 3-step
edge-margin and probe-bracketed gates; exactly 200 valid draws. A corner that
fails any gate writes `refusal-<point>.json` and is **listed, never dropped**;
`summary` reports `complete: true` only with 45/45 valid corners (exit 3
otherwise, and no aggregate is produced).

Reported per corner, as separate numbers: the absolute mean trip (centre NOT
subtracted; systematic offset = -mean trip) with SE(mean) = sigma/sqrt(N), and
the quantisation-corrected random sigma with SE(sigma) = sigma/sqrt(2(N-1)) and
a 95 % interval. Random 3-sigma alone is not a ratified total-offset pass; the
summary carries `ratified_total_offset_verdict: null`. Preamp/latch
decomposition and the resistor hand-budget stay withheld.

Fleet reproduction (run from a clean checkout so the source bundle is not
marked dirty; each `klt sim` Monte Carlo goes to the batch fleet, with no local
fallback if a submit fails -- report the error instead):

    OUT=sim/comparator-offset-tran-extracted-feasibility/campaign/<date>
    python3 sim/tools/extracted_tran_feasibility.py contract $OUT     # uvx klt==report's version
    for P in $(python3 -c "import sys; sys.path.insert(0,'sim/tools'); import extracted_tran_feasibility as e; print(*e.campaign_points())"); do
      python3 sim/tools/extracted_tran_feasibility.py probe $OUT --point $P --campaign
      klt sim $OUT/request-probe-$P.json --backend local --format json -o $PWD/$OUT/out > $OUT/report-probe-raw.json
      python3 sim/tools/extracted_tran_feasibility.py mc $OUT --point $P --campaign --probe-report $OUT/report-probe-raw.json
      KLT_SIM_BACKEND=batch klt sim $OUT/request-mc-$P.json --format json -o $PWD/$OUT/out-mc > $OUT/report-mc-$P.json
      python3 sim/tools/extracted_tran_feasibility.py evaluate $OUT --point $P --campaign
    done
    python3 sim/tools/extracted_tran_feasibility.py summary $OUT

The loop is orchestration of single `klt sim` submissions (the probes are
single-unit local runs, the Monte Carlo is fleet-side); it must be driven by
the fleet-dispatching operator, not as a local ngspice grid. Fleet cost
(45 x 200 transient units) and staircase bracketing at the extreme corners are
the known risks: a point whose trips leave the +-5.04 mV range fails
`EDGE_MARGIN` / `PROBE_NOT_BRACKETED` and is reported, not widened.
