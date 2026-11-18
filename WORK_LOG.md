# Work Log

Chronological record of merged pull requests and closed issues. Newest entries appear first.

### 2026-11-18

- **PR #447**: fix: accept the renderer's *(held)* row marker in the WORK_PLAN provenance checker
- **Issue #446** (closed): WORK_PLAN: annotate held issues in the machine-generated region (renderer + checker support)

### 2026-11-17

- **PR #443**: chore: prune 16 retired entries from the Loom install manifest
- **PR #441**: chore(loom): resync installed Loom to v0.19.1306
- **Issue #442** (closed): Loom install manifest lists 16 files that are not on disk (incl. a script an installed role prompt invokes)
- **PR #439**: ci: produce and upload item-1/item-10 signoff envelopes in CI
- **Issue #435** (closed): signoff: selftest.yml attests only item 9 — item 10 has no CI attestation path, so every inventoried-file edit forces a local re-produce

### 2026-11-16

- **PR #426**: chore(loom): resync installed Loom to v0.19.1302
- **PR #434**: sim: re-mint the extracted comparator-avg-power 45-corner record citable under DR-0008
- **Issue #398** (closed): signoff(sim): re-mint the extracted comparator-avg-power 45-corner record as citable under the corrected staged-source provenance check
- **PR #423**: fix: provenance guard checks the region's own shape, not just row titles
- **Issue #419** (closed): Provenance guard checks row titles but not section membership: an uncurated issue renders under 'Proposed' and CI stays green
- **PR #430**: fix: DR-0008 pinned guard compares a pinned binding config's selected entry, not the derived staged doc
- **Issue #429** (closed): klt_record: DR-0008 contradiction guard compares a derived staged doc for a pinned binding config
- **PR #427**: fix: classify gitignored staged sources as pinned provenance (DR-0008)
- **PR #424**: fix: name stale-pin and foreign causes in provenance row mismatch
- **Issue #421** (closed): sim/tools: accept a staged-and-committed sha256-matched source as pinned provenance (#398 ruling, option a)
- **Issue #416** (closed): Provenance guard: one title edit on any WORK_PLAN-referenced item reddens signoff CI on every open PR, and only a Guide tick can clear it
- **PR #422**: refactor(tests): replace importlib path-loading with sys.path + plain import in 15 test files
- **PR #420**: docs: identify klt 0.5.0 as the pinned pre-launch floor, not the fleet runner
- **PR #417**: docs: narrow parse_corner_id's strictness claim to the ratified temp range
- **Issue #425** (closed): Provenance guard: hoist the 447-char row-mismatch explanation out of the per-row loop
- **Issue #415** (closed): Replace importlib path-loading in 16 test files with #368's sys.path + plain import idiom
- **Issue #414** (closed): corners: parse_corner_id's "accepts exactly what corner_id emits" docstring is still an overstatement at :g's exponent boundary
- **Issue #405** (closed): docs: sim/README.md:30 still calls klt 0.5.0 'the fleet runner' (cm-window refusal floor)

### 2026-11-15

- **PR #413**: ci: verify WORK_PLAN.md's generated region against this repo's forge state
- **PR #412**: fix: enforce canonical corner ids in parse_corner_id
- **PR #409**: docs: drop stale backlog quantifier from ROADMAP DR-status paragraph
- **PR #401**: docs: attribute fleet request-schema gaps to the schema, not klt 0.5.0
- **PR #392**: fix: pin the cross-run counterparty by sha256 and restrict --compare-local to committed records
- **Issue #411** (closed): Guide's WORK_PLAN regeneration wrote asap7-stdcells's label state into this repo's roadmap (PR #410)
- **Issue #408** (closed): ROADMAP.md:50 claims ratification-gated work 'holds most of the open backlog'; measured, it is 3 of 15 open issues
- **Issue #406** (closed): corners.parse_corner_id is not the strict inverse its docstring claims: non-canonical temperatures parse
- **Issue #385** (closed): docs: comparator-avg-power README attributes the fleet `let` gap to klt 0.5.0, but the runner is 0.9.0
- **Issue #384** (closed): sim: cross_run_agreement cites its local record by basename, with no content hash
- **PR #407**: docs: refresh ROADMAP.md forward-looking sections against landed work
- **PR #402**: refactor: single-source the corner id format and parser in harness.corners
- **Issue #400** (closed): ROADMAP.md's Now/Next/Blocked sections present six closed issues as pending work at their own as-of commit
- **Issue #375** (closed): Consolidate the five hand-copied corner-id formatters and three divergent parsers onto sim/harness/corners.py
- **PR #399**: docs(sim): reconcile comparator-avg-power coverage prose with the committed extracted-DUT records
- **PR #393**: docs: drop volatile queue-label claims from ROADMAP.md
- **Issue #394** (closed): docs(sim): comparator-avg-power coverage prose still says the extracted-DUT campaign has not run (#374 landed)
- **Issue #379** (closed): ROADMAP.md's per-issue queue-label claims go stale within hours and nothing re-verifies them
- **Issue #364** (closed): Run the 45-corner comparator-avg-power campaign (plus the extracted DUT) that DR-0006's feasibility item 1 actually asks for
- **PR #397**: test: cover the missing-sim/harness/dut.py diagnostic in the integrator suite
- **PR #396**: signoff: inventory five omitted harness files for item 9 and refresh the CI-produced envelope
- **PR #390**: sim: commit 45-corner avg-power PVT fleet campaign record
- **PR #389**: feat(sim): extracted-binding two-phase dut_vos referral + the 45-point extracted fleet record
- **PR #388**: fix(pex): derive run_stage resume exemption from generated_by, not a hardcoded key
- **PR #386**: harness: echo restricting flags in the record Reproduce line
- **PR #381**: refactor: deduplicate the stage source_sha256 core behind one helper
- **PR #380**: refactor: replace importlib path-import blocks with the repo's sys.path import idiom
- **Issue #395** (closed): manifests/test-verify-integrator.py: no case covers the missing-sim/harness/dut.py diagnostic
- **Issue #374** (closed): sim: extracted-DUT comparator-avg-power coverage — fleet probe leg, first tb_vosprobe run, and the 45-corner extracted record
- **Issue #373** (closed): sim: run and commit the 45-corner comparator-avg-power campaign on the schematic DUT
- **Issue #371** (closed): Deduplicate the stage source_sha256 core hand-typed in all three parasitic-study manifest builders
- **Issue #368** (closed): Remove 7 hand-rolled importlib path-import blocks: the repo's own sys.path idiom already does this
- **Issue #367** (closed): signoff item 9: add four omitted harness files to the inventory and refresh the envelope from a green selftest run
- **Issue #366** (closed): run_stage's append-only check hardcodes one code-hash exemption, so resuming a lever stage after a source edit aborts
- **Issue #362** (closed): Record Reproduce line omits the run's corner-selection flags, so a subset record tells the reader to run the full grid
- **PR #387**: refactor: share the per-corner decision-time cell across the three ladder studies
- **PR #382**: Remove dead REQUIRED_POSITIVE constant in preamp_noise_pvt.py
- **PR #378**: sim: wire comparator-avg-power onto the fleet dispatch path (schematic binding)
- **PR #377**: refactor: share the duplicated item-5 source validators; fail closed on non-object derived entries
- **PR #376**: docs: reconcile signoff README verdicts with the graded report (items 1, 9, 10 are met)
- **PR #353**: docs: roadmap as of 2026-11-13
- **Issue #372** (closed): sim: wire comparator-avg-power onto the Spot-batch fleet path (schematic binding)
- **Issue #370** (closed): Consolidate the duplicated item-5 source validators in make_item5_envelope.py (the copy drifted fail-open)
- **Issue #360** (closed): Remove dead REQUIRED_POSITIVE constant in preamp_noise_pvt.py: names an invariant nothing reads
- **Issue #359** (closed): Share the per-corner decision-time cell builder: three copies of the 1.5 ns pass/fail rule derive committed evidence independently
- **Issue #354** (closed): signoff/README.md: reconcile the "Current verdict" section with the graded report (items 1, 9, 10 are met)

### 2026-11-14

- **PR #369**: evidence(noise): measure the 45-corner cascode preamp noise grid on the batch fleet
- **PR #365**: refactor(pex): classify stage.json code hashes by rule, not a fixed tuple
- **PR #361**: sim: add unscored periodic-clock bench for DR-0006's reset, supply-charge and window validation
- **Issue #363** (closed): item-9 attestation inventory omits four harness files its own scope covers, so they can change unattested
- **Issue #358** (closed): Derive the stage.json provenance key set by rule: the hardcoded allowlist already misses design_lever_study_py (#249 regression)
- **Issue #356** (closed): Add an unscored periodic-clock bench for DR-0006's pre-ratification validation (reset completion, supply charge per cycle)
- **Issue #355** (closed): Run the 45-corner preamp noise grid on the DR-0004 cascode experiment netlist

### 2026-11-13

- **Issue #88** (closed): Auditor Capability Request: worker ngspice 42 below pinned floor 46, selftest cannot run

### 2026-11-06

- **PR #350**: fix: re-pin open_pdks to f6eeac7 with ciel 2.6.1 and check tree revision
- **Issue #349** (closed): Re-pin sim open_pdks to f6eeac7 via ciel, with a revision-checked PDK search

### 2026-11-05

- **PR #346**: data: add complete 45-point paired preamp noise PVT campaign
- **Issue #209** (closed): Extend paired extracted preamp noise measurement to full PVT coverage

### 2026-11-02

- **PR #343**: feat(signoff): attest T1 item 9 with the selftest.yml-produced klt envelope
- **Issue #322** (closed): Re-audit T1 items 1, 9 and 10 under DR-0003 and attest them with klt signoff --attest

### 2026-10-29

- **Issue #67** (closed): README: embed the fleet burndown chart (one line)

### 2026-10-26

- **PR #339**: fix(kickback): nest 4-arg max() for ngspice 46 compatibility
- **Issue #336** (closed): selftest.yml: nominal comparator-kickback bench completes no points on the CI toolchain

### 2026-10-25

- **PR #337**: feat(selftest): surface failed nominal-bench ngspice logs and upload on failure
- **PR #335**: ci(selftest): attest item 9 on the toolchain runner and fix ngspice download
- **PR #334**: feat(signoff): attest T1 items 1 and 10 with klt 0.8.0 envelopes

### 2026-10-23

- **PR #332**: feat: store new sim evidence in the artifact store, commit manifests only
- **Issue #331** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

### 2026-10-17

- **PR #326**: feat: add device-lever study and proposed DR-0007 for td_od50 misses
- **PR #327**: refactor: reuse shared sha256/klt-version/git_state helpers in preamp-noise and tran-feasibility tools
- **Issue #325** (closed): Deduplicate shared helpers (parse_klt_version, git_state, sha256) across sim/layout tools
- **PR #324**: docs(signoff): add T1 item 1/9/10 inventories and DR-0003 re-audit

### 2026-10-14

- **PR #319**: sim/pex: extracted 45-point reverse-polarity campaign evidence (#164)
- **PR #317**: pex_measure: opt-in supplemental reverse-polarity campaign + 0.1 mV investigation (#164)
- **Issue #164** (closed): Extracted reverse-polarity regeneration coverage: fleet probe-leg path, and the 0.1 mV first-strobe referral gap
- **Issue #165** (closed): layout/pex/pex_measure.py: regeneration bench sha256 pins stale since #141 (and moved again by #158)
- **Issue #316** (closed): Re-run PEX attribution/budget/combo campaigns against the #158 reverse-polarity bench

### 2026-10-13

- **PR #166**: sim(regeneration): reverse-polarity (HIGH->LOW) decision-time ladder across PVT (#158)
- **Issue #158** (closed): Characterize reverse-polarity comparator delay across PVT

### 2026-10-12

- **PR #313**: docs(extracted-campaign): record #292 identity-gate completion assessment
- **PR #285**: Publish structured latch decision correctness in fleet records (#273)
- **Issue #231** (closed): Run an additive full-PVT extracted offset mismatch campaign after feasibility
- **Issue #273** (closed): Publish structured latch decision correctness in fleet records

### 2026-10-11

- **PR #310**: feat(sim): mismatch-on guard floors for transient offset benches (#309)
- **PR #308**: feat(sim): re-qualify kickback and cm-index records on the pinned open_pdks via the fleet (#288)
- **Issue #309** (closed): Add a collapsed-population (mismatch-on) guard to the whole-comparator transient offset bench
- **Issue #288** (closed): Two citable reference records were simulated with a non-pinned open_pdks revision
- **PR #306**: docs(sim): mark two records non-qualified under exact open_pdks pin; fleet probe evidence (#288)
- **PR #304**: fix(signoff): mark positive-node-only kickback fallback as incomplete item-5 coverage
- **PR #302**: fix: qualify schematic baselines against PDK revision and toolchain drift
- **PR #300**: signoff: require qualified DUT-bound sources for item-8 characterization claims
- **PR #299**: Fix wrapper fixture missing corners.py and claim-check deps (#295)
- **PR #298**: Validate characterization narrative numbers before issuing item-8 evidence
- **PR #297**: Bind extracted-offset campaign summaries to point and run identity
- **PR #294**: Validate distinct PVT corner coverage in item-8 source records
- **PR #291**: Clean-source 20261011 rerun of the 45-corner N=200 campaign (#247)
- **PR #290**: Quantify solver-tolerance sensitivity of the common-mode offset window (#240)
- **PR #287**: Qualify fleet reference evidence against the exact open_pdks revision
- **PR #286**: Mark September kickback record historical, drop #252 waiver
- **PR #284**: Enforce ngspice version floor on fleet record ingestion
- **PR #282**: ci: scheduled non-gating selftest + netlist --check workflow
- **PR #281**: feat(signoff): protect parasitic-study run archives as append-only (#266)
- **PR #279**: Reject ambiguous fleet units and duplicate ingredients (#278)
- **PR #277**: Validate characterization evidence chain before issuing item-8 pass (#275)
- **PR #271**: fix: match complete numeric tokens in claim drift guard (#268)
- **Issue #303** (closed): Mark positive-node-only kickback fallback as incomplete item-5 coverage
- **Issue #301** (closed): Qualify local schematic baselines against recorded PDK and toolchain provenance
- **Issue #296** (closed): Require qualified DUT-bound sources for current item-8 characterization claims
- **Issue #295** (closed): Build/runtime failure on main: wrapper fixtures omit corners.py after item-8 grid validation
- **Issue #293** (closed): Validate characterization narrative numbers before issuing item-8 evidence
- **Issue #292** (closed): Bind extracted-offset campaign summaries to point and run identity
- **Issue #289** (closed): Validate distinct PVT corner coverage in characterization source records
- **Issue #283** (closed): Qualify fleet reference evidence against the exact open_pdks revision
- **Issue #280** (closed): Run the harness selftest and netlist regeneration check in a non-gating scheduled CI workflow
- **Issue #278** (closed): Reject ambiguous normalized fleet units and duplicate measurement ingredients
- **Issue #275** (closed): Validate the characterization evidence chain before issuing item-8 pass
- **Issue #269** (closed): Enforce the ngspice version floor when ingesting fleet reference records
- **Issue #268** (closed): Match complete numeric values in the headline claim drift guard
- **Issue #266** (closed): Protect committed parasitic study run archives from evidence rewrites
- **Issue #252** (closed): Ledger kickback section cites schematic record 20260910-125341 as current although newer same-DUT records exist
- **Issue #247** (closed): Regenerate the extracted-offset 45x200 campaign from a clean committed source (follow-up to PR #244)
- **Issue #240** (closed): Quantify solver-tolerance sensitivity of the common-mode offset window
- **PR #274**: Preserve bundled campaign parameters in fleet record reproduction guidance
- **Issue #272** (closed): Preserve bundled campaign parameters in fleet record reproduction guidance

### 2026-10-10

- **PR #270**: Measure combined finite ground-C x series-R budgets (negative result, #264)
- **PR #267**: Require comparable committed schematic baseline for post-layout deltas
- **PR #265**: fix: fail closed when git cleanliness cannot be inspected
- **PR #263**: Reserve harness-owned PVT and dut_vos parameter names (#261)
- **PR #258**: Render actual per-corner bound verdicts in harness evidence tables
- **PR #259**: refactor(klt_record): share evidence archiving and provenance assembly
- **PR #257**: Reject invalid numeric check bounds when loading testbench manifests
- **PR #244**: feat(sim): extracted offset 45-point N=200 campaign results (experimental) (#231)
- **PR #253**: Guard published headline claims against drift from committed records (#245)
- **Issue #264** (closed): Measure combined finite parasitic budgets after the four-net ground-C study failed
- **Issue #262** (closed): Require a comparable committed schematic baseline for post-layout deltas
- **Issue #260** (closed): Fail closed when simulation source cleanliness cannot be verified
- **Issue #261** (closed): Prevent testbench redefinition of harness-owned PVT and offset parameters
- **Issue #255** (closed): Render actual per-corner bound verdicts in harness evidence tables
- **Issue #254** (closed): Simplify klt_record: share evidence archiving and provenance assembly
- **Issue #256** (closed): Reject invalid numeric check bounds when loading testbench manifests
- **Issue #245** (closed): Guard published headline claims against drift from committed evidence records
- **PR #250**: feat(signoff): size budget guard for protected sim/ evidence
- **PR #249**: Finite ground-C budget sweep for the post-layout delay gap (#243)
- **PR #248**: fix(pex): narrow pex_measure tb.json pin to deck fields + graded bounds (#241)
- **PR #242**: feat(pex): attribute the post-layout td_od50 misses to extracted parasitics (#229)
- **PR #237**: Protect committed probe artifacts with the append-only evidence guard
- **PR #236**: feat(sim): extracted offset 45-point campaign tool (experimental, not yet run) (#231)
- **PR #235**: docs(signoff): refresh item-10 CI disclosure and grader rulebook comments
- **PR #234**: feat: full 45-point common-mode window record for monotonic-index bench (#218)
- **PR #230**: docs: refresh whole-comparator offset headline to 45-point campaign
- **PR #228**: feat(signoff): score item-5 kickback on the both-node record (r4)
- **Issue #246** (closed): Set an evidence size budget for new protected sim/ artifacts
- **Issue #243** (closed): Establish finite routing-capacitance budgets for the post-layout delay gap
- **Issue #241** (closed): pex_measure.py's whole-file tb.json pin is stale since #181, so run_pex.py cannot regenerate item 7
- **Issue #239** (closed): Checkpoint orchestration blocked by worktree-write-confinement: investigate target routing
- **Issue #238** (closed): Auditor guard decision: keep unresolved-variable removal flagged
- **Issue #233** (closed): Refresh signoff item-10 CI disclosure after harness and source-pin checks landed
- **Issue #232** (closed): Protect committed feasibility probe artifacts with the append-only evidence guard
- **Issue #229** (closed): Attribute the 7 post-layout decision-time misses (T1 item 7) to extracted parasitics
- **Issue #223** (closed): Refresh headline whole-comparator offset claims after the 45-point campaign
- **Issue #218** (closed): Measure the consumer common-mode window with a monotonic index stimulus
- **Issue #204** (closed): Repin item-5 kickback row to the both-node schematic record (new scoring revision)

- **Issue #225** (closed): Guard README bench inventory: fix stale 'seven bench directories' and check it in bench-inventory
- **Issue #219** (closed): Establish extracted-layout transient offset Monte Carlo feasibility
- **Issue #177** (closed): Test run_lvs interface-pin and device-geometry contract checks
- **Issue #216** (closed): Reconcile bench inventory docs and guard characterize.sh coverage
- **Issue #212** (closed): Close unclosed file handles in layout scripts and make ResourceWarning fail the PDK-free suite
- **Issue #197** (closed): Auditor guard telemetry: stash-scope:create-redirect — keep flagged
- **Issue #210** (closed): Correct current characterization report ratification and average-power verdicts
- **PR #226**: Fix README bench count; add README-DRIFT checks (#225)
- **PR #224**: Establish extracted-layout transient offset Monte Carlo feasibility (#219)
- **PR #222**: feat: monotonic-index common-mode stimulus, semantics fixture, nominal fleet probe (#218)
- **PR #221**: test: cover run_lvs interface-pin and device-geometry contract checks
- **PR #220**: Reconcile bench inventory docs and guard characterize.sh coverage
- **PR #215**: Close unclosed file handles; fail PDK-free suite on ResourceWarning
- **PR #217**: feat(pex): paired preamp-noise 45-point PVT path; stopped at fleet executor-capability gate (#209)
- **PR #214**: docs: correct characterization report ratification and average-power verdicts
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
