#!/usr/bin/env bash
#
# sim/selftest.sh -- the HARNESS's own acceptance test.
#
# This is not a circuit test. It answers one question: does the corner runner
# actually do what its records say it does? Ported in intent from
# gf180-sar-adc/sim/selftest.sh.
#
# The failure this exists to catch is the one that leaves no trace: a runner
# that appears to sweep process corners but simulates typical everywhere
# (wrong model include, ignored parameter, misspelled section name). Every
# number it produces looks reasonable; every record it writes is worthless.
#
# So the test is a NEGATIVE CONTROL. `--sabotage-corners` forces every corner
# bundle to typical while keeping the corner NAMES. A bench whose anchor
# measurement carries a `min_spread_pct_by_axis[process]` floor MUST then
# fail. If it passes sabotaged, corner switching is not taking effect.
#
#   1. environment/toolchain/DUT-contract check
#   2. every bench runs at the nominal point         (must PASS)
#   3. the anchored benches run sabotaged            (must FAIL)
#
# Exit 0 only if all three hold.

set -uo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

RUNNER=(python3 "${SIM_DIR}/run_corners.py")
FAILED=0
declare -a RESULTS=()

note() { printf '\n---- %s\n' "$*"; }
ok()   { RESULTS+=("PASS  $*"); }
bad()  { RESULTS+=("FAIL  $*"); FAILED=$((FAILED + 1)); }

note "1. environment, toolchain pins and DUT interface contract"
if "${RUNNER[@]}" --check-env; then ok "environment"; else bad "environment"; fi

note "2. every bench completes at the nominal PVT point"
for campaign in comparator-offset-mc comparator-preamp-noise \
                comparator-regeneration comparator-kickback; do
  # A per-axis sensitivity check is SKIPPED, not failed, on a grid that does
  # not sweep that axis (harness/report.py swept_axes) -- so a single-point
  # run is expected to pass here, with the skips named in its output.
  if "${RUNNER[@]}" "${campaign}" \
       --corners tt --temps 27 --supply-tolerance 0 --no-write -j 1 \
       >/tmp/loom-selftest-$$.log 2>&1; then
    ok "nominal ${campaign}"
  else
    tail -20 /tmp/loom-selftest-$$.log
    bad "nominal ${campaign}"
  fi
done
rm -f /tmp/loom-selftest-$$.log

note "3. NEGATIVE CONTROL: sabotaged corners must FAIL the process-sensitivity checks"
# run_corners.py returns 0 from a sabotage run when the run correctly FAILED
# its checks, and 4 when it wrongly passed. It also forces --no-write, so a
# sabotaged run can never enter sim/ as evidence.
for campaign in comparator-offset-mc comparator-preamp-noise \
                comparator-regeneration comparator-kickback; do
  if "${RUNNER[@]}" "${campaign}" --sabotage-corners -j 4 \
       >/tmp/loom-sabotage-$$.log 2>&1; then
    ok "sabotage ${campaign} correctly failed its process-sensitivity check"
  else
    tail -20 /tmp/loom-sabotage-$$.log
    bad "sabotage ${campaign} PASSED -- corner switching is NOT taking effect"
  fi
done
rm -f /tmp/loom-sabotage-$$.log

echo
echo "=============================================================================="
echo "  HARNESS SELFTEST SUMMARY"
for line in "${RESULTS[@]}"; do
  echo "    ${line}"
done
echo "  ${FAILED} failure(s)"
echo "=============================================================================="
exit "${FAILED}"
