"""How does a split pension claim weight its two bridges?

`gb_t6067_0k` and `pn_annuity_6067` both read the surface at an effective
bridge ending near age 65.72, though they retire four years apart — so the
bridge end is a weighted claim age. Pay weights put it at 65.08, pay weights
counting Bituach Leumi at 65.70, and `gb_t60_0k` (everything at 60) ends at
exactly 60.00 even though Bituach Leumi still starts at 67. Each family below
moves one thing:

* `bw_share_*` — the recognised share claimed at 60 (the weight itself);
* `bw_exp_*`   — spending: does coverage of expenses enter?
* `bw_bal_*`   — the pension's size against a fixed Bituach Leumi;
* `bw_t60_*`   — all-at-60 with a pension that cannot cover spending;
* `bw_age_*`   — the retirement age (the end age should not move);
* `gb2_*`      — the gemel ladder notes/15 designed, with complete rows.
"""
from scenario import flow, form, pension, portfolio


def base(tactic="60-67", share=30, spend=5_000, balance=1_200_000, age=45, extra=()):
    return form(retire_at=age, base_problem_max_age=60,
                expenses=[flow(spend)],
                portfolios=[portfolio(1_200_000, description="W1"), *extra],
                pension=pension(balance, tactic=tactic, mukeret_pct=share, frozen=True))


SCENARIOS = {}
for share in (0, 10, 20, 50, 70, 90, 100):
    SCENARIOS[f"bw_share_{share}"] = base(share=share)
for spend in (2_000, 10_000, 20_000):
    SCENARIOS[f"bw_exp_{spend // 1000}k"] = base(spend=spend)
for balance in (300_000, 5_000_000):
    SCENARIOS[f"bw_bal_{balance // 1000}k"] = base(balance=balance)
SCENARIOS["bw_t60_bal300k"] = base(tactic="60", balance=300_000)
SCENARIOS["bw_t60_exp20k"] = base(tactic="60", spend=20_000)
for age in (40, 50):
    SCENARIOS[f"bw_age_{age}"] = base(age=age)
for tactic in ("60", "60-67", "67"):
    for gemel in (400_000, 1_600_000):
        SCENARIOS[f"gb2_t{tactic.replace('-', '')}_{gemel // 1000}k"] = base(
            tactic=tactic, extra=[portfolio(gemel, "mukeret_main", "gemel", description="M2")])
