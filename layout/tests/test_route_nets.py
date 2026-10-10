#!/usr/bin/env python3
"""PDK-free tests for layout/route_nets.py's pure-data helpers (#184).

`route_nets` imports `klayout.db` unconditionally. The mandatory helper
tests (`classify`, `assign_tracks`, `assign_links`) therefore import the
production module with minimal `klayout`/`klayout.db` doubles installed in
`sys.modules` only for the duration of the import, so they run with or
without klayout. `check_spacing` geometry tests need the real `klayout.db`
and are skipped only when it is absent.

    python3 layout/tests/test_route_nets.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

LAYOUT = Path(__file__).resolve().parents[1]
if str(LAYOUT) not in sys.path:
    sys.path.insert(0, str(LAYOUT))

try:
    import klayout.db as _real_db  # noqa: F401
    HAVE_KLAYOUT = True
except ImportError:
    HAVE_KLAYOUT = False


def _load(name: str, stub_klayout: bool):
    """Import layout/route_nets.py under a private module name."""
    saved = {k: sys.modules.get(k) for k in ("klayout", "klayout.db")}
    if stub_klayout:
        pkg = types.ModuleType("klayout")
        dbm = types.ModuleType("klayout.db")
        pkg.db = dbm
        sys.modules["klayout"], sys.modules["klayout.db"] = pkg, dbm
    try:
        spec = importlib.util.spec_from_file_location(
            name, LAYOUT / "route_nets.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if stub_klayout:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
    return mod


rn = _load("route_nets_helpers_under_test", stub_klayout=True)


def _port(name, x, deg=0):
    return {"name": name, "x_um": x, "direction_deg": deg, "width_um": 0.3}


def _pin(net, block, port, deg=0, kind="device", **kw):
    d = {"net": net, "block": block, "port": port, "dir": deg, "kind": kind}
    d.update(kw)
    return d


class Classify(unittest.TestCase):
    def setUp(self):
        self.reports = {
            "dp": {"ports": [
                _port("Q1_1_S", 0.0), _port("Q1_1_G", 5.0, 90),
                _port("Q2_1_S", 0.0), _port("Q2_1_G", 5.0, 90)]},
            "row": {"ports": [_port("M1_S", 0.0), _port("M1_G", 0.54, 90),
                              _port("M1_D", 1.08)]},
        }

    def test_two_row_split_up_down(self):
        pins = [_pin("a", "dp", "Q1_1_S"), _pin("b", "dp", "Q2_1_S"),
                _pin("c", "dp", "Q1_1_G", 90), _pin("d", "dp", "Q2_1_G", 90)]
        rn.classify(pins, self.reports)
        got = {p["port"]: p["updown"] for p in pins}
        self.assertEqual(got, {"Q1_1_S": "down", "Q2_1_S": "up",
                               "Q1_1_G": "down", "Q2_1_G": "up"})
        # Q1_1_S / Q2_1_S share x=0: both S/D pins get the escape stub,
        # the gates keep their own column
        stubs = {p["port"]: p["stub_um"] for p in pins}
        self.assertEqual(stubs, {"Q1_1_S": rn.STUB_UM, "Q2_1_S": rn.STUB_UM,
                                 "Q1_1_G": 0.0, "Q2_1_G": 0.0})

    def test_single_row_goes_up(self):
        pins = [_pin("a", "row", "M1_S")]
        rn.classify(pins, self.reports)
        self.assertEqual(pins[0]["updown"], "up")

    def test_crowded_sd_gets_stub_and_gate_keeps_column(self):
        pins = [_pin("a", "row", "M1_S"), _pin("g", "row", "M1_G", 90),
                _pin("d", "row", "M1_D")]
        rn.classify(pins, self.reports)
        by = {p["port"]: p for p in pins}
        self.assertEqual(by["M1_S"]["stub_um"], rn.STUB_UM)
        self.assertEqual(by["M1_D"]["stub_um"], rn.STUB_UM)
        self.assertEqual(by["M1_G"]["stub_um"], 0.0)

    def test_uncrowded_sd_has_no_stub(self):
        reports = {"res": {"ports": [_port("R_A", 0.0), _port("R_B", 0.92)]}}
        pins = [_pin("a", "res", "R_A"), _pin("b", "res", "R_B")]
        rn.classify(pins, reports)
        self.assertTrue(all(p["stub_um"] == 0.0 for p in pins))

    def test_non_device_pin_defaults_up_without_stub(self):
        pins = [_pin("a", "row", "X", kind="tap")]
        rn.classify(pins, self.reports)
        self.assertEqual(pins[0]["updown"], "up")
        self.assertEqual(pins[0]["stub_um"], 0.0)


class AssignTracks(unittest.TestCase):
    def test_distinct_monotone_tracks_in_net_order(self):
        pins = [{"net": n, "updown": u} for n, u in
                [("a", "up"), ("b", "up"), ("c", "up"),
                 ("a", "down"), ("c", "down")]]
        tracks, up, down = rn.assign_tracks(pins, 0.0, 10.0, ["c", "b", "a"])
        up_y = [tracks[(n, "up")] for n in ("c", "b", "a")]
        self.assertAlmostEqual(up_y[0], 10.0 + rn.CHANNEL_GAP_UM)
        for lo, hi in zip(up_y, up_y[1:]):
            self.assertAlmostEqual(hi - lo, rn.TRACK_PITCH_UM)
        dn_y = [tracks[(n, "down")] for n in ("c", "a")]
        self.assertAlmostEqual(dn_y[0], 0.0 - rn.CHANNEL_GAP_UM)
        self.assertAlmostEqual(dn_y[0] - dn_y[1], rn.TRACK_PITCH_UM)
        self.assertNotIn(("b", "down"), tracks)
        self.assertEqual(len(tracks), 5)
        self.assertEqual(set(up), {"a", "b", "c"})
        self.assertEqual(set(down), {"a", "c"})
        self.assertEqual(len(up["a"]), 1)


class AssignLinks(unittest.TestCase):
    def test_slots_clear_of_risers(self):
        # slots in (0,3): 0.46 1.08 1.70 2.32; riser at 1.40 kills 1.08, 1.70
        got = rn.assign_links(["a", "b"], [(0.0, 3.0)], [1.40])
        self.assertEqual(sorted(got), ["a", "b"])
        xs = sorted(got.values())
        self.assertAlmostEqual(xs[0], 0.46)
        self.assertAlmostEqual(xs[1], 2.32)
        for x in xs:
            self.assertGreaterEqual(abs(x - 1.40),
                                    rn.W_ROUTE_UM + rn.MIN_SPACE_UM)

    def test_links_spread_across_slots(self):
        got = rn.assign_links(["a", "b"], [(0.0, 3.0)], [])
        self.assertAlmostEqual(got["a"], 0.46)
        self.assertAlmostEqual(got["b"], 1.70)   # slots[2]

    def test_exhaustion_raises_systemexit(self):
        with self.assertRaises(SystemExit) as cm:
            rn.assign_links(["a", "b", "c"], [(0.0, 3.0)], [1.40])
        self.assertIn("2 channel-link slots for 3 nets", str(cm.exception))

    def test_gap_too_narrow_has_no_slots(self):
        with self.assertRaises(SystemExit):
            rn.assign_links(["a"], [(0.0, 0.5)], [])


@unittest.skipUnless(HAVE_KLAYOUT, "real klayout.db not installed")
class CheckSpacing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = _load("route_nets_real_under_test", stub_klayout=False)

    def _shapes(self, a, b):
        r = self.real
        return {"M1": {"A": [r._box(*a)], "B": [r._box(*b)]}}

    def test_far_apart_ok(self):
        self.assertEqual(self.real.check_spacing(
            self._shapes((0, 0, 1, 1), (2, 0, 3, 1))), [])

    def test_too_close_flagged(self):
        probs = self.real.check_spacing(
            self._shapes((0, 0, 1, 1), (1.2, 0, 2, 1)))
        self.assertEqual(len(probs), 1)
        self.assertIn("closer than", probs[0])

    def test_overlap_flagged_as_short(self):
        probs = self.real.check_spacing(
            self._shapes((0, 0, 1, 1), (0.5, 0, 2, 1)))
        self.assertEqual(len(probs), 1)
        self.assertIn("short", probs[0])

    def test_exactly_min_space_ok(self):
        self.assertEqual(self.real.check_spacing(
            self._shapes((0, 0, 1, 1), (1 + self.real.MIN_SPACE_UM, 0, 2.5, 1))),
            [])


if __name__ == "__main__":
    unittest.main()
