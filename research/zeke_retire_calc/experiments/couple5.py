"""Two men, no pensions, the age gap swept finely.

`couple4` found the pair reads its surface at a fixed blend of the two
statutory months — 0.5203 on the later one for gaps up to 60 months, ~0.55 at
84 and 120, ~0.50 at 144. The break sits near 84 months, the length of a
man's 60-to-67 window, so the windows overlapping may be what matters. This
fills in the gap axis, with the partner older (the direction is symmetric).
"""
from experiments.couple4 import pair

TODAY_MONTHS = 1990 * 12  # January 1990, months since year 0

SCENARIOS = {}
for gap in (1, 2, 3, 12, 48, 66, 72, 78, 81, 84, 87, 90, 96, 108, 132):
    born = TODAY_MONTHS - gap
    SCENARIOS[f"cp5_older_{gap:03d}"] = pair(f"{born // 12}-{born % 12 + 1:02d}-01")
