# Work Log

Chronological record of merged pull requests and closed issues. Newest entries appear first.

### 2026-10-10

- **Issue #188** (closed): Test run_extract_sim.py: netlist adaptation, positional pin wiring and fail-closed branches
- **Issue #189** (closed): Test verify-report.py grade_drift and pin checks, the signoff anti-rot gate
- **Issue #190** (closed): Test pex_measure.py pure helpers: template edits, derivation and grading
- **Issue #157** (closed): Measure total comparator offset: transient Monte Carlo covering the latch, plus a hand budget for load-resistor mismatch
- **Issue #194** (closed): Remove duplicated INTERFACE_PINS in layout/pex/run_pex.py and pin the contract in a test
- **Issue #193** (closed): Test gen_comparator connectivity tables against the netlist and committed placement evidence
- **Issue #200** (closed): Expand whole-comparator transient offset evidence to the full 45-point PVT grid
- **Issue #160** (closed): Measure kickback peaks on both comparator input nodes
- **Issue #184** (closed): Test layout route_nets channel-assignment helpers and the run_drc exit-code contract
- **Issue #202** (closed): Establish extracted preamp observation nodes for a paired post-layout noise feasibility probe
- **Issue #182** (closed): Prove paired preamp common-mode measurement feasibility for the consumer window
- **Issue #208** (closed): Test preamp_noise_probe fail-closed helpers and deck builder PDK-free
- **PR #191**: test(layout): cover run_extract_sim.py adaptation and fail-closed branches
- **PR #192**: test(signoff): cover verify-report.py drift and pin checks
- **PR #195**: test(pex): cover pex_measure pure helpers (#190)
- **PR #196**: Measure total comparator offset: thread-pinned transient MC record + load-R budget (#157)
- **PR #198**: Dedupe INTERFACE_PINS in run_pex and pin contract in a test (#194)
- **PR #199**: test(layout): cross-check gen_comparator tables vs netlist and evidence (#193)
- **PR #201**: Expand whole-comparator transient offset evidence to the full 45-point PVT grid
- **PR #203**: evidence(sim): both-node kickback schematic 45-corner record (#160)
- **PR #205**: test(layout): route_nets helpers and run_drc exit-code contract
- **PR #206**: Extracted preamp observation nodes and paired nominal noise feasibility probe
- **PR #207**: feat(sim): consumer-window CM paired-measurement feasibility; refuse unsupported fleet path (#182)
- **PR #211**: test(pex): PDK-free tests for preamp_noise_probe (#208)

### 2026-10-09

- **Issue #183** (closed): Test harness CLI main() refusal paths and the sabotage no-write guarantee
- **Issue #181** (closed): Refresh live simulation claims and reproduction guidance after spec ratification
- **PR #186**: test(harness): cover cli main() refusal paths and sabotage no-write (#183)
- **PR #187**: docs(sim): refresh live bench claims and reproduction guidance (#181)

- **PR #180**: test(harness): cover summarize() bound and per-axis branches (#176)
- **PR #179**: test(harness): cover testbench load/validation and PDK discovery (#172)
- **PR #178**: test(harness): cover toolchain drift gate (#171)
- **PR #173**: Reject invalid numeric inputs in offset yield sample adaptation
- **PR #175**: feat(sim): whole-comparator transient MC offset bench + load-R hand budget (fleet run pending) (#157)
- **PR #174**: Enforce byte identity of the pinned signoff rulebook (#168)
- **PR #170**: Measure kickback peaks on both comparator input nodes (#160)
- **PR #167**: Validate integrator paths, ordered ports, top subckt and area against committed artifacts
- **Issue #176** (closed): Test summarize() bound and per-axis sensitivity branches in sim/harness/report.py
- **Issue #172** (closed): Test testbench manifest validation and PDK discovery precedence in the sim harness
- **Issue #171** (closed): Test the toolchain drift gate (sim/harness/toolchain.py check and CLI enforcement)
- **Issue #169** (closed): Reject invalid numeric inputs in offset yield sample adaptation
- **Issue #168** (closed): Enforce byte identity of the pinned signoff rulebook
- **Issue #161** (closed): Validate integrator paths, ordered ports and area against committed artifacts
- **PR #162**: Assert reference False on not-citable records; check all staged testbench files vs clean commit (#156)
- **PR #159**: fix(sim): reject non-finite local measurements and fleet-derived results
- **PR #155**: fix(sim): bind replayed fleet evidence to its originating source bundle
- **PR #153**: Validate exact fleet PVT and MC coverage before reference scoring (#152)
- **PR #150**: ci: enforce append-only sim/ evidence with a base-comparison guard
- **PR #149**: Preserve partial simulator logs and probe warnings on timeout
- **PR #147**: ci: preserve started main Signoff runs (#145)
- **Issue #156** (closed): Test the complete-but-not-citable reference gate; widen clean-commit cross-check to all staged testbench files
- **Issue #154** (closed): Reject non-finite local measurements and fleet-derived results
- **Issue #151** (closed): Bind replayed fleet evidence to the originating DUT and testbench sources
- **Issue #152** (closed): Validate exact fleet PVT and Monte Carlo coverage before reference scoring
- **Issue #135** (closed): CI: enforce the append-only rule for sim/ evidence records
- **Issue #148** (closed): Preserve partial simulator logs and probe warnings on timeout
- **Issue #145** (closed): CI: preserve started main Signoff verification during merge bursts
- **PR #144**: test: PDK-free coverage for klt_record.py and mk_klt_request.py (#142)
- **PR #143**: sim: add td_od1_over_tau, deprecate mislabelled resolve_decades (#141)
- **PR #140**: spec: propose DR-0006 average-power operating condition (proposed, not ratified)
- **PR #139**: ci: run routing_table.py --check and add regression test (#121)
- **PR #138**: spec: propose DR-0005 metastability target (proposed, not ratified)
- **PR #137**: Pin repository-local netlisting configuration and recipe inputs
- **PR #132**: docs: refresh README status and split target-spec evidence into a ledger
- **PR #133**: Unify the PDK-free test entrypoint so npm test matches CI (#129)
- **PR #131**: ci: enforce klayout-tools grader pin consistency (#128)
- **PR #127**: Make item-5 envelope input validation survive python -O (#126)
- **PR #122**: ci: PDK-free netlist source-pin check (#120)
- **PR #119**: Verify derived signoff wrappers against their source records
- **PR #118**: ci(signoff): run PDK-free harness unittest suite (#110)
- **PR #117**: Keep unscored average power from passing T1 item 5 (scoring revision 2)
- **Issue #142** (closed): Test the evidence-minting path: PDK-free tests for klt_record.py derive() and the local-grid refusal guard
- **Issue #141** (closed): Correct the mislabelled resolve_decades metastability diagnostic (it is an e-fold ratio)
- **Issue #121** (closed): CI: run layout/routing_table.py --check and add a regression test for it
- **Issue #134** (closed): Draft the metastability target-spec decision and two-key ratification package
- **Issue #124** (closed): Auditor guard decision: keep git clean -fd flagged
- **Issue #136** (closed): Pin repository-local netlisting configuration and recipe inputs
- **Issue #130** (closed): docs: refresh README status and split bloated target-spec evidence cells into a ledger
- **Issue #129** (closed): Unify the PDK-free test entrypoint so npm test matches what CI runs
- **Issue #128** (closed): CI: enforce that the klayout-tools grader pin matches across workflow, regenerate.sh and verify-report.py
- **Issue #126** (closed): Make corner evidence input validation survive Python optimization
- **Issue #120** (closed): CI: PDK-free netlist source-pin check so a stale design/comparator.spice fails CI (enables T1 item 1)
- **Issue #111** (closed): Verify derived signoff wrappers against their source records
- **Issue #110** (closed): Run existing PDK-free harness regressions in GitHub Actions
- **Issue #108** (closed): Keep incomplete average-power coverage from passing T1 corner verification

- **PR #115**: Qualify consumer decision-speed verdict at half-LSB overdrive (#109)
- **PR #114**: signoff: cite klt pex report for T1 item 7 (#81)
- **PR #113**: design: cascode the preamp input pair; DR-0004 kickback result (45/45 schematic corners)
- **Issue #109** (closed): Substantiate consumer decision timing at the consumer overdrive
- **Issue #81** (closed): T1 item 7: produce a klt pex report from the committed post-layout records and cite it
- **Issue #102** (closed): design: reduce comparator kickback to the ratified 5 mV target (sole blocker of T1 item 5)

### 2026-10-08

- **PR #107**: signoff: declare ties[] in klt erc supply spec; item 11 grades met
- **PR #105**: refactor(layout): consolidate duplicated extract constants and run_extract (#101)
- **PR #100**: Preserve offset-probe simulator diagnostics in post-layout evidence
- **PR #99**: fix(sim): prevent run collisions from overwriting evidence
- **PR #98**: feat(signoff): cite derived corner-matrix envelope for T1 item 5 (#91)
- **PR #97**: signoff: bump grader to klayout-tools 0.6.0, re-grade T1 item 11
- **PR #96**: signoff: audit T1 items 1, 9, 10; leave uncited, disclose (DR-0003)
- **PR #93**: fix(manifests): mirror integrator maturity rung with the graded signoff tier
- **PR #92**: feat(signoff): wrap characterization report in a generic evidence envelope for T1 item 8
- **PR #87**: feat(signoff): cite klt yield report for offset MC as T1 item 6 (#82)
- **Issue #101** (closed): Consolidate duplicated extract constants and run_extract across layout/run_*.py
- **Issue #103** (closed): signoff: declare ties[] in the klt erc supply spec now that the upstream blocker is closed (T1 item 11)
- **Issue #86** (closed): Preserve offset-probe simulator diagnostics in post-layout evidence
- **Issue #85** (closed): Prevent simulation run collisions from overwriting append-only evidence
- **Issue #91** (closed): signoff: cite corner-matrix evidence for T1 item 5 (full corner verification)
- **Issue #89** (closed): signoff: honestly back T1 items 1, 9, 10 with disclosed envelope citations
- **Issue #90** (closed): signoff: bump grader pin so T1 item 11 (erc evidence) is recognized, then re-grade
- **Issue #84** (closed): Keep integrator maturity consistent with the signoff verdict
- **Issue #80** (closed): T1 item 8: wrap the characterization report in a generic evidence envelope, cite, re-grade
- **Issue #82** (closed): T1 item 6: produce a klt yield report for the offset Monte Carlo campaign and cite it

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
