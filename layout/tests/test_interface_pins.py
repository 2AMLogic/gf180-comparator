#!/usr/bin/env python3
"""INTERFACE_PINS is defined once (layout/layout_common.py) and matches the
external contract (#194).

    python3 layout/tests/test_interface_pins.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "layout"))
sys.path.insert(0, str(REPO / "layout" / "pex"))
import layout_common  # noqa: E402
import run_pex  # noqa: E402


def _top_ports(text: str) -> tuple:
    m = re.search(r"^\.subckt\s+comparator_dut\s+(.*)$", text, re.I | re.M)
    assert m, "no comparator_dut subckt"
    return tuple(m.group(1).split())


class InterfacePins(unittest.TestCase):
    def test_run_pex_uses_layout_common_object(self):
        self.assertIs(run_pex.INTERFACE_PINS, layout_common.INTERFACE_PINS)

    def test_matches_design_netlist_port_order(self):
        ports = _top_ports((REPO / "design/comparator.spice").read_text())
        self.assertEqual(layout_common.INTERFACE_PINS, ports)

    def test_matches_dut_readme(self):
        ports = _top_ports((REPO / "sim/dut/README.md").read_text())
        self.assertEqual(layout_common.INTERFACE_PINS, ports)


if __name__ == "__main__":
    unittest.main()
