"""Pin the unit of the regeneration bench's metastability diagnostic (issue #141).

``sim/comparator-regeneration/testbench/tb.json`` records
``td_od1_over_tau = td_b/((td_c-td_b)/ln(10))``. The denominator is
``tau`` in seconds (``tau_ps`` without the 1e12), so the quantity is
``td_od1 / tau`` -- the full 1 mV clock-to-output delay over the
regeneration time constant, in **e-folds** (natural-log units), not decades.
It used to be recorded only as ``resolve_decades``; that key is kept as a
deprecated alias with the identical expression so older records stay
comparable.

These tests evaluate the committed ``measure`` expressions exactly the way
``sim/tools/klt_record.py`` does (its own ``MATH`` table, ``eval`` with no
builtins) on synthetic ``td_b``/``td_c``, so the unit claim is checked, not
just stated. Stdlib only; no PDK, ngspice or klt involved.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SIM))

from harness import testbench as htb  # noqa: E402

BENCH_DIR = SIM / "comparator-regeneration" / "testbench"
NEW, OLD = "td_od1_over_tau", "resolve_decades"


def _klt_record_math() -> dict:
    spec = importlib.util.spec_from_file_location(
        "_klt_record_for_test", SIM / "tools" / "klt_record.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.MATH)


# (td_b, td_c) in seconds: a nominal-looking point, a slow one, and a
# deliberately round one where tau = 1 ns exactly.
SYNTHETIC = [
    (0.708e-9, 0.708e-9 + 0.100e-9 * math.log(10)),
    (1.237e-9, 1.237e-9 + 0.123e-9 * math.log(10)),
    (5.0e-9, 5.0e-9 + 1.0e-9 * math.log(10)),
]


class RegenerationMeasureUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tb = htb.load(BENCH_DIR)
        cls.math = _klt_record_math()

    def _eval(self, name: str, td_b: float, td_c: float) -> float:
        env = dict(self.math, td_b=td_b, td_c=td_c)
        expr = self.tb.measure[name].replace("^", "**")
        return eval(expr, {"__builtins__": {}}, env)

    def test_both_keys_present_with_identical_expression(self) -> None:
        self.assertIn(NEW, self.tb.measure)
        self.assertIn(OLD, self.tb.measure)
        self.assertEqual(self.tb.measure[NEW], self.tb.measure[OLD])

    def test_value_is_td_b_over_tau_in_seconds(self) -> None:
        for td_b, td_c in SYNTHETIC:
            tau_s = (td_c - td_b) / math.log(10)
            # tau_ps is the bench's own tau; the diagnostic must be td_b over
            # that same tau expressed in seconds.
            tau_ps = self._eval("tau_ps", td_b, td_c)
            self.assertAlmostEqual(tau_ps * 1e-12, tau_s, delta=tau_s * 1e-12)
            for name in (NEW, OLD):
                with self.subTest(name=name, td_b=td_b):
                    got = self._eval(name, td_b, td_c)
                    self.assertAlmostEqual(got, td_b / tau_s, places=9)
                    self.assertAlmostEqual(got, td_b / (tau_ps * 1e-12), places=9)

    def test_unit_is_e_folds_not_decades(self) -> None:
        # tau = 1 ns, td_b = 5 ns: exactly 5 e-folds. A decade count of the
        # same ratio would be 5/ln(10) ~= 2.17 -- the value must not be that.
        td_b, td_c = SYNTHETIC[2]
        got = self._eval(NEW, td_b, td_c)
        self.assertAlmostEqual(got, 5.0, places=9)
        self.assertNotAlmostEqual(got, 5.0 / math.log(10), places=3)
        # exp(-ratio) is the e-fold attenuation over the delay.
        self.assertAlmostEqual(math.exp(-got), math.exp(-td_b / 1e-9), places=12)

    def test_checks_document_units_and_deprecation(self) -> None:
        new_desc = self.tb.checks[NEW]["description"]
        self.assertIn("E-FOLDS", new_desc)
        self.assertIn("FULL", new_desc)
        old_desc = self.tb.checks[OLD]["description"]
        self.assertIn("DEPRECATED", old_desc)
        self.assertIn(NEW, old_desc)
        # Same floor on both: the rename relaxes nothing.
        self.assertEqual(self.tb.checks[NEW].get("min"), self.tb.checks[OLD].get("min"))


if __name__ == "__main__":
    unittest.main()
