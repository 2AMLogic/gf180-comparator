#!/usr/bin/env python3
"""Store a staged campaign's evidence; commit only its manifest and summary.

Issue #331. Anything that produces evidence -- a corner campaign, a
``klt sim`` batch, a PEX run, a derived report set -- writes its outputs into
a git-ignored scratch directory (``sim/.work/...`` or anywhere outside the
repo) and then runs::

    python3 sim/run_store_evidence.py <bench> <run-id> <staged-dir> --summary <summary.md>

Every regular file under ``<staged-dir>`` is put through ``klt artifact put``
under the logical name ``sim/<bench>/<kind>/<run-id>/<relative path>``
(``--kind`` is ``records`` by default). The repo then gains exactly two
files: ``manifests/artifacts/<bench>-<run-id>.manifest.json`` and the summary,
committed as ``sim/<bench>/<kind>/<run-id>.md`` with a "Stored evidence"
table appended. Nothing under ``<staged-dir>`` is copied into ``sim/``.

Fail closed: no broker (``$KLT_ARTIFACT_BROKER``), no ``klt`` with the
``artifact`` verb, an unreachable or refusing broker, or any failed put exits
10 with nothing committed; the staged files are left where they are.

Exit codes: 0 stored; 1 usage / bad staged directory; 10 not stored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import evidence_store as store_mod  # noqa: E402

KINDS = ("records", "corners", "probes", "yield")


def _staged_dir_problem(staged: Path, bench: str) -> str | None:
    if not staged.is_dir():
        return f"{staged} is not a directory"
    try:
        rel = staged.relative_to(REPO_ROOT)
    except ValueError:
        return None  # outside the repo: fine
    if rel.parts[:2] == ("sim", ".work"):
        return None  # git-ignored scratch
    return ("the staged directory is inside the repo but not under sim/.work/; "
            "stage evidence in git-ignored scratch so its bytes are never committed")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bench", help="bench directory name under sim/")
    ap.add_argument("run_id", help="campaign/run identity, e.g. 20261022-abc1234")
    ap.add_argument("staged", type=Path, help="directory holding the evidence bytes")
    ap.add_argument("--summary", type=Path, required=True,
                    help="Markdown summary to commit (results, method, reproduce)")
    ap.add_argument("--kind", choices=KINDS, default="records",
                    help="protected evidence directory (signoff/check_append_only_evidence.py "
                         "FAMILIES) the run belongs to")
    args = ap.parse_args(argv)

    try:
        store_mod.manifest_path(REPO_ROOT, args.bench, args.run_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not (REPO_ROOT / "sim" / args.bench).is_dir():
        print(f"ERROR: no bench directory sim/{args.bench}", file=sys.stderr)
        return 1
    staged = args.staged.resolve()
    problem = _staged_dir_problem(staged, args.bench)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    try:
        summary_text = args.summary.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read summary: {exc}", file=sys.stderr)
        return 1

    prefix = f"sim/{args.bench}/{args.kind}/{args.run_id}"
    summary_path = REPO_ROOT / "sim" / args.bench / args.kind / f"{args.run_id}.md"
    try:
        store_mod.preflight(REPO_ROOT)
        files = store_mod.stage_files(staged, prefix, exclude=[args.summary])
        manifest = store_mod.store_files(
            files, repo_root=REPO_ROOT, bench=args.bench, rid=args.run_id,
            summary_text=summary_text, summary_path=summary_path)
    except store_mod.StoreError as exc:
        print(f"EVIDENCE NOT STORED -- nothing committed (fail closed): {exc}",
              file=sys.stderr)
        return 10
    print(f"stored {len(files)} file(s) from {args.staged}")
    print(f"  manifest: {manifest.relative_to(REPO_ROOT)}")
    print(f"  summary:  {summary_path.relative_to(REPO_ROOT)}")
    print("commit both; the staged directory can be deleted once "
          f"`python3 scripts/check_artifact_manifests.py verify {manifest.relative_to(REPO_ROOT)}` "
          "passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
