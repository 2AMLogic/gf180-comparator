# gf180-comparator — agent instructions

Open-source canary block: a dynamic latched comparator on gf180mcu,
on GlobalFoundries GF180MCU, a 180 nm open CMOS PDK, designed and verified by AI agents.

- **PDK**: GlobalFoundries GF180MCU (https://github.com/google/gf180mcu-pdk). Open-source flow: xschem + ngspice for
  design/sim, klayout-tools (`klt`) for layout work.
- **New standalone block; two-PDK twin** with sg13g2-comparator (and the
  sky130 twin) — keep benches structurally identical.
- **Monte-Carlo offset is the headline**: gf180mcu ships mismatch models;
  commit run counts, seeds, and the sigma derivation. 3.3 V primary; 5 V
  flavor only via decision record (same rail discipline as gf180-opamp).
- **Metastability and kickback are first-class rows** — see
  sg13g2-comparator's CLAUDE.md; same bench definitions.
- **Cross-pollination protocol**: findings that affect gf180-sar-adc's
  embedded comparator get filed as issues on THAT repo, not silently fixed
  here or there.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and
  describe the gap, not the design.
- **Verification is the product**: no claim without a testbench; PVT corners
  on every recorded result; `sim/` results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not
  relax the ratified spec to make results pass.
