#!/usr/bin/env python3
"""Size budget for protected sim/ evidence (issue #246). Stdlib only, PDK-free.

Protected `sim/` evidence is append-only (sim/README.md), so every committed
byte is permanent and is paid for by every clone. This guard reads the sizes of
tracked blobs in a Git tree (default HEAD) and applies a forward-looking budget
to *protected* paths (same path policy as check_append_only_evidence.py):

    size <= 5 MiB   fine
    5 .. 25 MiB     WARN  (listed; exit 0)
    > 25 MiB        FAIL  unless the path has an allowlist entry with a reason

Allowlist: signoff/sim_size_allowlist.json, {"<path>": "<reason>"}. An entry
with an empty reason fails. An allowlisted file is exempt from WARN and FAIL
and is reported as grandfathered. An entry naming a path that is not a tracked
protected file is stale and fails (keeps the list honest). Existing large
files are grandfathered by listing them; none are ever modified or moved.

The largest tracked sim/** files are always listed (top 10).

Usage:
    python3 signoff/check_sim_size_budget.py [--rev REV] [--allowlist FILE]
Exit: 0 ok (warnings allowed), 1 budget violation, 2 usage/git error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MIB = 1024 * 1024
WARN_BYTES = 5 * MIB
FAIL_BYTES = 25 * MIB
TOP_N = 10
HERE = Path(__file__).resolve().parent
DEFAULT_ALLOWLIST = HERE / "sim_size_allowlist.json"


def _is_protected():
    spec = importlib.util.spec_from_file_location(
        "_append_only_policy", HERE / "check_append_only_evidence.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.is_protected


def tree_sizes(repo: Path, rev: str) -> dict[str, int]:
    """{path: size in bytes} for every blob under sim/ in `rev`."""
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "-l", "-z", "--full-tree", rev, "--", "sim"],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip())
    sizes: dict[str, int] = {}
    for rec in proc.stdout.split(b"\0"):
        if not rec:
            continue
        meta, _, raw = rec.partition(b"\t")
        fields = meta.decode().split()
        if fields[1] != "blob":
            continue
        sizes[raw.decode("utf-8", "surrogateescape")] = int(fields[3])
    return sizes


def load_allowlist(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object {{path: reason}}")
    return data


def evaluate(sizes: dict[str, int], allow: dict[str, str], is_protected,
             warn: int = WARN_BYTES, fail: int = FAIL_BYTES):
    """Return (failures, warnings, grandfathered) as lists of strings."""
    failures: list[str] = []
    warnings: list[str] = []
    grand: list[str] = []
    for p, reason in sorted(allow.items()):
        if not isinstance(reason, str) or not reason.strip():
            failures.append(f"allowlist entry has no reason: {p}")
        if p not in sizes or not is_protected(p):
            failures.append(f"stale allowlist entry (not a tracked protected file): {p}")
    for p, n in sorted(sizes.items()):
        if not is_protected(p) or n <= warn:
            continue
        mb = n / MIB
        if p in allow and str(allow[p]).strip():
            grand.append(f"{mb:7.2f} MiB  {p}  [{allow[p].strip()}]")
        elif n > fail:
            failures.append(
                f"{mb:.2f} MiB exceeds the {fail // MIB} MiB budget with no allowlist "
                f"entry: {p}")
        else:
            warnings.append(f"{mb:.2f} MiB is above the {warn // MIB} MiB warn "
                            f"threshold: {p}")
    return failures, warnings, grand


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST))
    args = ap.parse_args(argv)
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=args.repo,
                             check=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE).stdout.decode().strip()
        sizes = tree_sizes(Path(top), args.rev)
        allow = load_allowlist(Path(args.allowlist))
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: sim size budget cannot run: {exc}", file=sys.stderr)
        return 2
    failures, warnings, grand = evaluate(sizes, allow, _is_protected())

    print(f"sim size budget: warn > {WARN_BYTES // MIB} MiB, fail > {FAIL_BYTES // MIB} MiB "
          f"(protected paths; {args.rev})")
    print(f"largest tracked sim/** files (of {len(sizes)}):")
    for p, n in sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]:
        print(f"  {n / MIB:7.2f} MiB  {p}")
    for g in grand:
        print(f"GRANDFATHERED {g}")
    for w in warnings:
        print(f"WARN: {w}")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        print("Slim the report, or add a reasoned entry to signoff/sim_size_allowlist.json "
              "(see sim/README.md, 'Evidence size budget').")
        return 1
    print(f"OK: {len(warnings)} warning(s), {len(grand)} grandfathered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
