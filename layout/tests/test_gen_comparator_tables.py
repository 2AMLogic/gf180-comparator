#!/usr/bin/env python3
"""PDK-free cross-check of layout/gen_comparator.py's hand-transcribed tables
against design/comparator.spice and the committed gen-compose evidence (#193).

`NETS`, `PIN_LABELS` and `BLOCKS` are typed by hand from the schematics; a
wrong-net pin there still produces a clean gen-compose/LVS-shaped run for a
symmetric circuit. This test flattens the generated hierarchical netlist
(resolving port bindings through the top-level `XA`/`XL` instances) and checks:

  1. every NETS (device, terminal) sits on the claimed net in the netlist;
  2. every non-body multi-pin flat net is in NETS, PIN_LABELS nets are
     single-pin nets, and the two tables are disjoint;
  3. NETS | PIN_LABELS covers layout_common.INTERFACE_PINS;
  4. build_request() connectivity/pins/block ids equal the committed
     layout/comparator.gen-compose.json;
  5. BLOCKS W/L/flavour (and resistor geometry) agree with the netlist.

Stdlib only: `route_nets` (which imports klayout) is stubbed before
`gen_comparator` is imported.

    python3 layout/tests/test_gen_comparator_tables.py
"""

from __future__ import annotations

import json
import re
import sys
import types
import unittest
from pathlib import Path

LAYOUT = Path(__file__).resolve().parents[1]
REPO = LAYOUT.parent
NETLIST = REPO / "design" / "comparator.spice"
COMPOSE_JSON = LAYOUT / "comparator.gen-compose.json"

if str(LAYOUT) not in sys.path:
    sys.path.insert(0, str(LAYOUT))
sys.modules.setdefault("route_nets", types.ModuleType("route_nets"))

import gen_comparator as gc  # noqa: E402
import layout_common  # noqa: E402

MOS_MODELS = {"nfet_03v3": "nfet", "pfet_03v3": "pfet"}


def _logical_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("*"):
            continue
        if raw.startswith("+") and out:
            out[-1] += " " + raw[1:].strip()
        else:
            out.append(raw.strip())
    return out


def _um(value: str) -> float:
    m = re.fullmatch(r"([0-9.]+)u", value)
    assert m, f"unexpected length literal {value!r}"
    return float(m.group(1))


def parse_netlist(text: str):
    """Return (subckts, top_instances).

    subckts: name -> {"ports": [...], "devices": {dev: {...}}, "calls": [...]}
    Devices are keyed by bare name (no leading X). MOS: nets d g s b;
    resistor: nets m p b.
    """
    subckts: dict = {}
    cur = None
    for line in _logical_lines(text):
        tok = line.split()
        if tok[0].lower() == ".subckt":
            cur = {"ports": tok[2:], "devices": {}, "calls": []}
            subckts[tok[1]] = cur
        elif tok[0].lower() == ".ends":
            cur = None
        elif cur is not None and tok[0][0] in "Xx":
            model_idx = next(
                (i for i, t in enumerate(tok)
                 if t in MOS_MODELS or t == "ppolyf_u_1k"
                 or t in subckts or t.startswith("comparator_dut")), None)
            model = tok[model_idx]
            nets = tok[1:model_idx]
            params = dict(
                t.split("=", 1) for t in tok[model_idx + 1:] if "=" in t
                and "'" not in t.split("=", 1)[1])
            if model in subckts or model.startswith("comparator_dut"):
                cur["calls"].append((tok[0], nets, model))
            elif model in MOS_MODELS:
                cur["devices"][tok[0][1:]] = {
                    "kind": "mos", "model": model, "params": params,
                    "pins": dict(zip("dgsb", nets))}
            else:
                cur["devices"][tok[0][1:]] = {
                    "kind": "res", "model": model, "params": params,
                    "pins": dict(zip("mpb", nets))}
    return subckts, subckts["comparator_dut"]["calls"]


def flatten(subckts, top_calls):
    """Return (devices, ) with every pin net renamed to its top-level net.

    Internal nets keep their bare name (asserted unique across subckts).
    """
    devices: dict = {}
    seen_internal: dict = {}
    for _inst, actuals, sub in top_calls:
        cell = subckts[sub]
        assert len(actuals) == len(cell["ports"]), sub
        binding = dict(zip(cell["ports"], actuals))
        for dev, d in cell["devices"].items():
            assert dev not in devices, f"duplicate device {dev}"
            pins = {}
            for term, net in d["pins"].items():
                if net not in binding:
                    assert seen_internal.setdefault(net, sub) == sub, \
                        f"internal net {net} in two subckts"
                pins[term] = binding.get(net, net)
            devices[dev] = {**d, "pins": pins}
    return devices


def flat_net_pins(devices) -> dict[str, set[tuple[str, str]]]:
    nets: dict[str, set] = {}
    for dev, d in devices.items():
        for term, net in d["pins"].items():
            if term == "b":
                continue
            nets.setdefault(net, set()).add((dev, term))
    return nets


def load_flat(netlist_text: str | None = None):
    text = netlist_text if netlist_text is not None else NETLIST.read_text()
    subckts, top_calls = parse_netlist(text)
    return flatten(subckts, top_calls)


def check_tables(devices, nets_table, pin_labels):
    """Return a list of human-readable mismatch strings (empty == clean)."""
    problems: list[str] = []
    flat = flat_net_pins(devices)
    for net, pins in nets_table.items():
        want = set(pins)
        if len(want) != len(pins):
            problems.append(f"NETS[{net}] lists a pin twice")
        got = flat.get(net, set())
        if want != got:
            problems.append(
                f"NETS[{net}] mismatch: table-only={sorted(want - got)} "
                f"netlist-only={sorted(got - want)}")
    # 2. coverage
    for net, pins in flat.items():
        if len(pins) > 1 and net not in nets_table:
            problems.append(f"multi-pin net {net} {sorted(pins)} not in NETS")
    for net, entry in pin_labels.items():
        if len(flat.get(net, ())) != 1:
            problems.append(f"PIN_LABELS net {net} is not a single-pin net")
        if net in nets_table:
            problems.append(f"net {net} in both NETS and PIN_LABELS")
    # 3. interface
    missing = set(layout_common.INTERFACE_PINS) - set(nets_table) - set(pin_labels)
    if missing:
        problems.append(f"interface pins uncovered: {sorted(missing)}")
    return problems


class TablesVsNetlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.devices = load_flat()

    def test_parser_sanity(self):
        self.assertEqual(len(self.devices), 29)
        flat = flat_net_pins(self.devices)
        self.assertEqual(flat["aop"], {("MIN", "d"), ("RP", "m"), ("M1", "g")})
        self.assertEqual(flat["aon"], {("MIP", "d"), ("RN", "m"), ("M2", "g")})

    def test_nets_and_pin_labels_match_netlist(self):
        # Items 1-3.
        self.assertEqual(
            check_tables(self.devices, gc.NETS, gc.PIN_LABELS), [])

    @staticmethod
    def _dev_of(entry):
        for dev, (bid, suffix) in gc._DEV2BLOCK.items():
            if bid == entry["block"] and entry["port"].startswith(suffix + "_"):
                return dev
        raise AssertionError(entry)

    @staticmethod
    def _term_of(entry):
        return entry["port"].rsplit("_", 1)[1].lower()

    def test_pin_label_entries_resolve_to_the_netlist_pin(self):
        flat = flat_net_pins(self.devices)
        for net, entry in gc.PIN_LABELS.items():
            self.assertEqual(
                flat[net], {(self._dev_of(entry), self._term_of(entry))}, net)

    def test_every_device_is_in_exactly_one_block(self):
        self.assertEqual(set(gc._DEV2BLOCK), set(self.devices))
        listed = [d for _b, _g, devs in gc.BLOCKS for d in devs]
        self.assertEqual(len(listed), len(set(listed)))

    def test_block_params_match_netlist(self):
        # Item 5.
        for bid, (generator, params), devs in gc.BLOCKS:
            for dev in devs:
                d = self.devices[dev]
                where = f"{bid}/{dev}"
                if generator == "res_array":
                    self.assertEqual(d["kind"], "res", where)
                    self.assertEqual(_um(d["params"]["r_length"]),
                                     params["length_um"], where)
                    self.assertEqual(_um(d["params"]["r_width"]),
                                     params["width_um"], where)
                    self.assertEqual(d["model"], f"ppolyf_u_{params['flavor']}", where)
                else:
                    self.assertEqual(d["kind"], "mos", where)
                    self.assertEqual(_um(d["params"]["W"]), params["w_um"], where)
                    self.assertEqual(_um(d["params"]["L"]), params["l_um"], where)
                    self.assertEqual(MOS_MODELS[d["model"]], params["flavor"], where)
                    self.assertEqual(d["params"]["nf"], "1", where)
                self.assertEqual(d["params"]["m"], "1", where)


class RequestVsCommittedEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.req = gc.build_request()
        cls.doc = json.loads(COMPOSE_JSON.read_text())

    def test_connectivity_matches_committed_json(self):
        def norm(items):
            return {c["net"]: {(p["block"], p["port"]) for p in c["pins"]}
                    for c in items}
        self.assertEqual(norm(self.req["connectivity"]), norm(self.doc["nets"]))
        self.assertEqual(len(self.req["connectivity"]), len(self.doc["nets"]))
        self.assertEqual([c["net"] for c in self.req["connectivity"]],
                         [c["net"] for c in self.doc["nets"]])

    def test_pins_match_committed_json(self):
        def norm(items):
            return sorted((p["net"], p["block"], p["port"]) for p in items)
        self.assertEqual(norm(self.req["pins"]), norm(self.doc["pins"]))

    def test_block_ids_and_order_match_committed_json(self):
        self.assertEqual([b["id"] for b in self.req["blocks"]],
                         [b["id"] for b in self.doc["blocks"]])


if __name__ == "__main__":
    unittest.main()
