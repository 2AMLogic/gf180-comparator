#!/usr/bin/env python3
"""Adapt a committed offset-MC record's per-draw samples into a `klt yield`
sample-set document (issue #82).

No simulation is run. The harness prints every draw's `voa` (input-referred
offset, volts) into the per-corner ngspice log, so the raw samples are
already in the committed evidence trail; this script only re-reads them.

Cross-checks before writing anything (it refuses on any mismatch, so the
sample set can never silently drift from the record it claims to come from):
  * every `ok` point in the record has a log with exactly `n_samples` draws;
  * the population sigma of the parsed draws reproduces the record's
    `sig_vos_mv` and the mean reproduces `mean_vos_uv` (ngspice prints 10
    significant digits; tolerance is 1e-6 relative).

Negative control (deterministic, no RNG): the same draws with a forced
+NEG_SHIFT_V offset added -- the "forced offset" defect the klt yield docs
name. It exercises the *statistic*, not the circuit; see README.md.

Usage (from the repo root):
    python3 sim/comparator-offset-mc/yield/adapt_samples.py \
        sim/comparator-offset-mc/records/20260910-124917-4805118.json \
        sim/comparator-offset-mc/yield/samples-20260910-124917-4805118.json
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

NEG_SHIFT_V = 0.020  # forced offset: 20 mV > the 15 mV target limit
VOA = re.compile(r"^voa = (\S+)\s*$", re.M)


def main(record_path: str, out_path: str) -> int:
    rec_file = Path(record_path)
    rec = json.loads(rec_file.read_text())
    rid = rec["record_id"]
    logdir = rec_file.parent.parent / "corners" / rid
    measurements = []
    for pt in rec["points"]:
        if pt["status"] != "ok":
            sys.exit(f"{pt['corner_id']}: status {pt['status']} -- refusing")
        m = pt["measurements"]
        draws = [float(x) for x in VOA.findall((logdir / pt["log"]).read_text())]
        n = int(m["n_samples"])
        if len(draws) != n:
            sys.exit(f"{pt['corner_id']}: parsed {len(draws)} draws, record says {n}")
        mean = sum(draws) / n
        sig = math.sqrt(sum(d * d for d in draws) / n - mean * mean)  # population, as tb.json
        for got, want, what in ((sig * 1e3, m["sig_vos_mv"], "sig_vos_mv"),
                                (mean * 1e6, m["mean_vos_uv"], "mean_vos_uv")):
            if abs(got - want) > 1e-6 * max(abs(want), 1e-12):
                sys.exit(f"{pt['corner_id']}: {what} {got!r} != record {want!r}")
        measurements.append({
            "name": f"vos_v@{pt['corner_id']}",
            "unit": "V",
            "samples": draws,
            "source_corners": [pt["corner_id"]],
            "negative_control": {
                "samples": [d + NEG_SHIFT_V for d in draws],
                "description": (f"same draws with a forced +{NEG_SHIFT_V * 1e3:.0f} mV "
                                "offset added (deterministic, no RNG)"),
            },
        })
    doc = {
        "description": (f"Input-referred offset draws (V) of record {rid}, one measurement "
                        "per PVT point (each point is its own population; common random "
                        "numbers across points, so they are not pooled). Parsed from the "
                        f"committed per-corner logs by adapt_samples.py; seed 20260909 "
                        f"(ngspice setseed), N={rec['points'][0]['measurements']['n_samples']:.0f} per point."),
        "record_id": rid,
        "measurements": measurements,
    }
    Path(out_path).write_text(json.dumps(doc, indent=1) + "\n")
    print(f"wrote {out_path}: {len(measurements)} measurements x "
          f"{len(measurements[0]['samples'])} draws")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
