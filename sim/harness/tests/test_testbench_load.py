"""Unit tests for ``harness.testbench.load`` / ``validate_netlist`` (issue #172).

One case per raise branch of the manifest loader. PDK-free: every fixture is
a temporary experiment directory.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import testbench as tb_mod  # noqa: E402

CLEAN = "* clean fragment\nR1 a b 1k\n.param x=1\n.meas op foo param='1'\n"


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.exp = Path(self._tmp.name) / "exp"
        self.dir = self.exp / "testbench"
        self.dir.mkdir(parents=True)
        (self.dir / "frag.spice").write_text(CLEAN)

    def write(self, manifest=None, **overrides):
        m = {"netlist": "frag.spice", "measure": {"m_a": "expr"}}
        if manifest is not None:
            m = manifest
        m.update(overrides)
        (self.dir / "tb.json").write_text(json.dumps(m))
        return self.dir

    def load_manifest(self, **overrides):
        return tb_mod.load(self.write(**overrides))


class LoadSuccessTests(_Base):
    def test_three_input_forms(self):
        self.write()
        for target in (self.exp, self.dir, self.dir / "tb.json"):
            tb = tb_mod.load(target)
            self.assertEqual(tb.directory, self.dir.resolve())
            self.assertEqual(tb.experiment, "exp")

    def test_defaults(self):
        tb = self.load_manifest()
        self.assertEqual(tb.analyses, ("op",))
        self.assertIsNone(tb.offset_probe_testbench())


class LoadRaiseTests(_Base):
    def test_missing_manifest(self):
        with self.assertRaises(FileNotFoundError):
            tb_mod.load(self.dir)

    def test_malformed_json(self):
        (self.dir / "tb.json").write_text("{not json")
        with self.assertRaises(ValueError):  # JSONDecodeError
            tb_mod.load(self.dir)

    def test_missing_netlist_key(self):
        with self.assertRaisesRegex(ValueError, "missing required key 'netlist'"):
            tb_mod.load(self.write({"measure": {"m_a": "x"}}))

    def test_netlist_file_absent(self):
        with self.assertRaises(FileNotFoundError):
            self.load_manifest(netlist="nope.spice")

    def test_missing_measure_key(self):
        with self.assertRaisesRegex(ValueError, "missing required key 'measure'"):
            tb_mod.load(self.write({"netlist": "frag.spice"}))

    def test_empty_measure(self):
        with self.assertRaisesRegex(ValueError, "at least one measurement"):
            self.load_manifest(measure={})

    def test_measure_name_not_identifier(self):
        with self.assertRaisesRegex(ValueError, "alphanumeric/underscore"):
            self.load_manifest(measure={"m-a": "x"})

    def test_measure_name_not_lower_case(self):
        with self.assertRaisesRegex(ValueError, "lower case"):
            self.load_manifest(measure={"m_Vos": "x"})

    def test_unknown_evidence_key(self):
        with self.assertRaisesRegex(ValueError, "unknown key.*bogus"):
            self.load_manifest(evidence={"bogus": 1})

    def test_known_evidence_keys_accepted(self):
        tb = self.load_manifest(evidence={k: "v" for k in tb_mod.EVIDENCE_KEYS})
        self.assertEqual(set(tb.evidence), set(tb_mod.EVIDENCE_KEYS))


class CheckValidationTests(_Base):
    def test_check_not_a_measurement(self):
        with self.assertRaisesRegex(ValueError, "does not name a measurement"):
            self.load_manifest(checks={"zzz": {"min": 0}})

    def test_check_spec_not_object(self):
        with self.assertRaisesRegex(ValueError, "must be an object, got list"):
            self.load_manifest(checks={"m_a": [1]})

    def test_unknown_check_key(self):
        with self.assertRaisesRegex(ValueError, "unknown key.*mni"):
            self.load_manifest(checks={"m_a": {"mni": 0}})

    def test_axis_checks_not_object(self):
        for key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, f"{key} must be an object"):
                    self.load_manifest(checks={"m_a": {key: 5}})

    def test_unknown_axis(self):
        for key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "unknown axis/axes.*humidity"):
                    self.load_manifest(checks={"m_a": {key: {"humidity": 1}}})

    def test_valid_checks_accepted(self):
        tb = self.load_manifest(
            checks={"m_a": {"min": 0, "max": 1, "min_spread_pct_by_axis": {"supply": 1}}}
        )
        self.assertIn("m_a", tb.checks)


class CheckBoundValueTests(_Base):
    SCALARS = ("min", "max", "max_spread_pct", "min_spread_pct")
    AXIS_KEYS = ("min_spread_pct_by_axis", "max_spread_pct_by_axis")
    BAD = (float("nan"), float("inf"), float("-inf"), True, False, "1", None, [1], {})

    def test_bad_scalar_bounds(self):
        for key in self.SCALARS:
            for bad in self.BAD:
                with self.subTest(key=key, bad=bad):
                    with self.assertRaisesRegex(ValueError, rf"m_a.*{key}"):
                        self.load_manifest(checks={"m_a": {key: bad}})

    def test_bad_axis_bounds(self):
        for key in self.AXIS_KEYS:
            for bad in self.BAD:
                with self.subTest(key=key, bad=bad):
                    with self.assertRaisesRegex(ValueError, rf"m_a.*{key}\[supply\]"):
                        self.load_manifest(checks={"m_a": {key: {"supply": bad}}})

    def test_error_names_manifest(self):
        with self.assertRaisesRegex(ValueError, r"tb\.json"):
            self.load_manifest(checks={"m_a": {"min": "x"}})

    def test_nonstandard_constants_rejected_at_parse(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                self.write()
                (self.dir / "tb.json").write_text(
                    '{"netlist": "frag.spice", "measure": {"m_a": "expr"}, '
                    f'"checks": {{"m_a": {{"min": {token}}}}}}}'
                )
                with self.assertRaisesRegex(ValueError, r"m_a.*min.*nonstandard JSON constant " + token):
                    tb_mod.load(self.dir)

    def test_nonstandard_constant_outside_checks_rejected(self):
        self.write()
        (self.dir / "tb.json").write_text(
            '{"netlist": "frag.spice", "measure": {"m_a": "expr"}, "nominal_supply_v": NaN}'
        )
        with self.assertRaisesRegex(ValueError, "nominal_supply_v.*nonstandard"):
            tb_mod.load(self.dir)

    def test_reversed_pairs(self):
        cases = (
            {"min": 2, "max": 1},
            {"min_spread_pct": 5, "max_spread_pct": 1},
            {
                "min_spread_pct_by_axis": {"supply": 5},
                "max_spread_pct_by_axis": {"supply": 1},
            },
        )
        for spec in cases:
            with self.subTest(spec=spec):
                with self.assertRaisesRegex(ValueError, "reversed"):
                    self.load_manifest(checks={"m_a": spec})

    def test_negative_spreads(self):
        for key in self.SCALARS[2:]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, ">= 0"):
                    self.load_manifest(checks={"m_a": {key: -1}})
        for key in self.AXIS_KEYS:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, ">= 0"):
                    self.load_manifest(checks={"m_a": {key: {"process": -0.5}}})

    def test_valid_bounds_load(self):
        tb = self.load_manifest(
            checks={
                "m_a": {
                    "min": -1.5, "max": 3,
                    "min_spread_pct": 0, "max_spread_pct": 2.5,
                    "min_spread_pct_by_axis": {"supply": 0, "process": 1},
                    "max_spread_pct_by_axis": {"supply": 0, "process": 4.5},
                }
            }
        )
        self.assertEqual(tb.checks["m_a"]["min"], -1.5)

    def test_equal_pair_and_negative_min_ok(self):
        self.load_manifest(checks={"m_a": {"min": -2, "max": -2}})

    def test_existing_manifests_load(self):
        root = Path(__file__).resolve().parents[2]
        for tbdir in tb_mod.discover(root):
            with self.subTest(tb=str(tbdir)):
                tb_mod.load(tbdir)


class NetlistValidationTests(_Base):
    def test_forbidden_directive_lists_line_numbers(self):
        (self.dir / "frag.spice").write_text("* c\nR1 a b 1k\n.temp 27\n\n.INCLUDE foo\n")
        with self.assertRaises(ValueError) as cm:
            self.load_manifest()
        msg = str(cm.exception)
        self.assertIn("line 3: .temp 27", msg)
        self.assertIn("line 5: .INCLUDE foo", msg)  # case-insensitive match

    def test_each_forbidden_directive(self):
        for d in tb_mod.FORBIDDEN_DIRECTIVES:
            with self.subTest(directive=d):
                (self.dir / "frag.spice").write_text(f"{d} x\n")
                with self.assertRaises(ValueError):
                    self.load_manifest()

    def test_clean_fragment_passes(self):
        self.load_manifest()  # must not raise

    def test_similar_directive_not_flagged(self):
        # '.endc' is forbidden but the similar-prefixed '.ends' is not
        (self.dir / "frag.spice").write_text(".subckt a b\n.ends\n")
        self.load_manifest()


class OffsetProbeTests(_Base):
    def test_probe_netlist_missing(self):
        with self.assertRaises(FileNotFoundError):
            self.load_manifest(offset_probe={"netlist": "gone.spice", "measure": {"dut_vos": "x"}})

    def test_probe_measure_lacks_dut_vos(self):
        (self.dir / "probe.spice").write_text(CLEAN)
        with self.assertRaisesRegex(ValueError, "dut_vos"):
            self.load_manifest(offset_probe={"netlist": "probe.spice", "measure": {"other": "x"}})

    def test_probe_netlist_forbidden_directive(self):
        (self.dir / "probe.spice").write_text(".end\n")
        with self.assertRaises(ValueError):
            self.load_manifest(offset_probe={"netlist": "probe.spice", "measure": {"dut_vos": "x"}})

    def test_valid_probe(self):
        (self.dir / "probe.spice").write_text(CLEAN)
        tb = self.load_manifest(
            offset_probe={"netlist": "probe.spice", "measure": {"dut_vos": "x"}}
        )
        probe = tb.offset_probe_testbench()
        self.assertTrue(probe.name.endswith("-vosprobe"))


if __name__ == "__main__":
    unittest.main()
