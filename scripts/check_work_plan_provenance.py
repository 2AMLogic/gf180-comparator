#!/usr/bin/env python3
"""WORK_PLAN.md's generated region must cite only this repo's items, with
titles that match the forge (issue #411). Stdlib only, PDK-free, fail-closed.

The region between the `<!-- guide:plan-body:start -->` / `:end` markers
claims to be "generated from the repository's current GitHub label state"
(the file's own header line). This check discharges that claim: every
`- **#N**: title` row in the region must resolve -- in THIS repo, via the
forge API -- to an existing issue or PR whose title equals the rendered
title. PR #410 (commit 2af9216c, 2026-11-15) rendered a foreign repo's label
state into this file; see docs/forensics/2026-11-15-work-plan-provenance-
incident.md. Every foreign number also existed in this repo, closed, under an
unrelated title, so an existence-only check passes on exactly that input --
titles are matched, not just numbers.

Fail-closed (a check that cannot run must never look like one that passed,
.loom/docs/ci-principles.md):
  * missing or malformed region markers, or a whitespace-only region -> fail
  * no forge token (GITHUB_TOKEN / GH_TOKEN) -> fail, never skip
  * any API error (auth, permission, rate limit, network) -> fail, named
  * a number that resolves to nothing -> fail, named
  * a rendered title that does not match the forge title -> fail, named,
    quoting both titles
  * a line that names an item number but is not a strict '- **#N**:
    title' row (renderer format drift: bullet marker, indentation,
    container) -> fail, named -- a non-empty region must never parse
    to zero rows and look like a pass

Run by .github/workflows/signoff.yml as its own step. Deliberately NOT in
scripts/run-pdk-free-tests.sh, which must stay offline and PDK-free; the
offline unit tests (scripts/tests/test_check_work_plan_provenance.py) inject
a fake forge instead of the API.

Usage:
  python3 scripts/check_work_plan_provenance.py                 # WORK_PLAN.md
  python3 scripts/check_work_plan_provenance.py --plan PATH     # a file, or - for stdin
  python3 scripts/check_work_plan_provenance.py --repo OWNER/NAME

The repo is resolved in order: --repo, $GITHUB_REPOSITORY (set in GitHub
Actions and always the base repo, which is right even for fork PRs), then the
origin remote of the checkout this script lives in.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "WORK_PLAN.md"
START = "<!-- guide:plan-body:start -->"
END = "<!-- guide:plan-body:end -->"
ROW = re.compile(r"^- \*\*#(\d+)\*\*: (.*)$", re.M)
# Loose, line-level counterpart: ANY line in the region that names an
# item number. Used only to detect rows the strict ROW can no longer
# parse -- a renderer format change (bullet marker, indentation,
# numbered list, table row, heading) must fail the check, never parse to
# zero rows. A strict-ROW line is exempt, so a parsed row whose own
# title legitimately contains #M (e.g. '... matches CI (#129)') is not a
# false positive; a #N in a section blurb would be flagged (the
# fail-closed direction), and the renderer's blurbs contain none.
LOOSE = re.compile(r"#\d+")
# The renderer appends these suffixes in the Proposed sections only; a real
# title may also end in one, so suffix handling is a fallback, never the
# first comparison (see match()).
SUFFIX = re.compile(r" \*\((?:curated|architect|hermit)\)\*$")
API = "https://api.github.com/repos/{repo}/issues/{number}"
REMOTE = re.compile(r"github\.com[:/](.+/.+?)(?:\.git)?/?$")
ERR = "WORK-PLAN-PROVENANCE: "


class Failure(Exception):
    """A fail-closed condition with a human-readable, named message."""


def read_plan(path):
    if str(path) == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")


def extract_region(text):
    """The text between the markers, or raise Failure (fail closed)."""
    if START not in text or END not in text:
        raise Failure(f"{ERR}WORK_PLAN.md has no {START} / {END} region; "
                      f"cannot verify provenance")
    region = text[text.index(START) + len(START):text.index(END)]
    if not region.strip():
        raise Failure(f"{ERR}WORK_PLAN.md's {START} region is empty; "
                      f"cannot verify provenance")
    return region


def parse_rows(region):
    """[(number, rendered_title)] for every bullet row, in file order."""
    return [(int(m.group(1)), m.group(2).strip()) for m in ROW.finditer(region)]


def unparsed_rows(region):
    """Lines that name an item number but are not a strict ROW -- the
    renderer's row format has drifted (bullet marker, indentation,
    container), so the rows present cannot be verified. Line-level over
    unparsed lines (a strict-ROW line is exempt), so a parsed row whose
    own title contains #M is not a false positive."""
    return [ln for ln in region.split("\n")
            if LOOSE.search(ln) and not ROW.match(ln)]


def match(rendered, forge_title):
    """Exact match first; then allow a renderer-appended section suffix
    (the forge title itself never carries it unless it genuinely ends in
    one, which the exact comparison already covers)."""
    if rendered == forge_title:
        return True
    m = SUFFIX.search(rendered)
    return bool(m) and rendered[:m.start()] == forge_title


def fetch_item(repo, number, token, api=API):
    """GET /repos/{repo}/issues/{number} -- PRs included (GitHub unifies
    them; the title is the same object). Raises Failure on anything that is
    not a valid item, naming the cause; never returns a skip signal."""
    req = urllib.request.Request(
        api.format(repo=repo, number=number),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gf180-comparator-provenance-guard",
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.load(e).get("message", "")
        except Exception:
            pass
        if e.code in (401, 403):
            raise Failure(f"{ERR}forge rejected the token for {repo} "
                          f"(HTTP {e.code} {detail}); check GITHUB_TOKEN's "
                          f"'issues: read' and 'pull-requests: read' scopes")
        if e.code == 404:
            raise Failure(f"{ERR}#{number} does not exist in {repo} "
                          f"(HTTP 404)")
        raise Failure(f"{ERR}forge query for #{number} in {repo} failed "
                      f"(HTTP {e.code} {detail})")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Failure(f"{ERR}forge query for #{number} in {repo} failed "
                      f"({e.__class__.__name__}: {e})")


def resolve_repo(root, repo_arg=None):
    """--repo arg > $GITHUB_REPOSITORY > the checkout's origin remote.
    Failing all three is a fail-closed error, not a skip."""
    if repo_arg:
        return repo_arg
    env = os.environ.get("GITHUB_REPOSITORY", "")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", env):
        return env
    r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        m = REMOTE.search(r.stdout.strip())
        if m:
            return m.group(1)
    raise Failure(f"{ERR}cannot determine which repo to check against "
                  f"(no --repo, no $GITHUB_REPOSITORY, no origin remote)")


def check(plan_text, repo, token, fetch=fetch_item):
    """Core: returns [error strings]; empty means the region is provenance-
    clean. `fetch` is injectable so the offline tests never touch the API."""
    errs = []
    if not token:
        return [f"{ERR}no forge token (set GITHUB_TOKEN or GH_TOKEN); "
                f"cannot verify provenance"]
    try:
        region = extract_region(plan_text)
    except Failure as e:
        return [str(e)]
    for line in unparsed_rows(region):
        errs.append(f"{ERR}plan-body row does not match the renderer's "
                    f"'- **#N**: title' format -- renderer drift or a "
                    f"hand-edited row; cannot verify provenance for: "
                    f"{line!r}")
    rows = parse_rows(region)
    seen = {}
    for number, rendered in rows:
        if number not in seen:
            try:
                seen[number] = fetch(repo, number, token)["title"]
            except Failure as e:
                errs.append(str(e))
                seen[number] = None
        title = seen[number]
        if title is not None and not match(rendered, title):
            errs.append(f"{ERR}#{number} renders as {rendered!r} but {repo}'s "
                        f"item #{number} is titled {title!r} -- the pinned "
                        f"title no longer matches this repo's current "
                        f"title. Either (a) the region is stale or "
                        f"mis-rendered (an item retitle or renderer drift "
                        f"that outran the last re-render) -- the common "
                        f"case, cleared by regenerating the region with a "
                        f"Guide document-maintenance tick -- or (b) the "
                        f"row is foreign or contaminated (docs/forensics/"
                        f"2026-11-15-work-plan-provenance-incident.md). "
                        f"A red here does not mean your PR is at fault; "
                        f"it clears when the region is clean.")
    return errs


def main(argv=None, fetch=fetch_item):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--plan", default=str(PLAN),
                   help="WORK_PLAN.md path, or - for stdin")
    p.add_argument("--repo", help="OWNER/NAME (default: GITHUB_REPOSITORY "
                   "or the checkout's origin remote)")
    args = p.parse_args(argv)
    try:
        repo = resolve_repo(ROOT, args.repo)
    except Failure as e:
        print(e)
        return 1
    try:
        text = read_plan(args.plan)
    except OSError as e:
        print(f"{ERR}cannot read {args.plan}: {e}")
        return 1
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    errs = check(text, repo, token, fetch=fetch)
    for e in errs:
        print(e)
    if errs:
        print(f"{ERR}{len(errs)} provenance failure(s) in {args.plan} "
              f"against {repo}")
        return 1
    n = len(parse_rows(extract_region(text)))
    print(f"work plan provenance: ok ({n} row(s) checked against {repo})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
