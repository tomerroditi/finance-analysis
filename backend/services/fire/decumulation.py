"""The reference's decumulation return — measured, not derived.

After retirement a withdrawal portfolio stops earning the return the user typed
and earns a much lower, confidence-derived one instead (notes/07). The
reference calls this a Trinity-study result at 75% equities; the generating
formula is not recoverable from the outside, so this module ships the surface
**measured directly** off the calculator: 81 cells, each read off a recorded run
that pins it to within 0.0005 points. `build_decumulation_table.py` rebuilds the
whole file from the fixtures and re-checks that pinning (notes/14, notes/15).

Two structural facts make those scattered measurements one curve per confidence
level:

* **The surface is keyed on the bridge to the statutory pension age**
  (67 male, 65 female), not on the retirement age. A woman retiring at 52.75
  gets the rate a man retiring at 54.75 gets, not the one for a man of her age
  — the single female fixture is decisive. A plan that claims its pension
  earlier than that shortens the bridge further, which is why the caller passes
  `pension_age` rather than the function assuming one (notes/15).
* **Retiring past 60 lands on the same curve, shifted.** The rate collapses to
  zero by about age 54 and stays there through 60, then jumps back to ~2.7% at
  61. Those post-60 points are not a second surface: they sit on the pre-60
  curve at `bridge + POST_60_SHIFT`, to within the measurement noise, for every
  confidence level. Retiring past the bridge apparently removes the constraint
  that the shorter horizon was stress-testing.

Between measured bridges the curve is monotone-cubic (PCHIP) rather than
linear: it is convex through the steep stretch, where a chord runs several
tenths of a point below the truth. Only confidence 85 is densely sampled (45 of
the 81 cells), so the four other levels are interpolated **in the 85 curve's
own coordinate** rather than in years — the shape is shared, only the level
moves. Holding a sparse level's cell out and predicting it from the 85 shape
recovers it to within 0.03 points anywhere on the saturating stretch — but not
at the knee, because each level gives up at its own bridge and rule 100 gives
up about five years earlier than rule 85. That is why the cells between bridge
16 and 19 are measured on every level rather than interpolated; the two
hold-out tests in `test_decumulation_table` pin both halves of that.
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("decumulation_table.json")

BRANCH_AGE = 60.5
"""Retiring above this age uses the shifted branch.

The jump happens between the two measured ages that bracket it — 60.08 is still
on the collapsed part of the curve and 61.08 is already back at 2.74% — so this
is the midpoint of a gap the fixtures cannot narrow.
"""

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
        return (ys[i] * (2 * t3 - 3 * t2 + 1)
                + slopes[i] * width * (t3 - 2 * t2 + t)
                + ys[i + 1] * (-2 * t3 + 3 * t2)
                + slopes[i + 1] * width * (t3 - t2))


@lru_cache(maxsize=1)
def _surface() -> tuple[dict[float, list[tuple[float, float]]], _Curve, float]:
    raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    cells = {float(rule): sorted((float(bridge), rate) for bridge, rate in row.items())
             for rule, row in raw["bridge_years"].items()}
    return cells, _Curve(cells[REFERENCE_RULE]), float(raw["post_60_shift"])


def _for_rule(rule: float, bridge: float) -> float:
    cells, reference, _ = _surface()
    if rule == REFERENCE_RULE:
        return max(reference(bridge), 0.0)

    points = cells[rule]
    if bridge <= points[0][0]:
        return max(points[0][1], 0.0)
    if bridge >= points[-1][0]:
        return max(points[-1][1], 0.0)

    index = bisect_right([x for x, _ in points], bridge) - 1
    (low_bridge, low_rate), (high_bridge, high_rate) = points[index], points[index + 1]
    span = reference(high_bridge) - reference(low_bridge)
    if abs(span) < 1e-6:   # both ends sit on the collapsed part of the curve
        weight = (bridge - low_bridge) / (high_bridge - low_bridge)
    else:
        weight = min(max((reference(bridge) - reference(low_bridge)) / span, 0.0), 1.0)
    return max(low_rate + (high_rate - low_rate) * weight, 0.0)


def decumulation_return_pct(confidence: float, retire_age: float,
                            pension_age: float = 67) -> float:
    """Real return a withdrawal portfolio earns after retirement.

    `confidence` is the `retireRule` field; the reference rejects anything below
    80, and the surface is measured at 80-100 in steps of five. `pension_age` is
    the age the money being waited for arrives — the statutory age by default,
    earlier for a pension claimed early, and blended by the caller when a plan
    claims different components at different ages (notes/15).
    """
    cells, _, shift = _surface()
    bridge = pension_age - retire_age
    if retire_age > BRANCH_AGE:
        bridge += shift

    rules = sorted(cells)
    confidence = min(max(confidence, rules[0]), rules[-1])
    if confidence in cells:
        return _for_rule(confidence, bridge)
    index = bisect_left(rules, confidence)
    low, high = rules[index - 1], rules[index]
    weight = (confidence - low) / (high - low)
    return (_for_rule(low, bridge)
            + (_for_rule(high, bridge) - _for_rule(low, bridge)) * weight)
