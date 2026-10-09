"""Tests for ``harness.cli.main`` refusal paths, ``_load_dut`` selector
routing, ``_list`` grid sizing, and the ``--sabotage-corners`` implies
``--no-write`` guarantee (#183). PDK-free and ngspice-free."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import cli, toolchain  # noqa: E402

BANNER = "ngspice-46 : Circuit level simulation program"


class _SimulatedReached(AssertionError):
    """run_grid was called on a path that must refuse first."""


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class LoadDutRoutingTests(unittest.TestCase):
    def test_bare_id_selects_by_id(self):
        with mock.patch.object(cli.dut_mod, "load", return_value="D") as load:
            self.assertEqual(cli._load_dut("comparator-dr0001-layout"), ("D", "id"))
        load.assert_called_once_with(select="comparator-dr0001-layout")

    def test_json_filename_is_a_path(self):
        with mock.patch.object(cli.dut_mod, "load", return_value="D") as load:
            self.assertEqual(cli._load_dut("alt.json"), ("D", "path"))
        load.assert_called_once_with("alt.json")

    def test_dir_slash_json_is_a_path(self):
        with mock.patch.object(cli.dut_mod, "load", return_value="D") as load:
            self.assertEqual(cli._load_dut("dir/alt.json"), ("D", "path"))
        load.assert_called_once_with("dir/alt.json")

    def test_slash_without_json_is_a_path(self):
        with mock.patch.object(cli.dut_mod, "load", return_value="D") as load:
            self.assertEqual(cli._load_dut("dir/alt"), ("D", "path"))
        load.assert_called_once_with("dir/alt")

    def test_none_loads_default_binding(self):
        with mock.patch.object(cli.dut_mod, "load", return_value="D") as load:
            self.assertEqual(cli._load_dut(None), ("D", "path"))
        load.assert_called_once_with(None)


class ListTests(unittest.TestCase):
    def test_grid_size_is_product_of_axes(self):
        tb = mock.Mock(
            corners=["mos"],          # 5 corners
            temperatures_c=[-40.0, 27.0],  # 2
            nominal_supply_v=3.3,
            supply_tolerance=0.1,     # 3 supply points
            description="a bench",
        )
        with mock.patch.object(cli.tb_mod, "discover", return_value=[Path("/x/alpha")]), \
             mock.patch.object(cli.tb_mod, "load", return_value=tb):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli._list(), 0)
        self.assertIn("alpha", out.getvalue())
        self.assertIn("  30 points", out.getvalue())

    def test_zero_tolerance_collapses_supply_axis(self):
        tb = mock.Mock(corners=["tt"], temperatures_c=[27.0, 85.0],
                       nominal_supply_v=3.3, supply_tolerance=0.0, description="d")
        with mock.patch.object(cli.tb_mod, "discover", return_value=[Path("/x/b")]), \
             mock.patch.object(cli.tb_mod, "load", return_value=tb):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli._list()
        self.assertIn("   2 points", out.getvalue())


class _MainBase(unittest.TestCase):
    """Everything past argument parsing mocked; run_grid raises if reached."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sim = Path(self._tmp.name)
        (self.sim / "exp").mkdir()
        self.tb = mock.Mock(experiment="exp", experiment_dir=self.sim / "exp",
                            corners=["tt"], temperatures_c=[27.0],
                            nominal_supply_v=3.3, supply_tolerance=0.0,
                            measure=[])
        self.dut = mock.Mock(provenance="schematic", is_placeholder=False)
        self.dut.provenance_record.return_value = {}
        pdk = mock.Mock(version="a" * 40)
        self.run_grid = mock.Mock(side_effect=_SimulatedReached)
        self.find_pdk = mock.patch.object(cli.pdk_mod, "find_pdk", return_value=pdk)
        self.ngspice = mock.patch.object(
            cli.runner_mod, "ngspice_version", return_value=BANNER)
        self.load_dut = mock.patch.object(
            cli, "_load_dut", return_value=(self.dut, "id"))
        self.compat = mock.patch.object(cli, "_check_dut_compatibility")
        patches = [
            mock.patch.object(cli, "SIM_DIR", self.sim),
            mock.patch.object(cli, "WORK_DIR", self.sim / ".work"),
            mock.patch.object(cli.tb_mod, "load", return_value=self.tb),
            mock.patch.object(cli.runner_mod, "run_grid", self.run_grid),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.m_pdk = self.find_pdk.start()
        self.m_ngspice = self.ngspice.start()
        self.m_load_dut = self.load_dut.start()
        self.m_compat = self.compat.start()
        for p in (self.find_pdk, self.ngspice, self.load_dut, self.compat):
            self.addCleanup(p.stop)

    def assertRefused(self, needle, *argv):
        rc, _out, err = _run(*(argv or ("exp",)))
        self.assertEqual(rc, 1)
        self.assertIn(needle, err)
        self.run_grid.assert_not_called()


class RefusalTests(_MainBase):
    def test_unknown_experiment_directory(self):
        self.assertRefused("no experiment directory sim/nope", "nope")

    def test_pdk_not_found(self):
        self.m_pdk.side_effect = cli.pdk_mod.PdkNotFound("pdk-gone-msg")
        self.assertRefused("pdk-gone-msg")

    def test_ngspice_missing(self):
        self.m_ngspice.side_effect = cli.runner_mod.NgspiceMissing("no-ngspice-msg")
        self.assertRefused("no-ngspice-msg")

    def test_dut_error_from_load_dut(self):
        self.m_load_dut.side_effect = cli.dut_mod.DutError("bad-binding-msg")
        self.assertRefused("bad-binding-msg")

    def test_dut_error_from_compatibility_check(self):
        self.m_compat.side_effect = cli.dut_mod.DutError("incompatible-msg")
        self.assertRefused("incompatible-msg")


class SabotageNoWriteTests(_MainBase):
    def setUp(self):
        super().setUp()
        self.run_grid.side_effect = None
        self.run_grid.return_value = []
        self.work = self.sim / ".work" / "exp" / "r1"
        self.evidence = self.sim / "exp" / "corners" / "r1"
        self.reserve = mock.Mock(side_effect=lambda *a, **k: (
            ("r1", self.work) if "logs_root" in k else ("r1", self.evidence)))
        self.write_record = mock.Mock(return_value=cli.REPO_ROOT / "rec.json")
        for p in (
            mock.patch.object(toolchain, "check",
                              return_value=mock.Mock(drift=[], as_dict=lambda: {})),
            mock.patch.object(cli.report_mod, "reserve_run", self.reserve),
            mock.patch.object(cli.report_mod, "write_record", self.write_record),
            mock.patch.object(cli.report_mod, "summarize", return_value={}),
            mock.patch.object(cli.report_mod, "dirty_paths", return_value=[]),
            mock.patch.object(cli.report_mod, "git_short_sha", return_value="abc"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def assertScratchOnly(self):
        self.write_record.assert_not_called()
        self.reserve.assert_called_once()
        kwargs = self.reserve.call_args.kwargs
        self.assertEqual(kwargs.get("logs_root"), self.sim / ".work" / "exp")
        self.assertIs(kwargs.get("check_published"), False)
        self.assertEqual(self.run_grid.call_args.kwargs["log_dir"], self.work)

    def test_sabotage_implies_no_write(self):
        rc, out, _ = _run("exp", "--sabotage-corners")
        self.assertEqual(rc, 4)  # vacuous grid "passes", which sabotage rejects
        self.assertScratchOnly()
        self.assertIn("evidence writing disabled", out)

    def test_sabotage_forces_corners_to_typical(self):
        with mock.patch.object(cli.corners_mod, "sabotage",
                               wraps=cli.corners_mod.sabotage) as sab:
            _run("exp", "--sabotage-corners", "--corners", "mos")
        sab.assert_called_once()

    def test_explicit_no_write_is_scratch_only(self):
        rc, _out, _ = _run("exp", "--no-write")
        self.assertEqual(rc, 0)
        self.assertScratchOnly()

    def test_default_run_writes_evidence(self):
        """Control: without either flag the evidence path is taken, so the
        assertions above are not vacuous."""
        rc, _out, _ = _run("exp")
        self.assertEqual(rc, 0)
        self.write_record.assert_called_once()
        self.assertEqual(self.reserve.call_args.args, (self.tb.experiment_dir,))
        self.assertNotIn("logs_root", self.reserve.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
