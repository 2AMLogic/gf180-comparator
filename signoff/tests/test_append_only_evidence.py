#!/usr/bin/env python3
"""PDK-free regressions for signoff/check_append_only_evidence.py (#135).

Every case builds a disposable Git repository in a temp directory and runs
the verifier against it with a fully controlled environment (CI variables of
the real runner are stripped). Committed sim/ evidence is never touched.

    python3 signoff/tests/test_append_only_evidence.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "signoff" / "check_append_only_evidence.py"
_spec = importlib.util.spec_from_file_location("check_append_only_under_test", SCRIPT)
CHECK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CHECK)

REC = "sim/comparator-offset-mc/records/20260910-124917-4805118.json"
LOG = "sim/comparator-kickback/corners/20260910-125200-4805118/tt_27_3v3.log"
SNAP = "sim/comparator-regeneration/netlist-snapshots/20260910-125206-4805118.spice"
YIELD = "sim/comparator-offset-mc/yield/20260910-125341-4805118.json"
ENVELOPE = "sim/corner-matrix/item5-corner-matrix-20260910-124917-4805118.json"
NEW_EXP = "sim/comparator-brand-new/records/20261009-000000-abcdef0.md"
PROBE = "sim/comparator-offset-x/probes/20261010-negative-control/report-mc-tt.json"
PROBE_SRC = "sim/comparator-offset-x/probes/20261010-negative-control/sources/testbench/tb.spice"
PROBE_LOG = "sim/comparator-offset-x/probes/20261010-negative-control/err-mc-tt.attempt1.txt"
PROTECTED = [REC, LOG, SNAP, YIELD, ENVELOPE, NEW_EXP, PROBE, PROBE_SRC, PROBE_LOG]
UNPROTECTED = [
    "sim/comparator-offset-mc/README.md",
    "sim/comparator-offset-mc/testbench/tb.json",
    "sim/comparator-offset-mc/testbench/tb_offset.spice",
    "sim/harness/run.py",
    "sim/dut.json",
    "sim/corner-matrix/README.md",
    "sim/comparator-offset-x/README.md",
    "sim/comparator-offset-x/testbench/tb.spice",
    "sim/probes/x.json",
    "layout/reports/drc-summary.json",
    "signoff/block-manifest.json",
    "signoff/signoff-report.json",
]

_CLEAN_KEYS = ("CI", "GITHUB_ACTIONS", "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH",
               CHECK.ENV_EVENT, CHECK.ENV_PR_BASE, CHECK.ENV_PR_HEAD,
               CHECK.ENV_PUSH_BEFORE, CHECK.ENV_PUSH_AFTER)


def base_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in _CLEAN_KEYS and not k.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    })
    return env


class Repo:
    def __init__(self, root: Path):
        self.root = root
        self.env = base_env()
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE
                              ).stdout.decode().strip()

    def write(self, rel: str, text: str = "x\n") -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg: str = "c") -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def run(self, *args: str, env: dict[str, str] | None = None):
        e = base_env()
        e.update(env or {})
        p = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.root), *args],
                           env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.returncode, p.stdout + p.stderr


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.r = Repo(Path(self._tmp.name))
        for rel in PROTECTED + UNPROTECTED:
            self.r.write(rel, f"original {rel}\n")
        self.base = self.r.commit("baseline")

    def check(self, *args, env=None):
        return self.r.run("--base", self.base, *args, env=env)

    def assertFailsNaming(self, result, path, word=None):
        rc, out = result
        self.assertEqual(rc, 1, out)
        self.assertIn(CHECK.display(path), out)
        if word:
            self.assertIn(word, out)

    def assertPasses(self, result):
        rc, out = result
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)


class PolicyTests(unittest.TestCase):
    def test_families(self):
        for p in PROTECTED:
            self.assertTrue(CHECK.is_protected(p), p)
        for p in UNPROTECTED:
            self.assertFalse(CHECK.is_protected(p), p)
        self.assertTrue(CHECK.is_protected("sim/x/corners/a/b/c.log"))
        self.assertFalse(CHECK.is_protected("sim/records/x.json"))
        self.assertFalse(CHECK.is_protected("sim/x/records"))
        self.assertFalse(CHECK.is_protected("design/sim/x/records/y.json"))

    def test_no_allowlist_surface(self):
        # No CLI option or env var can exempt a protected path.
        rc = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                            stdout=subprocess.PIPE, text=True)
        self.assertEqual(rc.returncode, 0)
        options = set(re.findall(r"--[a-z-]+", rc.stdout))
        self.assertEqual(options, {"--help", "--base", "--head", "--merge-base", "--repo"})

    def test_display_escapes_control_chars(self):
        self.assertEqual(CHECK.display("sim/a/records/x.json"), "sim/a/records/x.json")
        self.assertEqual(CHECK.display("a\nb"), '"a\\nb"')


class TreeComparisonTests(Base):
    def test_unchanged_passes(self):
        self.assertPasses(self.check())

    def test_additions_pass_in_every_family(self):
        for rel in PROTECTED:
            self.r.write(rel.replace("4805118", "9999999").replace("abcdef0", "1234567")
                         .replace("20261010-negative-control", "20261011-new-probe"), "new\n")
        self.r.write("sim/corner-matrix/item5-corner-matrix-r3.json", "{}\n")
        self.r.write("sim/comparator-other/records/first.md", "new experiment\n")
        self.r.commit()
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("11 protected path(s) added", out)

    def test_unprotected_changes_pass(self):
        for rel in UNPROTECTED:
            self.r.write(rel, "edited\n")
        self.r.git("rm", "-q", "-f", "sim/harness/run.py")
        self.r.commit()
        self.assertPasses(self.check())

    def test_modification_fails_in_each_family(self):
        for rel in PROTECTED:
            with self.subTest(rel=rel):
                self.r.git("checkout", "-q", "-B", "work", self.base)
                self.r.write(rel, "rewritten\n")
                self.r.commit()
                self.assertFailsNaming(self.check(), rel, "modified")

    def test_probe_artifact_modification_deletion_fails(self):
        for rel in (PROBE, PROBE_SRC, PROBE_LOG):
            with self.subTest(rel=rel):
                self.r.git("checkout", "-q", "-B", "work", self.base)
                self.r.write(rel, "rewritten\n")
                self.r.commit()
                self.assertFailsNaming(self.check(), rel, "modified")
                self.r.git("checkout", "-q", "-B", "work2", self.base)
                self.r.git("rm", "-q", rel)
                self.r.commit()
                self.assertFailsNaming(self.check(), rel, "deleted")

    def test_probe_rename_and_mode_change_fail(self):
        self.r.git("mv", PROBE, PROBE.replace("report", "report2"))
        self.r.commit()
        self.assertFailsNaming(self.check(), PROBE, "moved/renamed")
        self.r.git("checkout", "-q", "-B", "work", self.base)
        os.chmod(self.r.root / PROBE_LOG, 0o755)
        self.r.commit()
        self.assertFailsNaming(self.check(), PROBE_LOG, "mode changed")

    def test_new_probe_and_experiment_docs_edit_pass(self):
        self.r.write("sim/comparator-offset-x/probes/20261011-corrected/report.json", "n\n")
        self.r.write("sim/comparator-offset-x/README.md", "edited docs\n")
        self.r.write("sim/comparator-offset-x/testbench/tb.spice", "edited tb\n")
        self.r.commit()
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("1 protected path(s) added", out)

    def test_deletion_fails(self):
        self.r.git("rm", "-q", ENVELOPE)
        self.r.commit()
        self.assertFailsNaming(self.check(), ENVELOPE, "deleted")

    def test_mode_change_fails(self):
        os.chmod(self.r.root / REC, 0o755)
        self.r.commit()
        self.assertFailsNaming(self.check(), REC, "mode changed")

    def test_symlink_type_change_fails(self):
        (self.r.root / LOG).unlink()
        os.symlink("elsewhere.log", self.r.root / LOG)
        self.r.commit()
        self.assertFailsNaming(self.check(), LOG, "type changed (file -> symlink)")

    def test_file_to_directory_fails(self):
        (self.r.root / SNAP).unlink()
        self.r.write(SNAP + "/inner.spice", "x\n")
        self.r.commit()
        self.assertFailsNaming(self.check(), SNAP, "file -> directory")

    def test_rename_within_protected_tree_fails(self):
        self.r.git("mv", REC, REC.replace(".json", "-renamed.json"))
        self.r.commit()
        self.assertFailsNaming(self.check(), REC, "moved/renamed")

    def test_rename_out_of_protected_tree_fails(self):
        (self.r.root / "archive").mkdir()
        self.r.git("mv", YIELD, "archive/yield.json")
        self.r.commit()
        self.assertFailsNaming(self.check(), YIELD, "archive/yield.json")

    def test_rename_with_edit_fails(self):
        self.r.git("mv", REC, REC + ".bak")
        self.r.write(REC + ".bak", "edited too\n")
        self.r.commit()
        self.assertFailsNaming(self.check(), REC, "deleted")

    def test_copy_preserving_original_passes(self):
        src = self.r.root / REC
        (self.r.root / (REC + ".copy")).write_bytes(src.read_bytes())
        (self.r.root / "elsewhere.json").write_bytes(src.read_bytes())
        self.r.commit()
        self.assertPasses(self.check())

    def test_modify_then_restore_in_later_commit_passes(self):
        self.r.write(REC, "temp\n")
        self.r.commit()
        self.r.write(REC, f"original {REC}\n")
        self.r.commit()
        self.assertPasses(self.check())

    def test_unusual_filenames(self):
        names = [
            "sim/comparator-kickback/records/sp ace.md",
            "sim/comparator-kickback/records/new\nline.md",
            "sim/comparator-kickback/records/tab\there.md",
            "sim/comparator-kickback/records/café-σ.md",
            "sim/comparator-kickback/records/-leading-dash.md",
            'sim/comparator-kickback/records/quote"back\\slash.md',
        ]
        for n in names:
            self.r.write(n, "orig\n")
        self.base = self.r.commit("odd names")
        for n in names:
            self.r.write(n, "changed\n")
        self.r.commit()
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        for n in names:
            self.assertIn(f"modified: {CHECK.display(n)}", out)
        # A newline name must not be able to forge a separate output line.
        self.assertNotIn("\nline.md", out)


class LocalBaselineTests(Base):
    def test_no_origin_main_is_named_local_skip(self):
        self.r.write(REC, "rewritten\n")
        self.r.commit()
        rc, out = self.r.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("SKIP (local-only)", out)
        self.assertIn("origin/main is not available", out)

    def test_head_equals_origin_main_is_named_local_skip(self):
        self.r.git("update-ref", "refs/remotes/origin/main", self.base)
        rc, out = self.r.run()
        self.assertEqual(rc, 0, out)
        self.assertIn("SKIP (local-only)", out)

    def test_default_uses_merge_base_with_origin_main(self):
        self.r.git("checkout", "-q", "-b", "feature")
        self.r.write(REC, "rewritten\n")
        self.r.commit()
        # origin/main advanced independently with new evidence
        self.r.git("checkout", "-q", "main")
        self.r.write("sim/comparator-kickback/records/main-only.md", "m\n")
        main2 = self.r.commit()
        self.r.git("update-ref", "refs/remotes/origin/main", main2)
        self.r.git("checkout", "-q", "feature")
        rc, out = self.r.run()
        self.assertEqual(rc, 1, out)
        self.assertIn(f"modified: {REC}", out)
        self.assertNotIn("main-only.md", out)

    def test_explicit_invalid_refs_fail(self):
        for args in (["--base", "no-such-ref"], ["--base", self.base, "--head", "nope"],
                     ["--base", "--upload-pack=x"], ["--base", "0" * 40]):
            with self.subTest(args=args):
                rc, out = self.r.run(*args)
                self.assertEqual(rc, 2, out)
                self.assertNotIn("SKIP", out)

    def test_explicit_args_win_even_in_ci(self):
        self.r.write(REC, "rewritten\n")
        self.r.commit()
        rc, out = self.check(env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(rc, 1, out)

    def test_explicit_merge_base_flag(self):
        self.r.git("checkout", "-q", "-b", "feature")
        self.r.write("sim/comparator-kickback/records/feature.md", "f\n")
        feature = self.r.commit()
        self.r.git("checkout", "-q", "main")
        self.r.write("sim/comparator-kickback/records/main-only.md", "m\n")
        main2 = self.r.commit()
        rc, out = self.r.run("--base", main2, "--head", feature)
        self.assertEqual(rc, 1, out)  # direct comparison sees main-only.md missing
        rc, out = self.r.run("--base", main2, "--head", feature, "--merge-base")
        self.assertEqual(rc, 0, out)


class CiBaselineTests(Base):
    def ci(self, **extra):
        env = {"GITHUB_ACTIONS": "true"}
        env.update(extra)
        return self.r.run(env=env)

    # ---- pull_request ------------------------------------------------------
    def _diverged_pr(self, violate: bool):
        """main advances after the PR branches; checkout is a synthetic merge."""
        self.r.git("checkout", "-q", "-b", "pr")
        self.r.write("sim/comparator-kickback/records/pr-new.md", "pr\n")
        if violate:
            self.r.write(REC, "rewritten by the PR\n")
        pr_head = self.r.commit("pr")
        self.r.git("checkout", "-q", "main")
        self.r.write("sim/comparator-kickback/records/main-later.md", "main\n")
        main_tip = self.r.commit("main later")
        # Synthetic merge commit whose tree RESTORES the original record, so a
        # checker that compared HEAD instead of the PR head would wrongly pass.
        self.r.git("checkout", "-q", "--detach", main_tip)
        self.r.write("sim/comparator-kickback/records/pr-new.md", "pr\n")
        self.r.git("add", "-A")
        tree = self.r.git("write-tree")
        merge = self.r.git("commit-tree", tree, "-p", main_tip, "-p", pr_head, "-m", "merge")
        self.r.git("checkout", "-q", "--detach", merge)
        return main_tip, pr_head

    def test_pr_diverged_history_passes_via_merge_base(self):
        base, head = self._diverged_pr(violate=False)
        rc, out = self.ci(APPEND_ONLY_EVENT="pull_request",
                          APPEND_ONLY_PR_BASE_SHA=base, APPEND_ONLY_PR_HEAD_SHA=head)
        self.assertEqual(rc, 0, out)
        self.assertIn("merge-base", out)

    def test_pr_uses_submitted_head_not_synthetic_merge(self):
        base, head = self._diverged_pr(violate=True)
        rc, out = self.ci(APPEND_ONLY_EVENT="pull_request",
                          APPEND_ONLY_PR_BASE_SHA=base, APPEND_ONLY_PR_HEAD_SHA=head)
        self.assertEqual(rc, 1, out)
        self.assertIn(f"modified: {REC}", out)
        self.assertIn("::error", out)

    def test_pr_from_event_payload_file(self):
        base, head = self._diverged_pr(violate=True)
        ev = self.r.root.parent / f"{self.r.root.name}-event.json"
        ev.write_text(json.dumps({"pull_request": {"base": {"sha": base},
                                                   "head": {"sha": head}}}))
        self.addCleanup(ev.unlink)
        rc, out = self.ci(GITHUB_EVENT_NAME="pull_request", GITHUB_EVENT_PATH=str(ev))
        self.assertEqual(rc, 1, out)
        self.assertIn(f"modified: {REC}", out)

    def test_pr_missing_head_fails(self):
        rc, out = self.ci(APPEND_ONLY_EVENT="pull_request", APPEND_ONLY_PR_BASE_SHA=self.base)
        self.assertEqual(rc, 2, out)
        self.assertIn("head SHA is missing", out)

    def test_pr_missing_object_fails(self):
        rc, out = self.ci(APPEND_ONLY_EVENT="pull_request", APPEND_ONLY_PR_BASE_SHA=self.base,
                          APPEND_ONLY_PR_HEAD_SHA="1" * 40)
        self.assertEqual(rc, 2, out)
        self.assertIn("not available in this clone", out)
        self.assertIn("git fetch origin", out)

    def test_pr_unrelated_histories_fail(self):
        self.r.git("checkout", "-q", "--orphan", "lonely")
        orphan = self.r.commit("orphan")
        rc, out = self.ci(APPEND_ONLY_EVENT="pull_request",
                          APPEND_ONLY_PR_BASE_SHA=self.base, APPEND_ONLY_PR_HEAD_SHA=orphan)
        self.assertEqual(rc, 2, out)
        self.assertIn("no merge base", out)

    # ---- push --------------------------------------------------------------
    def test_push_multi_commit_checks_whole_range(self):
        self.r.git("rm", "-q", REC)
        self.r.commit("delete in first pushed commit")
        self.r.write("sim/comparator-kickback/records/later.md", "x\n")
        after = self.r.commit("unrelated second commit")
        # HEAD^..HEAD alone would pass:
        self.assertEqual(self.r.run("--base", "HEAD^")[0], 0)
        rc, out = self.ci(APPEND_ONLY_EVENT="push", APPEND_ONLY_PUSH_BEFORE=self.base,
                          APPEND_ONLY_PUSH_AFTER=after)
        self.assertEqual(rc, 1, out)
        self.assertIn(f"deleted: {REC}", out)

    def test_push_clean_multi_commit_passes(self):
        self.r.write("sim/comparator-kickback/records/a.md", "a\n")
        self.r.commit()
        self.r.write("sim/comparator-offset-mc/README.md", "edited\n")
        after = self.r.commit()
        rc, out = self.ci(APPEND_ONLY_EVENT="push", APPEND_ONLY_PUSH_BEFORE=self.base,
                          APPEND_ONLY_PUSH_AFTER=after)
        self.assertEqual(rc, 0, out)

    def test_forced_push_erasing_evidence_fails(self):
        self.r.write("sim/comparator-kickback/records/published.md", "evidence\n")
        before = self.r.commit("evidence landed on main")
        # Force-push: history rewritten from the parent, evidence gone.
        self.r.git("reset", "-q", "--hard", self.base)
        self.r.write("sim/comparator-offset-mc/README.md", "rewrite\n")
        after = self.r.commit("rewritten main")
        # A merge-base comparison would wrongly pass here.
        self.assertEqual(self.r.run("--base", before, "--head", after, "--merge-base")[0], 0)
        rc, out = self.ci(APPEND_ONLY_EVENT="push", APPEND_ONLY_PUSH_BEFORE=before,
                          APPEND_ONLY_PUSH_AFTER=after)
        self.assertEqual(rc, 1, out)
        self.assertIn("deleted: sim/comparator-kickback/records/published.md", out)

    def test_push_from_event_payload_file(self):
        self.r.git("rm", "-q", LOG)
        after = self.r.commit()
        ev = self.r.root.parent / f"{self.r.root.name}-push.json"
        ev.write_text(json.dumps({"before": self.base, "after": after}))
        self.addCleanup(ev.unlink)
        rc, out = self.ci(GITHUB_EVENT_NAME="push", GITHUB_EVENT_PATH=str(ev))
        self.assertEqual(rc, 1, out)
        self.assertIn(f"deleted: {LOG}", out)

    def test_push_zero_before_fails(self):
        rc, out = self.ci(APPEND_ONLY_EVENT="push", APPEND_ONLY_PUSH_BEFORE="0" * 40,
                          APPEND_ONLY_PUSH_AFTER=self.base)
        self.assertEqual(rc, 2, out)
        self.assertIn("all-zero", out)

    def test_push_missing_before_object_fails(self):
        rc, out = self.ci(APPEND_ONLY_EVENT="push", APPEND_ONLY_PUSH_BEFORE="a" * 40,
                          APPEND_ONLY_PUSH_AFTER=self.base)
        self.assertEqual(rc, 2, out)
        self.assertIn("not available", out)

    def test_push_malformed_sha_fails(self):
        rc, out = self.ci(APPEND_ONLY_EVENT="push", APPEND_ONLY_PUSH_BEFORE="HEAD~1; rm -rf /",
                          APPEND_ONLY_PUSH_AFTER=self.base)
        self.assertEqual(rc, 2, out)
        self.assertIn("not a full commit SHA", out)

    # ---- unsupported / missing events --------------------------------------
    def test_missing_event_in_ci_fails_not_skips(self):
        for env in ({"GITHUB_ACTIONS": "true"}, {"CI": "true"}, {"CI": "1"}):
            with self.subTest(env=env):
                rc, out = self.r.run(env=env)
                self.assertEqual(rc, 2, out)
                self.assertNotIn("SKIP", out)
                self.assertIn("refusing to skip", out)

    def test_unsupported_event_fails(self):
        for ev in ("workflow_dispatch", "pull_request_target", "schedule"):
            with self.subTest(ev=ev):
                rc, out = self.ci(APPEND_ONLY_EVENT=ev)
                self.assertEqual(rc, 2, out)
                self.assertIn("unsupported CI event", out)

    def test_unreadable_event_payload_fails(self):
        rc, out = self.ci(GITHUB_EVENT_NAME="push",
                          GITHUB_EVENT_PATH=str(self.r.root / "missing-event.json"))
        self.assertEqual(rc, 2, out)


class WorkflowWiringTests(unittest.TestCase):
    """The Signoff workflow passes event SHAs via env and fetches full history."""

    def setUp(self):
        self.wf = (REPO_ROOT / ".github" / "workflows" / "signoff.yml").read_text()

    def test_env_wiring(self):
        for line in (
            "APPEND_ONLY_EVENT: ${{ github.event_name }}",
            "APPEND_ONLY_PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}",
            "APPEND_ONLY_PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            "APPEND_ONLY_PUSH_BEFORE: ${{ github.event.before }}",
            "APPEND_ONLY_PUSH_AFTER: ${{ github.event.after }}",
        ):
            self.assertIn(line, self.wf)

    def test_full_history_and_explicit_fetch(self):
        self.assertIn("fetch-depth: 0", self.wf)
        self.assertIn('git fetch --no-tags origin "$sha"', self.wf)

    def test_no_event_text_interpolated_into_run_scripts(self):
        # ${{ github.event... }} may only appear as env values, never in `run:`.
        in_run = False
        for line in self.wf.splitlines():
            s = line.strip()
            if s.startswith("run:"):
                in_run = True
            elif s.startswith("- ") or (s and not line.startswith(" " * 10)):
                in_run = False
            if in_run:
                self.assertNotIn("${{", line, line)

    def test_runner_registers_evidence_step(self):
        out = subprocess.run([str(REPO_ROOT / "scripts" / "run-pdk-free-tests.sh"), "--list"],
                             stdout=subprocess.PIPE, text=True, check=True).stdout
        self.assertRegex(out, r"(?mi)^evidence\s+.*append-only")


if __name__ == "__main__":
    unittest.main(verbosity=2)
