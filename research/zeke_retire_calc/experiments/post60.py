"""Retiring after 60: which bridge does the surface read?

Measured so far at four ages only (61-64, rule 85), where the rate sits on the
pre-60 curve at `67 - age + 23.45` (notes/15). A constant like that is a fit,
not a rule; every whole age from 61 to 70, every rule, and a woman beside the
man, say what the horizon actually is. Same idle-portfolio design as
`surface`.
"""
from experiments.surface import cell

SCENARIOS = {f"sp_r{rule}_a{age}": cell(rule, 67 - age)
             for rule in (80, 85, 90, 95, 100) for age in range(61, 71)}
SCENARIOS.update({f"sp_f_r85_a{age}": cell(85, 65 - age, gender="female", statutory=65)
                  for age in range(61, 71)})
