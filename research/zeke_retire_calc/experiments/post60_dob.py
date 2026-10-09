"""Is the post-60 horizon's 23-years-5-months constant, or tied to a date?

`post60` found a man retiring at A in (60, 67] reads the surface at
`67 + 23.4167 - A`, a woman at `65 + 23.4167 - A` — for one birth date
(January 1990) recorded in one month (September 2026). Five months is a
suspicious fraction; these vary the birth date's year and month.
"""
from scenario import flow, form, pension, portfolio


def cell(dob: str, age: int, gender: str = "male") -> dict:
    return form(retire_at=age, base_problem_max_age=70, retireRule=90,
                dateOfBirth=dob, gender=gender, balance=20_000_000,
                incomes=[flow(10_000, "now", "fire")], expenses=[flow(5_000)],
                portfolios=[portfolio(1_000_000_000, interest=20.0, fee=0.0)],
                pension=pension(0))


SCENARIOS = {
    "spd_1985_06_a63": cell("1985-06-01", 63),
    "spd_1975_11_a63": cell("1975-11-01", 63),
    "spd_1968_03_a63": cell("1968-03-01", 63),
    "spd_1968_03_a68": cell("1968-03-01", 68),
    "spd_1985_06_a63f": cell("1985-06-01", 63, "female"),
}
