#!/usr/bin/env bash
#
# design/netlist.sh -- THE one documented command that regenerates
# design/comparator.spice from design/comparator.sch.
#
#   ./design/netlist.sh          regenerate design/comparator.spice
#   ./design/netlist.sh --check  regenerate into a temp file and FAIL if it
#                                differs from the committed netlist
#
# Why a script rather than a bare `xschem -n`:
#
#   1. xschem emits the TOP-LEVEL cell as a COMMENTED `**.subckt comparator`
#      block that still contains a live `XDUT ... comparator_dut` instance
#      line. Left in, that line would instantiate a second, half-floating
#      comparator inside every deck the harness composes. It is deleted here,
#      and the deletion is asserted (exactly one such block, containing
#      exactly one instance line) rather than assumed.
#   2. The DUT netlist must not contain `.end` -- sim/dut/README.md's contract,
#      enforced by sim/harness/dut.py, because the harness owns the models, the
#      corner .lib sections, .temp and the .control block.
#   3. xschem stamps an ABSOLUTE `** sch_path:` into the netlist. Left in, the
#      committed netlist's sha256 -- which every record under sim/ stamps --
#      would depend on which directory the netlisting ran in. The paths are
#      rewritten to repo-relative here.
#
# The PDK is resolved by the SAME code path the corner runner uses
# (sim/run_corners.py --print-env), so xschem and ngspice cannot disagree about
# which gf180mcu install is in play.

set -euo pipefail

DESIGN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${DESIGN_DIR}/.." && pwd)"
TOP="comparator"
OUT="${DESIGN_DIR}/${TOP}.spice"

MODE="${1:-write}"
case "${MODE}" in
  write|--check) ;;
  *) echo "usage: $(basename "$0") [--check]" >&2; exit 1 ;;
esac

command -v xschem >/dev/null 2>&1 || {
  echo "xschem not found on PATH (sim/toolchain.json pins ${TOP} netlisting to xschem 3.4.7)" >&2
  exit 1
}

# PDK environment, resolved exactly as the corner runner resolves it.
eval "$(python3 "${REPO_ROOT}/sim/run_corners.py" --print-env)"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

( cd "${DESIGN_DIR}" && xschem \
    --rcfile "${DESIGN_DIR}/xschemrc" \
    -x -q -n -o "${WORK}" "${TOP}.sch" ) >"${WORK}/xschem.log" 2>&1 || {
  echo "xschem netlisting failed:" >&2
  cat "${WORK}/xschem.log" >&2
  exit 1
}

RAW="${WORK}/${TOP}.spice"
[ -s "${RAW}" ] || { echo "xschem wrote no netlist (${RAW})" >&2; cat "${WORK}/xschem.log" >&2; exit 1; }

python3 - "${RAW}" "${WORK}/${TOP}.clean" "${REPO_ROOT}" "${TOP}" <<'PY'
import re
import sys

raw_path, out_path, repo_root, top = sys.argv[1:5]
raw = open(raw_path).read().splitlines()

# 1. delete the commented top-level wrapper block, asserting what it contained.
start = [i for i, l in enumerate(raw) if l.strip().startswith(f"**.subckt {top}")]
if len(start) != 1:
    sys.exit(f"expected exactly one '**.subckt {top}' wrapper block, found {len(start)}")
end = [i for i, l in enumerate(raw) if l.strip().startswith("**.ends") and i > start[0]]
if not end:
    sys.exit("wrapper block has no '**.ends'")
block = raw[start[0]:end[0] + 1]
live = [l for l in block
        if l.strip() and not l.strip().startswith("*")]
if len(live) != 1 or "comparator_dut" not in live[0]:
    sys.exit(f"wrapper block should hold exactly one comparator_dut instance, found: {live!r}")
kept = raw[:start[0]] + raw[end[0] + 1:]

# 2. drop the simulator directives the harness owns (sim/dut/README.md).
kept = [l for l in kept if l.strip().lower() not in (".end",)]

# 3. make xschem's absolute path stamps repo-relative and reproducible.
out = []
for line in kept:
    line = line.replace(repo_root.rstrip("/") + "/", "")
    line = re.sub(r"(\*\* (?:sch|sym)_path:)\s*\S+", lambda m: m.group(0), line)
    out.append(line)

header = f"""* ===========================================================================
* GENERATED FILE -- do not edit. Regenerate with:  ./design/netlist.sh
*
* Source of truth: design/{top}.sch and the cells below it
*   design/comparator_dut.sch        -> .subckt comparator_dut
*   design/comparator_dut_analog.sch -> .subckt comparator_dut_analog
*   design/comparator_dut_latch.sch  -> .subckt comparator_dut_latch
*
* Topology, sizing and the gm/ID rows every device is cited against:
*   spec/decision-records/DR-0001-comparator-topology.md
*
* Interface contract (pin names and ORDER) : sim/dut/README.md
* Bound into the corner runner by          : sim/dut.json
*
* This file deliberately contains no .include / .lib / .temp / .control /
* .endc / .end: the harness supplies the models, the corner .lib sections,
* the temperature and the control block for every PVT point it composes.
* ===========================================================================
"""

text = header + "\n".join(l.rstrip() for l in out).strip("\n") + "\n"
text = re.sub(r"\n{3,}", "\n\n", text)
open(out_path, "w").write(text)
PY

CLEAN="${WORK}/${TOP}.clean"

# Contract self-check, so a bad export fails here rather than 45 PVT points later.
for sub in comparator_dut comparator_dut_analog comparator_dut_latch; do
  grep -qiE "^\.subckt ${sub}( |$)" "${CLEAN}" || {
    echo "generated netlist is missing '.subckt ${sub}' (sim/dut/README.md contract)" >&2
    exit 1
  }
done
if grep -niE '^[[:space:]]*\.(include|lib|temp|control|endc|end)([[:space:]]|$)' "${CLEAN}"; then
  echo "generated netlist contains a directive the harness owns" >&2
  exit 1
fi

if [ "${MODE}" = "--check" ]; then
  if diff -u "${OUT}" "${CLEAN}"; then
    echo "design/${TOP}.spice is up to date with design/${TOP}.sch"
  else
    echo "design/${TOP}.spice is STALE -- rerun ./design/netlist.sh" >&2
    exit 1
  fi
else
  cp "${CLEAN}" "${OUT}"
  echo "wrote ${OUT#"${REPO_ROOT}"/}"
fi
