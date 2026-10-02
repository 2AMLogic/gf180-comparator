#!/usr/bin/env bash
#
# sim/characterize.sh -- THE one-command entry point for this block.
#
# Ported in shape from gf180-sar-adc/sim/characterize.sh: two modes, one
# campaign per spec row, every campaign run through the same run_corners.py
# harness, a pass/fail summary printed at the end regardless of where a
# failure happened (one bad campaign does not stop the rest -- a reviewer
# gets one full report per invocation instead of bisecting failures one
# re-run at a time).
#
#   sim/characterize.sh smoke
#       One nominal PVT point (tt / 27 C / nominal supply) per campaign,
#       writing NO evidence. Seconds, not minutes -- proof that the whole
#       command surface runs from a clean checkout, nothing more.
#
#   sim/characterize.sh characterize
#       The full PVT campaign behind every spec row: the `mos` corner set
#       x (-40, 27, 125) C x (-10 %, nom, +10 %) supply = 45 points per
#       campaign. Mints a new, dated, append-only record per campaign under
#       sim/<experiment>/records/ (sim/README.md's format -- a genuinely new
#       record, never an overwrite of one already committed).
#
#   sim/characterize.sh selftest
#       Delegates to sim/selftest.sh -- the harness's own acceptance test,
#       including the sabotaged-corner negative control. This is a DIFFERENT
#       thing from the two modes above: it proves the HARNESS works, not that
#       the circuit does.
#
#   sim/characterize.sh postlayout
#       The post-layout (extracted-netlist) campaign, issue #23 (T1 item 7):
#       regenerates the parasitic-extracted DUT binding via
#       layout/run_extract_sim.py, then runs the two benches layout parasitics
#       most affect -- regeneration and kickback (design/README.md's own
#       asymmetry note: preamp-output parasitics lower noise, input parasitics
#       raise kickback) -- against the comparator-dr0001-layout binding over
#       the same full PVT grid. The two analog-partition benches (offset-mc,
#       preamp-noise) are not post-layout-runnable: a flat extraction has no
#       analog/latch partition, and run_corners.py refuses them with a message
#       naming the schematic binding.
#
# Exit status: 0 if every campaign that ran exited 0; otherwise the number of
# failing campaigns.

set -uo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

MODE="${1:-}"
case "${MODE}" in
  smoke|characterize|postlayout) ;;
  selftest) exec "${SIM_DIR}/selftest.sh" ;;
  *)
    echo "usage: $(basename "$0") {smoke|characterize|selftest|postlayout}" >&2
    echo "  smoke         one nominal point per campaign, writes no evidence (seconds)" >&2
    echo "  characterize  full 45-point PVT campaign, mints sim/ evidence records" >&2
    echo "  selftest      harness acceptance test incl. the sabotage negative control" >&2
    echo "  postlayout    regenerate the extracted DUT, then full 45-point PVT campaign" >&2
    echo "                for regeneration + kickback against the layout binding (#23)" >&2
    exit 1
    ;;
esac

JOBS="${JOBS:-}"
if [ -z "${JOBS}" ]; then
  JOBS="$(command -v nproc >/dev/null 2>&1 && nproc || echo 4)"
fi

RUNNER=(python3 "${SIM_DIR}/run_corners.py")

# Every campaign names, in its comment, which README.md target-specification
# row it backs. Cross-reference against that table.
#   comparator-offset-mc      -> Offset sigma
#   comparator-preamp-noise   -> Input-referred noise
#   comparator-regeneration   -> Decision time vs. overdrive (+ metastability)
#   comparator-kickback       -> Kickback
CAMPAIGNS=(
  comparator-offset-mc
  comparator-preamp-noise
  comparator-regeneration
  comparator-kickback
)

# Issue #23 (T1 item 7): the post-layout campaign scope. Only these two
# benches are runnable against the flat extracted binding, and they are the
# two the layout-parasitic asymmetry most affects (design/README.md):
# decision time through the preamplifier output's added RC, kickback through
# the input's added capacitance.
POSTLAYOUT_CAMPAIGNS=(
  comparator-regeneration
  comparator-kickback
)
POSTLAYOUT_DUT="comparator-dr0001-layout"

echo "=============================================================================="
echo "  gf180-comparator characterization -- mode=${MODE}  jobs=${JOBS}"
echo "=============================================================================="
"${RUNNER[@]}" --check-env || {
  echo "environment check failed; see sim/README.md 'Cold start'" >&2
  exit 1
}
echo

if [ "${MODE}" = "postlayout" ]; then
  echo "regenerating the post-layout DUT binding (layout/run_extract_sim.py)..."
  python3 "${REPO_ROOT}/layout/run_extract_sim.py" || {
    echo "post-layout extraction failed; see layout/run_extract_sim.py" >&2
    exit 1
  }
  echo
  CAMPAIGNS=("${POSTLAYOUT_CAMPAIGNS[@]}")
  RUNNER+=("--dut" "${POSTLAYOUT_DUT}")
fi

FAILED=0
declare -a RESULTS=()

for campaign in "${CAMPAIGNS[@]}"; do
  echo
  echo "######################## ${campaign} ########################"
  if [ "${MODE}" = "smoke" ]; then
    "${RUNNER[@]}" "${campaign}" \
      --corners tt --temps 27 --supply-tolerance 0 --no-write -j 1
  else
    "${RUNNER[@]}" "${campaign}" -j "${JOBS}"
  fi
  status=$?
  if [ "${status}" -eq 0 ]; then
    RESULTS+=("PASS  ${campaign}")
  else
    RESULTS+=("FAIL  ${campaign}  (exit ${status})")
    FAILED=$((FAILED + 1))
  fi
done

echo
echo "=============================================================================="
echo "  SUMMARY (${MODE})"
for line in "${RESULTS[@]}"; do
  echo "    ${line}"
done
echo "  ${FAILED} of ${#CAMPAIGNS[@]} campaigns failed"
echo "=============================================================================="
exit "${FAILED}"
