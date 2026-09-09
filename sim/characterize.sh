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
# Exit status: 0 if every campaign that ran exited 0; otherwise the number of
# failing campaigns.

set -uo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

MODE="${1:-}"
case "${MODE}" in
  smoke|characterize) ;;
  selftest) exec "${SIM_DIR}/selftest.sh" ;;
  *)
    echo "usage: $(basename "$0") {smoke|characterize|selftest}" >&2
    echo "  smoke         one nominal point per campaign, writes no evidence (seconds)" >&2
    echo "  characterize  full 45-point PVT campaign, mints sim/ evidence records" >&2
    echo "  selftest      harness acceptance test incl. the sabotage negative control" >&2
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

echo "=============================================================================="
echo "  gf180-comparator characterization -- mode=${MODE}  jobs=${JOBS}"
echo "=============================================================================="
"${RUNNER[@]}" --check-env || {
  echo "environment check failed; see sim/README.md 'Cold start'" >&2
  exit 1
}
echo

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
