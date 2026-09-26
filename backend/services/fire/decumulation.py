"""The reference's decumulation return — measured, not derived.

After retirement a withdrawal portfolio stops earning the return the user typed
and earns a much lower, confidence-derived one instead (notes/07). The
reference calls this a Trinity-study inversion at 75% equities; the surface is
not a formula anyone can recover from the outside (it is not even monotone —
rule 80 peaks at a 40-year horizon), so this module ships it **measured**.

The surface is a function of the confidence level (`retireRule`) and one
horizon, the bridge, in years (`bridge.py` says which). Every whole-year bridge
from 7 to 45 is read straight off the reference for rules 80, 85, 90, 95 and
100 — an idle 1e9 portfolio with no fee pins each cell to ~1e-9
(`experiments/surface.py`) — and fractional bridges measured off recorded
`retire_asap` runs sit between them. `build_decumulation_table.py` rebuilds the
file.

Between measured bridges each level is a monotone cubic (PCHIP); a level with
only a handful of cells borrows the reference level's shape between them.
Confidence does **not** interpolate linearly — rule 87 at a 15-year bridge is
0.120 against the 0.196 a straight line between 85 and 90 gives — so a level
off the measured grid is only as good as the nearest measured ones.
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("decumulation_table.json")

REFERENCE_RULE = 85.0
"""The only densely-sampled confidence level; lends its shape to the others."""


class _Curve:
    """Monotone cubic (Fritsch-Carlson PCHIP) through the measured cells."""

    def __init__(self, points: list[tuple[float, float]]) -> None:
        points = sorted(points)
        self.xs = [x for x, _ in points]
        self.ys = [y for _, y in points]
        self.slopes = self._slopes()

    def _slopes(self) -> list[float]:
        xs, ys = self.xs, self.ys
        if len(xs) < 2:
            return [0.0] * len(xs)
        widths = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        secants = [(ys[i + 1] - ys[i]) / widths[i] for i in range(len(xs) - 1)]
        slopes = [secants[0]] + [0.0] * (len(xs) - 2) + [secants[-1]]
        for i in range(1, len(xs) - 1):
            if secants[i - 1] * secants[i] <= 0:
                continue  # a local extremum: flat, so the curve cannot overshoot
            left = 2 * widths[i] + widths[i - 1]
            right = widths[i] + 2 * widths[i - 1]
            slopes[i] = (left + right) / (left / secants[i - 1] + right / secants[i])
        return slopes

    def __call__(self, x: float) -> float:
        xs, ys, slopes = self.xs, self.ys, self.slopes
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect_right(xs, x) - 1
        width = xs[i + 1] - xs[i]
        t = (x - xs[i]) / width
        t2, t3 = t * t, t * t * t
        return (
            ys[i] * (2 * t3 - 3 * t2 + 1)
            + slopes[i] * width * (t3 - 2 * t2 + t)
            + ys[i + 1] * (-2 * t3 + 3 * t2)
            + slopes[i + 1] * width * (t3 - t2)
        )


DENSE = 10
"""A level with at least this many cells is read on its own curve; a sparser
one borrows the reference level's shape between its cells."""


@lru_cache(maxsize=1)
def _surface() -> tuple[dict[float, list[tuple[float, float]]], dict[float, _Curve]]:
    raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    cells = {
        float(rule): sorted((float(bridge), rate) for bridge, rate in row.items())
        for rule, row in raw["bridge_years"].items()
    }
    curves = {
        rule: _Curve(points) for rule, points in cells.items() if len(points) >= DENSE
    }
    return cells, curves


def _for_rule(rule: float, bridge: float) -> float:
    cells, curves = _surface()
    if rule in curves:
        return max(curves[rule](bridge), 0.0)
    reference = curves[REFERENCE_RULE]

    points = cells[rule]
    if bridge <= points[0][0]:
        return max(points[0][1], 0.0)
    if bridge >= points[-1][0]:
        return max(points[-1][1], 0.0)

    index = bisect_right([x for x, _ in points], bridge) - 1
    (low_bridge, low_rate), (high_bridge, high_rate) = points[index], points[index + 1]
    span = reference(high_bridge) - reference(low_bridge)
    if abs(span) < 1e-6:  # both ends sit on the collapsed part of the curve
        weight = (bridge - low_bridge) / (high_bridge - low_bridge)
    else:
        weight = min(max((reference(bridge) - reference(low_bridge)) / span, 0.0), 1.0)
    return max(low_rate + (high_rate - low_rate) * weight, 0.0)


def decumulation_return_pct(confidence: float, bridge_years: float) -> float:
    """Real return a withdrawal portfolio earns after retirement.

    `confidence` is the `retireRule` field; the reference rejects anything below
    80. `bridge_years` is the horizon `bridge.bridge_months` works out.
    """
    cells, _ = _surface()
    rules = sorted(cells)
    confidence = min(max(confidence, rules[0]), rules[-1])
    if confidence in cells:
        return _for_rule(confidence, bridge_years)
    index = bisect_left(rules, confidence)
    low, high = rules[index - 1], rules[index]
    weight = (confidence - low) / (high - low)
    return (
        _for_rule(low, bridge_years)
        + (_for_rule(high, bridge_years) - _for_rule(low, bridge_years)) * weight
    )
