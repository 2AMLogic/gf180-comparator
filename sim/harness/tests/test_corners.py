"""Unit tests for ``harness.corners.build_grid``'s corner_id uniqueness check.

Regression coverage for #8: ``build_grid()`` used to build the full P x V x T
grid with no check that the resulting ``corner_id`` values (see
``PvtPoint.corner_id``, ``f"{corner}_{temp_c:g}c_{vdd:.2f}v"``) were unique.
A custom ``--temps``/``--supply-tolerance`` can produce distinct
``(corner, temp_c, vdd)`` tuples that render to the same string -- e.g.
``--supply-tolerance 0.001`` on the 3.3 V nominal yields 3.2967/3.3/3.3033 V,
all of which round to ``3.30`` under ``:.2f`` -- silently collapsing the
grid instead of raising.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.corners import (  # noqa: E402
    CORNERS,
    DEFAULT_NOMINAL_SUPPLY_V,
    DEFAULT_SUPPLY_TOLERANCE,
    DEFAULT_TEMPERATURES_C,
    CornerIdCollisionError,
    build_grid,
    corner_id,
    parse_corner_id,
    resolve_corners,
    supply_points,
)


class BuildGridCollisionTest(unittest.TestCase):
    def test_tight_supply_tolerance_collapses_corner_id_and_raises(self):
        """--supply-tolerance 0.001 on the 3.3 V nominal collapses all three
        supply points (3.2967 / 3.3 / 3.3033 V) to the same '3.30v' suffix
        under corner_id's ':.2f' formatting -- reproducing the scenario
        traced by hand in the original issue, executed here for real.
        """
        supplies = supply_points(nominal_v=3.3, tolerance=0.001)
        # Confirm the reproduction is real before asserting on its effect:
        # three *distinct* floats that all format identically under ':.2f'.
        self.assertEqual(len(set(supplies)), 3)
        self.assertEqual({f"{v:.2f}" for v in supplies}, {"3.30"})

        with self.assertRaises(CornerIdCollisionError) as ctx:
            build_grid([CORNERS["tt"]], [27.0], supplies)

        message = str(ctx.exception)
        self.assertIn("tt_27c_3.30v", message)
        # All three colliding vdd values should be named in the error so a
        # user can see which flag combination caused the collision.
        for vdd in supplies:
            self.assertIn(repr(vdd), message)

    def test_colliding_temperatures_also_raise(self):
        """The ':g' temperature format can collide independently of vdd."""
        supplies = supply_points(nominal_v=3.3, tolerance=0)
        with self.assertRaises(CornerIdCollisionError):
            build_grid([CORNERS["tt"]], [27.0, 27.0000001], supplies)

    def test_default_grid_has_no_false_positive_collision(self):
        """The default 45-point grid (characterize.sh/selftest.sh) must not
        trip the new check."""
        corner_list = resolve_corners(["mos"])  # tt, ff, ss, fs, sf
        supplies = supply_points(DEFAULT_NOMINAL_SUPPLY_V, DEFAULT_SUPPLY_TOLERANCE)
        points = build_grid(corner_list, list(DEFAULT_TEMPERATURES_C), supplies)
        self.assertEqual(len(points), 5 * len(DEFAULT_TEMPERATURES_C) * len(supplies))
        ids = [p.corner_id for p in points]
        self.assertEqual(len(ids), len(set(ids)))

    def test_default_full_corner_set_has_no_false_positive_collision(self):
        """The 'full' corner set (adds res_ff/res_ss) must also stay collision-free."""
        corner_list = resolve_corners(["full"])
        supplies = supply_points(DEFAULT_NOMINAL_SUPPLY_V, DEFAULT_SUPPLY_TOLERANCE)
        points = build_grid(corner_list, list(DEFAULT_TEMPERATURES_C), supplies)
        ids = [p.corner_id for p in points]
        self.assertEqual(len(ids), len(set(ids)))

    def test_zero_tolerance_single_supply_point_is_fine(self):
        """--supply-tolerance 0 collapses to a single supply point by design
        (see supply_points) -- not a collision, just one point per corner/temp."""
        supplies = supply_points(3.3, tolerance=0)
        self.assertEqual(supplies, [3.3])
        points = build_grid([CORNERS["tt"]], [27.0], supplies)
        self.assertEqual(len(points), 1)


class CornerIdFormatTest(unittest.TestCase):
    """The module-level id formatter and its parser (issue #375).

    ``corner_id`` is the single source of the ratified
    ``<process>_<temp>c_<supply>v`` format string; ``parse_corner_id`` is its
    inverse. Before #375 the format string was hand-copied in five places and
    parsed by three divergent regexes -- two of which rejected ids the
    ratified ``full`` corner set itself admits (``res_ff``/``res_ss``), and
    one of which accepted ids the formatter can never emit (``3.3v``).
    """

    def test_module_formatter_and_pvtpoint_agree(self):
        """Every grid point's PvtPoint.corner_id equals the module function."""
        corner_list = resolve_corners(["full"])
        supplies = supply_points(DEFAULT_NOMINAL_SUPPLY_V, DEFAULT_SUPPLY_TOLERANCE)
        for p in build_grid(corner_list, list(DEFAULT_TEMPERATURES_C), supplies):
            self.assertEqual(p.corner_id, corner_id(p.corner.name, p.temp_c, p.vdd))

    def test_canonical_ids(self):
        self.assertEqual(corner_id("tt", 27.0, 3.3), "tt_27c_3.30v")
        self.assertEqual(corner_id("ss", -40.0, 2.97), "ss_-40c_2.97v")
        self.assertEqual(corner_id("ff", 125, 3.63), "ff_125c_3.63v")

    def test_res_corners_round_trip(self):
        """``res_ff``/``res_ss`` -- ratified names carrying an underscore,
        members of the ``full`` set -- format and round-trip."""
        proc, temp, vdd = parse_corner_id("res_ff_27c_3.30v")
        self.assertEqual((proc, temp, vdd), ("res_ff", 27.0, 3.3))
        self.assertEqual(corner_id(proc, temp, vdd), "res_ff_27c_3.30v")
        proc, temp, vdd = parse_corner_id("res_ss_-40c_2.97v")
        self.assertEqual((proc, temp, vdd), ("res_ss", -40.0, 2.97))
        self.assertEqual(corner_id(proc, temp, vdd), "res_ss_-40c_2.97v")

    def test_parse_canonical(self):
        self.assertEqual(parse_corner_id("tt_27c_3.30v"), ("tt", 27.0, 3.3))
        self.assertEqual(parse_corner_id("ss_-40c_2.97v"), ("ss", -40.0, 2.97))
        self.assertEqual(parse_corner_id("ff_125c_3.63v"), ("ff", 125.0, 3.63))

    def test_parse_is_the_formatters_strict_inverse(self):
        """A 1-decimal supply (``3.3v``) is never formatter output and is
        rejected -- the reading make_item8_envelope.py's evidence gate already
        enforces on committed records."""
        with self.assertRaises(ValueError):
            parse_corner_id("tt_27c_3.3v")

    def test_parse_rejects_malformed(self):
        for bad in ("garbage", "tt_27c_3.30", "27c_3.30v", "tt/27C",
                    "tt_27C_3.30v", "tt_27c_3.30V", "tt_27c_3.300v",
                    "res_ff27c_3.30v"):
            with self.assertRaises(ValueError):
                parse_corner_id(bad)


if __name__ == "__main__":
    unittest.main()
