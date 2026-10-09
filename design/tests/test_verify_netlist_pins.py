#!/usr/bin/env python3
"""PDK-free regressions for design/verify-netlist-pins.py (issue #120).

Each case copies just the files the verifier reads (the schematic hierarchy,
the netlist, the pin file) into a temporary tree, mutates the copy, and runs
``check_pins(root)`` or the CLI with ``--root``. Committed files are never
touched. No xschem, no PDK, no ngspice.

    python3 design/tests/test_verify_netlist_pins.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "design" / "verify-netlist-pins.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PINS = _load("verify_netlist_pins_under_test", SCRIPT)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _committed_files() -> list[str]:
    pins = json.loads((REPO_ROOT / PINS.PIN_FILE).read_text())
    return [PINS.PIN_FILE, *pins["sources"], *pins["netlist"]]


class CommittedPins(unittest.TestCase):
    def test_committed_tree_passes(self) -> None:
        self.assertEqual(PINS.check_pins(REPO_ROOT), [])

    def test_input_set_is_the_full_hierarchy(self) -> None:
        # The curator asked for the exact .sch set to be verified: the top
        # sheet plus every in-repo sub-cell (.sch and its .sym), nothing from
        # design/proposed/ (which does not feed comparator.spice).
        self.assertEqual(PINS.discover_sources(REPO_ROOT), [
            "design/comparator.sch",
            "design/comparator_dut.sch", "design/comparator_dut.sym",
            "design/comparator_dut_analog.sch", "design/comparator_dut_analog.sym",
            "design/comparator_dut_latch.sch", "design/comparator_dut_latch.sym",
        ])

    def test_committed_pin_file_is_what_write_would_produce(self) -> None:
        self.assertEqual((REPO_ROOT / PINS.PIN_FILE).read_text(),
                         PINS.render(PINS.compute_pins(REPO_ROOT)))


class FixtureDrift(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel in _committed_files():
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / rel, dst)
        self.before = {rel: _sha(REPO_ROOT / rel) for rel in _committed_files()}

    def tearDown(self) -> None:
        self._tmp.cleanup()
        after = {rel: _sha(REPO_ROOT / rel) for rel in self.before}
        self.assertEqual(self.before, after)  # committed files untouched

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args],
                              capture_output=True, text=True, check=False)

    def _append(self, rel: str, text: str = "* edited\n") -> None:
        p = self.root / rel
        p.write_text(p.read_text() + text)

    def test_clean_fixture_passes(self) -> None:
        self.assertEqual(PINS.check_pins(self.root), [])
        self.assertEqual(self._cli("--check").returncode, 0)

    def test_stale_top_sch_fails(self) -> None:
        self._append("design/comparator.sch")
        problems = PINS.check_pins(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("design/comparator.sch: sha256", problems[0])
        res = self._cli("--check")
        self.assertEqual(res.returncode, 1)
        self.assertIn("STALE", res.stderr)

    def test_stale_sub_sch_fails(self) -> None:
        self._append("design/comparator_dut_latch.sch")
        problems = PINS.check_pins(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("design/comparator_dut_latch.sch", problems[0])

    def test_stale_sym_fails(self) -> None:
        # .sym files carry the pin order of the generated instance lines.
        self._append("design/comparator_dut_analog.sym")
        problems = PINS.check_pins(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("design/comparator_dut_analog.sym", problems[0])

    def test_stale_spice_fails(self) -> None:
        self._append("design/comparator.spice")
        problems = PINS.check_pins(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("design/comparator.spice: sha256", problems[0])
        self.assertEqual(self._cli("--check").returncode, 1)

    def test_missing_pin_file_fails(self) -> None:
        (self.root / PINS.PIN_FILE).unlink()
        problems = PINS.check_pins(self.root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("missing", problems[0])
        res = self._cli("--check")
        self.assertEqual(res.returncode, 1)
        self.assertIn("missing", res.stderr)

    def test_new_sub_schematic_unpinned_fails(self) -> None:
        d = self.root / "design"
        (d / "extra_cell.sym").write_text("v {xschem version=3.4.7}\n")
        (d / "extra_cell.sch").write_text("v {xschem version=3.4.7}\n")
        self._append("design/comparator_dut.sch", "C {extra_cell.sym} 0 0 0 0 {name=X9}\n")
        problems = PINS.check_pins(self.root)
        self.assertIn("design/extra_cell.sch: input of design/comparator.sch but not pinned",
                      problems)
        self.assertIn("design/extra_cell.sym: input of design/comparator.sch but not pinned",
                      problems)

    def test_hand_edited_pin_fails(self) -> None:
        pin = self.root / PINS.PIN_FILE
        data = json.loads(pin.read_text())
        data["netlist"]["design/comparator.spice"] = "0" * 64
        pin.write_text(json.dumps(data, indent=2) + "\n")
        self.assertEqual(len(PINS.check_pins(self.root)), 1)

    def test_repin_after_edit_passes(self) -> None:
        # Stands in for re-running ./design/netlist.sh, whose write mode ends
        # in exactly this --write call (xschem itself is not available in CI).
        self._append("design/comparator_dut.sch")
        self._append("design/comparator.spice")
        self.assertEqual(self._cli("--check").returncode, 1)
        self.assertEqual(self._cli("--write").returncode, 0)
        self.assertEqual(PINS.check_pins(self.root), [])
        self.assertEqual(self._cli("--check").returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
