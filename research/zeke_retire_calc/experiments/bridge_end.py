"""What exactly sets the bridge's end age?

`bridge_weights` found the effective bridge ends at `67 - 7·y(x)`, where
x = (pension paid from 60) / (monthly spending), independent of the retirement
age — at x = 0.32 only. This family checks that and asks what "spending" and
"pension" mean:

* `be_age*`   — retirement ages 40 / 50 at x = 0.11 and 0.75;
* `be_fem*`   — a woman: is the window 60→65 and the same y(x)?
* `be_net*`   — a pension big enough that tax and national insurance bite:
                is x gross or net?
* `be_exp*`   — spending that changes: a row ending at 60, a row starting at 60,
                an annual rise;
* `be_inc*`   — recurring non-work income continuing after retirement;
* `be_fine*`  — more points on y(x) near its ends.
"""
from scenario import flow, form, pension, portfolio

WORK = flow(10_000, "now", "fire")


def base(share=30, spend=None, balance=1_200_000, age=45, tactic="60-67",
         gender="male", incomes=None):
    return form(retire_at=age, base_problem_max_age=60, gender=gender,
                incomes=incomes or [WORK],
                expenses=spend or [flow(5_000)],
                portfolios=[portfolio(1_200_000, description="W1")],
                pension=pension(balance, tactic=tactic, mukeret_pct=share, frozen=True))


SCENARIOS = {
    "be_age40_s10": base(share=10, age=40),
    "be_age50_s10": base(share=10, age=50),
    "be_age40_s70": base(share=70, age=40),
    "be_age50_s70": base(share=70, age=50),
    "be_fem_s30": base(share=30, gender="female"),
    "be_fem_s70": base(share=70, gender="female"),
    "be_net_3m_20k": base(tactic="60", balance=3_000_000, spend=[flow(20_000)]),
    "be_net_6m_40k": base(tactic="60", balance=6_000_000, spend=[flow(40_000)]),
    "be_exp_end60": base(spend=[flow(3_000), flow(2_000, end="60")]),
    "be_exp_from60": base(spend=[flow(3_000), flow(2_000, "from_date", start_date="2050-01-01")]),
    "be_exp_rise": base(spend=[flow(5_000, rise=1.0)]),
    "be_inc_rent": base(incomes=[WORK, flow(1_000, "now", "forever")]),
    "be_inc_fire": base(incomes=[WORK, flow(1_000, "fire", "forever")]),
    "be_fine_s2": base(share=2),
    "be_fine_s5": base(share=5),
    "be_fine_s80": base(share=80),
    "be_fine_s85": base(share=85),
    "be_fine_s93": base(share=93),
}
