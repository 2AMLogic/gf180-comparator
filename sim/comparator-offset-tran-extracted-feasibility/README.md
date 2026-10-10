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
(rc=0; see `retry.log`). Reports carry `runner_compatibility: mismatch` (fleet runner klt 0.5.0,
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
* A 45-point x 200-draw campaign and any item-7 repinning need a later
  proposal; this probe sets no ratified-row verdict.

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
