# DR-0008: Staged-and-committed sources as pinned provenance (the corrected git_state check)

- **Status**: proposed
- **Date**: 2026-11-16
- **Decided by**: operator ruling 2026-11-15 on #398 (@rjwalters, attended
  `/fleet:decide` round 20261111-r14, q99, option (a)); record authored by the
  builder agent of issue #421
- **Supersedes**: none — first record for this decision
- **Superseded by**: (none while this record stands)
- **Related**: #398, #421, #151; DR-0002 (ratified bounds, untouched);
  `sim/comparator-avg-power/records/20261115-064156694329-8a67cff.json`

## Context

Record `20261115-064156694329-8a67cff` is `citable: false` for
`sources uncommitted at request generation: layout/lvs/comparator.dut-layout.spice (not tracked)`,
yet the bytes it cites are pinned by its own corner dir: the staged copy
`sources/dut/comparator.dut-layout.spice` is committed beside the record and
its sha256 (`796431fd…`) is declared by every one of the 48 body decks. The
generation path is gitignored scratch — regenerated per host by
`layout/run_extract_sim.py` — so `mk_klt_request.git_state`'s fallback loop
listed it `(not tracked)`. That answered a narrower question than the
docstring claimed: *"a gitignored or out-of-repo source has no committed
identity"* is false for this record, whose bytes have a committed identity in
the record's own tree even though the generation path has none at the origin
commit. #398 (the 45-point post-layout PVT re-mint) is parked on this
decision. The operator selected option (a): treat a staged-and-committed
source with a matching sha256 as pinned provenance; re-mint under the
corrected check. Options (b) and (c) — including tracking the netlist — were
declined, so `layout/lvs/comparator.dut-layout.spice` stays gitignored.

## Decision

A narrow provenance class, **staged-and-committed source** (pinned source):
a FILE source inside the repository that (1) is gitignored — not merely
untracked — at request generation, and whose bytes are (2) staged into the
record's own tree, (3) committed as part of the record (the corner dir is
archived atomically beside the record JSON, so a reader of a committed record
reads those bytes from that record's own commit), (4) sha256-matched — the
staged copy equals the bundle's `dut.netlist_sha256` / staged hash — and (5)
referenced by every deck: every body netlist, the 45 scored corners and the
probe decks alike, declares its hash in a `* source-sha256` line.

Implementation:

- **Generation** (`mk_klt_request`): `git_state` stops listing a gitignored
  file source as dirty; the new `git_ignored_sources` classifies exactly the
  untracked-and-ignored file sources, and `write_bundle` carries them as
  `origin.pinned_sources` (present only when nonempty). A source that is
  modified-tracked, untracked-but-not-ignored, outside the repository, or
  gitignored-but-index-staged-without-a-commit stays dirty.
- **Ingest** (`klt_record.verify_origin_commit`): a pinned path is excluded
  from the origin-commit byte checks (which cannot succeed for it by
  construction — it is not a blob at the origin commit), and is accepted only
  via the class's legs: staged copy present and hash-matched and declared by
  every deck (`verify_staged`, refused outright on any miss), the
  contradiction guard (a pinned path that IS a blob at the origin commit is a
  tracked file git vouches for — its staged copy must match, else
  `SOURCE_COMMIT_MISMATCH`), and the structural committed leg above. Leg
  failures refuse the ingest; they never mint a silently-citable record.
- **Record truthfulness**: every record's `source_bundle` gains
  `origin_pinned_sources`, so a reader can always tell a class record from a
  genuinely clean tree (`origin_dirty_paths == []` and
  `origin_pinned_sources == []` together mean clean). The item-5
  (`make_item5_envelope.py` citable/`dirty is not False`/
  `origin_dirty_paths == []`) and item-8 (`FLEET_FIELDS`, `dirty == False`)
  gates read exactly those frozen fields and pass a class record unchanged.

**`BUNDLE_VERSION` stays 2.** The new `origin.pinned_sources` key is optional
(written only when nonempty), and both ingest sites read it with
`.get(...) or []`, so pre-#421 v2 bundles — including every committed
record's bundle — ingest identically. Cost: a v2 bundle may or may not carry
the key, which the ingest path must (and does) tolerate; no field disambiguates
"pre-#421 tool" from "post-#421 tool, nothing pinned" (the two coincide —
pre-#421 tools never classify, so they never pin). Rejected: bumping to 3 —
`klt_record.load_bundle` compares with exact `!=`, so a bump makes every
existing work dir un-re-ingestable via `--from-report` for a purely additive,
absence-tolerated field.

What the class deliberately still refuses: a modified tracked source; an
untracked source that is not gitignored; a source outside the repository; a
gitignored source staged in the git index but not yet committed (porcelain
sees it — the class covers bytes only once the record carrying them lands); a
staged copy whose sha256 does not match the bundle; a staged file no deck
declares; a pinned path that is a tracked blob at the origin commit with
different bytes; a pinned path that is absolute, escaping, or has no staged
counterpart.

## Alternatives considered

- **Option (c): track `layout/lvs/comparator.dut-layout.spice`** — declined
  by the operator ruling; the netlist is per-host generated scratch and
  tracking it would churn the repo with unbuildable artifacts.
- **An "ignore this path" allowlist keyed on the path itself** — cannot
  distinguish a staged, hash-matched source from a deleted one, so it would
  excuse the genuinely dirty tree the ruling refuses to excuse.
- **Re-anchoring the committed leg to `origin["commit"]`** — measured
  impossible (`git cat-file -e` at `8a67cff2`): neither the generation path
  nor the staged copy is a blob there; the staged copy was first committed by
  the later record commit `ea7b1e5f`. The committed leg is inherently a claim
  about the record's own commit, hence its structural form above.

## Consequences

- `#398`'s re-mint can mint a citable record with the extracted DUT without
  tracking it and without relaxing any ratified gate; item 5 and item 8 pass
  the class record with no envelope change.
- All four conditions remain individually enforceable and each refusal names
  its leg, so a false-citable regression has a diagnostic, not a silence.
- Existing committed records are untouched: nothing re-grades `sim/`
  (append-only); the 8a67cff record stays `citable: false` as minted.
- The docstring equivalence "has committed identity ⇔ generation path is
  tracked" is gone; the committed leg is a claim about the record's own tree.
- The pattern is **specific to this repository's staging layer**
  (`mk_klt_request.stage_sources` pins bytes before `klt` ever sees a body);
  `klt` receives finished netlists and reports their hashes, so there is no
  klayout-tools capability gap to file — the tool boundary is not crossed.
- Cost: two code paths (bundle with and without the optional key) and a
  reader-side duty to check `origin_pinned_sources` when asserting "minted
  from a clean tree".

## Spec lines affected

- none — process/provenance decision; no README target-spec row or spec
  value is set, changed or scoped by this record (DR-0002 bounds untouched).
