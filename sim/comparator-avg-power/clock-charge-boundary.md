# Clock-charge boundary at the nominal DR-0006 condition (issue #452)


DR-0006's accounting boundary keeps the ideal clock source's charge OUTSIDE the
average-power row and requires it to be "recorded for the integrator" as an
informational line; feasibility item 4 asks reviewers to be shown how much the
figure depends on that boundary choice. This report answers the boundary
question at the nominal condition (16 MHz, 10 mV alternating overdrive, 20 fF
loads) with **no new simulation**: every number below is computed from the two
committed 45-corner records' own `q_win_pc`, `q_clk_pc`, `vsup_v` and
`p_avg_uw` columns.

**Definition.** `P_avg(pin charge inside the row) = VDD · (Q_win + Q_clk) / (N·T)`,
the same charge-form integral as the committed `p_avg_uw = VDD · Q_win / (N·T)`
with the clock pin's signed net charge added to the DUT's. At the nominal
condition `N·T` is exactly 1.000 µs (16 × 62.5 ns), so both figures are
`(charge in pC) × VDD in V` in µW. `Q_clk` is the signed net charge
(`-∫ i(vclk) dt` over 16 whole cycles) that the ideal `vclk` source delivers
through the clock input. The deltas below are exact arithmetic on the
committed measurements, not an estimate.

**What this is NOT.** The gate capacitance on the clock pin charges on each
rising edge and returns that charge on each falling edge, so over whole cycles
the signed net charge nearly cancels. A conventional CMOS clock driver
nevertheless draws about `C·VDD²` per cycle from *its* supply. The signed pin
charge therefore neither measures the energy delivered at the ideal clock port
(that is `-∫ v(clk)·i(vclk) dt`) nor the supply cost of any specified clock
driver (that is the integral of that driver's rail power). **The deltas below
are a diagnostic of the signed pin-charge integral only. They are not a bound
on, or an estimate of, the clock-driver cost a consumer pays**, and this report
makes no claim about that cost. Measuring it needs a specified driver or the
`v·i` port integral and is left open.

**Reading.** Folding the signed pin charge into the row's charge integral moves
the figure by at most **+0.1254 µW (+0.0753 %)** on the schematic grid
(`sf_27c_3.63v`) and **+0.0640 µW (+0.0318 %)** on the extracted grid
(`fs_125c_3.63v`). At the binding corner (`ff_125c_3.63v` on both DUTs) the
changes are +0.028 µW (schematic) and +0.045 µW (extracted). The binding corner
is the same with or without the pin charge. These figures say the signed pin
charge is small; they do not say the clock costs ≤ 0.08 % of the row.


## Schematic DUT — record [`20261115-075832478887-79abbcc`](records/20261115-075832478887-79abbcc.json)

Source: the 45-corner schematic campaign (issue #373), `citable: true`, 45 of 45 points; content hash (sha256, `20261115-075832478887-79abbcc.json`): `b33962e622ddc9df37679e8baa7f8cfbdcebbdd1ec92a6cc052042a5bab10ced`.


| corner | `q_win_pc` [pC] | `q_clk_pc` [pC] | `p_avg_uw` (pin charge outside, committed) | `p_avg_uw` (pin charge inside, computed) | delta [µW] | delta [%] |
|---|---:|---:|---:|---:|---:|---:|
| `ff_-40c_2.97v` | 42.3656 | 0.012203 | 125.826 | 125.862 | +0.0362 | +0.0288 |
| `ff_-40c_3.30v` | 44.2493 | 0.006337 | 146.023 | 146.044 | +0.0209 | +0.0143 |
| `ff_-40c_3.63v` | 46.2252 | 0.013828 | 167.797 | 167.848 | +0.0502 | +0.0299 |
| `ff_125c_2.97v` | 43.8336 | 0.000921 | 130.186 | 130.189 | +0.0027 | +0.0021 |
| `ff_125c_3.30v` | 45.9187 | 0.006192 | 151.532 | 151.552 | +0.0204 | +0.0135 |
| `ff_125c_3.63v` | 48.0679 | 0.007651 | 174.487 | 174.514 | +0.0278 | +0.0159 |
| `ff_27c_2.97v` | 42.9415 | 0.005629 | 127.536 | 127.553 | +0.0167 | +0.0131 |
| `ff_27c_3.30v` | 44.9114 | 0.008080 | 148.208 | 148.234 | +0.0267 | +0.0180 |
| `ff_27c_3.63v` | 46.9646 | 0.006991 | 170.481 | 170.507 | +0.0254 | +0.0149 |
| `fs_-40c_2.97v` | 41.5652 | 0.001698 | 123.449 | 123.454 | +0.0050 | +0.0041 |
| `fs_-40c_3.30v` | 43.3360 | 0.001228 | 143.009 | 143.013 | +0.0041 | +0.0028 |
| `fs_-40c_3.63v` | 45.1567 | 0.009845 | 163.919 | 163.955 | +0.0357 | +0.0218 |
| `fs_125c_2.97v` | 42.8367 | 0.009318 | 127.225 | 127.253 | +0.0277 | +0.0218 |
| `fs_125c_3.30v` | 44.7836 | 0.014942 | 147.786 | 147.835 | +0.0493 | +0.0334 |
| `fs_125c_3.63v` | 46.7996 | 0.017293 | 169.883 | 169.945 | +0.0628 | +0.0370 |
| `fs_27c_2.97v` | 42.0822 | 0.010257 | 124.984 | 125.015 | +0.0305 | +0.0244 |
| `fs_27c_3.30v` | 43.9117 | 0.008385 | 144.909 | 144.936 | +0.0277 | +0.0191 |
| `fs_27c_3.63v` | 45.8231 | 0.007636 | 166.338 | 166.366 | +0.0277 | +0.0167 |
| `sf_-40c_2.97v` | 41.4961 | 0.014435 | 123.243 | 123.286 | +0.0429 | +0.0348 |
| `sf_-40c_3.30v` | 43.3071 | 0.010630 | 142.914 | 142.949 | +0.0351 | +0.0245 |
| `sf_-40c_3.63v` | 45.1638 | 0.010416 | 163.945 | 163.982 | +0.0378 | +0.0231 |
| `sf_125c_2.97v` | 42.8232 | 0.008519 | 127.185 | 127.210 | +0.0253 | +0.0199 |
| `sf_125c_3.30v` | 44.8077 | 0.003197 | 147.865 | 147.876 | +0.0106 | +0.0071 |
| `sf_125c_3.63v` | 46.8711 | 0.010107 | 170.142 | 170.179 | +0.0367 | +0.0216 |
| `sf_27c_2.97v` | 42.0565 | 0.008366 | 124.908 | 124.933 | +0.0248 | +0.0199 |
| `sf_27c_3.30v` | 43.9047 | 0.011119 | 144.885 | 144.922 | +0.0367 | +0.0253 |
| `sf_27c_3.63v` | 45.8492 | 0.034537 | 166.433 | 166.558 | +0.1254 | +0.0753 |
| `ss_-40c_2.97v` | 40.7299 | 0.000520 | 120.968 | 120.969 | +0.0015 | +0.0013 |
| `ss_-40c_3.30v` | 42.5155 | 0.007846 | 140.301 | 140.327 | +0.0259 | +0.0185 |
| `ss_-40c_3.63v` | 44.3292 | 0.000471 | 160.915 | 160.917 | +0.0017 | +0.0011 |
| `ss_125c_2.97v` | 42.0566 | 0.007867 | 124.908 | 124.931 | +0.0234 | +0.0187 |
| `ss_125c_3.30v` | 43.9099 | 0.003087 | 144.903 | 144.913 | +0.0102 | +0.0070 |
| `ss_125c_3.63v` | 45.8330 | 0.019162 | 166.374 | 166.444 | +0.0696 | +0.0418 |
| `ss_27c_2.97v` | 41.3018 | 0.001909 | 122.666 | 122.672 | +0.0057 | +0.0046 |
| `ss_27c_3.30v` | 43.1252 | 0.014647 | 142.313 | 142.361 | +0.0483 | +0.0340 |
| `ss_27c_3.63v` | 44.9467 | 0.004803 | 163.156 | 163.174 | +0.0174 | +0.0107 |
| `tt_-40c_2.97v` | 41.5242 | 0.009822 | 123.327 | 123.356 | +0.0292 | +0.0237 |
| `tt_-40c_3.30v` | 43.3179 | 0.005287 | 142.949 | 142.967 | +0.0174 | +0.0122 |
| `tt_-40c_3.63v` | 45.1514 | 0.007598 | 163.900 | 163.927 | +0.0276 | +0.0168 |
| `tt_125c_2.97v` | 42.8221 | 0.006658 | 127.182 | 127.202 | +0.0198 | +0.0155 |
| `tt_125c_3.30v` | 44.7877 | 0.004761 | 147.799 | 147.815 | +0.0157 | +0.0106 |
| `tt_125c_3.63v` | 46.8289 | 0.010171 | 169.989 | 170.026 | +0.0369 | +0.0217 |
| `tt_27c_2.97v` | 42.0616 | 0.011477 | 124.923 | 124.957 | +0.0341 | +0.0273 |
| `tt_27c_3.30v` | 43.9052 | 0.007074 | 144.887 | 144.910 | +0.0233 | +0.0161 |
| `tt_27c_3.63v` | 45.8287 | 0.014796 | 166.358 | 166.412 | +0.0537 | +0.0323 |

- **Maximum over corners, pin charge inside the row**: **174.514 µW @ `ff_125c_3.63v`** (committed outside-boundary figure 174.487 µW at the same corner; +0.028 µW).
- **Largest absolute and relative move**: +0.1254 µW, +0.0753 % @ `sf_27c_3.63v`; the boundary does not change which corner binds (`ff_125c_3.63v` on both DUTs, either side of the boundary).

## Extracted DUT — record [`20261116-203811672880-81544ac`](records/20261116-203811672880-81544ac.json)

Source: the 45-corner post-layout extracted campaign, citable DR-0008 re-mint (issue #398), `citable: true`, 45 of 45 points; content hash (sha256, `20261116-203811672880-81544ac.json`): `cdc0590763c8a56017d6868eebbdd72a2062fdec085eca41c7420317e71e7d38`.


| corner | `q_win_pc` [pC] | `q_clk_pc` [pC] | `p_avg_uw` (pin charge outside, committed) | `p_avg_uw` (pin charge inside, computed) | delta [µW] | delta [%] |
|---|---:|---:|---:|---:|---:|---:|
| `ff_-40c_2.97v` | 48.6138 | 0.009360 | 144.383 | 144.411 | +0.0278 | +0.0193 |
| `ff_-40c_3.30v` | 51.4128 | 0.011824 | 169.662 | 169.701 | +0.0390 | +0.0230 |
| `ff_-40c_3.63v` | 54.3737 | 0.009522 | 197.377 | 197.411 | +0.0346 | +0.0175 |
| `ff_125c_2.97v` | 50.7528 | 0.012065 | 150.736 | 150.772 | +0.0358 | +0.0238 |
| `ff_125c_3.30v` | 53.8862 | 0.007381 | 177.825 | 177.849 | +0.0244 | +0.0137 |
| `ff_125c_3.63v` | 57.1285 | 0.012308 | 207.376 | 207.421 | +0.0447 | +0.0215 |
| `ff_27c_2.97v` | 49.4560 | 0.011972 | 146.884 | 146.920 | +0.0356 | +0.0242 |
| `ff_27c_3.30v` | 52.4051 | 0.010880 | 172.937 | 172.973 | +0.0359 | +0.0208 |
| `ff_27c_3.63v` | 55.5023 | 0.005003 | 201.473 | 201.492 | +0.0182 | +0.0090 |
| `fs_-40c_2.97v` | 47.6379 | 0.012647 | 141.485 | 141.522 | +0.0376 | +0.0265 |
| `fs_-40c_3.30v` | 50.2575 | 0.009903 | 165.850 | 165.882 | +0.0327 | +0.0197 |
| `fs_-40c_3.63v` | 52.9851 | 0.015456 | 192.336 | 192.392 | +0.0561 | +0.0292 |
| `fs_125c_2.97v` | 49.4451 | 0.011197 | 146.852 | 146.885 | +0.0333 | +0.0226 |
| `fs_125c_3.30v` | 52.3615 | 0.010809 | 172.793 | 172.829 | +0.0357 | +0.0206 |
| `fs_125c_3.63v` | 55.4009 | 0.017641 | 201.105 | 201.169 | +0.0640 | +0.0318 |
| `fs_27c_2.97v` | 48.3718 | 0.010992 | 143.664 | 143.697 | +0.0326 | +0.0227 |
| `fs_27c_3.30v` | 51.1008 | 0.005815 | 168.633 | 168.652 | +0.0192 | +0.0114 |
| `fs_27c_3.63v` | 53.9727 | 0.010370 | 195.921 | 195.959 | +0.0376 | +0.0192 |
| `sf_-40c_2.97v` | 47.5265 | 0.003706 | 141.154 | 141.165 | +0.0110 | +0.0078 |
| `sf_-40c_3.30v` | 50.1725 | 0.010510 | 165.569 | 165.604 | +0.0347 | +0.0209 |
| `sf_-40c_3.63v` | 52.9347 | 0.011098 | 192.153 | 192.193 | +0.0403 | +0.0210 |
| `sf_125c_2.97v` | 49.3535 | 0.011664 | 146.580 | 146.615 | +0.0346 | +0.0236 |
| `sf_125c_3.30v` | 52.3081 | 0.009354 | 172.617 | 172.648 | +0.0309 | +0.0179 |
| `sf_125c_3.63v` | 55.4062 | 0.011488 | 201.125 | 201.166 | +0.0417 | +0.0207 |
| `sf_27c_2.97v` | 48.2760 | 0.004964 | 143.380 | 143.394 | +0.0147 | +0.0103 |
| `sf_27c_3.30v` | 51.0245 | 0.013421 | 168.381 | 168.425 | +0.0443 | +0.0263 |
| `sf_27c_3.63v` | 53.9404 | 0.013337 | 195.804 | 195.852 | +0.0484 | +0.0247 |
| `ss_-40c_2.97v` | 46.5155 | 0.009460 | 138.151 | 138.179 | +0.0281 | +0.0203 |
| `ss_-40c_3.30v` | 49.2738 | 0.009549 | 162.604 | 162.635 | +0.0315 | +0.0194 |
| `ss_-40c_3.63v` | 51.9153 | 0.007481 | 188.453 | 188.480 | +0.0272 | +0.0144 |
| `ss_125c_2.97v` | 48.4042 | 0.010770 | 143.760 | 143.792 | +0.0320 | +0.0222 |
| `ss_125c_3.30v` | 51.1621 | 0.009090 | 168.835 | 168.865 | +0.0300 | +0.0178 |
| `ss_125c_3.63v` | 54.0635 | 0.011886 | 196.251 | 196.294 | +0.0431 | +0.0220 |
| `ss_27c_2.97v` | 47.4157 | 0.009237 | 140.825 | 140.852 | +0.0274 | +0.0195 |
| `ss_27c_3.30v` | 50.0733 | 0.011722 | 165.242 | 165.281 | +0.0387 | +0.0234 |
| `ss_27c_3.63v` | 52.7880 | 0.011954 | 191.620 | 191.664 | +0.0434 | +0.0226 |
| `tt_-40c_2.97v` | 47.5751 | 0.010556 | 141.298 | 141.329 | +0.0314 | +0.0222 |
| `tt_-40c_3.30v` | 50.2039 | 0.011078 | 165.673 | 165.709 | +0.0366 | +0.0221 |
| `tt_-40c_3.63v` | 52.9490 | 0.010857 | 192.205 | 192.244 | +0.0394 | +0.0205 |
| `tt_125c_2.97v` | 49.3901 | 0.011416 | 146.689 | 146.723 | +0.0339 | +0.0231 |
| `tt_125c_3.30v` | 52.3238 | 0.007375 | 172.668 | 172.693 | +0.0243 | +0.0141 |
| `tt_125c_3.63v` | 55.3903 | 0.011182 | 201.067 | 201.107 | +0.0406 | +0.0202 |
| `tt_27c_2.97v` | 48.3149 | 0.003612 | 143.495 | 143.506 | +0.0107 | +0.0075 |
| `tt_27c_3.30v` | 51.0494 | 0.013698 | 168.463 | 168.508 | +0.0452 | +0.0268 |
| `tt_27c_3.63v` | 53.9454 | 0.012415 | 195.822 | 195.867 | +0.0451 | +0.0230 |

- **Maximum over corners, pin charge inside the row**: **207.421 µW @ `ff_125c_3.63v`** (committed outside-boundary figure 207.376 µW at the same corner; +0.045 µW).
- **Largest absolute and relative move**: +0.0640 µW, +0.0318 % @ `fs_125c_3.63v`; the boundary does not change which corner binds (`ff_125c_3.63v` on both DUTs, either side of the boundary).

## The boundary at the item-4 sensitivity conditions (issue #452, 2026-11-21)

DR-0006's item 4 also asks that the boundary be visible where the condition
itself moves — at 100 fF loads and at 32 MHz. The ten SENSITIVITY-ONLY
records listed in the bench README (five conditions × two DUTs, each at
`tt_27c_3.30v` / `ff_125c_3.63v` / `ss_125c_2.97v`) each carry their own
`q_clk_pc` column, so the same fold-in arithmetic extends to them with no new
simulation: `p_avg_uw(inside) = p_avg_uw + VDD · q_clk_pc / (N·T)` with
`N·T` = 1.000 µs at the 16 MHz conditions and 0.500 µs at 32 MHz.

| condition | DUT | corner | `q_clk_pc` [pC] | `p_avg_uw` (outside, committed) | `p_avg_uw` (inside, computed) | delta [µW] | delta [%] |
|---|---|---|---:|---:|---:|---:|---:|
| `c_load` = 100 fF | schematic | `tt_27c_3.30v` | 0.006366 | 159.393 | 159.414 | +0.0210 | +0.0132 |
| `c_load` = 100 fF | schematic | `ff_125c_3.63v` | 0.006671 | 192.350 | 192.374 | +0.0242 | +0.0126 |
| `c_load` = 100 fF | schematic | `ss_125c_2.97v` | 0.006635 | 136.600 | 136.620 | +0.0197 | +0.0144 |
| `c_load` = 100 fF | extracted | `tt_27c_3.30v` | 0.012403 | 182.858 | 182.899 | +0.0409 | +0.0224 |
| `c_load` = 100 fF | extracted | `ff_125c_3.63v` | 0.012446 | 225.079 | 225.124 | +0.0452 | +0.0201 |
| `c_load` = 100 fF | extracted | `ss_125c_2.97v` | 0.010760 | 155.367 | 155.399 | +0.0320 | +0.0206 |
| `v_od` = 1 mV | schematic | `tt_27c_3.30v` | 0.006712 | 150.357 | 150.379 | +0.0221 | +0.0147 |
| `v_od` = 1 mV | schematic | `ff_125c_3.63v` | -0.001884 | 184.312 | 184.306 | -0.0068 | -0.0037 |
| `v_od` = 1 mV | schematic | `ss_125c_2.97v` | 0.010517 | 128.647 | 128.678 | +0.0312 | +0.0243 |
| `v_od` = 1 mV | extracted | `tt_27c_3.30v` | 0.012791 | 177.277 | 177.320 | +0.0422 | +0.0238 |
| `v_od` = 1 mV | extracted | `ff_125c_3.63v` | 0.013726 | 223.092 | 223.142 | +0.0498 | +0.0223 |
| `v_od` = 1 mV | extracted | `ss_125c_2.97v` | 0.011218 | 149.904 | 149.938 | +0.0333 | +0.0222 |
| `v_od` = 50 mV | schematic | `tt_27c_3.30v` | 0.004911 | 142.938 | 142.954 | +0.0162 | +0.0113 |
| `v_od` = 50 mV | schematic | `ff_125c_3.63v` | -0.003171 | 169.289 | 169.278 | -0.0115 | -0.0068 |
| `v_od` = 50 mV | schematic | `ss_125c_2.97v` | 0.013082 | 123.868 | 123.907 | +0.0389 | +0.0314 |
| `v_od` = 50 mV | extracted | `tt_27c_3.30v` | 0.013228 | 164.694 | 164.738 | +0.0437 | +0.0265 |
| `v_od` = 50 mV | extracted | `ff_125c_3.63v` | 0.011721 | 198.917 | 198.959 | +0.0425 | +0.0214 |
| `v_od` = 50 mV | extracted | `ss_125c_2.97v` | 0.013189 | 141.166 | 141.206 | +0.0392 | +0.0277 |
| `c_load` = 0 fF | schematic | `tt_27c_3.30v` | 0.006395 | 141.133 | 141.154 | +0.0211 | +0.0150 |
| `c_load` = 0 fF | schematic | `ff_125c_3.63v` | 0.007251 | 169.894 | 169.920 | +0.0263 | +0.0155 |
| `c_load` = 0 fF | schematic | `ss_125c_2.97v` | 0.008481 | 121.875 | 121.901 | +0.0252 | +0.0207 |
| `c_load` = 0 fF | extracted | `tt_27c_3.30v` | 0.015175 | 164.797 | 164.847 | +0.0501 | +0.0304 |
| `c_load` = 0 fF | extracted | `ff_125c_3.63v` | 0.014756 | 202.882 | 202.935 | +0.0536 | +0.0264 |
| `c_load` = 0 fF | extracted | `ss_125c_2.97v` | 0.010403 | 140.802 | 140.833 | +0.0309 | +0.0219 |
| `t_per` = 31.25 ns | schematic | `tt_27c_3.30v` | 0.004482 | 190.486 | 190.515 | +0.0296 | +0.0155 |
| `t_per` = 31.25 ns | schematic | `ff_125c_3.63v` | 0.007651 | 239.876 | 239.932 | +0.0555 | +0.0232 |
| `t_per` = 31.25 ns | schematic | `ss_125c_2.97v` | 0.006568 | 161.070 | 161.109 | +0.0390 | +0.0242 |
| `t_per` = 31.25 ns | extracted | `tt_27c_3.30v` | 0.011848 | 243.073 | 243.152 | +0.0782 | +0.0322 |
| `t_per` = 31.25 ns | extracted | `ff_125c_3.63v` | 0.011499 | 311.937 | 312.021 | +0.0835 | +0.0268 |
| `t_per` = 31.25 ns | extracted | `ss_125c_2.97v` | 0.010565 | 203.235 | 203.298 | +0.0628 | +0.0309 |

Reading: at the 16 MHz sensitivity conditions the fold-in moves the figure by
at most +0.0389 µW (schematic, `v_od` = 50 mV @ `ss_125c_2.97v`) /
+0.0536 µW (extracted, `c_load` = 0 fF @ `ff_125c_3.63v`); at 32 MHz, where
the same pin charge is spread over a 0.500 µs window, by at most +0.0555 µW
(schematic) / +0.0835 µW (extracted), both at `ff_125c_3.63v`. Two
`q_clk_pc` values are small and negative (schematic `v_od` = 1/50 mV @
`ff_125c_3.63v`) — the signed integral crossing zero, not an anomaly. The
boundary does not change which corner binds in any condition, and — the same
caveat as above — none of these numbers bounds the clock-driver supply cost,
which stays open.
