"""PDK-free regressions for sim/comparator-offset-mc/yield/adapt_samples.py
(issue #169): invalid numeric inputs are refused before any output is made."""
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "adapt_samples", ROOT / "sim/comparator-offset-mc/yield/adapt_samples.py")
adapt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adapt)

DRAWS = [1e-3, 2e-3, 3e-3, 4e-3]


def stats(draws):
    n = len(draws)
    mean = sum(draws) / n
    sig = math.sqrt(sum(d * d for d in draws) / n - mean * mean)
    return {"n_samples": n, "sig_vos_mv": sig * 1e3, "mean_vos_uv": mean * 1e6}


class AdaptSamples(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.out = self.base / "out.json"

    def run_adapter(self, tokens=None, **overrides):
        tokens = [repr(d) for d in DRAWS] if tokens is None else tokens
        meas = stats(DRAWS)
        meas.update(overrides)
        (self.base / "corners" / "r1").mkdir(parents=True, exist_ok=True)
        (self.base / "records").mkdir(exist_ok=True)
        (self.base / "corners" / "r1" / "c.log").write_text(
            "".join(f"voa = {t}\n" for t in tokens))
        rec = {"record_id": "r1", "points": [
            {"corner_id": "c", "status": "ok", "log": "c.log", "measurements": meas}]}
        (self.base / "records" / "r1.json").write_text(json.dumps(rec))
        return adapt.main(str(self.base / "records" / "r1.json"), str(self.out))

    def refused(self, *a, **kw):
        self.out.write_text("PRIOR")
        with self.assertRaises(SystemExit) as cm:
            self.run_adapter(*a, **kw)
        self.assertEqual(self.out.read_text(), "PRIOR")  # untouched
        return str(cm.exception)

    def test_valid_fixture_strict_json(self):
        self.assertEqual(self.run_adapter(), 0)
        doc = json.loads(self.out.read_text(), parse_constant=self.fail)
        m = doc["measurements"][0]
        self.assertEqual(m["samples"], DRAWS)
        self.assertEqual(m["negative_control"]["samples"],
                         [d + adapt.NEG_SHIFT_V for d in DRAWS])

    def test_nan_draw(self):
        msg = self.refused(tokens=["nan", "0.001", "0.002", "0.003"])
        self.assertIn("c:", msg)
        self.assertIn("draw 0", msg)

    def test_overflowing_exponent(self):
        self.assertIn("draw 1", self.refused(tokens=["0.001", "1e999", "0", "0"]))

    def test_nonfinite_expected_stats(self):
        for key in ("sig_vos_mv", "mean_vos_uv"):
            for bad in (float("nan"), float("inf")):
                with self.subTest(key=key, bad=bad):
                    self.assertIn(key, self.refused(**{key: bad}))

    def test_bad_counts(self):
        for bad in (0, -4, 4.5, True, "4", None):
            with self.subTest(bad=bad):
                self.assertIn("n_samples", self.refused(n_samples=bad))

    def test_count_mismatch(self):
        self.assertIn("parsed 4 draws", self.refused(n_samples=5))

    def test_arithmetic_overflow(self):
        # finite draws whose squares overflow: sigma is not computable
        self.assertIn("refusing", self.refused(tokens=["1e200", "1e200", "1e200", "1e200"]))


if __name__ == "__main__":
    unittest.main()
