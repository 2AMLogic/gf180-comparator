# `design/proposed/dr0004-cascode/` — proposed, not ratified

The xschem source of the preamp input-pair cascode proposed by
[DR-0004](../../../spec/decision-records/DR-0004-preamp-input-cascode-kickback.md)
(issue #102). This directory is **not** part of the ratified design:
`design/netlist.sh` does not read it, and `design/comparator.spice` is not
derived from it.

| file | what it is |
|---|---|
| `comparator_dut_analog.sch` | `design/comparator_dut_analog.sch` with the cascode added: input-pair drains renamed `xcp`/`xcn`, cascodes `MCP`/`MCN` (`nfet_03v3` L = 0.5 µ, W = 20 µ) up to `aon`/`aop`, divider `RCT`/`RCB` (`ppolyf_u_1k` 240 µ / 360 µ, `vcas` = 0.6·`vdd`), decoupler `MCC` (20 µ × 20 µ). The other two cells (`comparator_dut.sch`, `comparator_dut_latch.sch`) are unchanged and are not copied here. |

The netlist the experiment simulates is
[`sim/dut/experiment_comparator_dr0004_cascode.spice`](../../../sim/dut/experiment_comparator_dr0004_cascode.spice)
(DUT binding `comparator-dr0004-cascode-exp` in `sim/dut.json`). It was
written by hand to match this schematic, not netlisted by `design/netlist.sh`.
This host's xschem wraps long lines differently from the pinned xschem, so
`netlist.sh --check` cannot reproduce the committed bytes here. It reports
the ratified netlist stale for the same reason.

Why it lives here and not in `design/`: the ratified `design/comparator.spice`
is pinned by sha256 in the signoff LVS (item 4) and item-5 corner-matrix
envelopes. If DR-0004 is ratified, the follow-up (#112) moves this cell over
`design/comparator_dut_analog.sch`, regenerates `design/comparator.spice` with
`design/netlist.sh`, and re-runs layout, DRC, LVS and PEX. It then re-pins the
signoff manifest per `signoff/README.md`'s refresh contract.
