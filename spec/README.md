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

**This pass sets no decision record.** The target-spec table filled in by
issue #2 stays **DRAFT** — these are original engineering-judgment bounds
(numerically matched to the `sg13g2-comparator`/`sky130-comparator` twin set
for cross-PDK comparability, per `README.md`'s own basis notes), each
stating its own basis, not a ratified commitment. A DR is owed the first
time that table's rows are ratified, changed, or rescoped, not before.

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
ladder — a 10-item checklist, every item honestly unchecked as of this pass
(0/10; no schematic, layout, or `sim/` content exists yet beyond the
`design/`, `layout/`, `sim/`, and `measurements/` directory scaffolding).

## Porting plan

[`spec/porting-plan.md`](porting-plan.md) names the nearest mature sibling
(`gf180-sar-adc`, same PDK, same 3.3 V rail, comparator is a core subblock
of that ADC's own design) and the port/design split for this block's own
testbenches and design work — methodology and device-flavor facts transfer;
topology, sizing, and spec numbers are designed fresh.
