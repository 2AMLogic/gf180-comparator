# gf180-comparator

A dynamic latched comparator on GF180MCU on
[GlobalFoundries GF180MCU](https://github.com/google/gf180mcu-pdk), a 180 nm open CMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: just opened.** Nothing is designed yet. The first work is
the offset methodology — gf180mcu ships Monte-Carlo mismatch models, so the first result is the MC offset study at 3.3 V.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using this PDK, not just this repo.

## Why this block, on this PDK

gf180-sar-adc already embeds a comparator that has never been specified
standalone; this repo characterizes the decision element for its own sake —
offset, noise, metastability, kickback — on the catalog's most mature PDK,
as the gf180 twin of sg13g2-comparator (same benches, same spec structure,
opened together).

GF180MCU ships statistical mismatch models, so the offset story here is the
strong version: Monte-Carlo sigma with run counts and seeds committed. The
existing SAR's behavior is context, not a source — this repo derives its own
numbers from the models.

## Target specification (DRAFT — engineering to ratify)

Offset sigma (MC, run count stated), input-referred noise, decision time vs
overdrive, kickback into stated source impedance, supply/power at 3.3 V.

## License

Apache-2.0.
