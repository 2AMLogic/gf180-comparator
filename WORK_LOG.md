# Work Log

Chronological record of merged pull requests and closed issues. Newest entries appear first.

### 2026-10-04

- **PR #77**: docs: score noise, decision-time, kickback, supply-power rows against the ratified target-spec
- **Issue #75** (closed): spec: score the noise / decision-time / kickback / supply-power rows against the ratified target-spec

### 2026-10-03

- **PR #76**: docs: reconcile target-spec ratification status across repo docs
- **Issue #26** (closed): repo: final hygiene pass to close out T1 checklist (T1 item 10)

### 2026-10-02

- **PR #74**: spec: re-ratify DR-0002 via the two-key ceremony (EE + market keys)
- **PR #73**: feat: post-layout extracted-netlist simulation for regeneration and kickback
- **PR #72**: ratification: install the two-key reviewer variant (EE key + market key)
- **PR #70**: chore: cite the passing LVS report for T1 item 4 and re-grade (3/11)
- **Issue #71** (closed): Install the two-key reviewer variant and run the DR-0002 ratification ceremony (#3)
- **Issue #23** (closed): Post-layout (extracted-netlist) simulation (T1 item 7)
- **Issue #22** (closed): Layout signoff: LVS clean run (T1 item 4)
- **Issue #30** (closed): layout: complete comparator routing to reach LVS-clean (follow-up to #22)
- **Issue #68** (closed): signoff: cite the now-passing LVS report for T1 item 4 and re-grade (and re-check item 11)

### 2026-10-01

- **PR #69**: layout: LVS reaches status "match", error_count 0
- **Issue #40** (closed): layout: reach klt lvs status: match once the placeholder-0 resistor-value gap lands upstream

### 2026-09-22

- **PR #66**: docs: name consumers in the spec, publish the integrator view as data
- **Issue #64** (closed): 2am: reuse rule 9 — name this block's consumers in the spec, carry their requirement rows, publish the integrator view as data

### 2026-09-21

- **PR #63**: fix: drop netlist.sh no-op path-stamp re.sub, assert repo-relative stamps
- **PR #61**: feat: add klt erc supply spec and structural power-delivery report
- **PR #60**: docs: add narrative characterization report to measurements/
- **PR #58**: docs: score offset-sigma row against the ratified target-spec table
- **PR #59**: feat: add klt signoff block manifest as T1 verdict of record
- **Issue #62** (closed): Remove no-op re.sub in design/netlist.sh path-stamp rewrite (identity substitution masks the line's claim)
- **Issue #56** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo
- **Issue #25** (closed): docs: one-command narrative characterization report (T1 item 8)
- **Issue #24** (closed): sim: score offset Monte Carlo evidence against ratified target-spec (T1 item 6)
- **Issue #57** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read

### 2026-09-19

- **PR #27**: docs: draft DR-0002 proposing ratification of target-spec table
- **Issue #17** (closed): Ratify target-spec table via decision record (T1 item 5)

### 2026-09-18

- **Issue #47** (closed): Remove duplicated klt drc invocation logic in layout/run_drc.py and route_nets.py

### 2026-09-16

- **PR #55**: refactor: give the klt lvs invocation one home in run_lvs.py
- **PR #54**: fix: remove unused Pdk.xschem_dir property
- **PR #51**: fix: drop grep -q from verify-proposal-refs.sh to avoid pipefail/SIGPIPE false misses
- **PR #50**: fix: keep comparator.gen-compose.json's gds_path repo-relative
- **PR #49**: fix: wire package.json check:ci/test to the harness's real verification
- **PR #44**: refactor: give the klt drc invocation one home in run_drc.run_drc()
- **PR #43**: lvs: assert drawn device geometry against the schematic's own netlist; re-verify #30's criteria on klt 0.5.0
- **PR #41**: layout: route every net, fix the latch input crossing, drive LVS from 102 errors to 6 (#30)
- **PR #39**: fix: drop redundant klayout_version fragment from run_lvs.py summary line
- **PR #37**: layout: close klt gen-compose's metal1.space.1 violations, DRC clean (#20)
- **PR #36**: docs: document floorplan-vs-row evaluation for kickback separation
- **Issue #53** (closed): Simplify: dedupe klt lvs request+invoke+report logic in run_lvs.py
- **Issue #52** (closed): Remove Pdk.xschem_dir: unused property, no Python consumer
- **Issue #48** (closed): verify-proposal-refs.sh: grep -q under pipefail causes false MISSING FILE reports
- **Issue #45** (closed): layout: comparator.gen-compose.json embeds an absolute host path, breaking the README's byte-reproducibility check
- **Issue #46** (closed): Wire package.json check:ci/test to the harness's real verification (currently no-op stubs)
- **Issue #42** (closed): Remove duplicated klt-DRC invocation: run_drc() copy-pasted across layout/run_drc.py and layout/fix_metal1_space.py
- **Issue #38** (closed): Remove redundant klayout_version print in run_lvs.py (same value as engine_version)
- **Issue #20** (closed): Layout signoff: DRC clean run (T1 item 3)
- **Issue #28** (closed): layout: evaluate a 2D floorplan to shrink kickback-risk input/clk separation further (follow-up to #18)

### 2026-09-15

- **PR #35**: chore: remove unused ToolchainDrift exception class
- **PR #33**: docs: rebind sim/dut docs to the current schematic DUT binding
- **PR #31**: layout: run klt lvs against comparator.gds, document honest mismatch (#22)
- **PR #29**: layout: commit GDS implementing DR-0001 comparator topology
- **PR #16**: chore: remove unused pdk_available() and git_dirty() helpers
- **Issue #34** (closed): Remove unused ToolchainDrift exception class in sim/harness/toolchain.py
- **Issue #32** (closed): docs: sim/dut.json _comment and sim/dut/README.md still describe the placeholder DUT, contradicting the file's own fields
- **Issue #18** (closed): layout: create GDS/OASIS for the comparator (T1 item 2)
- **Issue #21** (closed): docs: check off T1 item 9 (testbenches shipped) with PR attribution
- **Issue #11** (closed): Remove unused pdk_available() and git_dirty() helpers
- **Issue #19** (closed): Layout: committed GDS/OASIS for the comparator (T1 item 2)

### 2026-09-11

- **Issue #15** (closed): permission-probe-delete-me

### 2026-09-10

- **PR #14**: sim: mint schematic-provenance records for DR-0001 comparator design
- **Issue #12** (closed): design: comparator topology decision record (DR-0001) + first `design/comparator.sch` (preamp + StrongARM latch) bound into `sim/dut.json`, with all four benches re-run at `provenance: schematic`
- **Issue #13** (closed): loom-doctor-write-check-1854765

### 2026-09-09

- **PR #10**: sim/harness: raise on colliding corner_id in build_grid()
- **PR #9**: fix: surface non-fatal ngspice errors as PointResult.warnings
- **PR #6**: sim: stand up the PVT harness and the four comparator experiment directories
- **Issue #8** (closed): sim harness: PvtPoint.corner_id has no uniqueness check — custom --supply-tolerance/--temps can silently collapse distinct PVT points
- **Issue #7** (closed): sim harness: run_point() treats a non-fatal ngspice error as status=ok when all measurements still parse
- **Issue #5** (closed): sim: stand up the harness + four comparator experiment directories with standalone stimuli, ported from gf180-sar-adc (porting-plan next steps 2-3)

### 2026-09-06

- **PR #4**: docs: draft target-spec table, porting plan, and gap-to-T1 tracker
- **Issue #2** (closed): Bootstrap the block: draft target-spec, porting/design plan, gap-to-T1 tracker (wave-5 standup completion)
