# `sim/dut/` — the device under test

Every testbench in `sim/` instantiates the DUT. The binding lives in one
file, [`sim/dut.json`](../dut.json), and the harness (`sim/harness/dut.py`)
includes it in every generated deck.

Today it points at the ratified schematic,
[`design/comparator.spice`](../../design/comparator.spice) — see "What is
bound here today" below. The repo also still ships
[`placeholder_comparator.spice`](placeholder_comparator.spice), the
deliberately crude stub that originally proved the plumbing ran before a
topology existed; it is no longer bound but is kept because real records
were committed against it (see "Placeholder history" below).

## What is bound here today

| field | value |
|---|---|
| `id` | `comparator-dr0001` |
| `provenance` | **`schematic`** |
| `netlist` | `design/comparator.spice` |

This is [DR-0001](../../spec/decision-records/DR-0001-comparator-topology.md)'s
topology: a resistively-loaded NMOS differential preamplifier
(`comparator_dut_analog`) feeding a StrongARM latch with isolation inverters
and a NOR SR output latch (`comparator_dut_latch`). See
[`design/README.md`](../../design/README.md) for the xschem source and
netlisting command.

`provenance: schematic` means records minted against this binding carry no
placeholder banner and are real schematic-level measurements — but they are
still pre-layout (no parasitics extracted). See [`sim/README.md`](../README.md)
for what that does and doesn't let you claim against the target-specification
table.

## Placeholder history

Before a topology was ratified, this file bound
[`placeholder_comparator.spice`](placeholder_comparator.spice) instead —
`id: placeholder-v1`, `provenance: placeholder`. That binding held until
commit c9bb71a rebound `sim/dut.json` to the real schematic above.

`provenance: placeholder` was load-bearing while it was live:
`sim/harness/report.py` puts a banner at the top of **every** record produced
under it saying the numbers substantiate the harness and not a spec row. A
placeholder measurement can therefore never be quoted against `README.md`'s
target-specification table by accident. The `placeholder-v1` records minted
under that binding are still committed in each experiment's `records/`
directory and still carry that banner — `sim/` is append-only evidence, so
nothing was rewritten when the binding changed.

### Why a placeholder existed at all

Before DR-0001, this repo's comparator topology was not decided. That
decision was [`spec/porting-plan.md`](../../spec/porting-plan.md) next step 1
and was explicitly out of scope for the original harness work (issue #5). But
the harness could not be *proven* to work without something to simulate —
"the four benches would run once a design exists" was exactly the kind of
untested claim this repo's `CLAUDE.md` forbids ("no claim without a
testbench").

So: a placeholder, loudly labelled, with real records committed against it,
and a one-line swap to the real design once it landed (which it has — see
"What is bound here today" above).

**The placeholder was never a topology proposal.** Its front end is a
textbook resistively-loaded NMOS pair at unconsidered sizing; its decision
stage is *behavioural* precisely so that it committed to no transistor
topology at all. Nothing about it should be read as having pre-empted the
decision record.

## Interface contract

A DUT netlist must define these three subcircuits with these pins, in this
order. `sim/harness/dut.py` checks it textually at load time and refuses a
mismatch — a silently reordered pin list would miswire all four benches into
plausible-looking wrong answers.

```
.subckt comparator_dut        vinp vinn clk ibias dout doutb vdd vss
.subckt comparator_dut_analog vinp vinn     ibias aop  aon   vdd vss
.subckt comparator_dut_latch  inp  inn  clk       dout doutb vdd vss
```

| pin | meaning |
|---|---|
| `vinp` / `vinn` | differential inputs. `v(vinp) > v(vinn)` ⇒ `dout` HIGH. |
| `clk` | decision strobe. LOW = reset, HIGH = evaluate. |
| `ibias` | bias-current input pin. The testbench forces `dut_ib` into it. |
| `dout` / `doutb` | complementary decision outputs, **held** between strobes. |
| `aop` / `aon` | front-end analog outputs. `v(aop) - v(aon) = +A_v·(v(vinp) - v(vinn))`. |
| `inp` / `inn` | decision-stage inputs — driven by `aop` / `aon` inside `comparator_dut`. |
| `vdd` / `vss` | supply and ground. |

The netlist must **not** contain `.include`, `.lib`, `.temp`, `.control`,
`.endc` or `.end` — the harness owns all of those (same rule as testbench
fragments). Operating-point parameters come from `sim/dut.json`'s `params`
map (`dut_ib`, `dut_vcm`), not from the netlist.

### Why the DUT is split into three subckts, not one

Two of the four experiments — [`comparator-offset-mc`](../comparator-offset-mc/)
and [`comparator-preamp-noise`](../comparator-preamp-noise/) — are
**small-signal analyses about a DC operating point** (`dc` sweeps and
`.noise`). A reset-and-regenerate decision stage has no DC operating point,
so `.noise` returns nothing usable for a full latched comparator and a DC
offset sweep is meaningless on one. This is the same constraint
`gf180-sar-adc` documents at length in its `sim/comparator-preamp-noise/`
testbench header.

Exposing the DC-resolvable front end separately is how those two benches stay
`.noise`/`dc`-based. `comparator_dut_latch` exists for the same reason from
the other side: the noise bench instantiates it with `clk` held low so the
front end's noise bandwidth is set by the capacitance it *actually* drives,
rather than by a lumped capacitor somebody invented — under-loading that node
would raise the bandwidth and so **under-report** the noise.

**This split is the one assumption the contract makes about the topology**,
and it is stated here rather than buried. If the ratified topology turns out
to have no DC-resolvable front end at all — a bare dynamic latch, say — then
`comparator_dut_analog` cannot be provided honestly, and the offset-MC and
preamp-noise benches must be re-founded on transient Monte Carlo / transient
noise instead (thousands of trials per corner rather than one deterministic
analysis). That is a known, named consequence of the topology decision,
recorded here so the decision record can *weigh* it rather than discover it.
It is not a reason to fake a front end.

## Swapping the binding (e.g. for a future revision or a post-layout run)

The procedure below is what already rebound this file from the placeholder
to `design/comparator.spice` (commit c9bb71a) and is the same procedure for
any future rebind — a new design revision, or a post-layout extracted
netlist:

1. Commit the netlist (e.g. a new `design/comparator.spice` revision, or an
   extracted netlist) satisfying the contract above.
2. Edit `sim/dut.json`, e.g.:

   ```json
   {
     "netlist": "../design/comparator.spice",
     "id": "comparator-dr000N",
     "provenance": "schematic",
     "params": {"dut_ib": 1e-05, "dut_vcm": 1.2}
   }
   ```

3. `python3 sim/run_corners.py --check-env` — confirms the contract is met.
4. Re-run the four experiments. Earlier records stay in `records/`
   (evidence is append-only) but every new record is stamped with the new
   `provenance` and carries no placeholder banner (unless rebinding back to
   the placeholder itself).

For a post-layout run, set `provenance` to `extracted` and point at the
extracted netlist; the record header distinguishes the two.
