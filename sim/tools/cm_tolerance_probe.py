#!/usr/bin/env python3
"""Solver-tolerance convergence probe for the monotonic-index common-mode bench
(issue #240).

SUPPLEMENTAL AND UNSCORED. It measures how much the bench's raw differential
outputs, gain, midpoint offset and endpoint-minus-midpoint offset move when the
ngspice dc solver tolerances (`reltol`, `abstol`, `vntol`) are tightened, for a
small fixed draw subset at two PVT points. It is a numerical-reproducibility
check of the EXISTING stimulus, not a CMRR specification: the consumer's
rejection verdict stays Unknown and nothing here is scored.

Design (all fixed before any probe result was ingested):

* Profiles (`mk_klt_request.TOLERANCE_PROFILES`): `baseline` (ngspice defaults,
  written explicitly), `tight`, `tighter`. One `klt sim` request per
  (profile, PVT point), each a normal `mk_klt_request.py` work dir whose body
  carries the profile's `.options` cards.
* PVT points: nominal `tt / 27 C / 3.30 V` and ONE hot point chosen
  mechanically from the committed full-grid record by `select_hot_point`:
  among the points at the highest temperature present, the one with the largest
  endpoint-shift spread, i.e. max(sig_dvos_dn_uv, sig_dvos_up_uv); ties break by
  corner id. Draws: sample_index 0..DRAWS-1 of the same seeded set.
* Application gate: each profile's body must contain EXACTLY its three `.options`
  cards, once, in order, with its values, and nothing else tolerance-like; the
  body must differ between profiles only in those cards; and the report must
  quote the body's sha256. Request metadata alone is never accepted.
* Pairing gate: identical executor-reported per-draw replay identity (`seed`,
  `process_seed`, `mismatch_seed` of each `corners[].monte_carlo`, which are
  identity-carrying values, not just the requested base seed), identical
  sample_index sets, DUT / testbench / simulator identity, AND the midpoint
  offset reproduced within PAIRING_MIDPOINT_TOL_V. If any is missing or
  violated the probe REFUSES and writes a refusal record with no numbers.
* Convergence criterion (`classify`), numerical reproducibility only:
  with d_last = max |change of endpoint-minus-midpoint offset| between the last
  two profiles and d_all = the same between baseline and the last profile, over
  all PVT points, draws and both endpoints,
    stable                d_last <= T and d_all <= T
    tolerance-dominated   d_last <= T and d_all >  T  (the baseline settings
                          move the quantity by more than T; the tight pair agrees)
    inconclusive          d_last >  T (not converged at the tightest setting),
                          or too few draws/points, or no profile changed any
                          raw output at all (tolerance control not evidenced).
  T = CONVERGENCE_THRESHOLD_V = 0.1 uV, a tenth of the ~1 uV scale at which the
  committed campaign's endpoint-shift sigmas sit.

    python3 sim/tools/cm_tolerance_probe.py ROOT              # generate, dispatch, ingest
    python3 sim/tools/cm_tolerance_probe.py ROOT --from-report  # ingest finished ROOT
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SIM))

import klt_record as kr  # noqa: E402
import mk_klt_request as mk  # noqa: E402

BENCH = mk.CM_INDEX_BENCH
EXP = SIM / BENCH
PROFILES = mk.TOLERANCE_PROFILE_ORDER
DRAWS = 8
MIN_DRAWS = 4
MIN_PVT = 2
NOMINAL = ("tt", 27.0, 3.30)
#: Declared before ingest: see the module docstring.
CONVERGENCE_THRESHOLD_V = 1e-7
PAIRING_MIDPOINT_TOL_V = 1e-4
TOL_KEYS = ("reltol", "abstol", "vntol")
REPLAY_KEYS = ("seed", "process_seed", "mismatch_seed")
GAIN_QUANTITIES = ("av_dn", "av_mid", "av_up")
VOLT_QUANTITIES = ("vos_mid", "dvos_dn", "dvos_up")
RAW_QUANTITIES = tuple(f"dv_{label}" for label in mk.CM_WINDOW_POINTS)
QUANTITIES = RAW_QUANTITIES + GAIN_QUANTITIES + VOLT_QUANTITIES
CLASSES = ("stable", "tolerance-dominated", "inconclusive")
RULE_TEXT = (
    "d_last = max |delta endpoint-minus-midpoint offset| between the last two profiles; d_all = the same between "
    "baseline and the last profile; both over all PVT points, draws and both endpoints. stable: d_last <= T and "
    "d_all <= T. tolerance-dominated: d_last <= T and d_all > T. inconclusive: d_last > T, too few draws/points, "
    "or no raw output changed between any two profiles (tolerance control not evidenced). A numerical "
    "reproducibility criterion, not a CMRR specification.")


class ProbeRefused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def pvt_key(proc: str, temp: float, vdd: float) -> str:
    return f"{proc}_{float(temp):g}c_{vdd:.2f}v"


def parse_pvt_key(key: str) -> tuple[str, float, float]:
    m = re.fullmatch(r"(\w+?)_(-?[0-9.]+)c_([0-9.]+)v", key)
    if not m:
        raise ProbeRefused("PVT_SELECTION_INVALID", f"unparsable PVT key {key!r}")
    return m.group(1), float(m.group(2)), float(m.group(3))


# --------------------------------------------------------------------------- selection

def select_hot_point(record: dict) -> dict:
    """Mechanical hot-point rule over a committed full-grid record's `derived`."""
    derived = record.get("derived") or {}
    pts = {}
    for k, v in derived.items():
        proc, t, vdd = parse_pvt_key(k)
        try:
            spread = max(float(v["sig_dvos_dn_uv"]), float(v["sig_dvos_up_uv"]))
        except (KeyError, TypeError, ValueError):
            raise ProbeRefused("PVT_SELECTION_INVALID", f"{k} lacks sig_dvos_dn_uv/sig_dvos_up_uv") from None
        if not math.isfinite(spread):
            raise ProbeRefused("PVT_SELECTION_INVALID", f"{k} spread is non-finite")
        pts[k] = (t, spread, proc, vdd)
    if not pts:
        raise ProbeRefused("PVT_SELECTION_INVALID", "record has no derived points")
    tmax = max(p[0] for p in pts.values())
    best = sorted((k for k, p in pts.items() if p[0] == tmax), key=lambda k: (-pts[k][1], k))[0]
    t, spread, proc, vdd = pts[best]
    return {"key": best, "process": proc, "temperature_c": t, "supply_v": vdd, "spread_uv": spread,
            "rule": "highest temperature present; largest max(sig_dvos_dn_uv, sig_dvos_up_uv); ties by corner id"}


def probe_points(record: dict) -> list[dict]:
    hot = select_hot_point(record)
    nom = {"key": pvt_key(*NOMINAL), "process": NOMINAL[0], "temperature_c": NOMINAL[1], "supply_v": NOMINAL[2]}
    return [nom, hot] if nom["key"] != hot["key"] else [nom]


# --------------------------------------------------------------------------- application gate

def _strip_tolerance(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not _tolerance_pairs(l))


def _tolerance_pairs(line: str) -> list[tuple[str, str]]:
    s = line.strip().lower()
    if not s.startswith(".opt"):
        return []
    return [(k, v) for k, v in re.findall(r"(\w+)\s*=\s*(\S+)", s) if k in TOL_KEYS]


def check_tolerance_body(body: str, profile: str) -> list[str]:
    """The body's tolerance cards, as the simulator would read them, must be
    exactly the profile's: each key once, profile order, profile value, finite."""
    want = mk.TOLERANCE_PROFILES.get(profile)
    if want is None:
        raise ProbeRefused("UNKNOWN_TOLERANCE_PROFILE", f"{profile!r} is not one of {list(PROFILES)}")
    got = [p for l in body.splitlines() for p in _tolerance_pairs(l)]
    out = []
    for k, v in got:
        try:
            ok = math.isfinite(float(v)) and float(v) > 0
        except ValueError:
            ok = False
        if not ok:
            raise ProbeRefused("TOLERANCE_NOT_APPLIED", f"{profile}: {k}={v!r} is not a finite positive number")
        out.append((k, float(v)))
    if [k for k, _ in out] != [k for k, _ in want]:
        raise ProbeRefused("TOLERANCE_NOT_APPLIED",
                           f"{profile}: body tolerance cards {out} are missing, duplicated or reordered vs {list(want)}")
    if out != [(k, float(v)) for k, v in want]:
        raise ProbeRefused("TOLERANCE_NOT_APPLIED", f"{profile}: body values {out} != profile {list(want)}")
    return mk.tolerance_option_lines(profile)


def check_deck_no_override(deck: str, profile: str) -> None:
    """An executor-generated deck must not carry its own tolerance cards (they
    could override or duplicate the profile's) and must include a netlist."""
    for line in deck.splitlines():
        if _tolerance_pairs(line):
            raise ProbeRefused("TOLERANCE_NOT_APPLIED", f"{profile}: executor deck carries its own tolerance card {line.strip()!r}")
    if not any(l.strip().lower().startswith(".include") and "netlist" in l for l in deck.splitlines()):
        raise ProbeRefused("TOLERANCE_NOT_APPLIED", f"{profile}: executor deck does not include the submitted netlist")


# --------------------------------------------------------------------------- loading

def replay_identity(report: dict, vdd: float) -> dict:
    """{pvt: {mcN: {seed, process_seed, mismatch_seed}}} as the EXECUTOR reported."""
    out: dict = {}
    for c in report.get("corners", []):
        cid, sample = kr.corner_id(c["corner_id"], vdd)
        mc = c.get("monte_carlo") or {}
        out.setdefault(cid, {})[sample] = {k: mc.get(k) for k in ("sample_index",) + REPLAY_KEYS}
    return out


def load_unit(work: Path, profile: str, point: dict) -> dict:
    """One ingested (profile, PVT) work dir -> data + identity meta. Raises
    ProbeRefused for unapplied tolerance / incomplete data; kr's own gates
    (staged-source hashes, report-to-body link, engine floor) refuse as usual."""
    vdd = point["supply_v"]
    n = f"main-v{vdd:.2f}"
    names = {n: ("main", vdd)}
    b = kr.load_bundle(work, BENCH)
    kr.verify_staged(work, b, names)
    tp = (b.get("parameters") or {}).get("tolerance_profile") or {}
    if tp.get("name") != profile or tp.get("cards") != mk.tolerance_option_lines(profile):
        raise ProbeRefused("TOLERANCE_NOT_BOUND", f"{work}: bundle names profile {tp.get('name')!r}, expected {profile!r}")
    rpath = work / f"report-{n}.json"
    if not rpath.is_file() or not rpath.read_text().strip():
        raise ProbeRefused("REPORT_MISSING", f"{rpath} absent: nothing to compare")
    report = json.loads(rpath.read_text())
    kr.verify_reports(work, b, names, {n: report})  # report quotes the bundled body sha256
    req_meta = b["requests"][n]
    body = (work / req_meta["netlist"]).read_text()
    check_tolerance_body(body, profile)
    decks = 0
    for c in report.get("corners", []):
        # The executor's per-unit deck `.include`s the submitted netlist by its
        # remote path instead of inlining it, so the cards are proven by the
        # body hash the report quotes; a returned deck is only checked for a
        # competing tolerance override and for actually including a netlist.
        d = (c.get("artifacts") or {}).get("deck")
        if d and (work / d).is_file():
            check_deck_no_override((work / d).read_text(), profile)
            decks += 1
    request = json.loads((work / req_meta["request"]).read_text())
    samples, issues = kr.collect_cm_index(report, request, vdd)
    if issues:
        raise ProbeRefused("INCOMPLETE_PROFILE_DATA", f"{profile}/{point['key']}: " + "; ".join(issues[:6]))
    env = report.get("environment") or {}
    remote = env.get("remote") or {}
    return {
        "samples": samples.get(point["key"], {}),
        "replay": replay_identity(report, vdd).get(point["key"], {}),
        "meta": {
            "origin_commit": b["origin"]["commit"], "origin_dirty": b["origin"]["dirty"],
            "dut_id": b["dut"]["dut_id"], "dut_netlist_sha256": b["dut"]["netlist_sha256"],
            "binding_entry_sha256": b["dut"]["binding_entry_sha256"],
            "testbench_netlist_sha256": b["testbench"]["netlist_sha256"],
            "testbench_manifest_sha256": b["testbench"]["manifest_sha256"],
            "engine_version": env.get("engine_version"), "runner_klt_version": remote.get("runner_klt_version"),
            "job_id": remote.get("job_id"), "provider": remote.get("provider"),
            "body": req_meta["netlist"], "body_sha256": req_meta["netlist_sha256"],
            "body_without_tolerance_sha256": mk.sha256_bytes(_strip_tolerance(body).encode()),
            "tolerance_cards": mk.tolerance_option_lines(profile), "decks_verified": decks,
            "monte_carlo": env.get("monte_carlo"),
        },
    }


# --------------------------------------------------------------------------- pairing / math

IDENTITY_KEYS = ("origin_commit", "dut_id", "dut_netlist_sha256", "binding_entry_sha256",
                 "testbench_netlist_sha256", "testbench_manifest_sha256", "engine_version", "runner_klt_version")


def check_pairing(data: dict) -> None:
    """data[profile][pvt] = {samples, replay, meta}. Raises ProbeRefused unless
    the profiles are complete, identical in everything but tolerance, and
    paired draw-for-draw by executor-reported replay identity."""
    profiles = list(data)
    if list(profiles) != list(PROFILES[:len(profiles)]) or len(profiles) < 3 or profiles[0] != "baseline":
        raise ProbeRefused("MISSING_PROFILE", f"need baseline plus >= 2 tighter profiles in order, got {profiles}")
    base = data["baseline"]
    if len(base) < MIN_PVT:
        raise ProbeRefused("MISSING_PVT", f"{len(base)} PVT point(s); need >= {MIN_PVT}")
    for prof in profiles[1:]:
        if sorted(data[prof]) != sorted(base):
            raise ProbeRefused("PVT_MISMATCH", f"{prof} covers {sorted(data[prof])}, baseline {sorted(base)}")
    labels = set(mk.CM_WINDOW_POINTS)
    for pvt in base:
        ref = base[pvt]
        if len(ref["samples"]) < MIN_DRAWS:
            raise ProbeRefused("TOO_FEW_DRAWS", f"{pvt}: {len(ref['samples'])} draws < {MIN_DRAWS}")
        for prof in profiles:
            u = data[prof][pvt]
            for k in IDENTITY_KEYS:
                if u["meta"].get(k) in (None, "") or u["meta"][k] != ref["meta"][k]:
                    raise ProbeRefused("IDENTITY_MISMATCH", f"{pvt}: {prof} {k} = {u['meta'].get(k)!r} vs baseline {ref['meta'][k]!r}")
            if u["meta"]["body_without_tolerance_sha256"] != ref["meta"]["body_without_tolerance_sha256"]:
                raise ProbeRefused("DECK_DRIFT", f"{pvt}: {prof} body differs from baseline beyond the tolerance cards")
            if sorted(u["samples"]) != sorted(ref["samples"]):
                raise ProbeRefused("UNPAIRED_DRAWS", f"{pvt}: {prof} draws {sorted(u['samples'])} != baseline {sorted(ref['samples'])}")
            for mc, dv in u["samples"].items():
                if set(dv) != labels:
                    raise ProbeRefused("COORDINATE_DRIFT", f"{pvt}/{mc}: {prof} labels {sorted(dv)} != the six coordinate points")
            for mc in u["samples"]:
                r = u["replay"].get(mc) or {}
                if any(not isinstance(r.get(k), int) or isinstance(r.get(k), bool) for k in REPLAY_KEYS):
                    raise ProbeRefused("REPLAY_IDENTITY_UNSUPPORTED",
                                       f"{pvt}/{mc}: executor reported no per-draw {REPLAY_KEYS} ({r!r}); equal request "
                                       "seeds alone do not prove the same mismatch realization")
                if r != ref["replay"].get(mc):
                    raise ProbeRefused("UNPAIRED_DRAWS", f"{pvt}/{mc}: {prof} replay identity {r} != baseline {ref['replay'].get(mc)}")
        if len({ref["replay"][mc]["mismatch_seed"] for mc in ref["samples"]}) != len(ref["samples"]):
            raise ProbeRefused("REPLAY_IDENTITY_UNSUPPORTED", f"{pvt}: draws do not carry distinct mismatch seeds")


def derive_draws(data: dict) -> dict:
    """-> derived[profile][pvt][mc] (gain/offset per draw); invalid gain refuses."""
    out: dict = {}
    for prof, pvts in data.items():
        for pvt, u in pvts.items():
            for mc, dv in u["samples"].items():
                try:
                    d = kr.derive_cm_window_draw(dv)
                except ValueError as e:
                    raise ProbeRefused(str(e.args[0]), f"{prof}/{pvt}/{mc}: {e.args[1]}") from None
                for label, v in dv.items():
                    d[f"dv_{label}"] = v
                out.setdefault(prof, {}).setdefault(pvt, {})[mc] = d
    return out


def check_midpoint_reproduced(derived: dict) -> None:
    """Pairing evidence beyond seeds: the same realization reproduces the
    midpoint offset; a re-rolled draw would move it by ~mV."""
    base = derived["baseline"]
    for prof, pvts in derived.items():
        for pvt, draws in pvts.items():
            for mc, d in draws.items():
                diff = abs(d["vos_mid"] - base[pvt][mc]["vos_mid"])
                if diff > PAIRING_MIDPOINT_TOL_V:
                    raise ProbeRefused("MIDPOINT_NOT_REPRODUCED",
                                       f"{pvt}/{mc}: {prof} midpoint offset differs from baseline by {diff:.3e} V "
                                       f"> {PAIRING_MIDPOINT_TOL_V:g} V; the draws are not the same realization")


def pair_names(profiles: list[str]) -> list[tuple[str, str]]:
    pairs = list(zip(profiles, profiles[1:]))
    if len(profiles) > 2:
        pairs.append((profiles[0], profiles[-1]))
    return pairs


def analyze(derived: dict) -> dict:
    """Profile-to-profile changes (later minus earlier) for every quantity,
    per draw and per PVT point, plus per-pair maxima over everything."""
    profiles = list(derived)
    res: dict = {}
    for a, b in pair_names(profiles):
        per_pvt: dict = {}
        for pvt in derived[a]:
            q = {}
            for name in QUANTITIES:
                deltas = {mc: derived[b][pvt][mc][name] - derived[a][pvt][mc][name] for mc in sorted(derived[a][pvt], key=lambda s: int(s[2:]))}
                vals = list(deltas.values())
                q[name] = {"unit": "V/V" if name in GAIN_QUANTITIES else "V", "per_draw": deltas,
                           "max_abs": max(abs(v) for v in vals), "mean": sum(vals) / len(vals)}
            per_pvt[pvt] = q
        agg = {name: max(per_pvt[p][name]["max_abs"] for p in per_pvt) for name in QUANTITIES}
        res[f"{a}->{b}"] = {"per_pvt": per_pvt, "max_abs_over_all": agg}
    return res


def classify(analysis: dict, profiles: list[str], n_pvt: int, n_draws: int,
             threshold: float = CONVERGENCE_THRESHOLD_V) -> tuple[str, str]:
    last = f"{profiles[-2]}->{profiles[-1]}"
    full = f"{profiles[0]}->{profiles[-1]}"
    if n_pvt < MIN_PVT or n_draws < MIN_DRAWS:
        return "inconclusive", f"only {n_pvt} PVT point(s) / {n_draws} draw(s)"
    moved = any(analysis[k]["max_abs_over_all"][r] != 0.0 for k in analysis for r in RAW_QUANTITIES)
    if not moved:
        return "inconclusive", "no raw differential output changed between any two profiles: tolerance control not evidenced"

    def edge(k):
        m = analysis[k]["max_abs_over_all"]
        return max(m["dvos_dn"], m["dvos_up"])

    d_last, d_all = edge(last), edge(full)
    if d_last > threshold:
        return "inconclusive", f"d_last = {d_last:.3e} V > T = {threshold:g} V: not converged at the tightest profile"
    if d_all <= threshold:
        return "stable", f"d_last = {d_last:.3e} V, d_all = {d_all:.3e} V, both <= T = {threshold:g} V"
    return "tolerance-dominated", f"d_last = {d_last:.3e} V <= T but d_all = {d_all:.3e} V > T = {threshold:g} V"


def run_analysis(data: dict) -> dict:
    """Full gated pipeline -> result dict (raises ProbeRefused)."""
    check_pairing(data)
    derived = derive_draws(data)
    check_midpoint_reproduced(derived)
    profiles = list(data)
    analysis = analyze(derived)
    n_pvt = len(data["baseline"])
    n_draws = min(len(u["samples"]) for u in data["baseline"].values())
    cls, why = classify(analysis, profiles, n_pvt, n_draws)
    return {"profiles": profiles, "derived": derived, "analysis": analysis, "classification": cls,
            "classification_reason": why, "n_pvt": n_pvt, "n_draws": n_draws}


# --------------------------------------------------------------------------- driver

def _record_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for p in sorted((EXP / "records").glob("*.json")):
        if "tolerance-probe" in p.name:
            continue
        if json.loads(p.read_text()).get("full_coverage"):
            return p
    raise ProbeRefused("PVT_SELECTION_INVALID", "no committed full-grid record found")


def layout(root: Path, points: list[dict]) -> list[tuple[str, dict, Path]]:
    return [(prof, pt, root / prof / pt["key"]) for prof in PROFILES for pt in points]


def generate(root: Path, points: list[dict]) -> None:
    for prof, pt, work in layout(root, points):
        work.mkdir(parents=True, exist_ok=True)
        subprocess.check_call([sys.executable, str(HERE / "mk_klt_request.py"), BENCH, str(work),
                               "--corners", pt["process"], "--temps", f"{pt['temperature_c']:g}",
                               "--supply-v", f"{pt['supply_v']:.2f}", "--mc-n", str(DRAWS),
                               "--tolerance-profile", prof])


def dispatch_all(root: Path, points: list[dict]) -> None:
    backend = os.environ.get("KLT_SIM_BACKEND", "")
    if backend != "batch":
        raise SystemExit(f"KLT_SIM_BACKEND={backend!r}: refusing to run the probe grid on a local backend "
                         "(shared dispatch worker). Export KLT_SIM_BACKEND=batch.")
    procs = {}
    for prof, pt, work in layout(root, points):
        n = f"main-v{pt['supply_v']:.2f}"
        with (work / f"report-{n}.json").open("w") as out, (work / f"stderr-{n}.txt").open("w") as err:
            procs[(prof, pt["key"])] = (n, work, subprocess.Popen(
                ["klt", "sim", "-o", str(work / f"out-{n}"), str(work / f"request-{n}.json"), "--format", "json"],
                stdout=out, stderr=err))
    for key, (n, work, pr) in procs.items():
        rc = pr.wait()
        print(f"{key}: klt sim rc={rc}", flush=True)
        if not (work / f"report-{n}.json").read_text().strip():
            raise SystemExit(f"klt sim {key} failed (rc={rc}):\n{(work / f'stderr-{n}.txt').read_text()}")


def _us(v: float) -> str:
    return f"{v * 1e6:.4g}"


def render_md(rid: str, plan: dict, res: dict | None, refusal: ProbeRefused | None) -> str:
    L = [f"# Tolerance probe {rid}", "",
         "SUPPLEMENTAL, UNSCORED numerical-reproducibility probe of `sim/comparator-offset-cm-index/` "
         "(issue #240). The consumer's rejection verdict stays **Unknown**; no CMRR figure is defined. "
         "Schematic preamp DC only -- not whole-comparator transient, not extracted-layout.", "",
         f"- PVT points: {', '.join('`'+p['key']+'`' for p in plan['points'])} (hot point rule: {plan['hot_rule']})",
         f"- Draws per point: {plan['draws']} (sample_index 0..{plan['draws'] - 1}); profiles: "
         + ", ".join(f"`{p}` {dict(mk.TOLERANCE_PROFILES[p])}" for p in PROFILES),
         f"- Predeclared threshold T = {CONVERGENCE_THRESHOLD_V:g} V; pairing midpoint tolerance {PAIRING_MIDPOINT_TOL_V:g} V",
         f"- Rule: {RULE_TEXT}"]
    if refusal:
        L += ["", f"## REFUSED: `{refusal.code}`", "", refusal.detail, "",
              "No numerical convergence claim is made; nothing was compared across unpaired or "
              "unproven-tolerance populations."]
        return "\n".join(L) + "\n"
    L += ["", f"## Classification: **{res['classification']}**", "", res["classification_reason"], "",
          "Maximum absolute profile-to-profile change over all points and draws (uV for voltages, V/V for gain):", "",
          "| pair | " + " | ".join(QUANTITIES) + " |", "|---|" + "---|" * len(QUANTITIES)]
    for pair, a in res["analysis"].items():
        m = a["max_abs_over_all"]
        L.append(f"| `{pair}` | " + " | ".join(f"{m[q]:.4g}" if q in GAIN_QUANTITIES else _us(m[q]) for q in QUANTITIES) + " |")
    L += ["", "Per-draw deltas, raw measurements and replay identities are in the JSON beside this file. "
          "Limitations: 8 draws at two PVT points characterise the solver sensitivity of THIS stimulus, not the "
          "full 45-point campaign; a `stable` result bounds the numerical error of the reported endpoint shifts "
          "only to the extent shown above and does not turn them into a precision measurement or a CMRR figure."]
    return "\n".join(L) + "\n"


def write_artifact(root: Path, plan: dict, data: dict | None, res: dict | None, refusal: ProbeRefused | None,
                   exp: Path = EXP) -> str:
    """Append-only: a fresh id, exclusive directories, never an existing path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    commit, dirty = kr.git_state()
    rid = f"{ts}-{commit[:7]}-tolerance-probe" + ("-refused" if refusal else "")
    for sub in ("records", "probes"):
        (exp / sub).mkdir(exist_ok=True)
    pdir = exp / "probes" / rid
    pdir.mkdir()  # exclusive
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not any(part.startswith(("out-", "stderr-")) for part in rel.parts):
            (pdir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, pdir / rel)
    body = {
        "record_id": rid, "bench": BENCH, "kind": "tolerance-probe", "ingest_commit": commit,
        "ingest_tooling_dirty": dirty, "scored": False, "verdict": "Unknown",
        "scope": "schematic preamp DC only; no CMRR, whole-comparator or extracted-layout claim",
        "plan": plan, "threshold_v": CONVERGENCE_THRESHOLD_V, "pairing_midpoint_tol_v": PAIRING_MIDPOINT_TOL_V,
        "classification_rule": RULE_TEXT, "evidence_dir": f"probes/{rid}",
    }
    if refusal:
        body.update({"outcome": "refused", "refusal": {"code": refusal.code, "detail": refusal.detail},
                     "classification": None})
    else:
        meta = {p: {k: u["meta"] for k, u in data[p].items()} for p in data}
        raw = {p: {k: {mc: s for mc, s in u["samples"].items()} for k, u in data[p].items()} for p in data}
        replay = {k: u["replay"] for k, u in data["baseline"].items()}
        body.update({"outcome": "compared", "classification": res["classification"],
                     "classification_reason": res["classification_reason"], "profiles": res["profiles"],
                     "tolerance_options": {p: mk.TOLERANCE_PROFILES[p] for p in res["profiles"]},
                     "executor_meta": meta, "replay_identity": replay, "raw_dv_v": raw,
                     "derived": res["derived"], "analysis": res["analysis"]})
    (exp / "records" / f"{rid}.json").write_text(json.dumps(body, indent=1, allow_nan=False, default=list) + "\n")
    (exp / "records" / f"{rid}.md").write_text(render_md(rid, plan, res, refusal))
    return rid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="scratch dir holding <profile>/<pvt>/ work dirs")
    ap.add_argument("--from-report", action="store_true", help="ingest a finished ROOT; skip generation/dispatch")
    ap.add_argument("--record", default=None, help="full-grid record JSON for hot-point selection")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    rec_path = _record_path(a.record)
    rec = json.loads(rec_path.read_text())
    points = probe_points(rec)
    plan = {"points": points, "draws": DRAWS, "hot_rule": points[-1].get("rule"),
            "selection_record": str(rec_path.relative_to(SIM.parent)) if rec_path.is_relative_to(SIM.parent) else str(rec_path),
            "selection_record_sha256": mk.sha256_file(rec_path)}
    if not a.from_report:
        generate(root, points)
        (root / "probe-plan.json").write_text(json.dumps(plan, indent=1) + "\n")
        dispatch_all(root, points)
    data: dict = {}
    try:
        for prof, pt, work in layout(root, points):
            data.setdefault(prof, {})[pt["key"]] = load_unit(work, prof, pt)
        res = run_analysis(data)
    except ProbeRefused as e:
        rid = write_artifact(root, plan, None, None, e)
        print(f"REFUSED {rid}: {e}", file=sys.stderr)
        return 2
    rid = write_artifact(root, plan, data, res, None)
    print(f"{rid}: {res['classification']} ({res['classification_reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
