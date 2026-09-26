"""Make the reference-parity harness in `research/zeke_retire_calc` importable."""

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[4] / "research" / "zeke_retire_calc"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
