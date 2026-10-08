# manifests/ — what an integrator takes, as data

This directory is this repo's fixed-path home for integrator-facing
structured data, per 2am cross-cutting rule 9
([`REUSE.md` §"Adopt or record"](https://github.com/2AMLogic/2am/blob/main/REUSE.md)):
*"publish what an integrator takes — the cell, its port list, the netlist and
GDS paths, measured area, maturity rung — as structured data rather than
README prose."*

| file | what it is |
|---|---|
| [`integrator.json`](integrator.json) | the integrator view: top cell, ordered port list with directions/meanings, netlist and GDS paths, measured area with its bbox derivation, and the maturity pointer below |

## Where the maturity rung lives, and why it is not duplicated here

The `klt signoff` block manifest — the graded maturity rung — lives at
**[`signoff/`](../signoff/)** in this repo, not here. Issue #57 landed it
there (PR #59, 2026-09-21) as this block's machine-graded T1 verdict of
record: [`signoff/block-manifest.json`](../signoff/block-manifest.json) (the
`klt signoff --manifest` input), [`signoff/signoff-report.json`](../signoff/signoff-report.json)
(the committed graded report), an anti-rot verifier CI runs on every push/PR
(`signoff/verify-report.py`, `.github/workflows/signoff.yml`), and
[`signoff/README.md`](../signoff/README.md). The gap-to-T1 tracker (#3)
points there.

That manifest is **byte-compatible in shape with the twins' `manifests/`
convention** — the same `{block, kind, evidence}` schema
(`sg13g2-comparator`'s `manifests/sg13g2-comparator.json` @ `fb49fe1` and
`sky130-comparator`'s `manifests/sky130-comparator.json` @ `e084b55`,
verified by live read 2026-09-22) — only the directory differs. This repo
deliberately does **not** copy it under `manifests/`: a second copy would
fork the verdict of record into two files that drift independently, and the
committed report would still be the one CI verifies at `signoff/`.
`integrator.json`'s `maturity` field points at the one verdict of record.

If the fleet later standardizes integrator views fleet-wide (the twins carry
`manifests/` directories but no integrator-view file yet — this issue is the
fleet-first precedent), the fixed path chosen here is
`manifests/integrator.json`, with repo-local maturity data pointer-addressed
from it rather than relocated.

## What `maturity.rung` means — and what it must never mean

`maturity.rung` mirrors the **graded tier** recorded in the verdict of
record: it is `signoff/signoff-report.json`'s `tier`, copied verbatim. Two
consequences:

- **The type is `string | null`.** While the grader awards no tier the rung
  is JSON `null` — not `"T1 (…)"`, not an aspirational string, not the
  milestone being chased. A supported non-null value is exactly one ladder
  rung from [`signoff/design-evidence-tiers.md`](../signoff/design-evidence-tiers.md)
  (`T1`/`T2`/`T3`/`T4`). Consumers must treat `null` as "no tier graded
  yet" (this type change is issue #84; before it the field carried a prose
  string the report did not support).
- **A graded tier is not an award.** Per the tiers doc, the checklist does
  not itself grant a tier — the operator's award (the T1 milestone tracked
  by #3, recorded on the product side) is a separate human act. Closing an
  issue, landing evidence, or re-grading the report never infers an award,
  and no field here assigns one. The rung answers only "what has the
  committed evidence been machine-graded to".

This is enforced, not merely documented: CI (a step in
[`signoff.yml`](../.github/workflows/signoff.yml)) runs
[`verify-integrator.py`](verify-integrator.py), which fails unless the rung
equals the committed report's `tier` — `null` on both sides, or the same
supported ladder value. A deliberate mismatch fails in either direction, so
the structured manifest can never advertise a tier the verdict of record
does not support (nor hide one it does). `maturity.verdict_of_record` names
the file the rung is compared against; the pointers (`manifest`, `readme`,
`grader`, `regenerate`) say how the grade is produced and reproduced.

## Update discipline

`integrator.json` carries an `as_of_commit` stamp: re-derive its measured
values (area from `layout/comparator.gen-compose.json`'s `bbox_um`, port
list from `sim/dut/README.md`'s interface contract) when the underlying
artifacts change, and move the stamp forward. Every path named inside it
must exist from a fresh clone of `main`.

Refreshing the signoff verdict refreshes this file too: whenever
`signoff/signoff-report.json` is re-graded and committed, update
`maturity.rung` to the new `tier` and the `provenance` stamp in the same
change — the CI consistency check above fails a PR that updates one
without the other.
