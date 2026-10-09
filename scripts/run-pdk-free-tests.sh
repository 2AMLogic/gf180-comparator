#!/usr/bin/env bash
# The single enumeration of PDK-free tests and --check verifiers (issue #129).
# `npm test` and .github/workflows/signoff.yml both run this script, so local
# and CI answers cannot drift. Needs python3 only; steps that need the pinned
# grader `klt` are skipped by name when it is absent. Does NOT run
# sim/selftest.sh (needs ngspice >= 46; see `npm run check:ci`).
#
# Usage:
#   scripts/run-pdk-free-tests.sh              run every step, in order
#   scripts/run-pdk-free-tests.sh <target>     targeted run; <target> is a step
#                                              id (substring match) or a path
#                                              to one test_*.py / test-*.py
#   scripts/run-pdk-free-tests.sh --list       list step ids and names
#
# TO ADD A STEP (e.g. #121): add one `step` line in the STEPS section below.
# TO ADD A TEST FILE: drop test_*.py (or test-*.py) in a directory listed in
# TEST_DIRS; it is discovered automatically. A test file anywhere else in the
# repo fails the `discovery` step until its directory is added.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
PY="${PYTHON:-python3}"

# Directories whose test files are run one by one as scripts (each is a
# stdlib unittest / self-checking script). sim/harness/tests is run through
# `unittest discover` instead (see the `harness` step).
TEST_DIRS=(design/tests signoff/tests manifests)
UNITTEST_DIRS=(sim/harness/tests)

have_klt() {
  [ -n "${KLT:-}" ] && [ -x "$KLT" ] && return 0
  [ -x "$(dirname "$("$PY" -c 'import sys;print(sys.executable)')")/klt" ] && return 0
  command -v klt >/dev/null 2>&1
}

run_test_dirs() {
  local rc=0 f d n=0
  for d in "${TEST_DIRS[@]}"; do
    for f in "$d"/test_*.py "$d"/test-*.py; do
      [ -e "$f" ] || continue
      n=$((n + 1))
      echo "--- $f"
      "$PY" "$f" || rc=1
    done
  done
  [ "$n" -gt 0 ] || { echo "no test files found in ${TEST_DIRS[*]}"; return 1; }
  return "$rc"
}

run_unittest_dirs() {
  local rc=0 d
  for d in "${UNITTEST_DIRS[@]}"; do
    "$PY" -m unittest discover -s "$d" -v || rc=1
  done
  return "$rc"
}

# Every test file in the repo must live in a covered directory.
check_discovery() {
  local rc=0 f d ok
  while IFS= read -r f; do
    ok=0
    for d in "${TEST_DIRS[@]}" "${UNITTEST_DIRS[@]}"; do
      [ "$(dirname "$f")" = "$d" ] && ok=1
    done
    if [ "$ok" = 0 ]; then
      echo "UNCOVERED test file: $f (add its directory to TEST_DIRS in $0)"
      rc=1
    fi
  done < <(find . \( -name .git -o -name .loom -o -name node_modules \) -prune -o \
             -type f \( -name 'test_*.py' -o -name 'test-*.py' \) -print | sed 's|^\./||' | sort)
  [ "$rc" = 0 ] && echo "all test files are under covered directories"
  return "$rc"
}

STEP_IDS=(); STEP_NAMES=(); STEP_KLT=(); STEP_CMDS=()
step() { STEP_IDS+=("$1"); STEP_NAMES+=("$2"); STEP_KLT+=("$3"); STEP_CMDS+=("$4"); }

# ---- STEPS (in order): id, CI-visible name, needs-klt (0/1), command -------
step discovery   "Test-file discovery coverage"                      0 'check_discovery'
step harness     "Run harness regression tests (PDK-free)"           0 'run_unittest_dirs'
step netlist-pin "Netlist source-pin check (PDK-free)"               0 "$PY design/verify-netlist-pins.py --check"
step klt-pin     "Grader pin consistency check"                      0 "$PY signoff/check_klt_pin.py"
step integrator  "Verify integrator manifest maturity consistency"   0 "$PY manifests/verify-integrator.py"
step regrade     "Re-grade the manifest and verify the committed pins" 1 "$PY signoff/verify-report.py"
step item5       "Item-5 corner-matrix wrapper freshness check"      0 "$PY signoff/make_item5_envelope.py --check"
step unit-tests  "Unit tests: design/tests, signoff/tests, manifests" 0 'run_test_dirs'
# ---- END STEPS --------------------------------------------------------------

if [ "${1:-}" = "--list" ]; then
  for i in "${!STEP_IDS[@]}"; do
    printf '%-12s %s%s\n' "${STEP_IDS[$i]}" "${STEP_NAMES[$i]}" "$([ "${STEP_KLT[$i]}" = 1 ] && echo ' [needs klt]')"
  done
  exit 0
fi

TARGET="${1:-}"
CI="${GITHUB_ACTIONS:-}"
group()    { [ -n "$CI" ] && echo "::group::$1" || echo "=== $1"; }
endgroup() { [ -n "$CI" ] && echo "::endgroup::"; return 0; }

# A path to a single test file: run just that.
if [ -n "$TARGET" ] && [ -f "$TARGET" ]; then
  case "$TARGET" in
    sim/harness/tests/*) exec "$PY" -m unittest discover -s sim/harness/tests -p "$(basename "$TARGET")" -v ;;
    *) exec "$PY" "$TARGET" ;;
  esac
fi

FAILED=(); SKIPPED=(); RAN=0
for i in "${!STEP_IDS[@]}"; do
  id="${STEP_IDS[$i]}"
  [ -z "$TARGET" ] || [[ "$id" == *"$TARGET"* ]] || continue
  name="${STEP_NAMES[$i]}"
  if [ "${STEP_KLT[$i]}" = 1 ] && ! have_klt; then
    if [ -n "$CI" ]; then
      echo "::error title=$name::klt missing in CI; refusing to skip"
      FAILED+=("$name (klt missing)"); continue
    fi
    echo "SKIP (klt not found; set \$KLT): $name"
    SKIPPED+=("$name"); continue
  fi
  RAN=$((RAN + 1))
  group "$name"
  if eval "${STEP_CMDS[$i]}"; then rc=0; else rc=1; fi
  endgroup
  if [ "$rc" != 0 ]; then
    [ -n "$CI" ] && echo "::error title=$name::step failed"
    echo "FAIL: $name"; FAILED+=("$name")
  fi
done

if [ -n "$TARGET" ] && [ "$RAN" = 0 ] && [ "${#SKIPPED[@]}" = 0 ]; then
  echo "no step or test file matches '$TARGET' (try --list)"; exit 2
fi
echo "=== summary: ran $RAN, failed ${#FAILED[@]}, skipped ${#SKIPPED[@]}"
for n in "${SKIPPED[@]+"${SKIPPED[@]}"}"; do echo "  skipped: $n"; done
for n in "${FAILED[@]+"${FAILED[@]}"}"; do echo "  FAILED:  $n"; done
[ "${#FAILED[@]}" = 0 ]
