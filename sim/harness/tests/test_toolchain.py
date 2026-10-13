"""Tests for the toolchain drift gate (#171): ``harness.toolchain.check`` and
its CLI enforcement. PDK-free and ngspice-free."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import cli, toolchain  # noqa: E402

HASH = "a" * 40
BANNER = "ngspice-46 : Circuit level simulation program"


class _Stop(Exception):
    """Raised to halt cli.main once it is past the drift gate."""


class _PinFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def pins(self, **over) -> Path:
        pins = {"open_pdks": HASH, "ngspice_min_major": 46, "python_min": "3.8"}
        pins.update(over)
        p = self.dir / "toolchain.json"
        p.write_text(json.dumps(pins))
        return p

    def check(self, pdk=HASH, banner=BANNER, **over):
        return toolchain.check(pdk, banner, path=self.pins(**over))


class CheckTests(_PinFile):
    def test_matching_pins_no_drift(self):
        self.assertEqual(self.check().drift, [])

    def test_open_pdks_mismatch(self):
        chain = self.check(pdk="b" * 40)
        self.assertEqual(len(chain.drift), 1)
        self.assertIn("open_pdks", chain.drift[0])

    def test_open_pdks_null_disables_only_that_check(self):
        self.assertEqual(self.check(pdk="b" * 40, open_pdks=None).drift, [])
        chain = self.check(pdk="b" * 40, open_pdks=None, banner="ngspice-40")
        self.assertEqual(len(chain.drift), 1)
        self.assertIn("ngspice", chain.drift[0])

    def test_ngspice_below_floor(self):
        chain = self.check(banner="ngspice-45 foo")
        self.assertEqual(len(chain.drift), 1)
        self.assertIn("floor 46", chain.drift[0])

    def test_ngspice_equal_or_newer(self):
        self.assertEqual(self.check(banner="ngspice-46").drift, [])
        self.assertEqual(self.check(banner="ngspice-47").drift, [])

    def test_unparseable_banner(self):
        chain = self.check(banner="spice3 something")
        self.assertEqual(len(chain.drift), 1)
        self.assertIn("could not parse", chain.drift[0])

    def test_unparseable_banner_ignored_without_ngspice_pin(self):
        self.assertEqual(self.check(banner="junk", ngspice_min_major=None).drift, [])

    def test_python_floor_above_running(self):
        chain = self.check(python_min="99.0")
        self.assertEqual(len(chain.drift), 1)
        self.assertIn("python", chain.drift[0])

    def test_python_floor_met(self):
        v = sys.version_info
        self.assertEqual(self.check(python_min=f"{v.major}.{v.minor}").drift, [])

    def test_python_pin_absent(self):
        self.assertEqual(self.check(python_min=None).drift, [])

    def test_observed_recorded(self):
        obs = self.check().observed
        self.assertEqual(obs["open_pdks"], HASH)
        self.assertEqual(obs["ngspice"], BANNER)

    def test_missing_pin_file(self):
        with self.assertRaises(FileNotFoundError):
            toolchain.check(HASH, BANNER, path=self.dir / "nope.json")


class AsDictAndMajorTests(unittest.TestCase):
    def test_as_dict_strips_underscore_pins(self):
        tc = toolchain.Toolchain(
            pins={"_comment": "x", "open_pdks": HASH}, observed={"a": 1}, drift=["d"]
        )
        d = tc.as_dict()
        self.assertEqual(d["pins"], {"open_pdks": HASH})
        self.assertEqual(d["observed"], {"a": 1})
        self.assertEqual(d["drift"], ["d"])
        self.assertIsNot(d["drift"], tc.drift)

    def test_ngspice_major(self):
        self.assertEqual(toolchain._ngspice_major("ngspice-46"), 46)
        self.assertEqual(toolchain._ngspice_major("** ngspice-43.1 : x"), 43)
        self.assertIsNone(toolchain._ngspice_major("ngspice 46"))
        self.assertIsNone(toolchain._ngspice_major(""))


class CliEnforcementTests(unittest.TestCase):
    """Drift is fatal by default; ``--allow-toolchain-drift`` accepts it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        (Path(self._tmp.name) / "exp").mkdir()
        pdk = mock.Mock(version=HASH)
        drifted = toolchain.Toolchain(pins={}, drift=["open_pdks: pinned X"])
        for p in (
            mock.patch.object(cli, "SIM_DIR", Path(self._tmp.name)),
            mock.patch.object(cli.tb_mod, "load"),
            mock.patch.object(cli.pdk_mod, "find_pdk", return_value=pdk),
            mock.patch.object(cli.runner_mod, "ngspice_version", return_value=BANNER),
            mock.patch.object(cli, "_load_dut", return_value=(mock.Mock(), "id")),
            mock.patch.object(cli, "_check_dut_compatibility"),
            mock.patch.object(cli.corners_mod, "resolve_corners", side_effect=_Stop),
            mock.patch.object(toolchain, "check", return_value=drifted),
        ):
            p.start()
            self.addCleanup(p.stop)

    def run_main(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(list(argv))
        return rc, err.getvalue()

    def test_run_path_refuses_on_drift(self):
        rc, err = self.run_main("exp")
        self.assertEqual(rc, 3)
        self.assertIn("TOOLCHAIN DRIFT", err)

    def test_run_path_proceeds_with_allow_flag(self):
        # Past the gate the patched resolve_corners raises _Stop.
        with self.assertRaises(_Stop):
            self.run_main("exp", "--allow-toolchain-drift")

    def test_check_env_drift(self):
        with mock.patch.object(cli.dut_mod, "load", return_value=mock.MagicMock()), \
             mock.patch.object(cli.tb_mod, "discover", return_value=[]), \
             mock.patch.object(toolchain, "xschem_banner", return_value="x"):
            self.assertEqual(self.run_main("--check-env")[0], 2)
            self.assertEqual(self.run_main("--check-env", "--allow-toolchain-drift")[0], 0)


if __name__ == "__main__":
    unittest.main()
