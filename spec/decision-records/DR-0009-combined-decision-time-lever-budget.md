# DR-0009: Pre-cascode decision-time budget for latch sizing and extracted RC

- **Status**: proposed
- **Date**: 2026-11-23
- **Decided by**: Builder for #453 (no ratification claim)
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: DR-0002, DR-0004, DR-0006, DR-0007, #112, #125, #202, #229, #264, #323, #453;
  `layout/pex/artifacts/design-levers-combined/PLAN.md`;
  `layout/pex/artifacts/design-levers-combined/20261123-192546-559b686/`

## Context

T1 item 7 (*Post-layout verification*) grades `unmet / check_failed` on
[`layout/pex/comparator.pex.json`](../../layout/pex/comparator.pex.json): 668 of
675 delta rows pass and 7 miss DR-0002's ratified `td_od50_ns <= 1.5 ns`
(worst `ss_125c_2.97v` at `2.02956 ns`, schematic `1.23747 ns`). Neither axis
closes `ss_125c_2.97v` alone on the pre-cascode extracted netlist:

- Global parasitic scaling alone (#264, `20261010-233444-c49a3f1/`): scaling all
  20 extracted ground-C cards to `f_c = 0.25` and all 114 series-R legs to
  `f_r = 0.50` leaves `ss_125c_2.97v` at `1.5062 ns` (`6.2 ps` over `1.5 ns`).
- Single device-width levers alone (#323 / DR-0007, `20261017-192854-fa963e7/`):
  `pair-x1.5` reaches `1.9389 ns` (`-90.7 ps`) and `tail-x1.5` reaches
  `1.9847 ns` (`-44.9 ps`).

This record executes the [committed staged plan](../../layout/pex/artifacts/design-levers-combined/PLAN.md)
(declared campaign cap **323** batch requests) on the **pre-cascode** extracted
comparator netlist (`layout/pex/artifacts/preamp-noise/comparator.dut-layout.cir`,
sha256 `a7ca3c00ea4db8a2b00cad69f2edc2d9320738499049cfa9c7faec517b7b5f45`)
via the Spot batch fleet (`klayout-tools==0.9.2`, tag `v0.9.2`, commit
`046ba74652fc096bd97071fc3237f7159dd40183`, `klt sim --backend batch --wait-for-capacity 600`).
An earlier attempt (`20261121-011230-45f12a5/`) launched zero fleet jobs because
its worker lacked the `batch-runner-submit` profile; that directory is preserved
unchanged under the append-only evidence rule. The qualified campaign in
[`layout/pex/artifacts/design-levers-combined/20261123-192546-559b686/`](../../layout/pex/artifacts/design-levers-combined/20261123-192546-559b686/timing.json)
spent **143 fleet jobs** (`5` controls + `63` primary + `54` remaining-five +
`21` kickback/offset, within the `323`-request cap; the conditional `21`-request
`pair-x2` stage did not run because six primary cells passed both initial
corners).

## Control qualification

Every extracted variant was centred independently on its own offset-probe trip
point; the schematic control used `0 V` centring as cited. All four control
decision times reproduced [`comparator.pex.json`](../../layout/pex/comparator.pex.json)
within `CONTROL_TOL_NS = ±0.0001 ns`:

| Control at 125 °C, 2.97 V | Cited `tt` (ns) | Rerun `tt` (ns) | `|Δ|` (ns) | Cited `ss` (ns) | Rerun `ss` (ns) | `|Δ|` (ns) | Probed `dut_vos` (`tt` / `ss`, mV) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ctrl` (extracted, probed trip point) | 1.58774 | 1.58774 | 0.0 | 2.02956 | 2.02956 | 0.0 | −8.9074 / −5.1865 (cited −8.9074 / −5.1865) |
| `sch` (schematic, centred at 0 V) | 0.986719 | 0.986719 | 0.0 | 1.23747 | 1.23747 | 0.0 | 0 / 0 (by convention) |

## Decision

**Proposed, not ratified. No schematic, layout, or cited signoff artifact is
changed, and T1 item 7 remains `unmet / check_failed`.**

1. **Combined existence and global `(f_c, f_r)` boundary.** Six of the 21
   primary combinations clear `td_od50_ns <= 1.5 ns` at both `tt_125c_2.97v`
   and `ss_125c_2.97v`, and **all six also pass all five remaining previously
   failing corners** (`7/7` corners `decision_ok = true`, zero decision-check
   failures). Every passing cell has `f_c = 0.25` (`(0.25, 1.0)` and
   `(0.25, 0.5)` across `tail-x1.5`, `pair-x1.5`, and `pair+tail`); no tested
   lever passes at `f_c >= 0.50` even with `f_r = 0.50` (fastest `f_c = 0.50`
   point is `pair+tail-cgr-0500-0500` at `1.56423 ns`, `64.23 ps` over `1.5 ns`).
   Because `(0.25, 1.0)` dominates `(0.25, 0.5)` componentwise in retained
   parasitics, there are **no incomparable passing `(f_c, f_r)` residue pairs**:
   the largest passing global parasitic residue on the measured grid is
   **`(f_c, f_r) = (0.25, 1.0)`** (`<= 25 %` of all 20 extracted ground-C cards,
   `<= 100 %` of all 114 series-R legs). No #229-restricted per-net variant was
   measured here, so **no per-net budget split is derived**.
2. **Recommended pre-cascode baseline combination.** Applying `PLAN.md`'s
   selection rule (smallest added total drawn `W` among 7-corner passers, then
   largest retained `C` and `R`):
   - `tail-x1.5` (`M$12`: `16 -> 24 µm`) and `pair-x1.5` (`M$9, M$13`:
     `8 -> 12 µm` each) tie for the smallest added total drawn width at
     **`+8.0 µm`** (`pair+tail` adds `+16.0 µm`).
   - **`tail-x1.5` at `(f_c, f_r) = (0.25, 1.0)` (`tail-x1.5-cgr-0250-1000`)**
     is selected as the pre-cascode reference budget: `ss_125c_2.97v`
     `td_od50_ns = 1.49201 ns` (`+7.99 ps` margin to `1.5 ns`; `tt_125c_2.97v`
     `1.18814 ns`), **independent of the DR-0004 input cascode**, and lowest
     post-layout kickback among all six passing candidates (`5.3125 mV` `tt`,
     `4.7365 mV` `ss`, vs `6.2932 / 5.6321 mV` for `pair-x1.5-cgr-0250-1000`).
   - Because `+7.99 ps` at `ss_125c_2.97v` omits the widened tail's own routing
     parasitics (see optimism note below), halving series resistance as well
     (`tail-x1.5-cgr-0250-0500`, `(0.25, 0.5)`) widens slow-corner margin to
     `+25.30 ps` (`1.47470 ns`), while `pair-x1.5-cgr-0250-1000` (`+8.0 µm`
     added `W`, `1.47165 ns`, `+28.35 ps`) and `pair+tail-cgr-0250-1000`
     (`+16.0 µm` added `W`, `1.43845 ns`, `+61.55 ps`) remain provisional until
     re-measured on the post-#112 cascode layout.

### Primary 21-cell ranking (sorted by `ss_125c_2.97v` `td_od50_ns`)

| Rank | Variant | Lever (`ΔW` total) | `(f_c, f_r)` | Cascode-indep.? | `tt_125c_2.97v` `td_od50` (ns) | `tt` margin (ps) | `ss_125c_2.97v` `td_od50` (ns) | `ss` margin (ps) | `Δdut_vos` vs `ctrl` (`tt` / `ss`, mV) | 2-corner 1.5 ns |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `pair+tail-cgr-0250-0500` | `pair+tail` (+16 µm) | (0.25, 0.5) | no | 1.14150 | +358.50 | 1.42019 | +79.81 | +5.88 / +3.39 | **PASS** |
| 2 | `pair+tail-cgr-0250-1000` | `pair+tail` (+16 µm) | (0.25, 1.0) | no | 1.15735 | +342.65 | 1.43845 | +61.55 | +5.58 / +3.18 | **PASS** |
| 3 | `pair-x1.5-cgr-0250-0500` | `pair-x1.5` (+8 µm) | (0.25, 0.5) | no | 1.16941 | +330.59 | 1.45500 | +45.00 | +6.12 / +3.51 | **PASS** |
| 4 | `pair-x1.5-cgr-0250-1000` | `pair-x1.5` (+8 µm) | (0.25, 1.0) | no | 1.18376 | +316.24 | 1.47165 | +28.35 | +5.82 / +3.30 | **PASS** |
| 5 | `tail-x1.5-cgr-0250-0500` | `tail-x1.5` (+8 µm) | (0.25, 0.5) | yes | 1.17307 | +326.93 | 1.47470 | +25.30 | +5.58 / +3.24 | **PASS** |
| 6 | `tail-x1.5-cgr-0250-1000` | `tail-x1.5` (+8 µm) | (0.25, 1.0) | yes | 1.18814 | +311.86 | 1.49201 | +7.99 | +5.31 / +3.03 | **PASS** |
| 7 | `pair+tail-cgr-0500-0500` | `pair+tail` (+16 µm) | (0.50, 0.5) | no | 1.25332 | +246.68 | 1.56423 | −64.23 | +3.72 / +2.13 | fail |
| 8 | `pair+tail-cgr-0500-1000` | `pair+tail` (+16 µm) | (0.50, 1.0) | no | 1.27029 | +229.71 | 1.58410 | −84.10 | +3.39 / +1.92 | fail |
| 9 | `pair-x1.5-cgr-0500-0500` | `pair-x1.5` (+8 µm) | (0.50, 0.5) | no | 1.28413 | +215.87 | 1.60351 | −103.51 | +4.14 / +2.34 | fail |
| 10 | `pair-x1.5-cgr-0500-1000` | `pair-x1.5` (+8 µm) | (0.50, 1.0) | no | 1.29964 | +200.36 | 1.62174 | −121.74 | +3.84 / +2.13 | fail |
| 11 | `tail-x1.5-cgr-0500-0500` | `tail-x1.5` (+8 µm) | (0.50, 0.5) | yes | 1.29205 | +207.95 | 1.63105 | −131.05 | +3.18 / +1.89 | fail |
| 12 | `tail-x1.5-cgr-0500-1000` | `tail-x1.5` (+8 µm) | (0.50, 1.0) | yes | 1.30832 | +191.68 | 1.65002 | −150.02 | +2.91 / +1.68 | fail |
| 13 | `pair+tail-cgr-0750-0500` | `pair+tail` (+16 µm) | (0.75, 0.5) | no | 1.36707 | +132.93 | 1.71318 | −213.18 | +1.92 / +1.11 | fail |
| 14 | `pair+tail-cgr-0750-1000` | `pair+tail` (+16 µm) | (0.75, 1.0) | no | 1.38522 | +114.78 | 1.73495 | −234.95 | +1.59 / +0.87 | fail |
| 15 | `pair-x1.5-cgr-0750-0500` | `pair-x1.5` (+8 µm) | (0.75, 0.5) | no | 1.40057 | +99.43 | 1.75759 | −257.59 | +2.49 / +1.41 | fail |
| 16 | `pair-x1.5-cgr-0750-1000` | `pair-x1.5` (+8 µm) | (0.75, 1.0) | no | 1.41733 | +82.67 | 1.77779 | −277.79 | +2.19 / +1.17 | fail |
| 17 | `tail-x1.5-cgr-0750-0500` | `tail-x1.5` (+8 µm) | (0.75, 0.5) | yes | 1.41338 | +86.62 | 1.79374 | −293.74 | +1.23 / +0.78 | fail |
| 18 | `tail-x1.5-cgr-0750-1000` | `tail-x1.5` (+8 µm) | (0.75, 1.0) | yes | 1.43092 | +69.08 | 1.81450 | −314.50 | +0.93 / +0.57 | fail |
| 19 | `pair+tail-cgr-1000-1000` | `pair+tail` (+16 µm) | (1.00, 1.0) | no | 1.50216 | −2.16 | 1.88980 | −389.80 | +0.06 / +0.03 | fail |
| 20 | `pair-x1.5-cgr-1000-1000` | `pair-x1.5` (+8 µm) | (1.00, 1.0) | no | 1.53673 | −36.73 | 1.93892 | −438.92 | +0.81 / +0.39 | fail |
| 21 | `tail-x1.5-cgr-1000-1000` | `tail-x1.5` (+8 µm) | (1.00, 1.0) | yes | 1.55580 | −55.80 | 1.98468 | −484.68 | −0.69 / −0.33 | fail |

### Seven-corner closure of the two-corner passing candidates

All six two-corner passers were probed and measured across the remaining five
post-layout failing corners (`remaining-five/`); `ss_125c_2.97v` remains the
binding corner for every candidate:

| Candidate | `fs_125c_2.97v` (ns) | `sf_125c_2.97v` (ns) | `ss_27c_2.97v` (ns) | `ss_125c_3.30v` (ns) | `ss_125c_3.63v` (ns) | `tt_125c_2.97v` (ns) | `ss_125c_2.97v` (ns) | 7-corner status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `pair+tail-cgr-0250-0500` | 1.11067 | 1.18872 | 1.16876 | 1.23429 | 1.10825 | 1.14150 | 1.42019 | **7/7 PASS** (+79.81 ps min margin) |
| `pair+tail-cgr-0250-1000` | 1.12641 | 1.20463 | 1.18724 | 1.25090 | 1.12365 | 1.15735 | 1.43845 | **7/7 PASS** (+61.55 ps min margin) |
| `pair-x1.5-cgr-0250-0500` | 1.13703 | 1.21837 | 1.19450 | 1.26457 | 1.13487 | 1.16941 | 1.45500 | **7/7 PASS** (+45.00 ps min margin) |
| `pair-x1.5-cgr-0250-1000` | 1.15134 | 1.23275 | 1.21148 | 1.27969 | 1.14888 | 1.18376 | 1.47165 | **7/7 PASS** (+28.35 ps min margin) |
| `tail-x1.5-cgr-0250-0500` | 1.13943 | 1.22400 | 1.21430 | 1.27338 | 1.13908 | 1.17307 | 1.47470 | **7/7 PASS** (+25.30 ps min margin) |
| `tail-x1.5-cgr-0250-1000` | 1.15441 | 1.23915 | 1.23183 | 1.28917 | 1.15372 | 1.18814 | 1.49201 | **7/7 PASS** (+7.99 ps min margin) |

### Item-5 side effects and named bench gaps on passing candidates

Each passing candidate and the unmodified extracted baseline (`ctrl`) were run
through the committed two-phase extracted kickback and offset-referral bench
(`sim/comparator-kickback`, `kickback/<id>/`, 3 batch jobs per DUT at
`125 °C, 2.97 V`, `decision_checks.status = "pass"` on every DUT):

| DUT | `kick_1k_peak_mv` `tt` (mV) | `Δkick` vs `ctrl` `tt` (mV) | `kick_1k_peak_mv` `ss` (mV) | `Δkick` vs `ctrl` `ss` (mV) | Two-phase `dut_vos` `tt` / `ss` (mV) | `Δdut_vos` vs `ctrl` `tt` / `ss` (mV) | Preamp noise |
|---|---:|---:|---:|---:|---:|---:|---|
| `ctrl` (unmodified extracted) | 9.5657 | 0.0 | 10.1158 | 0.0 | −8.9174 / −5.1666 | 0.0 / 0.0 | #202 baseline (PR #346) |
| `tail-x1.5-cgr-0250-1000` | 5.3125 | −4.2532 | 4.7365 | −5.3793 | −3.6080 / −2.1375 | +5.3094 / +3.0292 | Named bench gap (#202 pin) |
| `tail-x1.5-cgr-0250-0500` | 5.3540 | −4.2117 | 4.7764 | −5.3394 | −3.3081 / −1.9275 | +5.6093 / +3.2392 | Named bench gap (#202 pin) |
| `pair-x1.5-cgr-0250-1000` | 6.2932 | −3.2725 | 5.6321 | −4.4837 | −3.0681 / −1.8975 | +5.8493 / +3.2692 | Named bench gap (#202 pin) |
| `pair-x1.5-cgr-0250-0500` | 6.3335 | −3.2322 | 5.6744 | −4.4414 | −2.7681 / −1.6576 | +6.1493 / +3.5090 | Named bench gap (#202 pin) |
| `pair+tail-cgr-0250-1000` | 6.1374 | −3.4283 | 5.5440 | −4.5718 | −3.3380 / −2.0175 | +5.5794 / +3.1491 | Named bench gap (#202 pin) |
| `pair+tail-cgr-0250-0500` | 6.1786 | −3.3871 | 5.5869 | −4.5290 | −3.0081 / −1.7777 | +5.9092 / +3.3890 | Named bench gap (#202 pin) |

- **Kickback (`kick_1k_peak_mv`, DR-0002 target `<= 5.0 mV`):** Scaling
  extracted ground capacitance to `25 %` cuts post-layout kickback roughly in
  half relative to `ctrl` (`9.57 / 10.12 mV`), but **no candidate clears the
  `5.0 mV` bound at `tt_125c_2.97v` on the pre-cascode netlist** (`5.31..6.33 mV`),
  confirming that kickback closure still requires the DR-0004 input cascode
  (#112). Widening the latch input pair (`pair-x1.5`, `pair+tail`) raises peak
  kickback by `+0.81..+0.98 mV` relative to `tail-x1.5` at the same `(f_c, f_r)`
  by enlarging gate-overlap coupling onto `aop/aon`.
- **Offset (`dut_vos_v`):** Both the regeneration probe and the two-phase
  kickback probe measure **deterministic systematic offset** on the extracted
  netlist. Reducing ground-C to `f_c = 0.25` shrinks asymmetric extracted C
  imbalance, moving `|dut_vos_v|` from `8.92 / 5.17 mV` (`ctrl`) down to
  `2.77..3.61 / 1.66..2.14 mV` (`tt / ss`). Because `dut_vos_v` is a
  deterministic layout-systematic offset rather than a 3σ random-mismatch
  sigma, it is a different quantity from DR-0002's ratified offset row
  (`<= 15 mV 3σ` target / `<= 8 mV 3σ` stretch, whose basis disclaims
  extracted-layout and layout-systematic offset) and is not scored against it.
  **Random mismatch offset (`sigma(Vos)`) is a separate bench gap** on
  transformed extracted netlists: only an unrecorded feasibility probe
  (`sim/comparator-offset-tran-extracted-feasibility`) exists for extracted
  transient mismatch.
- **Extracted preamp noise (named bench gap):** `layout/pex/preamp_noise_pvt.py`
  pins both schematic and extracted DUT hashes to the #202 extraction and
  refuses any widened/scaled netlist with `SOURCE_IDENTITY_MISMATCH`. Per #453
  scope, no new extracted-noise bench was built here.
- **Average power:** Unscored until DR-0006 is ratified (#125); `tail-x1.5` and
  `pair+tail` increase dynamic latch tail charge per comparison.

## Consequences for the next layout and post-#112 re-measurement

All measurements in this record were taken on the **pre-cascode** extracted
netlist (`comparator-dr0001-layout` / #202 extraction).

| Lever | Drawn `W` change | Interaction with DR-0004 input cascode and post-#112 status |
|---|---|---|
| `tail-x1.5` | `M$12`: `16 -> 24 µm` (`+8 µm`) | **Independent of the DR-0004 input cascode** (acts on the clocked latch tail, downstream of `aop/aon`). Does not load `aop/aon`, though layout floorplan changes in #112 still require full post-layout re-extraction. |
| `pair-x1.5` | `M$9, M$13`: `8 -> 12 µm` each (`+8 µm`) | **Not independent — must be re-measured after #112.** Directly loads `aop/aon` and increases kickback coupling into the preamp output nodes that the DR-0004 cascode shields. |
| `pair+tail` | `M$12`: `16 -> 24 µm`; `M$9, M$13`: `8 -> 12 µm` (`+16 µm`) | **Not independent — must be re-measured after #112** for the `pair` component's load and kickback on `aop/aon`. |
| Conditional `pair-x2` (not run) | `M$9, M$13`: `8 -> 16 µm` each (`+16 µm`) | Gated off by `PLAN.md` because six primary cells passed; would also load `aop/aon` and require post-#112 re-measurement. |

- **Wiring-parasitic optimism:** `scale_devices` scales MOSFET `W`, `AS`/`AD`,
  and `PS`/`PD` only; it adds no interconnect resistance or ground/coupling
  capacitance for wider fingers or longer local routing. Every upsized timing
  figure is therefore **optimistic on wiring load** until layout re-extraction
  (especially `tail-x1.5-cgr-0250-1000`'s `+7.99 ps` margin).
- **Severity of the global `f_c <= 0.25` budget:** Even `pair+tail` (`+16 µm`)
  misses `1.5 ns` by `64.2 ps` at `f_c = 0.50, f_r = 0.50`. Across the three
  `1.5x` levers (`tail-x1.5` to `pair+tail`), device widening reduces
  `ss_125c_2.97v` by `44.9..139.8 ps` relative to `ctrl` (`2.02956 ns`) at
  `(1.0, 1.0)` and by `31.5..86.0 ps` relative to #264's `1.5062 ns` baseline
  at `(0.25, 0.5)` — enough to turn #264's `1.5062 ns` near-miss into
  a pass at `f_c = 0.25`, but not enough to lift the global capacitance ceiling
  to `f_c = 0.50`. Realizing `<= 25 %` of current global ground-C across all 20
  nets in layout is severe; after #112 lands, per-net attribution on the
  cascode layout (#229's four dominant nets vs inactive/rail ground C) should
  establish whether compacting the high-leverage internal nets achieves the same
  delay reduction without cutting total block ground-C to `25 %`.

## Alternatives considered

- **Arithmetic superposition of DR-0007 and #264:** At `(0.25, 0.5)`, DR-0007's
  `pair+tail` single-lever sum (`-135.6 ps` at `(1, 1)`) applied naively to
  #264's `1.5062 ns` would predict `1.371 ns`, overstating the measured
  `1.42019 ns` improvement by `49.6 ps` because parasitic scaling and device
  widening compress the same RC-dominated regeneration transient. Direct
  combined simulation avoids that error.
- **Triggering `pair-x2` (`LARGER_PAIR`):** Not run per `PLAN.md` because the
  primary grid already produced six 7-corner passers; widening the latch pair to
  `2x` would further load `aop/aon` and worsen pre-cascode kickback.
- **Building a custom transformed-DUT preamp-noise or extracted MC-offset bench:**
  Out of scope for #453; both gaps are recorded explicitly above.
- **Relaxing DR-0002's `1.5 ns` decision-time bound:** Prohibited by repository
  policy.

## Spec lines affected

- `README.md#target-specification-ratified-via-dr-0002` — `td_od50_ns <= 1.5 ns`
  and `kick_1k_peak_mv <= 5.0 mV` rows — measured against, not modified.
- `signoff/signoff-report.json` — unchanged; T1 item 7 remains
  `unmet / check_failed` on the cited `layout/pex/comparator.pex.json`.
