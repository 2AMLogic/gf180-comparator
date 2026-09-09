# `sim/`

xschem + ngspice testbenches and **append-only** results for
`gf180-comparator`, on the gf180mcu 3.3 V rail.

Four experiments, one per first-class row of
[`README.md`'s target specification](../README.md#target-specification-draft--engineering-to-ratify):

| experiment | row it backs | method |
|---|---|---|
| [`comparator-offset-mc/`](comparator-offset-mc/) | Offset σ | Monte Carlo on gf180mcu's `sw_stat_mismatch` local-mismatch models |
| [`comparator-preamp-noise/`](comparator-preamp-noise/) | Input-referred noise | `.noise`, total integrated output noise ÷ measured DC gain |
| [`comparator-regeneration/`](comparator-regeneration/) | Decision time vs. overdrive, **metastability** | transient overdrive ladder, τ extracted from it |
| [`comparator-kickback/`](comparator-kickback/) | **Kickback** | 1 kΩ source impedance *and* a floating high-Z input |

Metastability and kickback are first-class rows here, not appendices, per
[`CLAUDE.md`](../CLAUDE.md).

> **Current status: the device under test is a PLACEHOLDER.** This repo's
> comparator topology is not decided yet — that is
> [`spec/porting-plan.md`](../spec/porting-plan.md) next step 1, a separate
> decision record. `sim/dut.json` therefore binds
> [`sim/dut/placeholder_comparator.spice`](dut/), a deliberately crude stub,
> and **every record committed so far carries a banner saying its numbers
> substantiate the harness and not a spec row.** The plumbing is real,
> exercised, and reproducible; the circuit is not the design. Swapping in the
> real netlist is a one-line edit of `sim/dut.json` — see
> [`sim/dut/README.md`](dut/README.md).

## Cold start

Everything is stdlib Python plus ngspice; there is no virtualenv to create.

```bash
# 1. Install the pinned PDK (~5 GB). The hash is not decorative -- it IS the
#    device models, and it is checked before any point is simulated.
pip install volare
volare enable --pdk gf180mcu c6d73a35f524070e85faff4a6a9eef49553ebc2b

# 2. Install ngspice 46 or newer (Debian/Ubuntu: apt-get install ngspice).

# 3. Verify PDK, tools, pins and the DUT interface contract:
python3 sim/run_corners.py --check-env

# 4. Smoke the whole command surface -- one nominal point per bench, seconds:
./sim/characterize.sh smoke

# 5. Prove the HARNESS itself works, including the sabotage negative control:
./sim/selftest.sh

# 6. Reproduce every committed record (full 45-point PVT grid per bench):
./sim/characterize.sh characterize
```

`source sim/env.sh` exports the same PDK environment the harness resolved, so
an interactive `ngspice` or `xschem` session sees exactly what the runner
does.

If your PDK lives somewhere unusual, either set `GF180_PDK_PATH` (or the
conventional `PDK_ROOT` + `PDK` pair) or write a git-ignored
`sim/pdk.local.json`.

## Reproducing one record

Every record ends with the exact command that regenerates it. It is always:

```bash
python3 sim/run_corners.py <experiment-slug> -j 8
```

A re-run mints a **new** record; it never overwrites one already committed.
`sim/` is an evidence trail, not a status page.

## Pinned toolchain

[`sim/toolchain.json`](toolchain.json) pins the toolchain and the harness
**checks it before simulating**, refusing to run on a mismatch (override with
`--allow-toolchain-drift`, which then stamps the drift into every record made
under it).

| pin | value | checked? |
|---|---|---|
| open_pdks | `c6d73a35f524070e85faff4a6a9eef49553ebc2b` | **exact** — the hash *is* the device models |
| ngspice | ≥ 46 (major) | floor |
| Python | ≥ 3.9 | floor |
| xschem | 3.4.7 | recorded only — nothing here invokes xschem until `design/` has a schematic |

PDK variant: **gf180mcuD**, set in [`sim/pdk.json`](pdk.json).

## Corner grid

gf180mcu ships no single global process switch — each device family carries
its own `.lib` section — so a named corner here is a bundle of one section
per family. Full definitions and rationale:
[`sim/harness/README.md`](harness/README.md).

| axis | points |
|---|---|
| process | `tt`, `ff`, `ss`, `fs`, `sf` (the default `mos` set); `res_ff`, `res_ss` additionally in `full` |
| temperature | −40 °C, 27 °C, 125 °C |
| supply | 2.97 V, 3.30 V, 3.63 V (3.3 V ± 10 %) |

**45 points**, full factorial, per recorded run. Corner ids are
`<process>_<temp>c_<supply>v`, e.g. `ss_-40c_2.97v`.

Resistor corners are in the grid (and capacitor corners are not) because this
block's front-end gain rides on the poly load resistors and it has no
capacitor array — see the divergence table in the harness README.

## Directory convention

```
sim/<experiment-slug>/
  README.md                       method, provenance, and what was NOT ported
  testbench/tb.json               manifest: analyses, measurements, checks
  testbench/<name>.spice          netlist FRAGMENT (harness owns models/.temp/.control)
  records/<record-id>.md          the evidence record   <- append-only
  records/<record-id>.json        the same, machine-readable
  corners/<record-id>/<corner-id>.log   raw ngspice output, one per PVT point
  netlist-snapshots/<record-id>.spice   DUT + fragment exactly as simulated
```

`<record-id>` is `<UTC-YYYYmmdd-HHMMSS>-<short-sha>`.

## Record format

Every record states, in its header, everything needed to judge or reproduce
it:

- the **claim** it substantiates (or, today, that it substantiates the
  harness and not a spec row);
- the **DUT** — id, provenance (`placeholder` / `schematic` / `extracted`),
  path and sha256;
- the **testbench** fragment and manifest sha256s;
- the **commit**, flagged loudly if the working tree was dirty — a
  dirty-tree record is not citable;
- the **PDK** variant and open_pdks hash, and the **toolchain** observed,
  plus any accepted drift;
- the **corner matrix** actually run and how many points completed;
- for a Monte-Carlo record, the **seed, draw count and σ derivation**
  (`CLAUDE.md` requires all three);
- the full per-corner result table, the grid spread, the per-axis corner
  sensitivity, the verdict, and the reproduction command.

Raw per-corner ngspice logs are committed alongside (`.gitignore` explicitly
un-ignores `sim/*/corners/**/*.log` for this reason), so a reader can check a
number against the tool's own output rather than against a table somebody
transcribed.

## Rules

- **No claim without a testbench.** A number that is not in a record under
  `sim/` is not a result.
- **PVT corners on every recorded result.** A single-corner run is a smoke
  test and writes no evidence.
- **`sim/` is append-only.** Add records; never edit or delete one.
- **A placeholder measurement is never a spec claim.** The provenance stamp
  is the mechanism, not the etiquette.
- **Do not relax a check to make a result pass.** A check that is wrong gets
  a documented recalibration citing the record it was calibrated from — the
  convention every `min_spread_pct_by_axis` floor here already follows.
