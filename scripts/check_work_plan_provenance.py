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

The region's own self-consistency is checked offline, with zero API calls
(issue #419): the renderer's section suffixes (' *(curated)*' under
'## Proposed', ' *(architect)*' / ' *(hermit)*' under '## Proposed
(Architect / Hermit)', none anywhere else), the renderer's hold marker
' *(held)*' (issue #446) -- legal on a row in every section, but only as
the row's final token, after a section suffix in the Proposed sections --
and the Backlog Balance counts against the number of rows their sections
render. Both compare the file against the renderer's documented output
shape, so neither can be reddened by forge activity.

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
  * a row under '## Proposed' without its renderer ' *(curated)*' suffix
    (or ' *(architect)*' / ' *(hermit)*' under '## Proposed (Architect /
    Hermit)'), or a section suffix on a row in any other section -> fail,
    named, quoting the row (issue #419); a hold marker ' *(held)*' before
    a section suffix -> fail, named (issue #446)
  * a 'Backlog Balance' count that does not equal the number of '- **#N**:'
    rows its section renders -- table rows are paired to sections by
    position, one per section -- or a table row / section added or removed
    without the other -> fail, named, quoting both numbers and the section
    (issue #419)

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
# first comparison (see match()). 'held' is the renderer's hold marker
# (issue #446): appended to any row whose item carries a hold label, in
# every section -- it lives in this alternation so match()'s fallback
# strips it too, never as a section requirement (see PROPOSED_SUFFIXES).
SUFFIX = re.compile(r" \*\((?:curated|architect|hermit|held)\)\*$")
# The hold marker alone: one trailing ' *(held)*' (issue #446), stripped
# before title comparison -- after match()'s exact-match-first, so a forge
# title that genuinely ends in the same literal still matches exactly.
HELD = re.compile(r" \*\(held\)\*$")
# A trailing RUN of hold markers: a forge title that itself ends in the
# literal renders doubled, like a doubled section suffix; the shape check
# tolerates that the same way (see check_row_suffixes).
HELD_RUN = re.compile(r"(?: \*\(held\)\*)+$")
# A hold marker directly before a section suffix: a shape the renderer
# cannot emit -- ' *(held)*' is always a row's final token -- so it is
# rejected offline, before any forge query (issue #446).
MISPLACED_HELD = re.compile(
    r" \*\(held\)\* \*\((?:curated|architect|hermit)\)\*$")
# Region self-consistency (issue #419): the renderer requires its suffix on
# every row of the two Proposed sections and emits none anywhere else, and
# it derives the Backlog Balance table from the same shell variables the
# sections render. Both shapes are asserted offline, before the token gate.
PROPOSED_SUFFIXES = {
    "Proposed": (" *(curated)*",),
    "Proposed (Architect / Hermit)": (" *(architect)*", " *(hermit)*"),
}
BALANCE = "Backlog Balance"
BALANCE_HEADER = "| Bucket | Count |"
SECTION = re.compile(r"^## (.+?)\s*$", re.M)
COUNT_ROW = re.compile(r"^\|\s*(.+?)\s*\|\s*(\d+)\s*\|$")
COUNT_SEPARATOR = re.compile(r"^\|(\s*:?-+:?\s*\|)+$")
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


def split_sections(region):
    """[(heading, section_text)] for every '## ' heading, in render order;
    each section_text runs from its heading line to the next heading or
    the region end."""
    heads = list(SECTION.finditer(region))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(region)
        out.append((m.group(1), region[m.start():end]))
    return out


def check_row_suffixes(region):
    """The renderer's section suffixes are part of the region's documented
    shape (issue #419): every row under '## Proposed' must end in
    ' *(curated)*', every row under '## Proposed (Architect / Hermit)' in
    ' *(architect)*' or ' *(hermit)*', and rows in every other section
    must carry none. The hold marker ' *(held)*' (issue #446) is part of
    that shape too: legal on a row in ANY section, but only as the row's
    final token -- after the section suffix in the Proposed sections -- so
    trailing hold markers are stripped before the per-section test, and
    one that precedes a section suffix is a named failure. match() still
    tolerates a suffix when comparing against the forge title -- so a
    regeneration that drops the suffix would otherwise be
    indistinguishable from one that emits it; this makes the drop a named
    failure."""
    errs = []
    for heading, text in split_sections(region):
        required = PROPOSED_SUFFIXES.get(heading)
        for m in ROW.finditer(text):
            title = m.group(2).strip()
            if MISPLACED_HELD.search(title):
                errs.append(f"{ERR}#{m.group(1)} renders under "
                            f"'{heading}' with the hold marker before a "
                            f"section suffix, but the renderer emits "
                            f"' *(held)*' only as a row's final token: "
                            f"{m.group(0)!r}")
            base = HELD_RUN.sub("", title)
            if required is None:
                if SUFFIX.search(base):
                    errs.append(f"{ERR}#{m.group(1)} renders under "
                                f"'{heading}' carrying a section suffix, "
                                f"which only the Proposed sections are "
                                f"emitted with: {m.group(0)!r}")
            elif not any(base.endswith(s) for s in required):
                want = " or ".join(f"'{s}'" for s in required)
                errs.append(f"{ERR}#{m.group(1)} renders under '{heading}' "
                            f"without the renderer's {want} suffix: "
                            f"{m.group(0)!r}")
    return errs


def check_balance(region):
    """The Backlog Balance table is derived from the same shell variables
    the sections render (render_plan_body's count()), so count-equals-rows
    holds by construction at render time -- and nothing re-checked it
    afterwards, making a row cleanly deleted from the committed region
    invisible to every other check. Pair the table's rows to the region's
    other sections by POSITION, not by name: the bucket labels
    deliberately differ from the headings, so name-matching would need a
    hand-maintained bucket->heading map that drifts from the renderer --
    the failure mode issue #419 exists to close. The table must carry
    exactly one row per section, in render order, and each count must
    equal that section's number of '- **#N**:' rows, 0 included for a
    '_None._' section."""
    errs = []
    sections = split_sections(region)
    body = [(h, len(ROW.findall(t))) for h, t in sections if h != BALANCE]
    balance = [t for h, t in sections if h == BALANCE]
    if len(balance) != 1:
        errs.append(f"{ERR}region has {len(balance)} '{BALANCE}' sections; "
                    f"the renderer emits exactly one, and without it no "
                    f"section's row count can be checked")
        return errs
    pipe = [ln.strip() for ln in balance[0].split("\n")
            if ln.strip().startswith("|")]
    if not pipe:
        errs.append(f"{ERR}'{BALANCE}' section carries no table; the "
                    f"renderer emits '| Bucket | Count |' with one count "
                    f"row per section")
        return errs
    if pipe[0] != BALANCE_HEADER:
        errs.append(f"{ERR}'{BALANCE}' table does not start with the "
                    f"renderer's {BALANCE_HEADER!r} header row: "
                    f"{pipe[0]!r}")
    counts = []
    for ln in pipe[1:]:
        if COUNT_SEPARATOR.match(ln):
            continue
        m = COUNT_ROW.match(ln)
        if not m:
            errs.append(f"{ERR}'{BALANCE}' table row is not the renderer's "
                        f"'| label | count |' shape: {ln!r}")
            continue
        counts.append((m.group(1), int(m.group(2))))
    if len(counts) != len(body):
        errs.append(f"{ERR}'{BALANCE}' table has {len(counts)} count row(s) "
                    f"for {len(body)} rendered section(s) -- a section or a "
                    f"table row was added or removed without the other")
        return errs
    for (heading, n), (label, count) in zip(body, counts):
        if count != n:
            errs.append(f"{ERR}'{BALANCE}' row {label!r} says {count} but "
                        f"section '{heading}' renders {n} row(s) -- "
                        f"regenerate the plan or restore the deleted row(s)")
    return errs


def match(rendered, forge_title):
    """Exact match first (a forge title may genuinely end in a renderer
    suffix -- ' *(held)*' included, issue #446 -- which stripping would
    otherwise eat); then allow the renderer-appended markers: one hold
    marker, then a section suffix (the forge title itself never carries
    one, unless it genuinely ends in it, which the exact comparison
    already covers)."""
    if rendered == forge_title:
        return True
    base = HELD.sub("", rendered, count=1)
    if base == forge_title:
        return True
    m = SUFFIX.search(base)
    return bool(m) and base[:m.start()] == forge_title


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
    try:
        region = extract_region(plan_text)
    except Failure as e:
        return [str(e)]
    # Region-internal, offline checks (issue #419): zero API calls and no
    # dependence on live forge state, so they run ahead of the token gate
    # and still report on a tokenless invocation.
    errs.extend(check_row_suffixes(region))
    errs.extend(check_balance(region))
    if not token:
        errs.append(f"{ERR}no forge token (set GITHUB_TOKEN or GH_TOKEN); "
                    f"cannot verify provenance")
        return errs
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
