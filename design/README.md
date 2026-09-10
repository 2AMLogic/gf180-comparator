# design/

Schematics (xschem) and the netlist the corner runner actually simulates.

```
design/
  xschemrc                    repo xschem config: resolves the PDK by the same
                              rules as sim/harness/pdk.py, adds design/ to the
                              symbol path
  netlist.sh                  THE one command that regenerates comparator.spice
  comparator.sch              top sheet -- one comparator_dut instance
  comparator_dut.sch/.sym     the full clocked comparator
  comparator_dut_analog.sch/.sym   static preamplifier (the DC-resolvable front end)
  comparator_dut_latch.sch/.sym    StrongARM + isolation inverters + NOR SR latch
  comparator.spice            GENERATED -- do not edit
```

The topology, every device size, and the measured-record row each size is
derived from are in
[`spec/decision-records/DR-0001-comparator-topology.md`](../spec/decision-records/DR-0001-comparator-topology.md).
The pin names and **pin order** the three subcircuits must present are the
contract in [`sim/dut/README.md`](../sim/dut/README.md); `sim/harness/dut.py`
checks them textually at load time and refuses a mismatch.

## Regenerating the netlist

```bash
./design/netlist.sh            # rewrite design/comparator.spice from the .sch
./design/netlist.sh --check    # fail if the committed netlist is stale
```

That is the whole flow — it resolves the PDK through
`sim/run_corners.py --print-env` (so xschem and ngspice can never disagree
about which gf180mcu install is in play), runs xschem headless
(`-x -q -n --rcfile design/xschemrc`), and then does three things the raw
xschem output needs before the harness will accept it:

1. deletes the commented `**.subckt comparator` wrapper block, which still
   contains a live `XDUT ... comparator_dut` instance line — left in, that
   line would instantiate a second, half-floating comparator in every deck;
2. drops `.end`, because `sim/dut/README.md`'s contract reserves `.include`,
   `.lib`, `.temp`, `.control`, `.endc` and `.end` for the harness;
3. rewrites xschem's absolute `** sch_path:` stamps to repo-relative paths, so
   the committed netlist's sha256 — which every record under `sim/` stamps —
   does not depend on which directory the netlisting ran in.

Each of those is asserted rather than assumed: the script fails if there is
not exactly one wrapper block holding exactly one `comparator_dut` instance,
and it re-checks the three contract subcircuits and the forbidden directives
before writing.

## Running xschem interactively

```bash
source sim/env.sh                                   # PDK_ROOT / PDK / GF180_PDK_PATH
xschem --rcfile design/xschemrc design/comparator.sch
```

Pass `--rcfile` explicitly rather than relying on xschem's cwd-relative
`./xschemrc` auto-discovery, which only fires when xschem's working directory
happens to be `design/`.

**Hierarchical-cell symbols live next to their `.sch`, never in a `symbols/`
subdirectory.** xschem only descends into a child schematic when the
referencing symbol is found at the same relative path as a same-named `.sch`
file, and a symbol filed anywhere else netlists as an *empty* subcircuit with
no error at all — devices silently missing. `gf180-bandgap/design/README.md`
records the same trap on the same PDK.

## What is here and what is not

`design/` is schematic-level only: no parasitics, no layout, no extraction.
Post-layout extraction (`layout/`, not started) can only add capacitance at
the preamplifier output — which *lowers* measured noise — and at the input —
which *raises* measured kickback. So the noise numbers under `sim/` are
conservative in the right direction and the kickback numbers are not; DR-0001
states that asymmetry as a required post-layout re-check rather than a
formality.
