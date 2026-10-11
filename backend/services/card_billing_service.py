"""Each connected card's billing day and paying bank account, for display.

The schedule itself is worked out in ``backend.services.card_billing``; this
service reads the transactions it needs and shapes it per login and card.
"""

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.repositories.transactions import TransactionsRepository
from backend.services.card_billing import BillingSchedule, card_key, charge_date

#: A card with no purchase in this many months is no longer in use.
_ACTIVE_MONTHS = 6


class CardBillingService:
    """Billing day, its history and the paying account of every card."""

    def __init__(self, db: Session) -> None:
        """Initialize the service with a database session.

        Parameters
        ----------
        db : Session
            SQLAlchemy session.
        """
        self.repo = TransactionsRepository(db)

    def get_all(self, today: date | None = None) -> list[dict[str, Any]]:
        """Return each card login's cards with when they bill and who pays.

        Parameters
        ----------
        today : date, optional
            Defaults to today.

        Returns
        -------
        list of dict
            ``{"provider", "account_name", "cards": [...]}`` per login. Each
            card is ``{"account_number", "billing_day", "billing_day_source"
            ("reported" / "bills" / "default"), "next_billing_date"
            (``YYYY-MM-DD``), "changes" ([{"day", "from", "to"}] from the
            card's reported dates), "paid_from" ({"provider",
            "account_name"} or None)}``. Only cards used in the last
            :data:`_ACTIVE_MONTHS` months are listed.
        """
        today = today or date.today()
        df = self.repo.get_table(exclude_services=[Tables.INSURANCE.value])
        if df.empty:
            return []
        cards = df[df["source"] == Tables.CREDIT_CARD.value]
        if cards.empty:
            return []
        schedule = BillingSchedule.from_frame(df)
        this_month = pd.Period(today, "M")
        cutoff = (this_month - _ACTIVE_MONTHS).start_time
        purchased = pd.to_datetime(cards["date"], errors="coerce")
        cards = cards.assign(_purchased=purchased)

        logins: dict[tuple[str, str], list[dict[str, Any]]] = {}
        numbers = cards.get("account_number", pd.Series(None, index=cards.index))
        cards = cards.assign(
            _key=[
                card_key(p, a, n)
                for p, a, n in zip(
                    cards["provider"], cards["account_name"], numbers, strict=True
                )
            ]
        )
        for key, rows in cards.groupby("_key", sort=True):
            if rows["_purchased"].max() < cutoff:
                continue
            provider, account_name, number = key
            day, source = schedule.day_for(key, this_month)
            next_charge = charge_date(day, this_month)
            if next_charge < today:
                next_month = this_month + 1
                day_next, _ = schedule.day_for(key, next_month)
                next_charge = charge_date(day_next, next_month)
            stream = schedule.paid_from.get(key)
            logins.setdefault((provider, account_name), []).append(
                {
                    "account_number": number,
                    "billing_day": day,
                    "billing_day_source": source,
                    "next_billing_date": next_charge.isoformat(),
                    "changes": schedule.changes(key),
                    "paid_from": (
                        {"provider": stream[0], "account_name": stream[1]}
                        if stream
                        else None
                    ),
                }
            )
        return [
            {"provider": provider, "account_name": account_name, "cards": entries}
            for (provider, account_name), entries in sorted(logins.items())
        ]
