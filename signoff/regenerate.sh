#!/usr/bin/env bash
# Regenerate signoff/signoff-report.json -- the committed `klt signoff
# --manifest` tier-verdict report this repo treats as the verdict of record
# for its gap-to-T1 state (issue #57; tracker issue #3 points here).
#
# Run from the repo root:
#     ./signoff/regenerate.sh
#
# Grader distribution discipline (load-bearing, observed live in the fleet):
# this script grades with a throwaway venv + the *pip registry wheel* of the
# pinned klayout-tools version, NOT whatever `klt` happens to be on PATH.
# Same-version builds are not the same code -- a git snapshot or full
# checkout under the same version string can grade a different item table
# than the released wheel. Grading with the same distribution CI grades with
# (.github/workflows/signoff.yml) is what makes the committed report
# byte-reproducible; keep this pin and that pin in sync.
#
# The tiers-doc pin is equally load-bearing: released klt 0.5.0 bundles the
# older 10-item checklist (item 11, "Power delivery (structural)", shipped
# after that release -- klayout-tools#2025), so the grade always passes
# --tiers-doc signoff/design-evidence-tiers.md, the vendored verbatim copy of
# the 11-item rulebook at klayout-tools commit 31a3e3c4. Grading without it
# renders a 10-item report whose t1_item_count disagrees with the committed
# one -- signoff/verify-report.py catches that as drift and fails. When a
# klayout-tools release carrying the 11-item rulebook ships, move both this
# distribution pin and the vendored doc forward together, then re-grade.
set -euo pipefail

# Keep in sync with the signoff job's pip install in
# .github/workflows/signoff.yml.
KLT_VERSION="0.5.0"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet "klayout-tools==$KLT_VERSION"

# The *identity* of the grading build matters as much as its version string:
# a git-snapshot or full-checkout install of the same version can grade
# differently. The released registry wheel reports the git tag it was built
# from -- assert it.
"$WORK/venv/bin/klt" version --format json > "$WORK/klt-version.json"
python3 - "$WORK/klt-version.json" "$KLT_VERSION" <<'EOF'
import json, sys

info = json.load(open(sys.argv[1]))
version = sys.argv[2]
if info.get("package_version") != version or info.get("git_tag") != f"v{version}" \
        or info.get("is_release") is not True:
    print(
        f"FATAL: grading klt is not the released {version} registry wheel -- "
        f"got package_version={info.get('package_version')} "
        f"git_tag={info.get('git_tag')} is_release={info.get('is_release')}. "
        "A same-version snapshot/full-checkout install grades differently; "
        "refusing to grade with it.",
        file=sys.stderr,
    )
    sys.exit(1)
EOF

# `klt signoff` exits 3 when the block grades below T1. That exit code is
# DATA ("some items are unmet"), not a failure -- this block has unmet items
# that live as open sub-issues, exactly the state the verdict of record
# exists to state. Only the other exit codes (1 = bad manifest/unparseable
# doc, 2 = usage error) are failures.
set +e
"$WORK/venv/bin/klt" signoff \
    --manifest signoff/block-manifest.json \
    --tiers-doc signoff/design-evidence-tiers.md \
    --format json > signoff/signoff-report.json
SIGNOFF_RC=$?
set -e
if [ "$SIGNOFF_RC" -ne 0 ] && [ "$SIGNOFF_RC" -ne 3 ]; then
    echo "FATAL: klt signoff exited $SIGNOFF_RC (not a rendered tier report)" >&2
    exit "$SIGNOFF_RC"
fi

python3 - "$KLT_VERSION" <<'EOF'
import json, sys

report = json.load(open("signoff/signoff-report.json"))
print(f"graded with klayout-tools=={sys.argv[1]} (PyPI registry wheel)")
print(f"{report['block']}: kind={report['kind']} tier={report['tier']} "
      f"T1 {report['t1_met_count']}/{report['t1_item_count']} items met")
for item in report["items"]:
    if item["tier"] == "T1":
        marker = "MET  " if item["status"] == "met" else "UNMET"
        reason = "" if item["status"] == "met" else " -- " + str(item["reason"])
        print(f"  [{marker}] #{item['id']:<2} {item['title']}{reason}")
EOF
