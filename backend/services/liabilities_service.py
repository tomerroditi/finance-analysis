"""
Liabilities service with amortization calculation and payment tracking.

This module provides business logic for liability (loan/debt) tracking
and analysis, including amortization schedule generation for the
supported Israeli loan types (fixed, prime-linked, variable) and
payment structures (Shpitzer, equal principal, balloon), and payment
comparison against actual transactions.
"""

from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import LIABILITIES_CATEGORY
from backend.constants.loans import (
    AmortizationMethod,
    LoanType,
    PRIME_BASED_LOAN_TYPES,
)
from backend.constants.tables import LiabilityTransactionsTableFields as LTF
from backend.constants.tables import Tables
from backend.errors import ValidationException
from backend.repositories.liabilities_repository import LiabilitiesRepository
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.rates_service import RatesService


def _optional_number(value: Any) -> Optional[float]:
    """Normalize a possibly-NaN DataFrame value to ``float`` or ``None``."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value)


class LiabilitiesService:
    """
    Service for managing liabilities with business logic for amortization
    calculations, payment tracking, and loan lifecycle management.
    """

    def __init__(self, db: Session):
        """
        Initialize the liabilities service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.liabilities_repo = LiabilitiesRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.rates_service = RatesService(db)

    def _get_liability_category_transactions(self) -> pd.DataFrame:
        """
        Fetch all transactions in the Liabilities category.

        Returns
        -------
        pd.DataFrame
            Filtered transactions, or an empty DataFrame if none exist.
        """
        all_txns = self.transactions_repo.get_table()
        if all_txns.empty:
            return pd.DataFrame()
        return all_txns[all_txns["category"] == LIABILITIES_CATEGORY].copy()

    def get_all_liabilities(self, include_paid_off: bool = False) -> List[Dict[str, Any]]:
        """
        Get all liabilities as a list of dicts with calculated fields.

        Fetches all liability transactions once and enriches each liability
        record with amortization-based calculations.

        Parameters
        ----------
        include_paid_off : bool, optional
            When ``True``, paid-off liabilities are included. Default is ``False``.

        Returns
        -------
        list[dict]
            Liability records enriched with ``monthly_payment``,
            ``total_interest``, ``remaining_balance``, ``total_paid``,
            ``percent_paid``, and ``current_rate``.
        """
        df = self.liabilities_repo.get_all_liabilities(include_paid_off=include_paid_off)
        if df.empty:
            return []

        liab_txns = self._get_liability_category_transactions()

        records = df.to_dict(orient="records")
        for record in records:
            self._enrich_with_calculations(record, liab_txns)

        return records

    def get_liability(self, liability_id: int) -> Dict[str, Any]:
        """
        Get a single liability by ID with calculated fields.

        Parameters
        ----------
        liability_id : int
            ID of the liability to retrieve.

        Returns
        -------
        dict
            Liability record enriched with amortization-based calculations.
        """
        df = self.liabilities_repo.get_by_id(liability_id)
        liab_txns = self._get_liability_category_transactions()

        record = df.iloc[0].to_dict()
        self._enrich_with_calculations(record, liab_txns)
        return record

    def create_liability(
        self,
        name: str,
        tag: str,
        principal_amount: float,
        term_months: int,
        start_date: str,
        interest_rate: Optional[float] = None,
        loan_type: str = LoanType.FIXED_UNLINKED.value,
        amortization_method: str = AmortizationMethod.SHPITZER.value,
        rate_spread: Optional[float] = None,
        rate_reset_months: Optional[int] = None,
        lender: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Create a new liability record.

        The tag must already exist in the Liabilities category (selected
        by the user from existing tags that represent loans).

        Parameters
        ----------
        name : str
            Human-readable name for the liability.
        tag : str
            Tag identifying this specific liability.
        principal_amount : float
            Original loan amount.
        term_months : int
            Loan duration in months.
        start_date : str
            Date the loan was taken, in ``YYYY-MM-DD`` format.
        interest_rate : float, optional
            Annual interest rate as a percentage. Required for fixed-rate
            loans; for prime-based loans it is derived from the current
            prime rate plus ``rate_spread`` when omitted.
        loan_type : str, optional
            One of :class:`backend.constants.loans.LoanType` values.
        amortization_method : str, optional
            One of :class:`backend.constants.loans.AmortizationMethod` values.
        rate_spread : float, optional
            Spread over prime in percentage points — required for
            prime-based loan types, may be negative.
        rate_reset_months : int, optional
            Months between rate resets — required for variable loans.
        lender : str, optional
            Name of the lending institution.
        notes : str, optional
            Free-text notes about the liability.

        Raises
        ------
        ValidationException
            When the loan-type combination is invalid.
        """
        valid_types = {t.value for t in LoanType}
        if loan_type not in valid_types:
            raise ValidationException(f"Unknown loan type: {loan_type}")
        valid_methods = {m.value for m in AmortizationMethod}
        if amortization_method not in valid_methods:
            raise ValidationException(
                f"Unknown amortization method: {amortization_method}"
            )

        if loan_type in PRIME_BASED_LOAN_TYPES:
            if rate_spread is None:
                raise ValidationException(
                    "rate_spread is required for prime-based loan types"
                )
            if loan_type == LoanType.VARIABLE_UNLINKED.value and (
                rate_reset_months is None or rate_reset_months < 1
            ):
                raise ValidationException(
                    "rate_reset_months (>= 1) is required for variable loans"
                )
            if interest_rate is None:
                prime = self.rates_service.get_prime_at(start_date)
                interest_rate = round((prime or 0.0) + rate_spread, 4)
        elif interest_rate is None:
            raise ValidationException(
                "interest_rate is required for fixed-rate loans"
            )

        self.liabilities_repo.create_liability(
            name=name,
            tag=tag,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            start_date=start_date,
            loan_type=loan_type,
            amortization_method=amortization_method,
            rate_spread=rate_spread,
            rate_reset_months=rate_reset_months,
            lender=lender,
            notes=notes,
        )

    def update_liability(self, liability_id: int, **fields) -> None:
        """
        Update a liability record.

        Parameters
        ----------
        liability_id : int
            ID of the liability to update.
        **fields
            Field names and new values forwarded to the repository.
        """
        self.liabilities_repo.update_liability(liability_id, **fields)

    def mark_paid_off(self, liability_id: int, paid_off_date: str) -> None:
        """
        Mark a liability as paid off.

        Parameters
        ----------
        liability_id : int
            ID of the liability to mark as paid off.
        paid_off_date : str
            Date the liability was paid off, in ``YYYY-MM-DD`` format.
        """
        self.liabilities_repo.mark_paid_off(liability_id, paid_off_date)

    def reopen(self, liability_id: int) -> None:
        """
        Reopen a paid-off liability.

        Parameters
        ----------
        liability_id : int
            ID of the liability to reopen.
        """
        self.liabilities_repo.reopen(liability_id)

    def delete_liability(self, liability_id: int) -> None:
        """
        Delete a liability record.

        Parameters
        ----------
        liability_id : int
            ID of the liability to delete.
        """
        self.liabilities_repo.delete_liability(liability_id)

    def get_liability_analysis(self, liability_id: int) -> Dict[str, Any]:
        """
        Get detailed analysis for a liability.

        Returns an amortization schedule, transaction history, actual-vs-expected
        payment comparison, and summary totals.

        Parameters
        ----------
        liability_id : int
            ID of the liability to analyse.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``schedule`` – list of amortization schedule entries.
            - ``transactions`` – list of matched transaction dicts.
            - ``actual_vs_expected`` – list of monthly payment comparison dicts.
            - ``summary`` – dict with payment/interest totals and progress.
        """
        record = self.get_liability(liability_id)
        transactions = self.get_liability_transactions(liability_id)

        schedule = self._schedule_for_record(record)

        actual_vs_expected = self._compare_actual_vs_expected(schedule, transactions)

        receipts = [t for t in transactions if t["amount"] > 0]
        payments = [t for t in transactions if t["amount"] < 0]
        total_receipts = sum(t["amount"] for t in receipts)
        total_payments = sum(abs(t["amount"]) for t in payments)

        num_payments = min(len(payments), len(schedule))
        remaining_balance = (
            schedule[num_payments - 1]["remaining_balance"]
            if num_payments > 0
            else record["principal_amount"]
        )

        # Interest split: already paid vs projected remaining
        interest_paid = sum(e["interest_portion"] for e in schedule[:num_payments])
        interest_remaining = sum(e["interest_portion"] for e in schedule[num_payments:])
        total_interest_cost = interest_paid + interest_remaining

        # Next due payment (varies over the schedule for non-fixed loans)
        monthly_payment = (
            schedule[min(num_payments, len(schedule) - 1)]["payment"]
            if schedule
            else 0.0
        )

        total_cost = sum(e["payment"] for e in schedule)
        percent_paid = (total_payments / total_cost * 100) if total_cost > 0 else 0.0

        summary = {
            "total_receipts": total_receipts,
            "total_payments": total_payments,
            "total_interest_cost": total_interest_cost,
            "interest_paid": interest_paid,
            "interest_remaining": interest_remaining,
            "monthly_payment": monthly_payment,
            "remaining_balance": remaining_balance,
            "percent_paid": round(percent_paid, 2),
            "payments_made": len(payments),
        }

        return {
            "schedule": schedule,
            "transactions": transactions,
            "actual_vs_expected": actual_vs_expected,
            "summary": summary,
        }

    def detect_tag_transactions(self, tag: str) -> Dict[str, Any]:
        """
        Detect existing transactions for a liability tag.

        Looks for transactions with ``category == LIABILITIES_CATEGORY``
        and the given tag. Returns the receipt (first positive transaction)
        info and a list of all payment transactions.

        Parameters
        ----------
        tag : str
            The liability tag to search for.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``receipt`` – dict with ``date`` and ``amount`` of the first
              positive transaction, or ``None`` if not found.
            - ``payments`` – list of payment dicts (negative transactions)
              with ``date`` and ``amount``.
            - ``has_receipt`` – bool indicating if a receipt was found.
        """
        liab_txns = self._get_liability_category_transactions()
        if liab_txns.empty:
            return {"receipt": None, "payments": [], "has_receipt": False}

        matched = liab_txns[liab_txns["tag"] == tag].copy()

        if matched.empty:
            return {"receipt": None, "payments": [], "has_receipt": False}

        matched["amount"] = pd.to_numeric(matched["amount"], errors="coerce").fillna(0.0)
        matched = matched.sort_values("date")

        positive = matched[matched["amount"] > 0]
        negative = matched[matched["amount"] < 0]

        receipt = None
        if not positive.empty:
            first = positive.iloc[0]
            receipt = {"date": str(first["date"]), "amount": float(first["amount"])}

        payments = [
            {"date": str(row["date"]), "amount": float(row["amount"])}
            for _, row in negative.iterrows()
        ]

        return {
            "receipt": receipt,
            "payments": payments,
            "has_receipt": receipt is not None,
        }

    def get_liability_transactions(
        self, liability_id: int, tag: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all transactions associated with a liability.

        Fetches the liability's tag (unless provided), then filters all
        transactions by ``category == LIABILITIES_CATEGORY`` and matching tag,
        and also includes auto-generated liability transactions. Sorted by date.

        Parameters
        ----------
        liability_id : int
            ID of the liability.
        tag : str, optional
            Tag to filter by. If not provided, fetched from the liability record.

        Returns
        -------
        list[dict]
            Matching transactions sorted by date ascending.
        """
        if tag is None:
            record_df = self.liabilities_repo.get_by_id(liability_id)
            tag = record_df.iloc[0]["tag"]

        # Real transactions from bank/CC/cash tables
        liab_txns = self._get_liability_category_transactions()
        frames = []
        if not liab_txns.empty:
            matched = liab_txns[liab_txns["tag"] == tag].copy()
            if not matched.empty:
                matched["amount"] = pd.to_numeric(matched["amount"], errors="coerce").fillna(0.0)
                frames.append(matched)

        # Auto-generated liability transactions
        gen_txns = self.liabilities_repo.get_liability_transactions(liability_id)
        if gen_txns:
            gen_df = pd.DataFrame([
                {LTF.DATE.value: t.date, LTF.AMOUNT.value: t.amount,
                 LTF.DESCRIPTION.value: t.description,
                 "source": Tables.LIABILITY_TRANSACTIONS.value,
                 "category": LIABILITIES_CATEGORY, "tag": tag,
                 LTF.PAYMENT_NUMBER.value: t.payment_number}
                for t in gen_txns
            ])
            frames.append(gen_df)

        if not frames:
            return []

        combined = pd.concat(frames, ignore_index=True).sort_values("date")
        combined = combined.where(pd.notnull(combined), None)
        return combined.to_dict(orient="records")

    @staticmethod
    def _payment_date(start_date: date, months_ahead: int) -> date:
        """Get the payment date ``months_ahead`` months after ``start_date``.

        Day-of-month is clamped to 28 so every month has a valid date.

        Parameters
        ----------
        start_date : date
            Loan start date.
        months_ahead : int
            Number of months to advance.

        Returns
        -------
        date
            The resulting payment date.
        """
        safe_day = min(start_date.day, 28)
        month = start_date.month + months_ahead
        year = start_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        return date(year, month, safe_day)

    @staticmethod
    def _annuity_payment(balance: float, monthly_rate: float, months: int) -> float:
        """Compute the constant annuity payment for the remaining loan.

        Parameters
        ----------
        balance : float
            Outstanding principal.
        monthly_rate : float
            Monthly interest rate as a fraction (annual% / 100 / 12).
        months : int
            Remaining number of payments.

        Returns
        -------
        float
            The per-period payment amount.
        """
        if months <= 0:
            return balance
        if monthly_rate == 0:
            return balance / months
        factor = (1 + monthly_rate) ** months
        return balance * monthly_rate * factor / (factor - 1)

    @staticmethod
    def calculate_amortization_schedule(
        principal: float,
        annual_rate: float,
        term_months: int,
        start_date: date,
        amortization_method: str = AmortizationMethod.SHPITZER.value,
        rate_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calculate an amortization schedule.

        Supports the three Israeli payment structures and, through
        ``rate_steps``, loans whose rate changes over time (prime-linked
        and variable loans). When the rate changes mid-loan, Shpitzer
        payments are re-amortized over the remaining term at the new
        rate — the standard Israeli bank behavior.

        Parameters
        ----------
        principal : float
            Original loan amount.
        annual_rate : float
            Annual interest rate as a percentage (e.g. ``6.0`` for 6%).
            Used for the whole term when ``rate_steps`` is not given.
        term_months : int
            Total number of monthly payments.
        start_date : date
            Loan start date (first payment lands one month later).
        amortization_method : str, optional
            One of :class:`backend.constants.loans.AmortizationMethod`
            values. Defaults to Shpitzer (annuity).
        rate_steps : list[dict], optional
            Piecewise-constant annual rate curve — dicts with ``date``
            (YYYY-MM-DD) and ``value`` (percent), ascending. Each payment
            uses the rate in effect at the start of its interest period
            (the previous payment date), so a reset dated exactly N
            months after origination first affects payment N+1.

        Returns
        -------
        list[dict]
            List of ``term_months`` dicts with keys:

            - ``payment_number`` – 1-indexed payment number.
            - ``date`` – payment date string in ``YYYY-MM-DD`` format.
            - ``payment`` – total payment amount.
            - ``principal_portion`` – portion reducing the principal.
            - ``interest_portion`` – interest component.
            - ``remaining_balance`` – outstanding balance after this payment.
            - ``annual_rate`` – annual rate applied to this payment (%).
        """
        schedule: List[Dict[str, Any]] = []
        balance = principal
        current_rate: Optional[float] = None
        payment = 0.0
        fixed_principal_portion = principal / term_months if term_months else 0.0

        for i in range(1, term_months + 1):
            payment_date = LiabilitiesService._payment_date(start_date, i)
            date_str = payment_date.strftime("%Y-%m-%d")
            period_start_str = LiabilitiesService._payment_date(
                start_date, i - 1
            ).strftime("%Y-%m-%d")

            rate = annual_rate
            if rate_steps:
                for step in rate_steps:
                    if step["date"] <= period_start_str:
                        rate = step["value"]
                    else:
                        break
            monthly_rate = rate / 100.0 / 12.0

            interest_portion = balance * monthly_rate

            if amortization_method == AmortizationMethod.EQUAL_PRINCIPAL.value:
                principal_portion = min(fixed_principal_portion, balance)
                payment = principal_portion + interest_portion
            elif amortization_method == AmortizationMethod.BALLOON.value:
                principal_portion = balance if i == term_months else 0.0
                payment = interest_portion + principal_portion
            else:  # Shpitzer — re-amortize whenever the rate changes
                if current_rate is None or rate != current_rate:
                    remaining_months = term_months - i + 1
                    payment = LiabilitiesService._annuity_payment(
                        balance, monthly_rate, remaining_months
                    )
                    current_rate = rate
                principal_portion = payment - interest_portion
                if i == term_months or principal_portion > balance:
                    principal_portion = balance
                    payment = principal_portion + interest_portion

            balance = max(balance - principal_portion, 0.0)

            schedule.append({
                "payment_number": i,
                "date": date_str,
                "payment": round(payment, 2),
                "principal_portion": round(principal_portion, 2),
                "interest_portion": round(interest_portion, 2),
                "remaining_balance": round(balance, 2),
                "annual_rate": round(rate, 4),
            })

        return schedule

    def _get_rate_steps(self, record: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Build the piecewise annual-rate curve for a liability record.

        Fixed-rate loans return ``None`` (flat ``interest_rate`` applies).
        Prime-linked loans track every prime change plus their spread.
        Variable loans sample prime + spread only at their reset dates.
        When the rate series is empty, returns ``None`` so callers fall
        back to the stored flat rate.

        Parameters
        ----------
        record : dict
            Liability record (raw DB fields).

        Returns
        -------
        list[dict] or None
            Rate steps with ``date`` and ``value``, or ``None`` for a
            flat-rate schedule.
        """
        loan_type = record.get("loan_type") or LoanType.FIXED_UNLINKED.value
        if loan_type not in PRIME_BASED_LOAN_TYPES:
            return None

        start_date_str = str(record["start_date"])
        spread = _optional_number(record.get("rate_spread")) or 0.0
        prime_steps = self.rates_service.get_prime_steps(start_date_str)
        if not prime_steps:
            return None

        if loan_type == LoanType.PRIME_LINKED.value:
            return [
                {"date": s["date"], "value": round(s["value"] + spread, 4)}
                for s in prime_steps
            ]

        # Variable: rate locks at each reset date until the next reset.
        reset_months = int(
            _optional_number(record.get("rate_reset_months")) or 12
        )
        start = date.fromisoformat(start_date_str)
        term_months = int(record["term_months"])
        steps = []
        for offset in range(0, term_months, reset_months):
            reset_date = self._payment_date(start, offset).strftime("%Y-%m-%d")
            prime = None
            for s in prime_steps:
                if s["date"] <= reset_date:
                    prime = s["value"]
                else:
                    break
            if prime is None:
                prime = prime_steps[0]["value"]
            steps.append({"date": reset_date, "value": round(prime + spread, 4)})
        return steps

    def _schedule_for_record(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build the amortization schedule for a liability record.

        Parameters
        ----------
        record : dict
            Liability record (raw DB fields).

        Returns
        -------
        list[dict]
            Schedule entries from :meth:`calculate_amortization_schedule`.
        """
        return self.calculate_amortization_schedule(
            principal=record["principal_amount"],
            annual_rate=_optional_number(record.get("interest_rate")) or 0.0,
            term_months=int(record["term_months"]),
            start_date=date.fromisoformat(str(record["start_date"])),
            amortization_method=record.get("amortization_method")
            or AmortizationMethod.SHPITZER.value,
            rate_steps=self._get_rate_steps(record),
        )

    def _enrich_with_calculations(
        self, record: Dict[str, Any], liab_txns: pd.DataFrame
    ) -> None:
        """
        Enrich a liability record with amortization-based calculated fields.

        Modifies ``record`` in-place to add ``monthly_payment``,
        ``total_interest``, ``remaining_balance``, ``total_paid``,
        ``percent_paid``, ``payments_made``, and ``current_rate``.

        The remaining balance is read off the amortization schedule at
        the position of the last payment made, so interest portions are
        not counted as principal reduction.

        Parameters
        ----------
        record : dict
            Liability record dict to enrich (modified in-place).
        liab_txns : pd.DataFrame
            All transactions with ``category == LIABILITIES_CATEGORY``.
        """
        record["loan_type"] = record.get("loan_type") or LoanType.FIXED_UNLINKED.value
        record["amortization_method"] = (
            record.get("amortization_method") or AmortizationMethod.SHPITZER.value
        )
        record["rate_spread"] = _optional_number(record.get("rate_spread"))
        reset_months = _optional_number(record.get("rate_reset_months"))
        record["rate_reset_months"] = int(reset_months) if reset_months else None

        principal = record["principal_amount"]
        schedule = self._schedule_for_record(record)

        total_interest = round(sum(e["interest_portion"] for e in schedule), 2)
        total_cost = sum(e["payment"] for e in schedule)

        tag = record.get("tag", "")
        if not liab_txns.empty and tag:
            tag_txns = liab_txns[liab_txns["tag"] == tag].copy()
            tag_txns["amount"] = pd.to_numeric(tag_txns["amount"], errors="coerce").fillna(0.0)
            payments = tag_txns[tag_txns["amount"] < 0]
            total_paid = float(abs(payments["amount"].sum()))
            payment_count = len(payments)
        else:
            total_paid = 0.0
            payment_count = 0

        schedule_pos = min(payment_count, len(schedule))
        remaining_balance = (
            schedule[schedule_pos - 1]["remaining_balance"]
            if schedule_pos > 0
            else principal
        )

        # Next due payment (varies over the schedule for non-fixed loans)
        monthly_payment = (
            schedule[min(schedule_pos, len(schedule) - 1)]["payment"]
            if schedule
            else 0.0
        )

        # Effective annual rate today (last schedule entry not in the future)
        today_str = date.today().strftime("%Y-%m-%d")
        current_rate = _optional_number(record.get("interest_rate")) or 0.0
        for entry in schedule:
            if entry["date"] <= today_str:
                current_rate = entry["annual_rate"]
            else:
                break

        percent_paid = (total_paid / total_cost * 100) if total_cost > 0 else 0.0

        record["monthly_payment"] = round(monthly_payment, 2)
        record["total_interest"] = total_interest
        record["remaining_balance"] = round(remaining_balance, 2)
        record["total_paid"] = round(total_paid, 2)
        record["percent_paid"] = round(percent_paid, 2)
        record["payments_made"] = payment_count
        record["current_rate"] = round(current_rate, 4)

    def get_debt_over_time(self) -> Dict[str, Any]:
        """Get debt-over-time data for all active liabilities using actual transactions.

        Returns a time series per liability showing the remaining balance after
        each actual payment, plus a total line across all liabilities. The
        balance after the k-th payment is read off the amortization schedule,
        so interest portions are not counted as principal reduction.

        Returns
        -------
        dict
            Dictionary with ``series`` (per-liability) and ``total`` keys.
        """
        df = self.liabilities_repo.get_all_liabilities(include_paid_off=False)
        if df.empty:
            return {"series": [], "total": []}

        liab_txns = self._get_liability_category_transactions()
        if not liab_txns.empty:
            liab_txns["amount"] = pd.to_numeric(liab_txns["amount"], errors="coerce").fillna(0.0)

        series = []
        for _, row in df.iterrows():
            record = row.to_dict()
            tag = record["tag"]
            principal = float(record["principal_amount"])
            schedule = self._schedule_for_record(record)
            points = [{"date": record["start_date"], "balance": principal}]

            if not liab_txns.empty and tag:
                payments = liab_txns[
                    (liab_txns["tag"] == tag) & (liab_txns["amount"] < 0)
                ].sort_values("date")

                for k, (_, txn) in enumerate(payments.iterrows(), start=1):
                    pos = min(k, len(schedule))
                    balance = (
                        schedule[pos - 1]["remaining_balance"] if pos > 0 else principal
                    )
                    points.append({
                        "date": str(txn["date"])[:10],
                        "balance": balance,
                    })

            series.append({"name": record["name"], "points": points})

        # Build total line using last-known balance per liability at each date
        all_dates = sorted({p["date"] for s in series for p in s["points"]})
        total = []
        for d in all_dates:
            total_balance = 0.0
            for s in series:
                last_balance = 0.0
                for p in s["points"]:
                    if p["date"] <= d:
                        last_balance = p["balance"]
                    else:
                        break
                total_balance += last_balance
            total.append({"date": d, "balance": round(total_balance, 2)})

        return {"series": series, "total": total}

    def generate_missing_transactions(self, liability_id: int) -> int:
        """Auto-generate missing payment transactions from the amortization schedule.

        Creates liability-specific transactions (not bank transactions) for
        months where no payment exists, up to and including the current month.

        Parameters
        ----------
        liability_id : int
            ID of the liability to generate transactions for.

        Returns
        -------
        int
            Number of transactions created.
        """
        record = self.get_liability(liability_id)

        schedule = self._schedule_for_record(record)

        # Get existing payment months from all sources (real + generated)
        transactions = self.get_liability_transactions(liability_id, tag=record.get("tag"))
        existing_months = set()
        for txn in transactions:
            if txn.get("amount") is not None and txn["amount"] < 0:
                existing_months.add(str(txn["date"])[:7])

        current_month = date.today().strftime("%Y-%m")
        created = 0

        for entry in schedule:
            month_key = entry["date"][:7]
            if month_key > current_month:
                break
            if month_key in existing_months:
                continue

            self.liabilities_repo.add_liability_transaction(
                liability_id=liability_id,
                date=entry["date"],
                amount=-entry["payment"],
                payment_number=entry["payment_number"],
                description=f"{record['name']} - Payment #{entry['payment_number']}",
            )
            created += 1

        if created > 0:
            self.liabilities_repo.commit()

        return created

    @staticmethod
    def _compare_actual_vs_expected(
        schedule: List[Dict[str, Any]],
        transactions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Compare actual payments against the amortization schedule by month.

        Groups negative transactions by ``YYYY-MM`` and compares to schedule
        entries for each month.

        Parameters
        ----------
        schedule : list[dict]
            Amortization schedule entries from ``calculate_amortization_schedule``.
        transactions : list[dict]
            Transaction dicts for this liability (from ``get_liability_transactions``).

        Returns
        -------
        list[dict]
            List of dicts with keys: ``date``, ``expected_payment``,
            ``actual_payment``, ``difference``.
        """
        actual_by_month: Dict[str, float] = {}
        for txn in transactions:
            amount = txn.get("amount", 0)
            if amount is not None and amount < 0:
                month_key = str(txn["date"])[:7]  # YYYY-MM
                actual_by_month[month_key] = actual_by_month.get(month_key, 0.0) + abs(amount)

        current_month = date.today().strftime("%Y-%m")

        result = []
        for entry in schedule:
            month_key = entry["date"][:7]
            if month_key > current_month:
                break
            expected = entry["payment"]
            actual = actual_by_month.get(month_key, 0.0)
            result.append({
                "date": entry["date"],
                "expected_payment": round(expected, 2),
                "actual_payment": round(actual, 2),
                "difference": round(actual - expected, 2),
            })

        return result
