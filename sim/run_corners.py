#!/usr/bin/env python3
"""PVT corner runner for gf180-comparator.

    python3 sim/run_corners.py --check-env
    python3 sim/run_corners.py --list
    python3 sim/run_corners.py comparator-offset-mc

Stdlib only, no virtualenv required. See sim/harness/README.md for the
harness reference and sim/README.md for the evidence-record format it writes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
