# Forensics: foreign WORK_PLAN.md render, 2026-11-15 (PR #410, issue #411)

Tracked, self-contained capture of the contaminated `WORK_PLAN.md` region and
the measured root-cause determination for issue #411.

Why this file exists: the primary evidence lived in exactly one place — the
`.loom/worktrees/docs-guide` worktree parked at commit `2af9216c` — and
`.loom/scripts/docs-worktree.sh` documents that path as *"a single stable
worktree slot … one slot, reused every tick"* that it **resets on each run**.
The next Guide document-maintenance tick on this repo overwrites the slot, so
the live copy is perishable. Everything needed to understand the incident is
reproduced below; nothing here depends on the slot surviving or on `2af9216c`
staying reachable. (Choice of location: this is tooling forensics, not
simulation evidence — `sim/` is the append-only record for simulation results
per the repo `CLAUDE.md` — and not ratified-spec material, so it lives under
`docs/` rather than `spec/` or `sim/`.)

## The contaminated commit

- Repo: `2AMLogic/gf180-comparator`, branch `docs/guide-update-20261115-200543`
  (never merged; superseded by the rewritten PR #410 head `83faa49`, which
  contains only the correct `WORK_LOG.md` half).
- Commit: `2af9216cb25941bf5997603bcb13d3d45c7c3193`
- Author: `loom-fleet-dispatch[bot]`, date `2026-11-15 20:06:39 +0000`
- Message: `docs: update WORK_LOG and WORK_PLAN` ("Automated document
  maintenance by Guide triage agent. Co-Authored-By: Claude Sonnet 5.5")
- Diffstat: `WORK_LOG.md | 4 ++++`, `WORK_PLAN.md | 75 +++++++++-------` —
  **one commit, one Guide tick: a foreign `WORK_PLAN.md` region and a correct
  `WORK_LOG.md` update.**

The foreign region rendered **`asap7-stdcells`'** label state into this repo:
all nine sections and all nine rows of the Backlog Balance table. Every
foreign number also exists in *this* repo — closed, under an unrelated title
(e.g. `#122` here is the closed PR "ci: PDK-free netlist source-pin check
(#120)") — so the render is internally consistent, plausibly formatted, and
cross-linked to the wrong work. It does not look broken on inspection.

## The foreign region (byte-exact capture)

Reproduce (while `2af9216c` is reachable):
`git show 2af9216c:WORK_PLAN.md`. The region as committed:

<!-- loom:issue-411-region-capture:start -->

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#145**: fix: correct drifted decision-record enumeration and item-9 klt pin in attested evidence

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073)

## Important

`loom:important`; taken before unlabelled work.

- **#110**: Re-take the full DRC/LVS regression record under the CI-pinned klt 0.9.0

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#137**: a7s_common: gate_contact's v1= parameter now shadows the module-level v1() helper
- **#139**: Docs: ROADMAP.md is on main but nothing links it
- **#154**: normalize_paths CLI: the relative-prefix test is vacuous, and a trailing flag crashes instead of printing usage
- **#156**: `--verify` cannot re-check any committed record: 541 of 581 envelopes drift on nondeterministic and uncommitted derived inputs

## In Progress

Issues currently being built (`loom:building`).

- **#120**: Docs: stale decision-record enumeration in spec/stdcells.md, and the declared 0.8.0 pin in t1-item9-inventory.json
- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073)
- **#129**: Collapse the package.json test/check alias chain onto one gate that runs all six self-test files
- **#142**: Item 9 inventory does not content-hash klt_helper.py (nor check_lef.py / write_lef.py)
- **#144**: Four harness/evidence scripts outside item 9 are unpinned, incl. item 2's own check command

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#143**: build: run all six self-tests as one package.json gate
- **#161**: fix(lef): emit a pin's own net M2 as port geometry, not obstruction

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#145**: fix: correct drifted decision-record enumeration and item-9 klt pin in attested evidence
- **#153**: evidence: pin six unpinned harness/design scripts into T1 item 1 and 10
- **#159**: manifests: content-hash harness helpers in T1 item 9 attestation

## Proposed

Issues carrying `loom:curated`.

- **#120**: Docs: stale decision-record enumeration in spec/stdcells.md, and the declared 0.8.0 pin in t1-item9-inventory.json *(curated)*
- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073) *(curated)*
- **#137**: a7s_common: gate_contact's v1= parameter now shadows the module-level v1() helper *(curated)*
- **#139**: Docs: ROADMAP.md is on main but nothing links it *(curated)*
- **#142**: Item 9 inventory does not content-hash klt_helper.py (nor check_lef.py / write_lef.py) *(curated)*
- **#144**: Four harness/evidence scripts outside item 9 are unpinned, incl. item 2's own check command *(curated)*
- **#149**: integration/run_par.sh records an early-stage OpenROAD refusal as invalid-input (exit 1), not as a recorded refusal (exit 3) *(curated)*
- **#151**: klt_helper.py is not importable: module-level sys.argv indexing blocks unit-testing its pure parts *(curated)*
- **#154**: normalize_paths CLI: the relative-prefix test is vacuous, and a trailing flag crashes instead of printing usage *(curated)*
- **#156**: `--verify` cannot re-check any committed record: 541 of 581 envelopes drift on nondeterministic and uncommitted derived inputs *(curated)*

## Proposed (Architect / Hermit)

- **#133**: Drop the vendored design-evidence-tiers.md: a second, already-stale pin to klayout-tools that the pinned wheel already ships *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`) | 4 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 3 |
| Curated | 10 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->

<!-- loom:issue-411-region-capture:end -->

## The correct WORK_LOG half from the same commit

The four entries `2af9216c` added to `WORK_LOG.md` are all genuine
`gf180-comparator` items (verified against the forge; merge/close times from
the API on 2026-11-15):

```
- **PR #407**: docs: refresh ROADMAP.md forward-looking sections against landed work   (merged 19:12:36Z)
- **PR #402**: refactor: single-source the corner id format and parser in harness.corners (merged 17:51:58Z)
- **Issue #400** (closed): ROADMAP.md's Now/Next/Blocked sections present six closed issues as pending work at their own as-of commit (closed 19:12:37Z)
- **Issue #375** (closed): Consolidate the five hand-copied corner-id formatters and three divergent parsers onto sim/harness/corners.py (closed 17:51:59Z)
```

The parent commit's `WORK_LOG.md` top entry was `PR #399` (merged 14:58:39Z);
the next merge, PR #409, happened at 20:37:29Z — *after* this tick. The four
entries above are exactly the set merged/closed in
`[parent-WORK_LOG, 20:06:39Z]`, so the WORK_LOG half is complete and correct
for a fetch in **[19:12:37Z, 20:06:39Z]** — consistent with live queries run
correctly against this repo shortly before committing.

## Root cause: measured, not hypothesised

The issue's stated hypothesis — the generator's unpinned `gh` queries
resolving against the wrong cwd/`GH_REPO` — is **refuted**. The measurement,
re-verified on 2026-11-15 from the artifacts below:

### 1. The foreign region is asap7-stdcells' own render, byte-for-byte

`asap7-stdcells` ran its own Guide document-maintenance tick at
16:19:56–16:20:43Z (branch `docs/guide-update-20261115-161956`, its slot
reflog), committing `a8ff04978c7008515a9a78938a927d406a1bd7a4` and pushing
its (still-open, unmerged) PR #162. The `<!-- guide:plan-body -->` region of
`a8ff049`'s `WORK_PLAN.md` is **byte-identical** to the region captured above
(`diff` of the two regions: empty). That region matches *no* committed
asap7-stdcells `WORK_PLAN.md` before it (closest: `f81970c`, same day 10:36Z,
50 of 91 lines differ) — it is that tick's fresh render.

A live query in the committing tick is therefore impossible: the foreign
render's underlying label state had already moved on by 19:36:18Z (asap7
issue #156 left Ready), yet the committed region still shows #156 in Ready.

### 2. The committing tick ran 20:05:44 → 20:06:39 and queried correctly

The gf180-comparator slot reflog shows `docs/guide-update-20261115-200543`
checked out at 20:05:44Z and the commit landing 20:06:39Z — a ~55-second
tick. Two guard denials in `.loom/logs/guard-decisions.log` bracket the
successful commands:

- `2026-11-15T20:06:25Z` — **deny** `worktree-write-confinement-unresolved-var`
  (catastrophic tier; lossless — nothing ran). The denied command's heredoc
  contains the tick's **own, correct gf180-comparator render** (`#406` Ready;
  `#384 #385 #408` In Progress; `#409` PRs awaiting review; `#392 #401`
  approved; curated set `#3 #125 #323 #384 #385 #406 #408`) — exactly this
  repo's live label state at 20:06. The generator's queries were never pointed
  at the wrong repo.
- `2026-11-15T20:06:33Z` — **deny** `loom:role-tool-policy` on the tick's
  add/commit/push/PR-create attempt.

### 3. The transfer route: shared `/tmp` scratch files between repos' ticks

The denied splice command shows the tick's two-phase scratch protocol: write
the computed body to `/tmp/body.md`, then splice it between the region
markers. Both phases use **literal, repo-independent `/tmp` paths** on a host
running ~110 sibling Loom repos:

- `/tmp/body.md` — mtime **16:20** (the asap7-stdcells tick), content: the
  asap7-stdcells region, byte-identical to what landed in `2af9216c`. The
  20:06:25Z denial left it untouched (mtime proves nothing overwrote it).
- `/tmp/docswt` — mtime **20:05** (the gf180 tick), content: this repo's
  docs-guide slot path.

So the causal chain is: the gf180 tick's body-write was guard-denied
(20:06:25Z); its subsequent splice consumed the stale `/tmp/body.md` that the
asap7-stdcells tick had written at the same literal path ~3 h 45 min earlier.
The WORK_LOG half was written by a command shape the guard allowed, so it got
the correct content — hence the one-sided contamination the Curator flagged.

### Verdict (AC2)

- **Refuted**: "the generator's unpinned queries resolved against the wrong
  repo at generation time." The generator was never run against the wrong
  repo; its gf180 render is in the guard log, correct to the minute.
- **Confirmed**: the WORK_PLAN phase of the committing tick did not faithfully
  land the generator's output — it spliced a stale, cross-repo scratch file
  left by another repo's tick. The failure mode is *shared-host scratch
  collision between document-maintenance ticks*, aggravated by the
  guard-denied rewrite of the tick's own body file.
- **Boundary of this record**: successful commands are not logged, so the
  exact reason the final splice read `/tmp/body.md` stale (retry logic
  assuming the earlier step had populated it, vs. a deliberate re-read) is not
  directly observable. The data source itself is certain (byte-identity +
  mtimes). The out-of-band check on the next real Guide run (issue #411's test
  plan) verifies the guard added by this issue holds on a live tick.

## Out-of-band verification owed

On the **next real Guide document-maintenance run on this repo**: confirm
`WORK_PLAN.md`'s rendered region matches this repo's measured label state at
that run, and record the observation with the head SHA it was taken at. A unit
test cannot distinguish "the generator now queries the right repo" from "no
tick has fired since"; only the live run closes that line.
