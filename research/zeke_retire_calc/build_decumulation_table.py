#!/usr/bin/env python3
"""Build the decumulation surface the engine ships, from direct measurements.

Every cell is read straight off a reference run designed for it: an idle 1e9
portfolio with no fee and a 20% return, 20M of cash so it is never drawn, and
nothing else that could move (`experiments/surface.py`). Its post-retirement
growth *is* the surface value, pinned to ~1e-9.

* `sf_r<rule>_n<months>` — a pinned retirement age, so whole-year bridges.
* `sff_r<rule>_m<months>` — every month in between, reached through the
  reference's post-60 rule (bridge.py, notes/18).

Where both designs measured the same cell they agree to 1e-9
(`test_decumulation_table`), and the first one recorded is kept.

Run:  python research/zeke_retire_calc/build_decumulation_table.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import parity  # noqa: E402
from surface_read import measured_rate  # noqa: E402

OUT = HERE.parents[1] / "backend" / "services" / "fire" / "decumulation_table.json"

DESIGNS = (("sf_r", "_n"), ("sff_r", "_m"))
"""Fixture prefix, and the marker before the bridge in months."""


def cells() -> dict[float, dict[float, float]]:
    """`{rule: {bridge years: rate}}` from every surface fixture on disk."""
    out: dict[float, dict[float, float]] = defaultdict(dict)
    for prefix, marker in DESIGNS:
        for name in parity.corpus([prefix]):
            rule = float(name[len(prefix):].split("_")[0])
            bridge = int(name.split(marker)[1]) / 12
            reading = measured_rate(name)
            if reading is not None:
                out[rule].setdefault(round(bridge, 6), round(reading[0], 8))
    return {rule: dict(sorted(row.items())) for rule, row in sorted(out.items())}


def main() -> None:
    table = cells()
    payload = {"bridge_years": {str(int(rule)): {f"{b:.6f}": r for b, r in row.items()}
                                for rule, row in table.items()}}
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    for rule, row in table.items():
        print(f"rule {rule:g}: {len(row)} cells, bridge {min(row):.2f}-{max(row):.2f}")


if __name__ == "__main__":
    main()
