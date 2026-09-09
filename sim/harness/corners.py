"""Process / voltage / temperature corner definitions for gf180mcu.

The gf180mcu ngspice model library (``sm141064.ngspice``) does not ship a
single "ss" switch that skews every device. Each device family carries its
own ``.lib`` section:

    MOS      typical | ff | ss | fs | sf
    BJT      bjt_typical | bjt_ff | bjt_ss
    diode    diode_typical | diode_ff | diode_ss
    resistor res_typical | res_ff | res_ss
    MOS cap  moscap_typical | moscap_ff | moscap_ss
    MIM cap  mimcap_typical | mimcap_ff | mimcap_ss

A *named corner* here is therefore a bundle of exactly one section per
device family. Section ordering follows the PDK's own xschem testbenches
(MOS first, then passives), and ``design.ngspice`` is always included ahead
of them because it defines the global switch params (``sw_stat_global``,
``sw_stat_mismatch``, ``mc_skew``, ...) the sections reference.

PORTED FROM ``2AMLogic/gf180-sar-adc``'s ``sim/harness/corners.py``: the
per-family ``.lib``-bundle structure, the ``sabotage()`` negative control,
the ``<process>_<temp>c_<supply>v`` corner-id convention, and the
-40/27/125 degC x +/-10 % supply axes.

ADAPTED FOR THIS BLOCK. gf180-sar-adc's corner set adds CAPACITOR-dominated
corners (``cap_ff``/``cap_ss``/``mim_*``/``moscap_*``) because a SAR ADC's
accuracy rides on its CDAC. **A standalone comparator has no capacitor
array**, so those corners are dropped here rather than carried as dead
weight -- keeping them would put seven never-load-bearing process points in
every evidence matrix and imply a capacitor-accuracy story this block does
not have. What IS kept is the RESISTOR corner pair: the comparator's
front-end gain is set by its load resistors, so the poly sheet-rho skew is a
first-order gain axis here in a way it never was for the ADC's CDAC.

BJT and diode sections are pinned to typical in every bundle. This block
instantiates neither; the sections are included only because a global
``ff``/``ss`` corner in this PDK is defined as "every family skewed" and
dropping them would make ``ff``/``ss`` here mean something different from
``ff``/``ss`` in the sibling repo's records.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

# Default PVT axes. CLAUDE.md mandates PVT corners on every recorded result.
DEFAULT_TEMPERATURES_C: tuple[float, ...] = (-40.0, 27.0, 125.0)
DEFAULT_SUPPLY_TOLERANCE: float = 0.10  # +/-10 %, per README.md's supply row
DEFAULT_NOMINAL_SUPPLY_V: float = 3.3   # gf180mcu 3.3 V flavor (CLAUDE.md)

#: Device families in the order their ``.lib`` sections are included.
FAMILIES: tuple[str, ...] = ("mos", "res", "bjt", "diode", "moscap", "mimcap")

_MOS, _RES, _BJT, _DIODE, _MOSCAP, _MIMCAP = range(len(FAMILIES))


def _bundle(mos: str, bjt: str, diode: str, res: str, moscap: str, mimcap: str) -> tuple[str, ...]:
    return (mos, res, bjt, diode, moscap, mimcap)


@dataclass(frozen=True)
class Corner:
    """A named process corner: an ordered list of model ``.lib`` sections."""

    name: str
    sections: tuple[str, ...]
    description: str = ""


_TYPICAL = _bundle(
    mos="typical",
    bjt="bjt_typical",
    diode="diode_typical",
    res="res_typical",
    moscap="moscap_typical",
    mimcap="mimcap_typical",
)


def _all(skew: str, description: str) -> Corner:
    """Global corner: every device family skewed the same direction."""
    if skew not in ("ff", "ss"):  # pragma: no cover - programming error
        raise ValueError(f"no global {skew!r} bundle exists in the PDK")
    return Corner(
        name=skew,
        sections=_bundle(
            mos=skew,
            bjt=f"bjt_{skew}",
            diode=f"diode_{skew}",
            res=f"res_{skew}",
            moscap=f"moscap_{skew}",
            mimcap=f"mimcap_{skew}",
        ),
        description=description,
    )


def _mos_only(name: str, mos_section: str, description: str) -> Corner:
    """MOS skewed, passives at typical."""
    return Corner(name=name, sections=(mos_section,) + _TYPICAL[1:], description=description)


def _skew(name: str, overrides: dict[int, str], description: str) -> Corner:
    """Typical everywhere except the named family indices."""
    sections = list(_TYPICAL)
    for index, section in overrides.items():
        sections[index] = section
    return Corner(name=name, sections=tuple(sections), description=description)


CORNERS: dict[str, Corner] = {
    "tt": Corner("tt", _TYPICAL, "all device families typical"),
    "ff": _all("ff", "all device families fast"),
    "ss": _all("ss", "all device families slow"),
    "fs": _mos_only("fs", "fs", "fast NMOS / slow PMOS, passives typical"),
    "sf": _mos_only("sf", "sf", "slow NMOS / fast PMOS, passives typical"),
    # Resistor-dominated corners. A comparator front end with resistive loads
    # has its gain set by (g_m x R_load), so the poly sheet-rho skew moves the
    # gain -- and therefore the input-referred offset and noise -- directly.
    # The five MOS corners above leave resistors at typical, so without these
    # the resistor models would never be exercised off-typical at all.
    "res_ff": _skew("res_ff", {_RES: "res_ff"}, "resistors fast (low sheet rho), rest typical"),
    "res_ss": _skew("res_ss", {_RES: "res_ss"}, "resistors slow (high sheet rho), rest typical"),
}

CORNER_SETS: dict[str, tuple[str, ...]] = {
    # Minimum bar for a quick smoke run. NOT a valid evidence matrix on its own.
    "tt": ("tt",),
    # The five classic MOS corners -- the default.
    "mos": ("tt", "ff", "ss", "fs", "sf"),
    # MOS corners plus the resistor skews that move this block's gain.
    "full": ("tt", "ff", "ss", "fs", "sf", "res_ff", "res_ss"),
}
DEFAULT_CORNER_SET = "mos"


def resolve_corners(names: list[str] | tuple[str, ...] | None) -> list[Corner]:
    """Turn a list of corner *or* corner-set names into Corner objects."""
    if not names:
        names = [DEFAULT_CORNER_SET]
    resolved: list[Corner] = []
    seen: set[str] = set()
    for name in names:
        expanded = CORNER_SETS.get(name, (name,))
        for corner_name in expanded:
            if corner_name in seen:
                continue
            if corner_name not in CORNERS:
                raise KeyError(
                    f"unknown corner {corner_name!r}; "
                    f"known corners: {', '.join(sorted(CORNERS))}; "
                    f"known sets: {', '.join(sorted(CORNER_SETS))}"
                )
            seen.add(corner_name)
            resolved.append(CORNERS[corner_name])
    return resolved


def sabotage(corner_list: list[Corner]) -> list[Corner]:
    """Return the same corner *names* with every section forced to typical.

    This is the harness's **negative control**, not a feature: it reproduces
    the exact silent failure mode this repo is most exposed to -- a runner
    that appears to sweep process corners but actually simulates typical
    everywhere (wrong model include, ignored parameter, wrong section name).

    ``sim/selftest.sh`` runs a testbench once normally and once sabotaged;
    the sabotaged run **must fail** its per-axis sensitivity checks. If it
    passes, corner switching is not taking effect and every downstream
    evidence record is worthless. The CLI forces ``--no-write`` whenever this
    is used, so a sabotaged run can never enter ``sim/`` as evidence.
    """
    return [
        Corner(name=corner.name, sections=_TYPICAL, description=f"SABOTAGED ({corner.description})")
        for corner in corner_list
    ]


def supply_points(
    nominal_v: float = DEFAULT_NOMINAL_SUPPLY_V,
    tolerance: float = DEFAULT_SUPPLY_TOLERANCE,
) -> list[float]:
    """Nominal supply and its +/- tolerance rails, low to high."""
    if tolerance <= 0:
        return [round(nominal_v, 6)]
    return [
        round(nominal_v * (1.0 - tolerance), 6),
        round(nominal_v, 6),
        round(nominal_v * (1.0 + tolerance), 6),
    ]


@dataclass(frozen=True)
class PvtPoint:
    """One point in the PVT grid -- exactly one ngspice invocation."""

    corner: Corner
    temp_c: float
    vdd: float
    index: int = field(default=0, compare=False)

    @property
    def corner_id(self) -> str:
        """The ``<process>_<temp>c_<supply>v`` id from ``sim/README.md``.

        This is the ratified corner naming for evidence records: the raw log
        for this point is ``corners/<record-id>/<corner-id>.log`` (e.g.
        ``ss_-40c_2.97v.log``, ``tt_27c_3.30v.log``).
        """
        return f"{self.corner.name}_{self.temp_c:g}c_{self.vdd:.2f}v"

    def as_dict(self) -> dict:
        return {
            "corner": self.corner.name,
            "corner_sections": list(self.corner.sections),
            "temp_c": self.temp_c,
            "vdd": self.vdd,
            "corner_id": self.corner_id,
        }


def build_grid(
    corners: list[Corner],
    temperatures: list[float] | tuple[float, ...],
    supplies: list[float],
) -> list[PvtPoint]:
    """Full factorial P x V x T grid, in a stable, reproducible order."""
    return [
        PvtPoint(corner=corner, temp_c=float(temp), vdd=float(vdd), index=i)
        for i, (corner, temp, vdd) in enumerate(
            itertools.product(corners, temperatures, supplies)
        )
    ]
