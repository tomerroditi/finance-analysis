"""When each credit card bills, and which bank account pays it.

Israeli cards bill on a fixed day of the month — almost always the 1st, the
2nd or the 10th — and a bill that falls on a Friday, a Saturday or a bank
holiday is charged on the next business day. Both facts matter twice: a
reported charge date has to be read back to the day the card *meant* (a bill
on Sunday the 12th is a 10th-of-the-month card, not a 12th one), and an
estimated one has to be pushed forward the way the bank would push it.

The billing day is per card, not per login: two cards behind one Isracard
login can bill on different days into different bank accounts. And it can
change — a cardholder can move their billing day — so a card's history is a
sequence of (month, day) pairs read off the ``billing_date`` its own rows
carry, never one number. An estimate for a purchase uses the day in force
nearest to the month it was billed in.

A card refund is often not credited on a bill at all but paid straight into
the bank account a few days later; such a refund counts on the day the bank
received it.

Where no row of a card reports a billing date yet, its bills still show in
the bank: the paying account is found by matching the card's monthly totals
against each bank-side ``Credit Cards`` bill stream, and that stream's usual
day stands in for the card's. Isracard and Max do not report the paying
account, so this match is the only source for it.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from itertools import combinations

import pandas as pd
from holidays.countries.israel import Israel

from backend.constants.categories import CREDIT_CARDS
from backend.constants.tables import Tables

#: The days of the month Israeli cards bill on.
NOMINAL_BILLING_DAYS = (1, 2, 10)

#: Billing day assumed for a card nothing else is known about.
DEFAULT_BILLING_DAY = 10

#: A card's cycle closes this many days before its billing day. Fitted on
#: real Isracard data: 10th cards bill purchases up to the 8th the same
#: month, 1st/2nd cards bill the whole previous month.
CYCLE_CLOSE_DAYS = 2

#: Friday and Saturday, as ``date.weekday()`` numbers them.
_WEEKEND = (4, 5)

#: Longest run of closed days a bill can be pushed across (a two-day holiday
#: that meets a weekend).
_MAX_SHIFT_DAYS = 6

#: Bank-side bill dates can trail the card's charge by a posting day.
_BANK_POSTING_LAG_DAYS = 1

#: A month where the card's total and the bill are within this share (plus
#: :data:`_MATCH_SLACK`) of each other counts as a match.
_MATCH_TOLERANCE = 0.25
_MATCH_SLACK = 5.0
#: Months a card and a bill stream must share before they can be paired, and
#: the share of them that must match.
_MATCH_MIN_MONTHS = 3
_MATCH_MIN_SHARE = 0.5
#: How far back the pairing looks, in months.
_MATCH_WINDOW_MONTHS = 18

#: A refund paid straight to the bank arrives within this many days of
#: showing on the card (2–5 days in practice), and covers at most this many
#: refund rows; the candidates searched are capped to keep it cheap.
_DIRECT_REFUND_DAYS = 10
_DIRECT_REFUND_MAX_ROWS = 3
_DIRECT_REFUND_POOL = 12
_AGORA = 0.005
#: How far a batch of foreign-currency refunds may sit from the shekel
#: transfer that repaid it (one card's rate against another's).
_FX_TOLERANCE = 0.02

#: ``(provider, account_name, account_number)`` — one physical card.
CardKey = tuple[str, str, str]
#: ``(provider, account_name, issuer)`` — one bank-side bill stream, the issuer
#: being its description in :func:`issuer_key` form.
StreamKey = tuple[str, str, str]

_SOURCE = "source"
_DATE = "date"
_AMOUNT = "amount"
_BILLING_DATE = "billing_date"


@lru_cache(maxsize=64)
def _bank_holidays(year: int) -> frozenset[date]:
    """Return Israel's public holidays in ``year`` — the days banks close."""
    return frozenset(Israel(years=year))


def is_business_day(day: date) -> bool:
    """Whether Israeli banks charge on ``day`` (not Fri/Sat, not a holiday)."""
    return day.weekday() not in _WEEKEND and day not in _bank_holidays(day.year)


def next_business_day(day: date) -> date:
    """Return ``day`` itself, or the first business day after it."""
    while not is_business_day(day):
        day += timedelta(days=1)
    return day


def charge_date(billing_day: int, month: pd.Period) -> date:
    """Return the day a card billing on ``billing_day`` charges in ``month``.

    Parameters
    ----------
    billing_day : int
        The card's day of the month.
    month : pd.Period
        The billing month.

    Returns
    -------
    date
        That day (the month's last, for a day the month lacks), moved past
        any weekend or holiday.
    """
    day = min(billing_day, month.days_in_month)
    return next_business_day(date(month.year, month.month, day))


def billing_months(purchased: pd.Series, billing_day: int) -> pd.Series:
    """Return the month each purchase is billed in, for a card billing on a day.

    A card's cycle closes :data:`CYCLE_CLOSE_DAYS` before its billing day: a
    purchase up to then is on that month's bill, a later one on next month's.
    So a 10th-of-the-month card bills a purchase from the 5th five days later,
    and a 1st or 2nd card always bills the month after.

    Parameters
    ----------
    purchased : pd.Series
        Purchase dates (datetime).
    billing_day : int
        The card's day of the month.

    Returns
    -------
    pd.Series
        Billing months (Period).
    """
    month = purchased.dt.to_period("M")
    late = purchased.dt.day > billing_day - CYCLE_CLOSE_DAYS
    return month.where(~late, month + 1)


def _subset_summing_to(pool: pd.DataFrame, target: float) -> list[str]:
    """Return the fewest rows of ``pool`` whose amounts make up ``target``.

    Parameters
    ----------
    pool : pd.DataFrame
        Candidate rows, ``_uid`` and ``amount``, most likely first.
    target : float
        The amount to make up.

    Returns
    -------
    list of str
        The rows' ``_uid`` values, or empty when no combination fits.
    """
    rows = list(zip(pool["_uid"], pool[_AMOUNT], strict=True))
    for size in range(1, _DIRECT_REFUND_MAX_ROWS + 1):
        for combo in combinations(rows, size):
            if abs(sum(amount for _, amount in combo) - target) < _AGORA:
                return [uid for uid, _ in combo]
    return []


def _batch_summing_to(window: pd.DataFrame, target: float) -> list[str]:
    """Return one card's refunds of one day that together make up ``target``.

    A batch of refunds — eight cancelled ad charges, say — is paid back as one
    transfer, and when they were charged in a foreign currency the transfer is
    converted at a different rate than the refunds were. So a whole day's
    refunds on one card match within :data:`_FX_TOLERANCE` rather than to the
    agora, the latest such day first.

    Parameters
    ----------
    window : pd.DataFrame
        Candidate refunds with ``_key``, ``_day``, ``_uid`` and ``amount``.
    target : float
        The bank credit.

    Returns
    -------
    list of str
        The batch's ``_uid`` values, or empty when no batch fits.
    """
    for _, batch in window.groupby(["_key", "_day"], sort=False):
        if abs(batch[_AMOUNT].sum() - target) <= target * _FX_TOLERANCE:
            return batch["_uid"].tolist()
    return []


def nominal_billing_day(charged: date, posting_lag: int = 0) -> int:
    """Read the card's own billing day back from a date it was charged on.

    A charge on a usual billing day is that day. Otherwise the date may be a
    usual day pushed past closed days, so the walk goes back over the days
    before it that were closed (and ``posting_lag`` more, for a date the
    bank recorded) and takes the nearest usual day it reaches.

    Parameters
    ----------
    charged : date
        When the bill was charged.
    posting_lag : int, optional
        Extra days a bank may post a bill after the card charged it.

    Returns
    -------
    int
        The card's day of the month.
    """
    if charged.day in NOMINAL_BILLING_DAYS:
        return charged.day
    day = charged - timedelta(days=1)
    lag_left = posting_lag
    for _ in range(_MAX_SHIFT_DAYS + posting_lag):
        if is_business_day(day):
            # An open day would have been charged on, unless the bank only
            # posted the bill late.
            if lag_left == 0:
                break
            lag_left -= 1
        if day.day in NOMINAL_BILLING_DAYS:
            return day.day
        day -= timedelta(days=1)
    return charged.day


_FINAL_LETTERS = str.maketrans("ךםןףץ", "כמנפצ")
_DEBIT_PREFIX = "חיובמ"


def issuer_key(description: object) -> str:
    """Reduce a bank's card-bill description to the issuer it names.

    One issuer's bills reach the bank under several spellings: with and
    without "חיוב מ-", with and without dashes, a card number run into the
    name, and — from an older scraper — the Hebrew stored backwards. Letters
    only, final forms folded, the debit prefix dropped, and the one of the
    string and its reverse that sorts first: every spelling lands on one key.

    Parameters
    ----------
    description : object
        The bank row's description.

    Returns
    -------
    str
        The issuer key.
    """
    letters = "".join(ch for ch in str(description) if ch.isalpha())
    letters = letters.translate(_FINAL_LETTERS)
    if letters.endswith(_DEBIT_PREFIX[::-1]):
        letters = letters[::-1]
    letters = letters.removeprefix(_DEBIT_PREFIX)
    return min(letters, letters[::-1])


def _mode(values: Iterable[int]) -> int | None:
    """Return the most common value (the smallest on a tie), or None when empty."""
    series = pd.Series(list(values), dtype="Int64").dropna()
    if series.empty:
        return None
    return int(series.mode().min())


def card_key(row_provider: object, row_account: object, row_number: object) -> CardKey:
    """Build a :data:`CardKey`, tolerating missing values."""
    return (
        str(row_provider),
        str(row_account),
        "" if pd.isna(row_number) else str(row_number),
    )


@dataclass
class BillingSchedule:
    """Every card's billing day over time, and the bank account paying it.

    Attributes
    ----------
    history : dict
        Card -> ``[(billing month, day), ...]`` in month order, from the
        billing dates the card reported.
    paid_from : dict
        Card -> the bill stream its totals matched.
    stream_days : dict
        Bill stream -> its usual billing day, read off the bank's dates.
    direct_refunds : dict
        Card row (its ``unique_id``) -> the day the bank received it, for a
        refund the issuer paid straight into the bank account rather than
        crediting it on a bill.
    """

    history: dict[CardKey, list[tuple[pd.Period, int]]] = field(default_factory=dict)
    paid_from: dict[CardKey, StreamKey] = field(default_factory=dict)
    stream_days: dict[StreamKey, int] = field(default_factory=dict)
    direct_refunds: dict[str, pd.Timestamp] = field(default_factory=dict)

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> "BillingSchedule":
        """Build the schedule from a frame holding card rows and bank bills.

        Parameters
        ----------
        df : pd.DataFrame
            Transactions with ``source``, ``provider``, ``account_name``,
            ``account_number``, ``date``, ``amount``, ``category`` and, for
            card rows, ``billing_date``.

        Returns
        -------
        BillingSchedule
            The schedule; empty when the frame holds no card rows.
        """
        schedule = cls()
        if df.empty or _SOURCE not in df.columns:
            return schedule
        cards = df[df[_SOURCE] == Tables.CREDIT_CARD.value]
        if cards.empty:
            return schedule
        bills = df[
            (df[_SOURCE] == Tables.BANK.value) & (df["category"] == CREDIT_CARDS)
        ]
        keys = [
            card_key(p, a, n)
            for p, a, n in zip(
                cards["provider"],
                cards["account_name"],
                cards.get("account_number", pd.Series(index=cards.index, dtype=object)),
                strict=True,
            )
        ]
        cards = cards.assign(_key=keys)
        reported = (
            pd.to_datetime(cards[_BILLING_DATE], errors="coerce")
            if _BILLING_DATE in cards.columns
            else pd.Series(pd.NaT, index=cards.index)
        )
        cards = cards.assign(_reported=reported)

        for key, rows in cards[cards["_reported"].notna()].groupby("_key"):
            by_month: dict[pd.Period, list[int]] = {}
            for charged in rows["_reported"].drop_duplicates():
                by_month.setdefault(charged.to_period("M"), []).append(
                    nominal_billing_day(charged.date())
                )
            schedule.history[key] = sorted(
                (month, _mode(days) or DEFAULT_BILLING_DAY)
                for month, days in by_month.items()
            )

        if not bills.empty:
            schedule._match_streams(cards, bills)
            schedule._match_direct_refunds(cards, bills)
        return schedule

    def _match_direct_refunds(self, cards: pd.DataFrame, bills: pd.DataFrame) -> None:
        """Find card refunds the issuer paid straight into a bank account.

        A refund is often not credited on the next bill but transferred to
        the paying account a few days after it shows on the card — a positive
        bank-side ``Credit Cards`` row. Each such credit is matched to the
        card refunds dated in the :data:`_DIRECT_REFUND_DAYS` before it, on
        cards that bank account pays (or whose payer is unknown): up to
        :data:`_DIRECT_REFUND_MAX_ROWS` of them summing to it to the agora,
        or else one card's refunds of one day summing to it within
        :data:`_FX_TOLERANCE`.
        """
        if "unique_id" not in cards.columns:
            return
        credits = bills[bills[_AMOUNT] > 0]
        credits = credits.assign(_day=pd.to_datetime(credits[_DATE], errors="coerce"))
        credits = credits.dropna(subset=["_day"]).sort_values("_day")
        refunds = cards[cards[_AMOUNT] > 0]
        refunds = refunds.assign(
            _day=pd.to_datetime(refunds[_DATE], errors="coerce"),
            _uid=refunds["unique_id"].astype(str),
        )
        refunds = refunds.dropna(subset=["_day"])
        if credits.empty or refunds.empty:
            return
        payer = {key: stream[:2] for key, stream in self.paid_from.items()}
        refunds = refunds.assign(_payer=refunds["_key"].map(payer))
        for _, credit in credits.iterrows():
            bank = (str(credit["provider"]), str(credit["account_name"]))
            window = refunds[
                (refunds["_day"] <= credit["_day"])
                & (
                    refunds["_day"]
                    >= credit["_day"] - timedelta(days=_DIRECT_REFUND_DAYS)
                )
                & ~refunds["_uid"].isin(self.direct_refunds)
                & refunds["_payer"].map(lambda p, b=bank: pd.isna(p) or p == b)
            ].sort_values("_day", ascending=False)
            target = float(credit[_AMOUNT])
            match = _subset_summing_to(
                window[["_uid", _AMOUNT]].head(_DIRECT_REFUND_POOL), target
            ) or _batch_summing_to(window, target)
            for uid in match:
                self.direct_refunds[uid] = credit["_day"]

    def _match_streams(self, cards: pd.DataFrame, bills: pd.DataFrame) -> None:
        """Pair each card with the bill stream its monthly totals follow."""
        bill_dates = pd.to_datetime(bills[_DATE], errors="coerce")
        bills = bills.assign(
            _stream=list(
                zip(
                    bills["provider"].astype(str),
                    bills["account_name"].astype(str),
                    bills["description"].map(issuer_key),
                    strict=True,
                )
            ),
            _month=bill_dates.dt.to_period("M"),
            _day=bill_dates,
        ).dropna(subset=["_day"])
        for stream, rows in bills.groupby("_stream"):
            day = _mode(
                nominal_billing_day(d.date(), _BANK_POSTING_LAG_DAYS)
                for d in rows["_day"]
            )
            if day is not None:
                self.stream_days[stream] = day
        stream_totals = {
            stream: rows.groupby("_month")[_AMOUNT].sum()
            for stream, rows in bills.groupby("_stream")
        }

        purchased = pd.to_datetime(cards[_DATE], errors="coerce")
        cards = cards.assign(_purchased=purchased).dropna(subset=["_purchased"])
        latest = bills["_month"].max()
        first = latest - _MATCH_WINDOW_MONTHS
        for key, rows in cards.groupby("_key"):
            reported_day = self.history[key][-1][1] if key in self.history else None
            best: tuple[float, int, StreamKey] | None = None
            for stream, bill_totals in stream_totals.items():
                # Paid from this stream, the card bills on its day: bucket the
                # purchases into the bills they would have landed on.
                day = reported_day or self.stream_days.get(stream, DEFAULT_BILLING_DAY)
                month = (
                    rows["_reported"]
                    .dt.to_period("M")
                    .fillna(billing_months(rows["_purchased"], day))
                )
                totals = rows.groupby(month)[_AMOUNT].sum()
                totals = totals[(totals.index > first) & (totals.index <= latest)]
                both = pd.concat([totals, bill_totals], axis=1, keys=["card", "bill"])
                both = both.dropna()
                both = both[both["card"] != 0]
                if len(both) < _MATCH_MIN_MONTHS:
                    continue
                gap = (both["card"] - both["bill"]).abs()
                share = float(
                    (gap <= both["card"].abs() * _MATCH_TOLERANCE + _MATCH_SLACK).mean()
                )
                candidate = (share, len(both), stream)
                if share >= _MATCH_MIN_SHARE and (
                    best is None or candidate[:2] > best[:2]
                ):
                    best = candidate
            if best is not None:
                self.paid_from[key] = best[2]

    def day_for(self, key: CardKey, month: pd.Period) -> tuple[int, str]:
        """Return a card's billing day for ``month``, and where it came from.

        Parameters
        ----------
        key : CardKey
            The card.
        month : pd.Period
            The billing month asked about.

        Returns
        -------
        tuple of (int, str)
            The day, and ``"reported"`` (the card's own dates, from the
            month nearest ``month``; an earlier one on a tie), ``"bills"``
            (the paying bill stream's usual day) or ``"default"``.
        """
        history = self.history.get(key)
        if history:
            nearest = min(history, key=lambda item: (abs((item[0] - month).n), item[0]))
            return nearest[1], "reported"
        stream = self.paid_from.get(key)
        if stream is not None and stream in self.stream_days:
            return self.stream_days[stream], "bills"
        return DEFAULT_BILLING_DAY, "default"

    def changes(self, key: CardKey) -> list[dict[str, object]]:
        """Return a card's billing day as consecutive runs, oldest first.

        Returns
        -------
        list of dict
            ``{"day", "from", "to"}`` with months as ``YYYY-MM``.
        """
        runs: list[dict[str, object]] = []
        for month, day in self.history.get(key, []):
            if runs and runs[-1]["day"] == day:
                runs[-1]["to"] = str(month)
            else:
                runs.append({"day": day, "from": str(month), "to": str(month)})
        return runs
