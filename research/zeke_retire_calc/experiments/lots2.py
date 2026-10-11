"""The synthetic purchase history behind FIFO / LIFO, read lot by lot.

The reference has no purchase history, so it manufactures one from the balance
and the profit fraction (notes/13). Our ladder leaves a few shekels of tax a
month at high profit fractions (`combos2`: cx2_002, 010, 035). This reads the
ladder directly: one person retiring in month 1 with a single 8M withdrawal
portfolio and nothing else, spending 30,000 a month, so every month before 60
sells into the ladder at the flat 25% and `tax / 0.25 / gross` is the gain
fraction of exactly the lots that month sold — newest first under LIFO,
oldest first under FIFO. One thing moves per run: the profit fraction, the
order, the portfolio's return, its fee, and its size.
"""
from scenario import flow, form, pension, portfolio


def household(profit: int, lots: str = "lifo", interest: float = 5.0, fee: float = 0.0,
              balance: int = 8_000_000) -> dict:
    return form(base_problem_max_age=60, incomes=[flow(10_000, "now", "fire")],
                expenses=[flow(30_000)],
                portfolios=[portfolio(balance, interest=interest, fee=fee, profit_pct=profit,
                                      lots=lots, description="W1")],
                pension=pension(0))


SCENARIOS = {f"lt2_lifo_p{p}": household(p) for p in (20, 50, 70, 90)}
SCENARIOS.update({f"lt2_fifo_p{p}": household(p, "fifo") for p in (50, 90)})
SCENARIOS.update({
    "lt2_lifo_p70_r3": household(70, interest=3.0),
    "lt2_lifo_p70_r8": household(70, interest=8.0),
    "lt2_lifo_p70_fee": household(70, fee=0.5),
    "lt2_lifo_p70_big": household(70, balance=24_000_000),
})
