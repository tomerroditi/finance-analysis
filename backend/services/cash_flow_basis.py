"""The two ways the dashboard can count the same income and spending.

Both bases count card purchases one by one — never the bank-side bill that
pays for them, which would count them twice and hide their categories — and
both leave out ``Ignore`` transfers and Prior Wealth. They differ in *when*
money counts and in what a refund is:

- **Net cost** (``net_cost``, the default): what things cost. A purchase
  counts on the day it was made, and a refund matched to a purchase comes off
  that purchase, in the purchase's month; an unmatched one comes off the
  spending of the category it landed in.
- **Cash flow** (``cash_flow``): money as it moved. A card purchase counts on
  the day the card company charged it to the bank — so a month's card
  spending is that month's bills, split by what the bills paid for — and one
  not charged yet does not count at all. A refund is income on the day it
  arrived, and every purchase counts at its full price.

A card row's charge day is its ``billing_date`` as the card's site reported
it. Rows scraped before that was kept have none until a scrape sees them
again; they are estimated as the card's usual billing day in the month after
the purchase, which is how Israeli cards bill (an instalment row is already
dated in its own month by the scraper).
"""

from datetime import date
from typing import Literal

import pandas as pd

from backend.constants.categories import NON_EXPENSE_CATEGORIES
from backend.constants.tables import Tables

Basis = Literal["net_cost", "cash_flow"]
BASIS_NET_COST: Basis = "net_cost"
BASIS_CASH_FLOW: Basis = "cash_flow"

#: Label the income breakdown gives refunds on the cash-flow basis.
REFUNDS_SOURCE_LABEL = "Refunds"

#: Billing day assumed for a card none of whose rows reports one yet.
DEFAULT_BILLING_DAY = 10

_BILLING_DATE = "billing_date"


def refund_mask(df: pd.DataFrame) -> pd.Series:
    """Return the rows that are money coming back on spending.

    A positive amount in an expense category — anything outside
    ``NON_EXPENSE_CATEGORIES``, uncategorised rows included.

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame with ``category`` and ``amount``.

    Returns
    -------
    pd.Series
        Boolean Series aligned with ``df``.
    """
    return (df["amount"] > 0) & ~df["category"].isin(NON_EXPENSE_CATEGORIES)


def date_cards_by_billing(df: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Move each card row to the day it was charged to the bank.

    Rows of other sources are untouched. A card row charged after ``today``
    has not left the bank yet and is dropped.

    Parameters
    ----------
    df : pd.DataFrame
        Transactions frame with ``source`` and ``date`` (``YYYY-MM-DD``), and
        ``billing_date`` when card rows are present.
    today : date, optional
        The cut-off for charges still to come. Defaults to today.

    Returns
    -------
    pd.DataFrame
        A copy with card rows re-dated.
    """
    is_card = df["source"] == Tables.CREDIT_CARD.value
    if not is_card.any():
        return df
    df = df.copy()
    cards = df.loc[is_card]
    reported = (
        pd.to_datetime(cards[_BILLING_DATE], errors="coerce")
        if _BILLING_DATE in cards.columns
        else pd.Series(pd.NaT, index=cards.index)
    )
    charged = reported.fillna(_estimated_billing(cards, reported))
    df.loc[is_card, "date"] = charged.dt.strftime("%Y-%m-%d").fillna(cards["date"])
    not_charged = pd.Series(False, index=df.index)
    not_charged.loc[is_card] = charged > pd.Timestamp(today or date.today())
    return df[~not_charged]


def _estimated_billing(cards: pd.DataFrame, reported: pd.Series) -> pd.Series:
    """Estimate each card row's charge day from its card's usual billing day.

    Parameters
    ----------
    cards : pd.DataFrame
        Card rows, with ``provider``, ``account_name`` and ``date``.
    reported : pd.Series
        The billing dates the card reported (``NaT`` where none).

    Returns
    -------
    pd.Series
        The card's billing day in the month after each purchase.
    """
    account = cards["provider"].astype(str) + "\x1f" + cards["account_name"].astype(str)
    days = reported.dt.day.groupby(account).agg(
        lambda s: int(s.mode().iloc[0]) if s.notna().any() else DEFAULT_BILLING_DAY
    )
    billing_day = account.map(days).fillna(DEFAULT_BILLING_DAY).astype(int)
    purchased = pd.to_datetime(cards["date"], errors="coerce")
    next_month = (purchased.dt.to_period("M") + 1).dt.to_timestamp()
    day = billing_day.clip(upper=next_month.dt.days_in_month)
    return next_month + pd.to_timedelta(day - 1, unit="D")
