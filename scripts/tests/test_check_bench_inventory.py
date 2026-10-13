#!/usr/bin/env python3
"""PDK-free fixture tests for scripts/check_bench_inventory.py README-DRIFT
checks (#225). Builds temp trees; never touches the real sim/ or READMEs.

    python3 scripts/tests/test_check_bench_inventory.py
"""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location(
    "cbi", REPO / "scripts" / "check_bench_inventory.py")
CBI = importlib.util.module_from_spec(_s)
_s.loader.exec_module(CBI)

CAMP = ["comparator-alpha", "comparator-beta"]
EXTRA = list(CBI.NOT_RUN_BY_CHARACTERIZE)
ALL = CAMP + EXTRA


def build(root, names=ALL, count="six", readme_names=None, sim_names=None):
    root = Path(root)
    (root / "sim").mkdir()
    for n in names:
        (root / "sim" / n).mkdir()
    (root / "sim" / "characterize.sh").write_text(
        "CAMPAIGNS=(\n" + "\n".join(CAMP) + "\n)\n")
    rn = ALL if readme_names is None else readme_names
    sn = ALL if sim_names is None else sim_names
    (root / "README.md").write_text(
        f"`sim/` holds {count} bench directories: "
        + ", ".join(f"`{n}`" for n in rn) + ".\n")
    (root / "sim" / "README.md").write_text(
        "\n".join(f"- {n}" for n in sn) + "\n")


def run(root):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = CBI.main(root)
    return rc, buf.getvalue()


class ReadmeDrift(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = t.name

    def test_pass(self):
        build(self.root, count=_word(len(ALL)))
        rc, out = run(self.root)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("README-DRIFT", out)

    def test_missing_name_readme(self):
        build(self.root, count=_word(len(ALL)), readme_names=ALL[:-1])
        rc, out = run(self.root)
        self.assertEqual(rc, 1)
        self.assertIn(f"README-DRIFT: sim/{ALL[-1]} is not mentioned", out)

    def test_missing_name_sim_readme(self):
        build(self.root, count=_word(len(ALL)), sim_names=ALL[1:])
        rc, out = run(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("in sim/README.md", out)

    def test_prefix_name_does_not_satisfy_longer_name(self):
        names = ["comparator-offset-tran", "comparator-offset-tran-x"]
        self.assertTrue(CBI.mentions(names[0], "`comparator-offset-tran-x`") is False)
        self.assertTrue(CBI.mentions(names[1], "`comparator-offset-tran-x`"))

    def test_wrong_count(self):
        build(self.root, count="seven" if len(ALL) != 7 else "eight")
        rc, out = run(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("README-DRIFT: README.md says", out)

    def test_real_repo_passes(self):
        rc, out = run(REPO)
        self.assertEqual(rc, 0, out)


def _word(n):
    return {v: k for k, v in CBI.NUMBERS.items()}[n]


if __name__ == "__main__":
    unittest.main()
