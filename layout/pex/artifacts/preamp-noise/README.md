# Extracted vs schematic preamp noise: paired nominal feasibility probe (issue #202)

**Feasibility result: POSITIVE.** Both preamp outputs of the flat extracted
DUT can be observed, from extraction connectivity alone, without touching any
extracted device or R/C, and the committed noise methodology returns finite
positive gain and noise on both legs of the pair at one nominal point.

This is a measurement-ACCESS result at ONE point (tt, 27 C, 3.30 V). It is not
a PVT record, not a spec verdict and not a signoff input. Nothing under `sim/`
(records, bounds, `sim/dut.json` refusal of the analog-partition benches) was
changed.

## What reset-state noise does and does not cover

The deck holds the whole comparator in reset (`clk` = 0) and runs `.noise` about
that DC point. It measures the **preamp's** thermal and flicker noise (with the
real latch gate load in place) referred to the input by the measured DC gain.
**It excludes the latch's regenerative noise**: `.noise` has no operating point
to linearise about during regeneration. This does NOT measure whole-comparator
decision noise and does NOT complete T1 item 7.

## Method (same as `sim/comparator-preamp-noise/testbench/`)

`vn_in_uv` = integrated output noise (1 Hz..1 GHz) / measured DC differential
gain; `vn_in_hf_uv` is the same from 1 kHz up; fnoicor = PDK default 0;
mismatch off; `dut_ib`, `dut_vcm` from `sim/dut.json` (identical for both
entries); same stimulus (`vd` ac 1, split +/-0.5 onto `vcm`). The whole
`comparator_dut` is instantiated (`Xdut`), not the analog partition.
Cross-check: the schematic leg of this deck reproduces the harness bench on this
host (`python3 sim/run_corners.py comparator-preamp-noise --corners tt --temps
27 --supply-tolerance 0 --no-write --allow-toolchain-drift`) to all printed
digits: av_dc 18.0123, vn_in_uv 91.2549, and the committed record
`sim/comparator-preamp-noise/records/20260910-125200-4805118.json`
(ngspice-46). (The later 20261008 tt row, 18.49 / 99.46, was taken at
ngspice-42 with toolchain drift accepted and does not match this host's
ngspice-42 either; not investigated here.)

## Observation mapping (`layout/pex/preamp_nodes.py`)

Derived from connectivity of the adapted extracted netlist, never from net
numbers: the two `ppolyf_u_1k` loads each have exactly one terminal on the
`vdd` hub, and the other terminal's hub is a preamp output. Each output must
have exactly one input-pair NMOS drain (gates on `vinp`/`vinn`, distinct, shared
tail source, tail driven by exactly one `ibias`-gated NMOS to `vss`, bulks on
`vss`, resistor substrate on `vss`) and exactly one other terminal, a
decision-stage gate. Anything else raises `MappingError`. The layout-label
names and the `klt extract` report's per-net terminal lists are cross-checked
against the structural answer. Regressions:
`python3 layout/tests/test_preamp_nodes.py` (15 cases, incl. changed
connectivity, extra terminals, swapped gates, wrong tail, wrong
bulk/substrate, a third resistor, no `--parasitics` legs).

Result on the current layout (DR-0001, `layout/comparator.gds`):

| output (schematic sense) | hub node | input device (gate) | load | latch gate |
|---|---|---|---|---|
| `aop` | `aop` | `M$15` (`vinn`) | `X$29` | `M$9` |
| `aon` | `aon` | `M$14` (`vinp`) | `X$28` | `M$13` |

Body bias: the preamp NMOS bulks and both resistor substrate pins resolve (via
their series legs) to the `vss` hub. Observation uses ngspice hierarchical
names (`xdut.xlayout_dut.aop`), leaving every device and R/C untouched.
Two placements are measured: the **hub** (lumped net node, primary) and the
**drain leg** (input-device side of its series R).

## Results (tt, 27 C, 3.30 V; `record.json` has everything)

| case | av_dc | onoise (uV) | **vn_in_uv** | vn_in_hf_uv | inoise_band_uv | white (nV/rtHz) | ENBW (MHz) |
|---|---|---|---|---|---|---|---|
| schematic, bench 10 fF allowance per output | 18.012 | 1643.7 | **91.25** | 90.97 | 329.9 | 250.15 | 43.18 |
| schematic, no allowance (like-for-like) | 18.012 | 1853.6 | **102.91** | 102.66 | 329.5 | 250.21 | 54.89 |
| extracted, hub | 17.930 | 1271.2 | **70.90** | 70.53 | 340.1 | 252.11 | 25.42 |
| extracted, drain leg | 17.942 | 1272.3 | **70.91** | 70.54 | 341.4 | 252.28 | 25.43 |
| extracted, hub, `vsubs` tied to 0 V (sensitivity) | 17.930 | 1271.1 | **70.89** | 70.53 | 340.1 | 252.11 | 25.42 |

Delta, extracted hub vs schematic: gain -0.46 % (vs either schematic row);
white density +0.8 %; vn_in -22 % vs the committed bench (which carries the
stated 10 fF placeholder) and -31 % vs the no-allowance schematic. The
extracted leg carries no extra 10 fF: the extraction supplies the real routing
and gate loading (493.5 fF extracted total, 35-40 fF on each output net).

Interpretation limits (read before quoting):

* The integrated noise falls because the extracted outputs are **more heavily
  loaded**: ENBW drops 54.9 -> 25.4 MHz while the white density is unchanged
  (+0.8 %). The 1 GHz integration makes the number bandwidth-sensitive; this is
  a lower noise *bandwidth*, not a quieter preamp, and `inoise_band_uv`
  (ngspice's own per-bin referral) goes UP 3 %.
* The extraction is first-order lumped (one star R and one ground C per net, no
  lateral coupling, `distributed_rc` false). Hub vs drain-leg agree to 0.02 %
  here, so placement within the lumped model is not a limiting factor, but that
  agreement says nothing about a distributed model.
* Extracted DC outputs differ by 6.1 mV (`dc_hub_p` 2.0504 V vs `dc_hub_n`
  2.0443 V; schematic: equal), the layout's systematic asymmetry. The
  small-signal gain is taken about that real operating point.
* The extraction ties its global `vsubs` node to 0 through 1e12 ohm (AC
  floating). Tying it to 0 V changes vn_in by 0.004 %, so it is not
  limiting at this point.
* Extraction identity: `klt 0.7.0+g5e5b55992a7f` / klayout 0.30.12 was used on
  this host, newer than the 0.6.0 that minted the committed
  `layout/lvs/comparator.extract-rc.json`. The probe re-extracts to a scratch
  directory and does not overwrite that report; its own netlist hash is in
  `record.json`. The schematic netlist sha256 (`0df618e7...`) is the file at
  commit 424f03f.

## Reproduce

```
python3 layout/pex/preamp_noise_probe.py --outdir layout/pex/artifacts/preamp-noise
```

Four single-unit local `ngspice -b` runs (no loop over PVT points, ~1 s each).
`*.cir` are the exact decks, `*.log` the ngspice output,
`comparator.dut-layout.cir` the adapted extracted netlist.

## Follow-up (contingent, not started)

A full 45-point extension (mos corner set x 3 T x 3 V), as a `klt sim` request
on the batch fleet with the same observation mapping. This probe supports
no PVT, signoff-promotion or spec-row claim; the schematic bounds and existing
records are untouched.
