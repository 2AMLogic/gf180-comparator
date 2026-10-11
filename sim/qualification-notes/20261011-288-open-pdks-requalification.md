# Superseding note: two records not qualified under the exact-revision policy (#288)

Append-only. The records named here are **not edited**; this note changes their
standing only.

`sim/toolchain.json` pins `open_pdks` to `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
(exact match: "a different one silently yields numbers no other record in sim/
is comparable with"). Every executor report of the two record sets below states
`provenance.pdk.version = "open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7"`
(6 of 6 reports), and `check_pdk_identity` (`sim/tools/klt_record.py`, #283)
refuses them with `PDK_QUALIFICATION_FAILED`. They predate that check.

| record | corner set | committed standing | standing from this note |
|---|---|---|---|
| `sim/comparator-kickback/records/20261010-022609774981-bf851ec` | `sim/comparator-kickback/corners/20261010-022609774981-bf851ec` | `citable: true`, `reference: true` | **NOT QUALIFIED under the exact-revision policy: do not cite as reference evidence** |
| `sim/comparator-offset-cm-index/records/20261010-130605300890-d8e9253` | `sim/comparator-offset-cm-index/corners/20261010-130605300890-d8e9253` | `citable: true`, `reference: true` | **NOT QUALIFIED under the exact-revision policy: do not cite as reference evidence** |

**No replacement exists yet.** Nothing in this repository is described as
citable that was not produced on the pin. Status: **evidence pending
re-qualification** (#288). The numbers in these records are retained as history
and as a diagnostic; they are not withdrawn as measurements.

## Consumers (annotated in place, not re-scored)

- Kickback `bf851ec` is load-bearing: `measurements/characterization-report.md`
  (+ `.sources.json`; hash-pinned by the item-8 envelope, so annotated here
  rather than in place: refresh it with the re-pointing follow-up), `signoff/README.md` (item-5 revisions r4/r5 score
  `kickback_1k_peak_mv` on it), `signoff/make_item5_envelope.py`,
  `signoff/verify-report.py`, `signoff/block-manifest.json`,
  `spec/claim-registry.json`, `sim/comparator-kickback/README.md`. The item-5
  kickback score rests on a non-qualifying revision until it is re-minted. No
  new envelope revision is cut here (the headline verdict, 1/45 within 5 mV and
  0/45 within 2 mV, is unchanged and is not relaxed).
- cm-index `d8e9253` is unscored: `sim/README.md`,
  `sim/comparator-offset-cm-index/README.md`, and `selection_record` of probe
  plan `.../probes/20261011-091529310543-f16ddbe-tolerance-probe/probe-plan.json`
  (kept as history; a rerun probe must select from a qualified record).

## Stage A: fleet capability evidence (#288)

- Probe command (single unit, `--backend batch`, trivial divider netlist, same
  models/lib as the committed fleet probes):
  `klt sim --backend batch -o out --format json request.json` (klt 0.7.0+g122d607d5c52).
  **The submit failed on every attempt (14 attempts over about 40 minutes)**, verbatim:
  `batch backend failed: batch-fleet-provision.sh launch failed (exit 1): error: 8 instance(s) already running + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8`
  (later attempts reported 9, 11 and 15 instances running). This is fleet
  capacity saturation, not a statement about the image. No local grid fallback
  was run.
- Existing fleet reports (all runner klt 0.5.0, AMI `ami-0e40e3245f1923ac8`):
  17 committed report sets under `sim/` show `open_pdks c6d73a35...`, including
  the most recent fleet job in the repo
  (`sim/comparator-offset-cm-index/probes/20261011-091529310543-f16ddbe-tolerance-probe`,
  committed 2026-10-11) and `comparator-offset-tran` `4a4df37`/`d84e59d`; only
  these two record sets (plus `sim/comparator-offset-tran-extracted-feasibility/campaign/20261011`,
  a non-reference feasibility campaign) show `f6eeac7...`. The **same AMI id**
  appears with both revisions, so the revision is not determined by the image id
  alone; it is plausible the pin is suppliable and the 2026-10-10/11 `f6eeac7`
  jobs landed on a differently provisioned volare tree. **Not proven**: a fresh
  reported `provenance.pdk.version` was not obtained.

## Disposition and what remains

The pin is **not changed**. DR-0007 (asking whether `f6eeac7` should be the pin)
is deliberately **not** filed: the evidence above does not show the pin is
unavailable, only that the fleet was saturated. Remaining work, in the
follow-up on #288: when capacity is available, run the single-unit probe, then
(if it reports `c6d73a35...`) re-run both benches through the fleet
(`KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py comparator-kickback`
and `... comparator-offset-cm-index`), re-point the consumers above, and cut a
new item-5 revision; if it reports anything else, file DR-0007.

## Stage A result (second probe, 2026-10-11 ~19:38Z) and Stage B1 re-mint

Append-only addendum; nothing above is edited.

- **Stage A, fleet probe**: the single-unit `klt sim --backend batch` probe
  (trivial resistor-divider netlist, same models/lib as the committed fleet
  probes) first failed again with the verbatim capacity error
  `8 instance(s) already running + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8`
  (19:3x Z attempt 1), then was accepted on attempt 2. The fleet job
  (`klt-sim-db984e84e0ee`, AMI `ami-0e40e3245f1923ac8`, runner klt 0.5.0,
  `aws-batch-fleet`) reported **`provenance.pdk.version = "open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b"`**,
  i.e. the `sim/toolchain.json` pin. (The probe's own measurement errored by
  construction of the trivial netlist; only the reported provenance is used.)
  Conclusion: the pin is suppliable; the earlier `f6eeac7` jobs were a
  differently provisioned volare tree. DR-0007 is therefore **not** filed and
  the pin is unchanged.
- **Stage B1, re-mint through the fleet** (`KLT_SIM_BACKEND=batch python3 sim/tools/klt_record.py <bench>` at clean commit `7e20c78`);
  `check_pdk_identity` accepted both, every leg reporting `c6d73a35...`:

| superseded (NOT qualified, kept as history) | replacement (qualified, pin `c6d73a35...`) |
|---|---|
| `sim/comparator-kickback/records/20261010-022609774981-bf851ec` | `sim/comparator-kickback/records/20261011-195826615490-7e20c78` |
| `sim/comparator-offset-cm-index/records/20261010-130605300890-d8e9253` | `sim/comparator-offset-cm-index/records/20261011-210628443577-7e20c78` |

  Result tables are identical row for row (45 of 45 rows each; the rendered
  `Result` tables diff empty): the PDK-revision difference did not move any
  scored or reported number. The kickback verdict is unchanged and not
  relaxed: 1/45 within the 5 mV target, 0/45 within the 2 mV stretch, worst
  10.0098 mV at `sf_-40c_3.63v`. The cm-index record stays unscored.
  The cm-index fleet submit hit the same capacity error on its first attempt
  and succeeded on the second; no local fallback was run.
- **Re-pointing**: item-5 envelope revision 6 (same semantics as r5, new
  kickback record id; r4/r5 files untouched), `signoff/block-manifest.json`,
  `signoff/verify-report.py` pin, `spec/claim-registry.json`,
  `measurements/characterization-report.{md,sources.json,item8.json}`,
  `spec/evidence-ledger.md`, `spec/consumers.md` and the bench READMEs.
  Left as history (cite the superseded record on purpose):
  the r4/r5 envelopes, the probe plan's `selection_record`, and
  `sim/harness/tests/test_cm_index_semantics.py::test_committed_record_selects_ss_125c_2p97`.
