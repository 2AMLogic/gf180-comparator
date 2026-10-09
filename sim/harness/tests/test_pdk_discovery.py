"""Unit tests for ``harness.pdk.find_pdk`` precedence and refusal (issue #172).

PDK-free and host-independent: the config loader and the built-in search
roots are patched to tempdirs and the PDK env vars are cleared, so a worker
with a real PDK installed gets the same answers as one without.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import pdk as pdk_mod  # noqa: E402

_REAL_LOAD_CONFIG = pdk_mod._load_config
PDK_ENV = ("GF180_PDK_PATH", "PDK_ROOT", "PDK")


class FindPdkTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.config: dict = {}
        self.builtin: tuple = ()
        env = {k: v for k, v in os.environ.items() if k not in PDK_ENV}
        for patcher in (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(pdk_mod, "_load_config", lambda: self.config),
            mock.patch.object(pdk_mod, "BUILTIN_SEARCH_ROOTS", ()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_variant(self, parent: Path, name: str = "gf180mcuD") -> Path:
        d = parent / name
        (d / "libs.tech" / "ngspice").mkdir(parents=True)
        (d / "libs.tech" / "ngspice" / "sm141064.ngspice").write_text("*\n")
        return d

    def set_builtin(self, *roots):
        patcher = mock.patch.object(pdk_mod, "BUILTIN_SEARCH_ROOTS", tuple(str(r) for r in roots))
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- GF180_PDK_PATH ---------------------------------------------------
    def test_direct_path_valid(self):
        v = self.make_variant(self.tmp / "a")
        os.environ["GF180_PDK_PATH"] = str(v)
        found = pdk_mod.find_pdk()
        self.assertEqual(found.path, v)
        self.assertEqual(found.source, "GF180_PDK_PATH")
        self.assertEqual(found.variant, "gf180mcuD")

    def test_direct_path_invalid_raises_without_fallthrough(self):
        good_root = self.tmp / "root"
        self.make_variant(good_root)
        os.environ["PDK_ROOT"] = str(good_root)  # valid, must be ignored
        os.environ["GF180_PDK_PATH"] = str(self.tmp / "empty")
        with self.assertRaises(pdk_mod.PdkNotFound) as cm:
            pdk_mod.find_pdk()
        self.assertIn("GF180_PDK_PATH", str(cm.exception))

    def test_direct_path_beats_pdk_root(self):
        v = self.make_variant(self.tmp / "a")
        self.make_variant(self.tmp / "root")
        os.environ["GF180_PDK_PATH"] = str(v)
        os.environ["PDK_ROOT"] = str(self.tmp / "root")
        self.assertEqual(pdk_mod.find_pdk().source, "GF180_PDK_PATH")

    # -- PDK_ROOT ---------------------------------------------------------
    def test_pdk_root_valid(self):
        v = self.make_variant(self.tmp / "root")
        os.environ["PDK_ROOT"] = str(self.tmp / "root")
        found = pdk_mod.find_pdk()
        self.assertEqual((found.path, found.source), (v, "PDK_ROOT"))

    def test_pdk_root_invalid_falls_through_to_config_root(self):
        os.environ["PDK_ROOT"] = str(self.tmp / "bad")
        v = self.make_variant(self.tmp / "cfg")
        self.config = {"search_roots": [str(self.tmp / "cfg")]}
        found = pdk_mod.find_pdk()
        self.assertEqual(found.path, v)
        self.assertTrue(found.source.startswith("search_root:"))

    def test_pdk_root_invalid_listed_in_tried_when_exhausted(self):
        os.environ["PDK_ROOT"] = str(self.tmp / "bad")
        with self.assertRaises(pdk_mod.PdkNotFound) as cm:
            pdk_mod.find_pdk()
        self.assertIn(str(self.tmp / "bad" / "gf180mcuD"), str(cm.exception))

    # -- search roots -----------------------------------------------------
    def test_config_roots_before_builtin(self):
        cfg_v = self.make_variant(self.tmp / "cfg")
        self.make_variant(self.tmp / "builtin")
        self.config = {"search_roots": [str(self.tmp / "cfg")]}
        self.set_builtin(self.tmp / "builtin")
        self.assertEqual(pdk_mod.find_pdk().path, cfg_v)

    def test_builtin_root_used_last(self):
        v = self.make_variant(self.tmp / "builtin")
        self.set_builtin(self.tmp / "builtin")
        found = pdk_mod.find_pdk()
        self.assertEqual(found.path, v)
        self.assertEqual(found.source, f"search_root:{self.tmp / 'builtin'}")

    def test_pdk_root_beats_search_roots(self):
        v = self.make_variant(self.tmp / "root")
        self.make_variant(self.tmp / "cfg")
        self.config = {"search_roots": [str(self.tmp / "cfg")]}
        os.environ["PDK_ROOT"] = str(self.tmp / "root")
        self.assertEqual(pdk_mod.find_pdk().path, v)

    def test_exhausted_lists_every_tried_path(self):
        os.environ["PDK_ROOT"] = str(self.tmp / "r1")
        self.config = {"search_roots": [str(self.tmp / "r2")]}
        self.set_builtin(self.tmp / "r3")
        with self.assertRaises(pdk_mod.PdkNotFound) as cm:
            pdk_mod.find_pdk()
        msg = str(cm.exception)
        # Compare full path strings: bare 'r1'/'r2' could collide with the
        # random TemporaryDirectory name and break the ordering check.
        paths = [str(self.tmp / r / "gf180mcuD") for r in ("r1", "r2", "r3")]
        for p in paths:
            self.assertIn(p, msg)
        idx = [msg.index(p) for p in paths]
        self.assertEqual(idx, sorted(idx))

    # -- variant selection ------------------------------------------------
    def test_variant_precedence(self):
        root = self.tmp / "root"
        for name in ("gf180mcuA", "gf180mcuB", "gf180mcuC", "gf180mcuD"):
            self.make_variant(root, name)
        os.environ["PDK_ROOT"] = str(root)
        self.assertEqual(pdk_mod.find_pdk().variant, "gf180mcuD")  # default
        self.config = {"variant": "gf180mcuC"}
        self.assertEqual(pdk_mod.find_pdk().variant, "gf180mcuC")  # config
        os.environ["PDK"] = "gf180mcuB"
        self.assertEqual(pdk_mod.find_pdk().variant, "gf180mcuB")  # env
        self.assertEqual(pdk_mod.find_pdk("gf180mcuA").variant, "gf180mcuA")  # arg

    # -- config -----------------------------------------------------------
    def test_invalid_config_json_raises_runtime_error(self):
        sim = self.tmp / "sim"
        sim.mkdir()
        (sim / "pdk.json").write_text("{oops")
        with mock.patch.object(pdk_mod, "SIM_DIR", sim):
            with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
                _REAL_LOAD_CONFIG()

    def test_local_config_overrides_committed(self):
        sim = self.tmp / "sim"
        sim.mkdir()
        (sim / "pdk.json").write_text('{"variant": "gf180mcuC", "x": 1}')
        (sim / "pdk.local.json").write_text('{"variant": "gf180mcuB"}')
        with mock.patch.object(pdk_mod, "SIM_DIR", sim):
            self.assertEqual(_REAL_LOAD_CONFIG(), {"variant": "gf180mcuB", "x": 1})


if __name__ == "__main__":
    unittest.main()
