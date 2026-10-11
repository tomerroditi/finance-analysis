"""The decumulation surface at confidence levels between the measured five.

The engine reads 80/85/90/95/100 off measured cells and interpolates the
reference's solver drift for everything else, which costs up to 0.2% in the
12-18 year knee (`sf_r82_n180`, `sf_r87_n180`). The confidence field is a free
number input, so any level is reachable. This measures two off-grid levels
monthly through the knee — enough, with the five dense ones, to recover the
solver itself — plus one fractional level to see whether the field takes it.
Same idle-portfolio design as `surface_fine`.
"""
from experiments.surface_fine import cell

KNEE = range(132, 253)
"""11 to 21 years: where the drift is non-zero for levels 81-89."""

SCENARIOS = {f"sff_r{rule}_m{months}": cell(rule, months)
             for rule in (82, 87) for months in KNEE}
SCENARIOS["sff_r82.5_m180"] = cell(82.5, 180)


def knee(rule: float) -> float:
    """Years at which the author's withdrawal rate times the horizon reaches 1."""
    return (100 * rule ** 0.6 / 379) ** 2


SCENARIOS.update({
    f"sff_r{rule}_m{months}": cell(rule, months)
    for rule in (81, 93, 99, 82.5)
    for months in range(round(12 * (knee(rule) - 3)), round(12 * (knee(rule) + 5)) + 1, 9)
})
"""A check of the recovered solver (decumulation.py) on levels it never saw:
eleven cells across each knee, where the solver's early stop moves the rate
most, and a fractional level."""
