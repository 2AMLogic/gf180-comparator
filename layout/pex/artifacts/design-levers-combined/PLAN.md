# Pre-cascode combined timing study (#453)

Run this plan with the batch fleet on the extracted DUT pinned by
`parasitic_attribution.load_extracted()`. Each request is one `klt sim`
job. The campaign cap is **323 requests**, including the conditional
follow-ups. Run each stage once. Stop on a missing report, an unqualified
control, or a stage that would exceed the cap. A retry of a launched job
costs another request. Collect a launched job by ID if interrupted.

| Stage | Condition and points | Requests |
|---|---|---:|
| Controls | Extracted identity and schematic at tt and ss, 125 °C, 2.97 V | 5 |
| Primary grid | Valid controls. Pair ×1.5, tail ×1.5, and pair+tail ×1.5 at each of seven cells | 63 |
| Larger pair | Only if all 21 primary cells have resolved measurements and none passes both corners. Pair ×2 at the same seven cells | 21 |
| Other failing corners | For every two-corner pass, run the other five cited misses. Four temperature/supply probe groups and five ladders per candidate | 9 per candidate |
| Kickback and offset referral | At the original two points, use the existing kickback bench with a by-path extracted binding. One shared probe and two centred main requests per DUT, including the unchanged extracted baseline for the comparison | 3 per candidate + 3 baseline if any pass |

Use (1, 1) and #264's six cells (ground-C fractions 0.75, 0.5, 0.25
crossed with series-R fractions 1, 0.5). Apply the C and R fractions to all
ground-C cards and all series-R legs. Probe every extracted variant
independently. Use the cited zero-centred schematic ladders. Compare the
four control times with the cited report using `CONTROL_TOL_NS`.
A missing control or one outside tolerance withholds all timing conclusions.

The primary branch can spend at most 5 + 63 + 21 × (9 + 3) + 3 = 323.
The optional larger-pair branch can spend at most 5 + 63 + 21 +
7 × (9 + 3) + 3 = 176. The extracted preamp-noise recorder pins both
DUT hashes to the #202 extraction and refuses a transformed DUT. Record
this gap for each passing candidate. The two-phase probe measures
deterministic offset referral. Mismatch offset requires its own bench.

Rank complete cells by measured slow-corner delay. For a layout budget,
prefer the smallest added total drawn W among candidates passing all seven
delay points, then retain as much C and R as the measured cells permit.
Report incomparable residue pairs separately. Keep the budget global and
record kickback, deterministic offset shift and any missing side effects.
Widening adds junction geometry but omits new wiring load. Pair changes
load aop/aon and require remeasurement after #112. Tail width is a
post-preamp lever. All measurements here use the pre-cascode extraction.
