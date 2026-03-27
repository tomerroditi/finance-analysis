"""
Liabilities service with amortization calculation and payment tracking.

This module provides business logic for liability (loan/debt) tracking
and analysis, including amortization schedule generation and payment
comparison.
"""

from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import LIABILITIES_CATEGORY
from backend.repositories.liabilities_repository import LiabilitiesRepository
from backend.repositories.transactions_repository import TransactionsRepository


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
            and ``percent_paid``.
        """
        df = self.liabilities_repo.get_all_liabilities(include_paid_off=include_paid_off)
        if df.empty:
            return []

        all_txns = self.transactions_repo.get_table()
        liab_txns = pd.DataFrame()
        if not all_txns.empty:
            liab_txns = all_txns[all_txns["category"] == LIABILITIES_CATEGORY].copy()

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

        all_txns = self.transactions_repo.get_table()
        liab_txns = pd.DataFrame()
        if not all_txns.empty:
            liab_txns = all_txns[all_txns["category"] == LIABILITIES_CATEGORY].copy()

        record = df.iloc[0].to_dict()
        self._enrich_with_calculations(record, liab_txns)
        return record

    def create_liability(
        self,
        name: str,
        tag: str,
        principal_amount: float,
        interest_rate: float,
        term_months: int,
        start_date: str,
        lender: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Create a new liability record and auto-create its tag.

        Adds the tag to the Liabilities category via ``CategoriesTagsService``
        (no-op if the tag already exists), then persists the liability record.

        Parameters
        ----------
        name : str
            Human-readable name for the liability.
        tag : str
            Tag identifying this specific liability.
        principal_amount : float
            Original loan amount.
        interest_rate : float
            Annual interest rate as a percentage (e.g. ``4.5`` for 4.5%).
        term_months : int
            Loan duration in months.
        start_date : str
            Date the loan was taken, in ``YYYY-MM-DD`` format.
        lender : str, optional
            Name of the lending institution.
        notes : str, optional
            Free-text notes about the liability.
        """
        from backend.services.tagging_service import CategoriesTagsService

        cat_service = CategoriesTagsService(self.db)
        cat_service.add_tag(LIABILITIES_CATEGORY, tag)

        self.liabilities_repo.create_liability(
            name=name,
            tag=tag,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            start_date=start_date,
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
            - ``summary`` – dict with ``total_paid``, ``total_interest_paid``,
              ``remaining_balance``, and ``payments_made``.
        """
        record = self.get_liability(liability_id)
        transactions = self.get_liability_transactions(liability_id)

        start_date = date.fromisoformat(record["start_date"])
        schedule = self.calculate_amortization_schedule(
            principal=record["principal_amount"],
            annual_rate=record["interest_rate"],
            term_months=record["term_months"],
            start_date=start_date,
        )

        actual_vs_expected = self._compare_actual_vs_expected(schedule, transactions)

        receipts = [t for t in transactions if t["amount"] > 0]
        payments = [t for t in transactions if t["amount"] < 0]
        total_receipts = sum(t["amount"] for t in receipts)
        total_payments = sum(abs(t["amount"]) for t in payments)

        num_payments = len(payments)
        remaining_balance = schedule[num_payments]["remaining_balance"] if num_payments < len(schedule) else 0.0

        # Interest split: already paid vs projected remaining
        interest_paid = sum(e["interest_portion"] for e in schedule[:num_payments])
        interest_remaining = sum(e["interest_portion"] for e in schedule[num_payments:])
        total_interest_cost = interest_paid + interest_remaining

        # Monthly payment from schedule (constant for fixed-rate)
        monthly_payment = schedule[0]["payment"] if schedule else 0.0

        percent_paid = (total_payments / record["principal_amount"] * 100) if record["principal_amount"] > 0 else 0.0

        summary = {
            "total_receipts": total_receipts,
            "total_payments": total_payments,
            "total_interest_cost": total_interest_cost,
            "interest_paid": interest_paid,
            "interest_remaining": interest_remaining,
            "monthly_payment": monthly_payment,
            "remaining_balance": remaining_balance,
            "percent_paid": round(percent_paid, 1),
            "payments_made": num_payments,
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
        all_txns = self.transactions_repo.get_table()
        if all_txns.empty:
            return {"receipt": None, "payments": [], "has_receipt": False}

        mask = (all_txns["category"] == LIABILITIES_CATEGORY) & (all_txns["tag"] == tag)
        matched = all_txns[mask].copy()

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

    def get_liability_transactions(self, liability_id: int) -> List[Dict[str, Any]]:
        """
        Get all transactions associated with a liability.

        Fetches the liability's tag, then filters all transactions by
        ``category == LIABILITIES_CATEGORY`` and matching tag, and also
        includes auto-generated liability transactions. Sorted by date.

        Parameters
        ----------
        liability_id : int
            ID of the liability.

        Returns
        -------
        list[dict]
            Matching transactions sorted by date ascending.
        """
        from sqlalchemy import select

        from backend.models.liability import LiabilityTransaction

        record_df = self.liabilities_repo.get_by_id(liability_id)
        tag = record_df.iloc[0]["tag"]

        # Real transactions from bank/CC/cash tables
        all_txns = self.transactions_repo.get_table()
        frames = []
        if not all_txns.empty:
            mask = (all_txns["category"] == LIABILITIES_CATEGORY) & (all_txns["tag"] == tag)
            matched = all_txns[mask].copy()
            if not matched.empty:
                matched["amount"] = pd.to_numeric(matched["amount"], errors="coerce").fillna(0.0)
                frames.append(matched)

        # Auto-generated liability transactions
        gen_txns = self.db.execute(
            select(LiabilityTransaction).where(LiabilityTransaction.liability_id == liability_id)
        ).scalars().all()
        if gen_txns:
            gen_df = pd.DataFrame([
                {"date": t.date, "amount": t.amount, "description": t.description,
                 "source": "liability_transactions", "category": LIABILITIES_CATEGORY,
                 "tag": tag, "payment_number": t.payment_number}
                for t in gen_txns
            ])
            frames.append(gen_df)

        if not frames:
            return []

        combined = pd.concat(frames, ignore_index=True).sort_values("date")
        combined = combined.where(pd.notnull(combined), None)
        return combined.to_dict(orient="records")

    @staticmethod
    def calculate_amortization_schedule(
        principal: float,
        annual_rate: float,
        term_months: int,
        start_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Calculate a standard amortization schedule.

        Uses the standard annuity formula for non-zero rates. For zero-rate
        loans, divides principal evenly across all periods.

        Parameters
        ----------
        principal : float
            Original loan amount.
        annual_rate : float
            Annual interest rate as a percentage (e.g. ``6.0`` for 6%).
        term_months : int
            Total number of monthly payments.
        start_date : date
            Date of the first payment (month is incremented for each period).

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
        """
        monthly_rate = annual_rate / 100.0 / 12.0

        if monthly_rate == 0:
            payment = principal / term_months
        else:
            payment = principal * monthly_rate * (1 + monthly_rate) ** term_months / (
                (1 + monthly_rate) ** term_months - 1
            )

        schedule = []
        balance = principal
        safe_day = min(start_date.day, 28)

        for i in range(1, term_months + 1):
            # Calculate payment date by incrementing months
            month = start_date.month + i
            year = start_date.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            payment_date = date(year, month, safe_day)

            interest_portion = balance * monthly_rate
            principal_portion = payment - interest_portion
            balance = max(balance - principal_portion, 0.0)

            schedule.append({
                "payment_number": i,
                "date": payment_date.strftime("%Y-%m-%d"),
                "payment": round(payment, 2),
                "principal_portion": round(principal_portion, 2),
                "interest_portion": round(interest_portion, 2),
                "remaining_balance": round(balance, 2),
            })

        return schedule

    def _enrich_with_calculations(
        self, record: Dict[str, Any], liab_txns: pd.DataFrame
    ) -> None:
        """
        Enrich a liability record with amortization-based calculated fields.

        Modifies ``record`` in-place to add ``monthly_payment``,
        ``total_interest``, ``remaining_balance``, ``total_paid``, and
        ``percent_paid``.

        Parameters
        ----------
        record : dict
            Liability record dict to enrich (modified in-place).
        liab_txns : pd.DataFrame
            All transactions with ``category == LIABILITIES_CATEGORY``.
        """
        principal = record["principal_amount"]
        annual_rate = record["interest_rate"]
        term_months = record["term_months"]
        start_date = date.fromisoformat(record["start_date"])

        schedule = self.calculate_amortization_schedule(
            principal=principal,
            annual_rate=annual_rate,
            term_months=term_months,
            start_date=start_date,
        )

        monthly_payment = schedule[0]["payment"] if schedule else 0.0
        total_interest = round(monthly_payment * term_months - principal, 2)

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

        if payment_count < len(schedule):
            remaining_balance = schedule[payment_count]["remaining_balance"]
        else:
            remaining_balance = 0.0

        percent_paid = (total_paid / (monthly_payment * term_months) * 100) if monthly_payment > 0 else 0.0

        record["monthly_payment"] = round(monthly_payment, 2)
        record["total_interest"] = total_interest
        record["remaining_balance"] = round(remaining_balance, 2)
        record["total_paid"] = round(total_paid, 2)
        record["percent_paid"] = round(percent_paid, 2)

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
        from backend.models.liability import LiabilityTransaction

        record = self.get_liability(liability_id)
        start_date_obj = date.fromisoformat(record["start_date"])

        schedule = self.calculate_amortization_schedule(
            principal=record["principal_amount"],
            annual_rate=record["interest_rate"],
            term_months=record["term_months"],
            start_date=start_date_obj,
        )

        # Get existing payment months from all sources (real + generated)
        transactions = self.get_liability_transactions(liability_id)
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

            txn = LiabilityTransaction(
                liability_id=liability_id,
                date=entry["date"],
                amount=-entry["payment"],
                payment_number=entry["payment_number"],
                description=f"{record['name']} - Payment #{entry['payment_number']}",
            )
            self.db.add(txn)
            created += 1

        if created > 0:
            self.db.commit()

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
