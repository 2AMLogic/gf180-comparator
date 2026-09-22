# spec/

This directory holds this block's specification-related documents and their
decision history. **The target-spec table itself lives in the top-level
[`README.md`](../README.md#target-specification-draft--engineering-to-ratify)**
— not a `spec/target-spec.md` file. This is a deliberate fleet convention
(confirmed against both same-wave twins:
[`sg13g2-comparator`'s `spec/README.md`](https://github.com/2AMLogic/sg13g2-comparator/blob/main/spec/README.md)
and
[`sky130-comparator`'s `spec/README.md`](https://github.com/2AMLogic/sky130-comparator/blob/main/spec/README.md),
both merged, both keep the table in the top-level README and ratify it via a
decision record), not a one-off choice for this repo.

## Decision records

A decision record is required whenever a value or approach in the
top-level README's target-spec table is **set, changed, or scoped** — not
for routine design/sim work that merely targets the existing table. To
write one: copy `decision-records/TEMPLATE.md` (create it, mirroring the
decision-record shape used by
[`gf180-sar-adc`'s `spec/decision-records/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/spec/decision-records) —
e.g.
[DR-0015](https://github.com/2AMLogic/gf180-sar-adc/blob/main/spec/decision-records/DR-0015-comparator-topology.md)'s
Context / Decision / Alternatives considered / Spec lines affected /
Consequences sections — if no template exists yet in this repo) to
`decision-records/DR-NNNN-<slug>.md` (next unused `NNNN`, one decision per
record), fill it in, and commit it alongside the spec change it justifies.
Never edit a ratified record after the fact — if a decision changes,
supersede it with a new `DR-NNNN` that says so, per the same convention
`gf180-sar-adc` uses.

**Issue #2's pass set no decision record**, and the target-spec table stayed
**DRAFT** through several subsequent measurement passes — these are original
engineering-judgment bounds (numerically matched to the
`sg13g2-comparator`/`sky130-comparator` twin set for cross-PDK comparability,
per `README.md`'s own basis notes), each stating its own basis, not a ratified
commitment. Ratification against the first measured result against every row
is now proposed in
[`decision-records/DR-0002-target-spec-ratification.md`](decision-records/DR-0002-target-spec-ratification.md)
(`Status: proposed`, no numeric bound changed); the table stays DRAFT until
that record's PR is approved and merged, per
[2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)'s ratify-by-PR-approval
pattern.

## Review bar

One-command characterization plus README reproducibility is a standing bar
for this block, from day one — not deferred until the block reaches T1. Any
design challenge or external review of this canary should be able to
regenerate every cited result (schematic → netlist → testbench → evidence
record) from a single documented command per experiment, matching the
`sim/`-evidence conventions `gf180-sar-adc` already uses for its own
comparator subblock (see `spec/porting-plan.md`'s citation of that repo's
`sim/comparator-offset-mc/`, `sim/comparator-regeneration/`,
`sim/comparator-preamp-noise/`, and `sim/comparator-kickback/` experiment
directories). This is wired into the gap-to-T1 tracker (#3) from the start
rather than added retroactively.

## Gap-to-T1 tracker

[#3](https://github.com/2AMLogic/gf180-comparator/issues/3) tracks this
block's gap to T1 sim-validated per the klayout-tools design-evidence
ladder — a checklist that began as 10 items, every one honestly unchecked
as of the original 2026-09-06 survey pass (0/10; no schematic, layout, or
`sim/` content existed yet beyond the `design/`, `layout/`, `sim/`, and
`measurements/` directory scaffolding), and gained an eleventh item —
*power delivery (structural)*, graded from a `klt erc` supply-spec run —
on 2026-09-17
([klayout-tools#2025](https://github.com/2AMLogic/klayout-tools/issues/2025);
this repo's evidence is #56's). The tracker issue itself, not this stub,
is the live per-item state.

## Consumers

[`spec/consumers.md`](consumers.md) names this block's consumers (today:
`gf180-sar-adc`, per the `2AMLogic/2am` `repos.yml` `consumes:` edge), carries
one requirement row per constraint each consumer imposes, and states the
same-block-class facts once. The structured integrator view it complements
lives at [`manifests/integrator.json`](../manifests/integrator.json).

## Porting plan

[`spec/porting-plan.md`](porting-plan.md) names the nearest mature sibling
(`gf180-sar-adc`, same PDK, same 3.3 V rail, comparator is a core subblock
of that ADC's own design) and the port/design split for this block's own
testbenches and design work — methodology and device-flavor facts transfer;
topology, sizing, and spec numbers are designed fresh.
