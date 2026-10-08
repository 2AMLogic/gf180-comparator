#!/usr/bin/env python3
"""Emit `klt sim` requests for the four benches, derived from their tb.json.

Why this exists: `sim/run_corners.py` fans ngspice out from the invoking
host. Shared dispatch workers must not run SPICE grids themselves; they
express the grid as a `klt sim` request and let `KLT_SIM_BACKEND=batch` send
it to the Spot fleet. The request is derived from the bench's own `tb.json`,
`sim/dut.json` and `sim/harness/corners.py`, so the corner list, supply
points, DUT binding, fragment and measurement definitions are the harness's,
not a second hand-maintained copy.

One `klt sim` request carries ONE analysis, so a bench becomes one or more
"legs":

    comparator-kickback     leg `main`  (tran + .meas cards)
    comparator-regeneration leg `main`  (tran + .meas cards)
    comparator-preamp-noise leg `noise` (noise 1 Hz..1 GHz), leg `ac` (gain)
    comparator-offset-mc    leg `main`  (monte_carlo, one dc sweep per draw)

Derived quantities (`tb.json` "measure") are computed from the raw per-leg
values by `sim/tools/klt_record.py`; the `.meas` cards / expressions below
are the raw ingredients.

    python3 sim/tools/mk_klt_request.py BENCH OUTDIR [--corners ...]
        [--temps ...] [--supply-tolerance F] [--mc-n N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))

from harness import corners as hc  # noqa: E402
from harness import dut as hdut  # noqa: E402
from harness import pdk as hpdk  # noqa: E402
from harness import testbench as htb  # noqa: E402

#: ngspice 46 prints `.meas` results with 5 mantissa decimals by default;
#: widen so sub-microvolt kickback differences are not quantised away.
NGSPICE_INIT = ["set measureprec=12", "set numdgt=12"]

OFFSET_MC_SEED = 20260909
OFFSET_MC_N = 200


def tran_meas_cards(tb) -> list[dict]:
    """`meas tran ...` analysis lines -> klt `.meas` measurement entries."""
    out = []
    for line in tb.analyses[1:]:
        parts = line.split()
        if parts[0] != "meas":
            raise SystemExit(f"{tb.name}: unexpected analysis card {line!r}")
        out.append({"name": parts[2], "spice": "." + line})
    return out


def legs_for(bench: str, tb, mc_n: int) -> dict[str, dict]:
    """leg name -> {analysis, measurements, monte_carlo?}."""
    if bench in ("comparator-kickback", "comparator-regeneration"):
        kind, args = tb.analyses[0].split(None, 1)
        return {"main": {"analysis": {"kind": kind, "args": args},
                         "measurements": tran_meas_cards(tb)}}
    if bench == "comparator-preamp-noise":
        return {
            "noise": {
                "analysis": {"kind": "noise", "args": "v(aop,aon) vd dec 20 1 1e9"},
                "measurements": [
                    {"name": "onoise_total", "expr": "onoise_total", "unit": "V"},
                    {"name": "inoise_total", "expr": "inoise_total", "unit": "V"},
                ],
            },
            "ac": {
                "analysis": {"kind": "ac", "args": "dec 20 1 1e9"},
                "measurements": [
                    {"name": "av_dc", "expr": "mag(v(aop)-v(aon))[0]", "unit": "V/V"},
                ],
            },
        }
    if bench == "comparator-offset-mc":
        # Scalars only (klt `expr` must reduce to one real number): the six
        # operating points of `dc vd 0 2m 2m vcmd -50m 50m 50m`, then the
        # same algebra the bench's .control loop uses.
        m = [{"name": f"dv{i}", "expr": f"v(aop)[{i}]-v(aon)[{i}]", "unit": "V"} for i in range(6)]
        m += [
            {"name": "avc", "expr": "(dv1-dv0)/2e-3"},
            {"name": "ava", "expr": "(dv3-dv2)/2e-3"},
            {"name": "ave", "expr": "(dv5-dv4)/2e-3"},
            {"name": "voc", "expr": "-dv0/avc", "unit": "V"},
            {"name": "voa", "expr": "-dv2/ava", "unit": "V"},
            {"name": "voe", "expr": "-dv4/ave", "unit": "V"},
            {"name": "ddc", "expr": "voc-voa", "unit": "V"},
            {"name": "dde", "expr": "voe-voa", "unit": "V"},
            {"name": "drr", "expr": "v(rpa)[2]-v(rpb)[2]", "unit": "V"},
        ]
        return {"main": {
            "analysis": {"kind": "dc", "args": "vd 0 2m 2m vcmd -50m 50m 50m"},
            "measurements": m,
            "monte_carlo": {"n": mc_n, "seed": OFFSET_MC_SEED, "vary": "mismatch"},
        }}
    raise SystemExit(f"unknown bench {bench!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("outdir")
    ap.add_argument("--corners", nargs="*", default=None)
    ap.add_argument("--temps", nargs="*", type=float, default=None)
    ap.add_argument("--supply-tolerance", type=float, default=None)
    ap.add_argument("--mc-n", type=int, default=OFFSET_MC_N)
    ap.add_argument("--dut", default=None)
    a = ap.parse_args()

    tb = htb.load(SIM / a.bench)
    pdk = hpdk.find_pdk()
    dut = hdut.load(select=a.dut)
    if dut.provenance != "schematic":
        raise SystemExit("mk_klt_request.py supports the schematic binding only "
                         "(dut_vos probe leg is not implemented)")
    out = Path(a.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    corner_list = hc.resolve_corners(a.corners or list(tb.corners))
    tol = tb.supply_tolerance if a.supply_tolerance is None else a.supply_tolerance
    vdds = hc.supply_points(tb.nominal_supply_v, tol)
    temps = list(a.temps) if a.temps else [float(t) for t in tb.temperatures_c]

    body = [
        f"* {tb.name} -- GENERATED by sim/tools/mk_klt_request.py, do not edit",
        f"* dut={dut.dut_id} ({dut.provenance}) sha256={dut.netlist_sha256[:16]}",
        f".param vdd_nom={tb.nominal_supply_v!r}",
        f".param vdd_val={tb.nominal_supply_v!r}",
        ".param temp_c=27.0",
        *dut.param_lines(),
        # The harness injects dut_vos (0 for a schematic DUT, the probed
        # trip-point offset for an extracted one). Only the schematic
        # binding is supported here; an extracted DUT needs the probe leg.
        ".param dut_vos=0.0",
        *(f".param {k}={v}" for k, v in tb.params.items()),
        # A copy of the PDK's design.ngspice, staged with the request: an
        # off-host runner does not expand the harness's absolute PDK path.
        '.include "design.ngspice"',
        *(f".options {o}" for o in tb.options),
        f'.include "{dut.netlist}"',
        f'.include "{tb.netlist}"',
        "",
    ]
    (out / "design.ngspice").write_text(Path(pdk.design_include).read_text())
    (out / "body.spice").write_text("\n".join(body))

    process = [{"name": c.name, "sections": list(c.sections)} for c in corner_list]
    for leg, spec in legs_for(a.bench, tb, a.mc_n).items():
        req = {
            "netlist": "body.spice",
            "engine": "ngspice",
            "models": {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"},
            "corners": {
                "process": process,
                "supply_v": {"vdd_val": vdds},
                "temperature_c": temps,
            },
            "analysis": spec["analysis"],
            "measurements": spec["measurements"],
            "options": {
                "timeout_s": 600,
                "keep_artifacts": True,
                "ngspice_init": NGSPICE_INIT,
            },
        }
        if "monte_carlo" in spec:
            req["monte_carlo"] = spec["monte_carlo"]
        (out / f"request-{leg}.json").write_text(json.dumps(req, indent=2) + "\n")
        n = len(corner_list) * len(vdds) * len(temps) * (a.mc_n if "monte_carlo" in spec else 1)
        print(f"wrote {out}/request-{leg}.json ({n} units)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
