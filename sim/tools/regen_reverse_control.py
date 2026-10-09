#!/usr/bin/env python3
"""Reverse-polarity ladder controls for comparator-regeneration (issue #158).

    python3 sim/tools/regen_reverse_control.py [--corner tt_27c_3.30v]
        [--dut ID] [--allow-toolchain-drift]

ONE PVT point, run locally through the harness (a single-corner edge-
semantics check -- allowed on a shared dispatch worker; the 45-point grid
goes to the fleet via `sim/tools/klt_record.py`). Two decks:

  positive  the committed bench. Every reverse-polarity check in tb.json
            must PASS: the mirrored instances went HIGH on the first strobe
            (`dout_*_rev_first` >= 0.9), LOW on the second
            (`dout_*_rev_end` <= 0.1), and `tdr_*` timed that fall.
  negative  the committed bench with the second reverse decision PREVENTED
            (`suppress_reverse_flip`: the mirrored inputs stay positive, so
            the output never has to fall). The point MUST FAIL -- no
            `fall=1 td=35n` crossing exists, so `td_*_rev_ns` cannot be
            produced, and `dout_*_rev_end` stays high. If it passes, the
            reverse timing is not measuring the second decision.

Exit 0 only if the positive control passes its reverse checks and the
negative control fails them. Nothing is written under sim/ (both runs are
scratch, like `run_corners.py --no-write`).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(SIM))

from harness import corners as hc  # noqa: E402
from harness import dut as hdut  # noqa: E402
from harness import pdk as hpdk  # noqa: E402
from harness import report as hreport  # noqa: E402
from harness import runner as hrunner  # noqa: E402
from harness import testbench as htb  # noqa: E402
from harness import toolchain as htool  # noqa: E402

BENCH = "comparator-regeneration"
RUNGS = ("dv_big", "dv_mid", "dv_tiny")
INSTANCES = ("ra", "rb", "rc")
#: The reverse quantities whose checks decide the control outcome.
REVERSE_TIMING = ("td_od50_rev_ns", "td_od1_rev_ns", "td_od01_rev_ns", "tau_rev_ps")
REVERSE_PROOF = tuple(f"dout_{r}_rev_{s}" for r in ("od50", "od1", "od01") for s in ("first", "end"))


def reverse_pwl(inst: str, rung: str, flip: bool = True) -> str:
    """The committed mirrored PWL line for instance `inst` at `rung`
    (flip=True), or the same line with the second-strobe sign NOT flipped."""
    end = f"{{dut_vos-{rung}}}" if flip else f"{{dut_vos+{rung}}}"
    return (f"vs{inst} s{inst} 0 pwl(0 {{dut_vos+{rung}}} {{t_flip}} {{dut_vos+{rung}}} "
            f"{{t_flip+1n}} {end})")


def suppress_reverse_flip(text: str) -> str:
    """Prevent the second reverse decision: every mirrored input stays
    positive through the second strobe. Each rewrite must apply exactly
    once, so a renamed/reshaped ladder fails loudly instead of yielding a
    control that silently controls nothing."""
    for inst, rung in zip(INSTANCES, RUNGS):
        old, new = reverse_pwl(inst, rung), reverse_pwl(inst, rung, flip=False)
        n = text.count(old)
        if n != 1:
            raise ValueError(f"expected exactly one {old!r} in the fragment, found {n}")
        text = text.replace(old, new)
    return text


def stage(src_tb_dir: Path, root: Path, mutate=None) -> Path:
    """Copy the bench's testbench/ to root/<bench>/testbench (optionally
    rewriting the fragment) and return the copy's experiment dir."""
    dst = root / BENCH / htb.TESTBENCH_DIRNAME
    shutil.copytree(src_tb_dir, dst)
    if mutate is not None:
        tb = htb.load(dst)
        tb.netlist.write_text(mutate(tb.netlist.read_text()))
    return dst.parent


def run_one(exp_dir: Path, point, pdk, dut, workdir: Path) -> tuple[object, dict]:
    tb = htb.load(exp_dir)
    probe = tb.offset_probe_testbench() if dut.provenance == "extracted" else None
    res = hrunner.run_point(tb, pdk, dut, point, workdir, probe_tb=probe, num_threads=1)
    summaries = hreport.summarize(tb, [res])
    return res, summaries


def reverse_failures(res, summaries: dict) -> dict[str, list[str]]:
    """{reverse measure: reasons} -- a missing value counts as a failure."""
    out: dict[str, list[str]] = {}
    for name in REVERSE_TIMING + REVERSE_PROOF:
        s = summaries.get(name)
        reasons = list(s.failures) if s is not None else []
        if name not in (res.measurements or {}):
            reasons.append("no value (measurement not produced)")
        if reasons:
            out[name] = reasons
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corner", default="tt_27c_3.30v")
    ap.add_argument("--dut", default=None)
    ap.add_argument("--allow-toolchain-drift", action="store_true")
    a = ap.parse_args()

    m = re.fullmatch(r"(\w+?)_(-?\d+(?:\.\d+)?)c_([\d.]+)v", a.corner)
    if not m:
        raise SystemExit(f"bad corner id {a.corner!r}")
    pdk = hpdk.find_pdk()
    banner = hrunner.ngspice_version()
    chain = htool.check(pdk.version, banner)
    if chain.drift and not a.allow_toolchain_drift:
        raise SystemExit("toolchain drift (" + "; ".join(chain.drift) + "); "
                         "re-run with --allow-toolchain-drift for a scratch control")
    dut = hdut.load(select=a.dut)
    point = hc.build_grid(hc.resolve_corners([m.group(1)]), [float(m.group(2))],
                          [float(m.group(3))])[0]
    src = SIM / BENCH / htb.TESTBENCH_DIRNAME
    print(f"controls at {point.corner_id}, dut={dut.dut_id} ({dut.provenance}), {banner}"
          + (f" [DRIFT accepted: {'; '.join(chain.drift)}]" if chain.drift else ""))

    ok = True
    with tempfile.TemporaryDirectory(prefix="regen-rev-ctl-") as tmp:
        tmp = Path(tmp)
        for label, mutate, must_pass in (("positive", None, True),
                                         ("negative", suppress_reverse_flip, False)):
            exp = stage(src, tmp / label, mutate)
            res, summ = run_one(exp, point, pdk, dut, tmp / label / "work")
            fails = reverse_failures(res, summ)
            vals = {k: (res.measurements or {}).get(k) for k in REVERSE_TIMING + REVERSE_PROOF}
            print(f"\n[{label}] status={res.status} {res.message or ''}")
            for k, v in vals.items():
                print(f"  {k:22s} {v!r:>24}" + (f"   FAIL: {'; '.join(fails[k])}" if k in fails else ""))
            # The negative control must fail FOR THE RIGHT REASON: the timed
            # fall is gone and the mirrored outputs are still HIGH at the end.
            ends = [vals[k] for k in REVERSE_PROOF if k.endswith("_end")]
            right_reason = (any(vals[k] is None for k in REVERSE_TIMING)
                            and all(v is None or v > 0.1 for v in ends))
            good = (not fails and res.status == "ok") if must_pass else (bool(fails) and right_reason)
            verdict = "as required" if good else "WRONG"
            print(f"[{label}] reverse checks {'PASS' if not fails else 'FAIL'} -- {verdict}")
            ok &= good
    print("\nCONTROLS " + ("OK" if ok else "BROKEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
