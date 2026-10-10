#!/usr/bin/env python3
"""Append-only guard for committed simulation evidence (issue #135).

`sim/` results are append-only (CLAUDE.md, sim/README.md "Rules"). This
verifier compares two Git trees and fails if any *protected* path that exists
in the baseline is missing, modified, mode-changed or type-changed in the
head. Additions are always allowed. Stdlib only; no PDK, no simulator.

Protected path families (matched generically, so a new experiment directory
is protected with no edit here):

    sim/<experiment>/records/**
    sim/<experiment>/corners/**
    sim/<experiment>/netlist-snapshots/**
    sim/<experiment>/yield/**
    sim/<experiment>/probes/**           (committed feasibility probe artifacts)
    sim/corner-matrix/**/*.json          (item-5 revision envelopes)

Probe artifacts (reports, logs, refusals, and the `sources/` / `extract/`
copies bundled into a probe) are empirical results exactly as run, so the whole
subtree is immutable once committed. They stay experimental: protection does not
make them signoff evidence. Editable testbench/DUT sources live outside
`probes/`; a correction is a NEW probe identifier.

Everything else is out of scope: testbenches, harness code, experiment
README files, DUT/configuration sources, mutable `layout/` reports and the
signoff manifest/report (those keep their own re-pin/re-grade contract, see
signoff/README.md). There is deliberately NO allowlist or exception file: a
correction is a NEW run/revision path, never an overwrite.

Trees are read with `git ls-tree -r -z` (NUL-delimited) and compared path by
path on (mode, object type, blob id). Rename detection is never used: a move
is a deletion of the original (named, and rejected) plus an addition. A copy
that keeps the original is a pure addition and passes.

Baseline selection
------------------
CI (GITHUB_ACTIONS or CI set): the event decides, and nothing is ever skipped.
  pull_request  merge-base(PR base SHA, PR head SHA) .. PR head SHA. The
                checkout's synthetic merge commit (HEAD) is never used.
  push          event `before` SHA .. event `after` SHA, directly -- every
                commit in the push, forced pushes included. An all-zero
                `before` fails.
  SHAs come from the workflow environment (APPEND_ONLY_EVENT,
  APPEND_ONLY_PR_BASE_SHA, APPEND_ONLY_PR_HEAD_SHA, APPEND_ONLY_PUSH_BEFORE,
  APPEND_ONLY_PUSH_AFTER), falling back to GITHUB_EVENT_NAME and the JSON at
  GITHUB_EVENT_PATH. Missing/malformed/unresolvable data or an unsupported
  event fails with a diagnostic (exit 2).

Local:
  --base REV [--head REV]   compare REV .. head (default HEAD); with
                            --merge-base, compare merge-base(REV, head) ..
                            head. A bad explicit ref fails (exit 2).
  (no --base)               merge-base(origin/main, HEAD) .. HEAD. If
                            origin/main is unavailable, equals HEAD, or has
                            no common history, prints "SKIP (local-only)" and
                            exits 0.

Usage:
    python3 signoff/check_append_only_evidence.py
    python3 signoff/check_append_only_evidence.py --base origin/main --merge-base
    python3 signoff/check_append_only_evidence.py --base <sha> --head <sha>

Exit: 0 pass (or local-only skip), 1 protected evidence changed, 2 baseline
or usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROG = "check_append_only_evidence"
FAMILIES = ("records", "corners", "netlist-snapshots", "yield", "probes")
CORNER_MATRIX = "corner-matrix"
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ZERO_RE = re.compile(r"^0+$")

ENV_EVENT = "APPEND_ONLY_EVENT"
ENV_PR_BASE = "APPEND_ONLY_PR_BASE_SHA"
ENV_PR_HEAD = "APPEND_ONLY_PR_HEAD_SHA"
ENV_PUSH_BEFORE = "APPEND_ONLY_PUSH_BEFORE"
ENV_PUSH_AFTER = "APPEND_ONLY_PUSH_AFTER"


class BaselineError(Exception):
    """The comparison endpoints cannot be determined (exit 2)."""


# --------------------------------------------------------------------------
# Path policy
# --------------------------------------------------------------------------

def is_protected(path: str) -> bool:
    """True if `path` (repo-relative, '/'-separated) is immutable evidence."""
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "sim":
        return False
    if parts[1] == CORNER_MATRIX:
        return path.endswith(".json")
    return len(parts) >= 4 and parts[2] in FAMILIES


def display(path: str) -> str:
    """Unambiguous rendering of a path for diagnostics.

    Plain printable paths are shown as-is; anything with control characters,
    quotes, backslashes, leading/trailing blanks or undecodable bytes is shown
    as a JSON string literal so newline/tab names cannot forge output lines.
    """
    plain = (
        path.isprintable()
        and path == path.strip()
        and '"' not in path
        and "\\" not in path
    )
    if plain:
        try:
            path.encode("utf-8")
            return path
        except UnicodeEncodeError:  # surrogate-escaped non-UTF-8 bytes
            pass
    return json.dumps(path)


# --------------------------------------------------------------------------
# Git plumbing
# --------------------------------------------------------------------------

def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if check and proc.returncode != 0:
        raise BaselineError(
            f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()}"
        )
    return proc


def resolve(repo: Path, rev: str) -> str | None:
    """Resolve `rev` to a commit SHA, or None if it is not available."""
    if not rev or rev.startswith("-"):
        return None
    proc = git(repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
               rev + "^{commit}", check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip()


def merge_base(repo: Path, a: str, b: str) -> str | None:
    proc = git(repo, "merge-base", a, b, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip().splitlines()[0]


def is_shallow(repo: Path) -> bool:
    proc = git(repo, "rev-parse", "--is-shallow-repository", check=False)
    return proc.stdout.decode().strip() == "true"


def ls_tree(repo: Path, commit: str) -> dict[str, tuple[str, str, str]]:
    """{path: (mode, type, object id)} for every non-tree entry of `commit`."""
    out = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).stdout
    entries: dict[str, tuple[str, str, str]] = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, _, raw_path = rec.partition(b"\t")
        mode, otype, oid = meta.decode().split(" ")
        entries[os.fsdecode(raw_path)] = (mode, otype, oid)
    return entries


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

def _kind(mode: str) -> str:
    return {"120000": "symlink", "160000": "submodule"}.get(mode, "file")


def compare(repo: Path, base: str, head: str) -> tuple[list[str], int, int]:
    """Return (violations, protected-in-base count, protected additions)."""
    old = ls_tree(repo, base)
    new = ls_tree(repo, head)
    by_oid: dict[str, list[str]] = {}
    for p, (_, _, oid) in new.items():
        by_oid.setdefault(oid, []).append(p)

    violations: list[str] = []
    protected = 0
    for path in sorted(old):
        if not is_protected(path):
            continue
        protected += 1
        omode, otype, ooid = old[path]
        if path in new:
            nmode, ntype, noid = new[path]
            if _kind(omode) != _kind(nmode) or otype != ntype:
                violations.append(
                    f"type changed ({_kind(omode)} -> {_kind(nmode)}): {display(path)}")
            elif omode != nmode:
                violations.append(f"mode changed ({omode} -> {nmode}): {display(path)}")
            elif ooid != noid:
                violations.append(f"modified: {display(path)}")
            continue
        prefix = path + "/"
        if any(p.startswith(prefix) for p in new):
            violations.append(f"type changed (file -> directory): {display(path)}")
            continue
        moved = [p for p in by_oid.get(ooid, []) if p not in old]
        if moved:
            where = ", ".join(display(p) for p in sorted(moved)[:3])
            violations.append(
                f"deleted (moved/renamed; same bytes now at {where}): {display(path)}")
        else:
            violations.append(f"deleted: {display(path)}")
    added = sum(1 for p in new if p not in old and is_protected(p))
    return violations, protected, added


# --------------------------------------------------------------------------
# Baseline resolution
# --------------------------------------------------------------------------

def in_ci(env: dict[str, str]) -> bool:
    for key in ("GITHUB_ACTIONS", "CI"):
        val = env.get(key, "").strip().lower()
        if val and val not in ("0", "false", "no"):
            return True
    return False


def _event_payload(env: dict[str, str]) -> dict:
    path = env.get("GITHUB_EVENT_PATH", "")
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise BaselineError(f"cannot read GITHUB_EVENT_PATH {path!r}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _dig(data: dict, *keys: str) -> str:
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(k)
    return cur if isinstance(cur, str) else ""


def _need_sha(repo: Path, label: str, value: str, source: str) -> str:
    if not value:
        raise BaselineError(
            f"{label} is missing (expected from {source}); the Signoff workflow "
            f"must pass it -- see .github/workflows/signoff.yml")
    if not SHA_RE.match(value):
        raise BaselineError(f"{label} {value!r} is not a full commit SHA")
    if ZERO_RE.match(value):
        raise BaselineError(
            f"{label} is the all-zero SHA; there is no previous commit to compare "
            "against. This workflow only runs on an existing main branch, so this "
            "is unsupported -- refusing to skip in CI")
    sha = resolve(repo, value)
    if sha is None:
        hint = " (the clone is shallow: use actions/checkout fetch-depth: 0)" \
            if is_shallow(repo) else ""
        raise BaselineError(
            f"{label} {value} is not available in this clone{hint}; fetch it "
            f"explicitly (git fetch origin {value}) before running this check")
    return sha


def ci_endpoints(repo: Path, env: dict[str, str]) -> tuple[str, str, str]:
    """(baseline, head, description) for a CI run; never skips."""
    event = env.get(ENV_EVENT, "").strip() or env.get("GITHUB_EVENT_NAME", "").strip()
    if not event:
        raise BaselineError(
            f"running in CI but no event name ({ENV_EVENT} / GITHUB_EVENT_NAME); "
            "refusing to skip")
    payload = _event_payload(env)
    if event == "pull_request":
        src = f"{ENV_PR_BASE} or pull_request.base.sha"
        base = _need_sha(repo, "pull_request base SHA",
                         env.get(ENV_PR_BASE, "").strip()
                         or _dig(payload, "pull_request", "base", "sha"), src)
        src = f"{ENV_PR_HEAD} or pull_request.head.sha"
        head = _need_sha(repo, "pull_request head SHA",
                         env.get(ENV_PR_HEAD, "").strip()
                         or _dig(payload, "pull_request", "head", "sha"), src)
        mb = merge_base(repo, base, head)
        if mb is None:
            hint = " (the clone is shallow: use fetch-depth: 0)" if is_shallow(repo) else ""
            raise BaselineError(
                f"no merge base between PR base {base} and PR head {head}{hint}")
        return mb, head, f"pull_request: merge-base({base[:12]}, {head[:12]}) = {mb[:12]}"
    if event == "push":
        before = _need_sha(repo, "push before SHA",
                           env.get(ENV_PUSH_BEFORE, "").strip() or _dig(payload, "before"),
                           f"{ENV_PUSH_BEFORE} or event.before")
        after = _need_sha(repo, "push after SHA",
                          env.get(ENV_PUSH_AFTER, "").strip() or _dig(payload, "after"),
                          f"{ENV_PUSH_AFTER} or event.after")
        return before, after, f"push: before {before[:12]} -> after {after[:12]}"
    raise BaselineError(
        f"unsupported CI event {event!r}: only pull_request and push are "
        "supported; refusing to skip")


def local_endpoints(repo: Path, args) -> tuple[str, str, str] | str:
    """(baseline, head, description), or a skip reason string."""
    head_rev = args.head or "HEAD"
    head = resolve(repo, head_rev)
    if head is None:
        raise BaselineError(f"--head {head_rev!r} does not resolve to a commit")
    if args.base:
        base = resolve(repo, args.base)
        if base is None:
            raise BaselineError(f"--base {args.base!r} does not resolve to a commit")
        if args.merge_base:
            mb = merge_base(repo, base, head)
            if mb is None:
                raise BaselineError(f"no merge base between {args.base!r} and {head_rev!r}")
            return mb, head, f"merge-base({args.base}, {head_rev}) = {mb[:12]}"
        return base, head, f"{args.base} -> {head_rev}"
    upstream = resolve(repo, "origin/main")
    if upstream is None:
        return "origin/main is not available (pass --base REV to compare explicitly)"
    if upstream == head:
        return f"{head_rev} equals origin/main; nothing to compare"
    mb = merge_base(repo, upstream, head)
    if mb is None:
        return f"origin/main and {head_rev} share no history"
    return mb, head, f"merge-base(origin/main, {head_rev}) = {mb[:12]}"


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog=PROG, description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="baseline revision (explicit; a bad ref fails)")
    ap.add_argument("--head", help="head revision (default HEAD)")
    ap.add_argument("--merge-base", action="store_true",
                    help="with --base: compare from merge-base(base, head)")
    ap.add_argument("--repo", default=".", help="repository path (default: cwd)")
    args = ap.parse_args(argv)
    env = dict(os.environ) if env is None else env
    repo = Path(args.repo)

    try:
        top = git(repo, "rev-parse", "--show-toplevel").stdout.decode().strip()
        repo = Path(top)
        if args.base or args.head:
            ends = local_endpoints(repo, args)
            mode = "explicit"
        elif in_ci(env):
            ends = ci_endpoints(repo, env)
            mode = "ci"
        else:
            ends = local_endpoints(repo, args)
            mode = "local"
        if isinstance(ends, str):
            print(f"SKIP (local-only): append-only evidence check not run -- {ends}")
            return 0
        base, head, desc = ends
        violations, protected, added = compare(repo, base, head)
    except BaselineError as exc:
        print(f"ERROR: append-only evidence check cannot run: {exc}", file=sys.stderr)
        if in_ci(env):
            print(f"::error title=append-only evidence::{exc}")
        return 2

    print(f"append-only evidence [{mode}] {desc}")
    if violations:
        print(f"FAIL: {len(violations)} committed protected evidence path(s) changed "
              f"between {base[:12]} and {head[:12]}:")
        for v in violations:
            print(f"  {v}")
        print("sim/ evidence is append-only: restore the original bytes and mode, and "
              "record a correction as a NEW run/revision path (update citations to "
              "point at it). See sim/README.md, 'Append-only enforcement'.")
        if in_ci(env):
            for v in violations:
                print(f"::error title=append-only evidence::{v}")
        return 1
    print(f"OK: {protected} protected path(s) in baseline unchanged; "
          f"{added} protected path(s) added")
    return 0


if __name__ == "__main__":
    sys.exit(main())
