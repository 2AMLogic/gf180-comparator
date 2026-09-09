"""Pinned-toolchain check.

``sim/toolchain.json`` pins the exact open_pdks commit the device models must
come from, plus floors for ngspice and Python. The pins are **checked before
any PVT point is simulated**, not merely recorded afterwards: a different
open_pdks hash is a different set of device models, so a record taken under
one hash is not comparable with a record taken under another, and nothing in
the resulting numbers would look wrong.

Ported from ``2AMLogic/gf180-sar-adc``'s ``sim/harness/toolchain.py``.
Deliberately NOT ported: that repo's ``scipy_min`` pin (nothing here needs
scipy -- the harness is stdlib-only) and its ``xschem_commit`` cache key
(no schematic exists in ``design/`` yet, so nothing invokes xschem).
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLCHAIN_JSON = REPO_ROOT / "sim" / "toolchain.json"


class ToolchainDrift(RuntimeError):
    """A pinned tool version does not match what is installed."""


@dataclass
class Toolchain:
    pins: dict
    observed: dict = field(default_factory=dict)
    drift: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pins": {k: v for k, v in self.pins.items() if not k.startswith("_")},
            "observed": self.observed,
            "drift": list(self.drift),
        }


def load_pins(path: Path = TOOLCHAIN_JSON) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"no toolchain pin file at {path}")
    return json.loads(path.read_text())


def _ngspice_major(version_banner: str) -> int | None:
    match = re.search(r"ngspice-(\d+)", version_banner)
    return int(match.group(1)) if match else None


def check(pdk_version: str, ngspice_banner: str, path: Path = TOOLCHAIN_JSON) -> Toolchain:
    """Compare the pins against what is actually installed.

    Returns a :class:`Toolchain` whose ``drift`` list is empty when every
    checked pin matches. The caller decides whether drift is fatal (it is, by
    default -- ``--allow-toolchain-drift`` overrides and stamps the drift into
    the record).
    """
    pins = load_pins(path)
    observed = {
        "open_pdks": pdk_version,
        "ngspice": ngspice_banner,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    drift: list[str] = []

    pinned_pdk = pins.get("open_pdks")
    if pinned_pdk and pdk_version != pinned_pdk:
        drift.append(
            f"open_pdks: pinned {pinned_pdk}, installed {pdk_version} -- "
            "the hash IS the device models; records taken under a different "
            "hash are not comparable with the ones already in sim/"
        )

    pinned_ng = pins.get("ngspice_min_major")
    major = _ngspice_major(ngspice_banner)
    if pinned_ng is not None:
        if major is None:
            drift.append(f"ngspice: could not parse a major version from {ngspice_banner!r}")
        elif major < int(pinned_ng):
            drift.append(f"ngspice: pinned floor {pinned_ng}, installed major {major}")

    pinned_py = pins.get("python_min")
    if pinned_py:
        want = tuple(int(p) for p in str(pinned_py).split("."))
        if sys.version_info[: len(want)] < want:
            drift.append(f"python: pinned floor {pinned_py}, running {platform.python_version()}")

    return Toolchain(pins=pins, observed=observed, drift=drift)


def xschem_banner() -> str:
    """Best-effort xschem version string. Recorded, never checked (see json)."""
    try:
        out = subprocess.run(
            ["xschem", "--version"], capture_output=True, text=True, check=False, timeout=20
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "not installed"
    text = (out.stdout + out.stderr).strip()
    return text.splitlines()[0].strip() if text else "unknown"
