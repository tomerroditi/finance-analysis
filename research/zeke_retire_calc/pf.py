"""Helpers for the portfolio-tax probes (notes/03)."""
import sys
sys.path.insert(0, '.')
import probe

PTYPES = ["portfolio", "ibkr", "gemel", "polisa", "kaspit", "pikadon"]


def prow(i, typ="portfolio", bal=0, dep="", goal=0, interest="5.0", fee="0.1",
         profit="0.0", desig="withdraw", lot="flat", desc=None):
    return {
        f"portfolioDesignation{i}": desig,
        f"portfolio_type{i}": typ,
        f"portfolioBalance{i}": str(bal),
        f"portfolio_deposit{i}": str(dep),
        f"portfolio_goal{i}": str(goal),
        f"portfolioInterest{i}": str(interest),
        f"portfolioFee{i}": str(fee),
        f"portfolioProfitFraction{i}": str(profit),
        f"portfolio_fifo_lifo{i}": lot,
        f"portfolioDescription{i}": desc if desc is not None else f"P{i}-{typ}",
    }


def build(rows, **extra):
    ov = dict(probe.BASE)
    for k in list(ov):
        if k.startswith("portfolio"):
            del ov[k]
    ov["num_portfolio_fields"] = str(len(rows))
    for n, r in enumerate(rows, 1):
        ov.update({k.replace("@", str(n)): v for k, v in r.items()})
    ov.update({k: str(v) for k, v in extra.items()})
    return ov
