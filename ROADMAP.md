# gf180-comparator roadmap

A dynamic latched comparator (static differential preamplifier into a StrongARM
latch) on the open GF180MCU PDK, built to show a fully evidenced analog block
and to surface klayout-tools gaps along the way.

Status as of 2026-11-13, `main` @ `c27e451`.

The verdict of record is [`signoff/signoff-report.json`](signoff/signoff-report.json),
per-row results are in [`spec/evidence-ledger.md`](spec/evidence-ledger.md) and the
label queue is [`WORK_PLAN.md`](WORK_PLAN.md); where they disagree with this file, they win.

## Where it stands

The block is **below T1: 9 of 11 T1 items graded `met`** by the pinned grader
(`klayout-tools==0.8.0`, report `tier: null`).

| T1 item | Grade | Evidence |
|---|---|---|
| 1 Design sources | met | `signoff/envelopes/item-1.json` (attested, PR #334; re-attested PR #350) |
| 2 Layout | met | `layout/lvs/comparator.extract.json` |
| 3 DRC clean | met | `layout/drc/comparator.drc.json` (coverage gaps listed in `signoff/README.md`) |
| 4 LVS clean | met | `layout/lvs/comparator.lvs.json` |
| 5 Full corner verification vs ratified spec | **unmet**, `check_failed` | cited corner matrix fails the kickback bound; average power not scored (clock rate TBD) |
| 6 Monte Carlo evidence | met | offset row, N = 200 per corner, 45 corners |
| 7 Post-layout verification | **unmet**, `check_failed` | `layout/pex/comparator.pex.json`: 7 of 675 delta rows miss the 1.5 ns decision-time target |
| 8 Characterization report | met | `measurements/characterization-report.item8.json` |
| 9 Testbenches shipped | met | `signoff/envelopes/item-9.json` (attested from `selftest.yml`, PR #343) |
| 10 Repo hygiene | met | `signoff/envelopes/item-10.json` |
| 11 Power delivery (structural) | met | `layout/erc/comparator.erc.json` |

Against the target table ratified by DR-0002 (bounds unchanged since):

- **Offset** and **input-referred noise** meet target and stretch at all 45
  corners. A paired extracted/schematic preamp noise campaign is also complete
  at 45/45 on both legs (PR #346).
- **Decision time** meets the target on the schematic at 45/45 and misses it at
  7 of 45 post-layout corners (worst 2.034 ns against 1.5 ns).
- **Kickback** misses the 5 mV target at every post-layout corner
  (8.49 to 14.58 mV).
- **Supply / power**: static power meets target and stretch; the average-power
  bound is unscored because the table's clock rate is still TBD.

Decision records: DR-0002 is ratified. DR-0001 (topology), DR-0003 (claim
policy for items 1, 9, 10), DR-0004 (input cascode), DR-0005 (metastability
row), DR-0006 (average-power condition, 16 MHz) and DR-0007 (decision-time
levers, a negative result) all read `Status: proposed`. Both unmet items need
a design change that sits in a proposed record, which is why every open issue
carries `loom:blocked`.

## Now

Startable today without a ratification. None has an issue yet.

1. **Bring `signoff/README.md` back in line with the graded report.** Its
   "Current verdict" list and the "unmet — item 1" and "unmet — item 10"
   sections still say items 1, 9 and 10 are `no_evidence`, while the report
   grades them `met` and the same file's attestation section says so too.
   Done when the verdict list and per-item headings match
   `signoff-report.json` and `./scripts/run-pdk-free-tests.sh` passes.
   Blocked by: nothing.
2. **Complete the 45-corner noise grid for the DR-0004 cascode experiment.**
   DR-0004 records noise at the nominal point only, because the batch runner
   then had no noise analysis (klayout-tools#2894); PR #346 has since run a
   45-point noise campaign on the runner. Done when a
   `sim/comparator-preamp-noise/records/` entry for DUT
   `comparator-dr0004-cascode-exp` covers 45/45 corners and DR-0004's "Not run"
   note and noise row quote it. Blocked by: nothing; this is the evidence gap
   option 2 of the #112 decision names.
3. **Add an unscored periodic-clock bench for DR-0006's validation items.**
   DR-0006 lists what must be measured before it can be ratified: reset
   completion and supply charge per cycle under the proposed 16 MHz stimulus.
   No bench produces either. Done when a bench deck, its `tb.json`, PDK-free
   tests and one nominal-point schematic record are committed, marked unscored,
   with the README bench count and the item-10 attestation refreshed.
   Blocked by: nothing; scoring stays out until DR-0006 is ratified (#125).

## Next

- **Layout, DRC, LVS, extraction and post-layout campaign for the cascode
  netlist** (#112). Done when `layout/gen_comparator.py` generates the cascode
  devices, the DRC/LVS/extract envelopes are re-pinned and a 45-point
  post-layout kickback and regeneration record exists. Blocked by: DR-0004
  ratification.
- **Combined decision-time lever, re-measured on the cascode layout.** DR-0007
  recommends the input-pair lever together with the parasitic reduction the
  combined-budget study (#264) found necessary; the pair-plus-tail combination
  was never run. Done when a proposed record ranks the combination at
  `ss_125c_2.97v` and `tt_125c_2.97v` with source records. Blocked by: #112.
  Needs a new issue; #323 is parked as delivered-with-negative-result.
- **45-corner DR-0006 validation campaign**, schematic and extracted, using
  the bench from Now item 3. Done when both records exist with a recorded
  reset-completion margin per corner. Blocked by: Now item 3.
- **Average-power scoring** (#125 stage 2): transient-power bench wired into
  the item-5 corner-matrix wrapper with regressions. Blocked by: DR-0006
  ratification.
- **Re-grade items 5 and 7** once the cascode layout and power scoring land.
  Done when `signoff-report.json` grades both from re-pinned envelopes.

## Later

- **Close item 7 by floorplan rather than device sizing.** Question first:
  after the cascode re-layout, how much of the post-layout delay is still on
  the nets the attribution study (#229) named?
- **Whole-comparator offset on the extracted netlist.** Only a feasibility
  probe exists (`comparator-offset-tran-extracted-feasibility`, no record).
  Question first: is the transient Monte Carlo affordable at a useful N?
- **Metastability as a scored row** (DR-0005). It needs no new simulation;
  the question is whether its deterministic small-overdrive definition is accepted.
- **Grader re-pin and rulebook re-vendor** (pin is klt 0.8.0; procedure in
  `signoff/README.md`). Question first: does a newer grader change any grade?
- **5 V flavor.** Only by decision record, per `CLAUDE.md`; nothing is drafted.

## Blocked and waiting

- **DR-0004 ratification** gates #112 and, through it, items 5 and 7 (triage
  of 2026-10-15 on #112). **DR-0006 ratification** gates power scoring (#125).
- **DR-0005 and DR-0007** stay proposed; DR-0007 says it waits on #112.
- **#323** needs a disposition: close as delivered with the DR-0007 negative
  result, or re-scope. Builders claimed and released it three times.
- **#3** (gap-to-T1 tracker) still quotes 3 of 11 items met; the report grades 9 of 11.
- **#123, #95, #94, #83, #1** are tooling and guard holds, not design work.

Agents cannot supply ratification keys. Until a Now item is filed, the ready queue is empty.

## Not planned

- Relaxing any DR-0002 bound to make a row pass.
- More parasitic-trimming studies for item 7: #264 found none clears `ss_125c_2.97v`.
- T2 and above: the grader reports `tier_not_supported` for those rows.
- Fixing `gf180-sar-adc`'s embedded comparator from here; findings go to that repo.
