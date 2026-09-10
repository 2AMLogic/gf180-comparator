# `sim/comparator-preamp-noise/`

**Input-referred noise** of the comparator front end over the full PVT grid,
via ngspice `.noise`, reported as **total integrated output noise divided by
the measured DC gain**.

Backs [`README.md`'s noise row](../../README.md#target-specification-draft--engineering-to-ratify)
(≤ 1.0 mV rms differential, ≤ 0.6 mV stretch) and, together with
`sim/comparator-regeneration/`'s τ, the noise-floor half of the metastability
story.

```bash
python3 sim/run_corners.py comparator-preamp-noise -j 8
```

## Method

One `op`, two `.noise` runs (1 Hz–1 GHz and 1 kHz–1 GHz) and one `.ac`, per
PVT point.

**The quoted number is `onoise_total / A_v(DC)`, not ngspice's own
`inoise_total`.** That is the whole reason this bench was worth porting: the
sibling repo's own record documents a prior **200× magnitude error** from
reporting `sqrt(onoise_total)` directly as the answer. Both referrals are in
the record side by side:

| measurement | what it is |
|---|---|
| `vn_in_uv` | **the quoted number** — integrated output noise ÷ measured DC gain |
| `inoise_band_uv` | ngspice's own input referral over the same band |

**They are not expected to agree, and the record shows why.** ngspice refers
each frequency bin through the AC transfer function *at that frequency*, so
every bin above the front end's bandwidth is divided by a rolled-off gain and
inflates the total. On the committed record ngspice's figure runs several
times larger for exactly that reason. Keeping both makes the divergence an
explained property of two referrals rather than an unexplained factor
somebody rediscovers later — which is precisely what the sibling's 200× error
was.

**Total integrated noise, not a density.** A comparator *samples* its input
noise at the decision instant rather than filtering it, so the band-limited
total is the relevant quantity. That is why the integration runs to 1 GHz
rather than to some assumed signal bandwidth, and why `enbw_mhz` is reported
so a reader can re-derive the total by hand as (density × √ENBW).

**The two-band split is the flicker story.** `vn_in_hf_uv` integrates from
1 kHz up; `flicker_frac_pct` is the sub-kHz share of the noise *power*.
Sub-kHz noise drifts slowly enough to behave as an offset rather than as
per-decision noise, so keeping the split visible is what lets a reader
separate the two. `fnoicor` is at the PDK default (0, as-extracted) and the
flicker fraction is what a reader rescales to see whether the worst-case
setting would change any verdict.

**The decision stage is instantiated, with its clock held low.** It draws no
current in reset, but its input capacitance is part of the load that sets the
front end's noise bandwidth. Omitting it would over-state the bandwidth and
therefore *over*-state the noise; replacing it with an invented lumped
capacitor would make the answer depend on the invention.

## What this bench cannot reach

`.noise` is a small-signal analysis about a DC operating point. A
reset-and-regenerate decision stage has none, and ngspice offers no
PSS/pnoise and no automatic device-level transient noise. So the decision
stage's own noise is **not in this record** and is not claimed. Referred to
the comparator input it is divided by the gain measured here, which is why
the front end is where a noise budget gets closed. See
[`sim/dut/README.md`](../dut/README.md) for what happens to this bench if the
ratified topology turns out to have no DC-resolvable front end at all — that
is a named consequence for the topology decision to weigh, not a gap to paper
over.

## Provenance

Methodology ported from
[`gf180-sar-adc/sim/comparator-preamp-noise/`](https://github.com/2AMLogic/gf180-sar-adc/tree/main/sim/comparator-preamp-noise),
per [`spec/porting-plan.md`](../../spec/porting-plan.md).

**Ported:** the divide-integrated-output-noise-by-measured-DC-gain
methodology and the units caution behind it; the two-band (full / >1 kHz)
split and its flicker-as-slow-offset rationale; instantiating the decision
stage in reset for its loading; stating the `fnoicor` setting on every
flicker number; reporting ENBW and the white density so the integral can be
checked by hand; the "under-load the output node, because that is the
conservative direction" convention for the routing allowance.

**Deliberately NOT ported:**

- **The topology and its sizing**, and its ≈ 0.08–0.13 mV rms result.
- **The 10-µs-conversion / ten-bit-trial argument** for which noise is
  correlated across decisions. That is a SAR sequencing property; a
  standalone comparator has no conversion to span, so the flicker split is
  reported as a property of the block and the correlation argument is left to
  whoever integrates it.
- **`.nodeset` operating-point hints.** That repo's deck needs them for its
  specific bias arrangement; this bench converges without, and a hint that is
  not needed is a hidden dependency on a guess.
- **The `av_dc`/`f3db` pair's specific numeric bounds**, which are that
  design's. `av_dc` is kept, but as a *sensitivity anchor* with a
  unity floor rather than as a gain specification.

## Records

| record | DUT | grid | verdict |
|---|---|---|---|
| [`20260910-000413-3383e41`](records/20260910-000413-3383e41.md) | `comparator-dr0001` (**schematic**) | 45/45, `mos` × 3 T × 3 V | PASS |
| [`20260909-055524-e2bb637`](records/20260909-055524-e2bb637.md) | `placeholder-v1` (**placeholder**) | 45/45, `mos` × 3 T × 3 V | PASS |

The first row is the current reference: taken against
[DR-0001](../../spec/decision-records/DR-0001-comparator-topology.md)'s
static preamp + StrongARM latch, no placeholder banner. `vn_in_uv` is
91.25 µV rms at nominal, 128.8 µV rms worst-case — comfortably inside both
the README ≤ 1.0 mV target and the ≤ 0.6 mV stretch (reference against a
still-DRAFT row, not a verdict). The `av_dc` per-axis floors (calibrated
against the placeholder DUT, below) held on the real schematic with margin
and were not recalibrated.

**Read the banner on the placeholder row.** It was taken against the
placeholder DUT and substantiates the harness, not the noise row; it stays
committed as append-only evidence but is superseded as the current
reference. It is also the record the `av_dc` per-axis floors are calibrated
from (observed weakest slices: process 32.57 %, temperature 44.55 %).
