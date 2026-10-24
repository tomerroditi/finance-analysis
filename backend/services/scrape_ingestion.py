"""Ingestion of one successful scrape into the database.

A ``ScrapingResult`` from the root ``scraper`` package becomes transaction
rows (with the dedup keys every later re-scrape is matched against), is
saved, auto-tagged, reconciled against the bank's reported balance, and —
for insurance — re-keyed onto stored policies and followed by the policy
metadata, clearing-house reports, pension loans and Keren Hishtalmut
investments the scrape carries.

The scraper lifecycle (launch, 2FA, timeout, the history row) stays in
``backend.scraper.adapter``; this module only ever sees a finished result,
so it can be driven directly in tests without a scraper or an event loop.

Each step opens its own session and commits on its own. The steps after the
transaction save are isolated from one another — a failing auto-tag or
metadata write is logged and never undoes the rows already saved, because
the scrape itself succeeded.
"""

import json
import logging
from collections.abc import Iterator
from datetime import date
from typing import TYPE_CHECKING, Any

import pandas as pd

from backend.constants.providers import CLEARING_HOUSE_REPORTS_EXTRA, Services
from backend.constants.tables import SERVICE_TO_TABLE, TransactionsTableFields
from backend.database import get_db_context
from backend.repositories.transactions import TransactionsRepository
from backend.services.bank_balance_service import BankBalanceService
from backend.services.tagging_rules_service import TaggingRulesService
from backend.services.tagging_service import CategoriesTagsService
from backend.utils.log_sanitize import scrub

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from scraper.models.account import AccountResult
    from scraper.models.result import ScrapingResult
    from scraper.models.transaction import Transaction

logger = logging.getLogger(__name__)


def format_key_amount(amount: float | str | None) -> str:
    """Render an amount for a dedup key at fixed 2-decimal precision.

    A raw float repr is not a stable key: ``0.1 + 0.2`` renders as
    ``0.30000000000000004`` while ``0.3`` renders as ``0.3``, so two runs
    that reach the same amount by different arithmetic produce different
    keys for the same transaction.

    Parameters
    ----------
    amount : float or str
        The transaction's charged amount.

    Returns
    -------
    str
        The amount at 2 decimal places, or its ``str`` form if it is not
        numeric at all.
    """
    try:
        return f"{float(amount):.2f}"
    except (TypeError, ValueError):
        return str(amount)


def scraped_rows(
    result: "ScrapingResult", provider_name: str
) -> Iterator[tuple["AccountResult", "Transaction", str, str, str]]:
    """Yield ``(account, txn, txn_date, row_id, unique_id)`` per scraped row.

    Centralises dedup-key construction so the base frame and the
    insurance memo map can never disagree about a row's ``id``.

    ``id`` is the DB-visible key that
    ``TransactionsRepository.add_scraped_transactions`` dedups on, via
    the composite ``(id, provider, date, amount)``. Rows without a
    provider ``identifier`` fell back to
    ``"{account}_{date}_{amount}"``, so two genuinely distinct same-day,
    same-amount transactions collapsed onto one key. Once the first was
    stored, every overlapping re-scrape (the window reaches back 7 days)
    matched both incoming rows against it and dropped the second
    **permanently**.

    The discriminator is deliberately minimal, because the key is
    matched against rows **already in the user's database**:

    * Rows that carry a provider identifier are untouched. A repeated
      identifier means the provider itself considers the rows the same,
      and re-keying them would re-insert historical rows as duplicates.
    * The **first** identifier-less row of each
      ``(account, date, amount)`` group keeps the exact legacy string,
      including the raw float repr of the amount. Every such row already
      in the DB therefore still matches and is still deduped.
    * Only the 2nd, 3rd, … occurrence gains a ``#N`` suffix — those are
      precisely the rows that are being lost today.

    The float repr is left alone in ``id`` on purpose. Reformatting it
    (e.g. to 2dp) would change the key of *every* identifier-less row
    ever stored, re-inserting each as a duplicate on the next
    overlapping scrape. ``unique_id`` is not persisted (``unique_id`` is
    an autoincrement PK on the DB side and is excluded from the insert
    via ``TransactionBase.BASE_COLUMN_NAMES``), so it is free to use the
    deterministic 2-decimal form.

    Parameters
    ----------
    result : ScrapingResult
        The scraping result from the scraper framework.
    provider_name : str
        Provider identifier, the prefix of every ``unique_id``.

    Yields
    ------
    tuple
        ``(account, txn, txn_date, row_id, unique_id)``.
    """
    # Occurrence counters, per scrape. Keyed on the exact tuple whose
    # collisions we are disambiguating.
    fallback_counts: dict[tuple[str, str, str], int] = {}
    unique_counts: dict[tuple[str, str, str, str], int] = {}

    for account in result.accounts:
        for txn in account.transactions:
            # Normalise date to YYYY-MM-DD
            txn_date = txn.date
            if "T" in txn_date:
                txn_date = txn_date.split("T")[0]

            identifier = txn.identifier or ""
            key_amount = format_key_amount(txn.charged_amount)

            unique_key = (
                str(account.account_number),
                txn_date,
                key_amount,
                identifier,
            )
            unique_n = unique_counts.get(unique_key, 0) + 1
            unique_counts[unique_key] = unique_n
            unique_id = (
                f"{provider_name}_{account.account_number}"
                f"_{txn_date}_{key_amount}_{identifier}"
            )
            if unique_n > 1:
                unique_id = f"{unique_id}#{unique_n}"

            if txn.identifier:
                row_id = txn.identifier
            else:
                # Legacy format preserved verbatim for the first
                # occurrence — see the note above on backward compat.
                row_id = f"{account.account_number}_{txn_date}_{txn.charged_amount}"
                fallback_key = (
                    str(account.account_number),
                    txn_date,
                    str(txn.charged_amount),
                )
                fallback_n = fallback_counts.get(fallback_key, 0) + 1
                fallback_counts[fallback_key] = fallback_n
                if fallback_n > 1:
                    row_id = f"{row_id}#{fallback_n}"

            yield account, txn, txn_date, row_id, unique_id


def reported_bank_balance(result: "ScrapingResult") -> float | None:
    """Return what the bank says the credential's accounts hold.

    Sums the checking accounts' reported balances. Savings deposits are
    left out: money moved into one is tracked as an investment, not as
    bank cash. ``None`` when any checking account came back without a
    balance — a partial sum would read as money gone missing.

    Parameters
    ----------
    result : ScrapingResult
        The scraping result from the scraper framework.

    Returns
    -------
    float or None
        The summed checking balance, or ``None`` when it is not fully known.
    """
    checking = [a for a in result.accounts if not a.savings_account]
    if not checking or any(a.balance is None for a in checking):
        return None
    return float(sum(float(a.balance) for a in checking))


def ingestion_for(
    service_name: str,
    provider_name: str,
    account_name: str,
    start_date: date,
    log_id: str,
) -> "ScrapeIngestion":
    """Build the ingestion pipeline for the given service type.

    Parameters
    ----------
    service_name : str
        Service type (``"banks"``, ``"credit_cards"``, ``"insurances"``).
    provider_name, account_name, start_date, log_id
        Forwarded to the pipeline constructor.

    Returns
    -------
    ScrapeIngestion
        An ``InsuranceIngestion`` for insurances, otherwise a base
        ``ScrapeIngestion``.
    """
    cls = (
        InsuranceIngestion
        if service_name == Services.INSURANCE.value
        else ScrapeIngestion
    )
    return cls(service_name, provider_name, account_name, start_date, log_id)


class ScrapeIngestion:
    """Turns one successful scrape of one credential into stored rows.

    Parameters
    ----------
    service_name : str
        Service type (``"credit_cards"``, ``"banks"``, ``"insurances"``).
    provider_name : str
        Provider identifier (e.g. ``"isracard"``, ``"hapoalim"``).
    account_name : str
        User-assigned account label.
    start_date : date
        Start of the scraped window. Pending rows inside it that the scrape
        no longer reports are reconciled away on save.
    log_id : str
        Identity prefix for log lines, shared with the adapter so a scrape's
        lines read as one story.
    """

    def __init__(
        self,
        service_name: str,
        provider_name: str,
        account_name: str,
        start_date: date,
        log_id: str,
    ) -> None:
        self.service_name = service_name
        self.provider_name = provider_name
        self.account_name = account_name
        self.start_date = start_date
        self._log_id = log_id
        self._table_name = SERVICE_TO_TABLE.get(service_name, "")

    def ingest(self, result: "ScrapingResult") -> pd.DataFrame:
        """Store a successful scrape and return the rows it produced.

        An empty window is still an authoritative scrape of that window:
        pending rows must be reconciled, the bank balance recomputed and the
        insurance metadata (balances, snapshots) refreshed even when no new
        transaction arrived. A result with no accounts at all stores
        nothing — the adapter records that as a failure.

        These are blocking sync DB writes. They are deliberately not moved
        to an executor by the caller: thread-pool work is not cancellable
        by the scrape's ``asyncio.wait_for`` timeout, so the hop would let
        DB writes outlive the 5-minute ceiling.

        Parameters
        ----------
        result : ScrapingResult
            A result whose ``success`` is true.

        Returns
        -------
        pd.DataFrame
            The scraped rows, sorted by date, with the
            ``TransactionsTableFields`` columns.
        """
        self.before_rows(result)
        frame = self.to_frame(result)
        if not result.accounts:
            return frame
        if not frame.empty:
            frame = frame.sort_values(by=["date"])
        self._save(frame)
        self._auto_tag()
        self._rebalance(reported_bank_balance(result))
        self.after_save(result)
        return frame

    def before_rows(self, result: "ScrapingResult") -> None:
        """Adjust the result before it becomes rows (no-op by default)."""

    def after_save(self, result: "ScrapingResult") -> None:
        """Store what the result carries beside its rows (no-op by default)."""

    def to_frame(self, result: "ScrapingResult") -> pd.DataFrame:
        """Convert a ``ScrapingResult`` to the frame the repository stores.

        Parameters
        ----------
        result : ScrapingResult
            The scraping result from the scraper framework.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns matching ``TransactionsTableFields``.
        """
        rows: list[dict[str, Any]] = []
        for account, txn, txn_date, row_id, unique_id in scraped_rows(
            result, self.provider_name
        ):
            rows.append(
                {
                    TransactionsTableFields.ID.value: row_id,
                    TransactionsTableFields.DATE.value: txn_date,
                    TransactionsTableFields.AMOUNT.value: txn.charged_amount,
                    TransactionsTableFields.DESCRIPTION.value: txn.description,
                    TransactionsTableFields.ACCOUNT_NUMBER.value: account.account_number,
                    TransactionsTableFields.TYPE.value: txn.type.value,
                    TransactionsTableFields.STATUS.value: txn.status.value,
                    TransactionsTableFields.ACCOUNT_NAME.value: self.account_name,
                    TransactionsTableFields.PROVIDER.value: self.provider_name,
                    TransactionsTableFields.CATEGORY.value: None,
                    TransactionsTableFields.TAG.value: None,
                    TransactionsTableFields.SOURCE.value: self._table_name,
                    TransactionsTableFields.UNIQUE_ID.value: unique_id,
                    TransactionsTableFields.SPLIT_ID.value: None,
                }
            )

        if not rows:
            # Keep the canonical columns so an empty window can still be
            # saved without a KeyError on the dedup columns.
            return pd.DataFrame(columns=[f.value for f in TransactionsTableFields])

        return pd.DataFrame(rows)

    def _save(self, frame: pd.DataFrame) -> None:
        """Persist the scraped frame, reconciling the window's pending rows."""
        with get_db_context() as db:
            TransactionsRepository(db).add_scraped_transactions(
                frame,
                self._table_name,
                scrape_start_date=self.start_date.strftime("%Y-%m-%d"),
            )

    def _auto_tag(self) -> None:
        """Apply tagging rules to transactions that have no category yet."""
        try:
            with get_db_context() as db:
                CategoriesTagsService(db).add_new_credit_card_tags()
                tagging_rules_service = TaggingRulesService(db)
                count = tagging_rules_service.apply_rules(overwrite=False)
                count += tagging_rules_service.auto_tag_credit_cards_bills()
                if count > 0:
                    logger.info(
                        "%s: Auto-tagged %d transactions",
                        scrub(self._log_id),
                        count,
                    )
        except Exception as exc:
            logger.error(
                "%s: Error auto-tagging — %s",
                scrub(self._log_id),
                scrub(exc),
            )

    def _rebalance(self, reported: float | None) -> None:
        """Update the bank balance after a bank scrape.

        Parameters
        ----------
        reported : float or None
            The balance the bank reported (see :func:`reported_bank_balance`).
            When given it becomes the account's balance; without it the
            stored prior wealth is kept and the transactions are re-added
            to it.
        """
        if self.service_name != Services.BANK.value:
            return
        try:
            with get_db_context() as db:
                balance_service = BankBalanceService(db)
                if reported is None:
                    balance_service.recalculate_for_account(
                        self.provider_name,
                        self.account_name,
                    )
                    return
                drift = balance_service.apply_scraped_balance(
                    self.provider_name, self.account_name, reported
                )
                if drift:
                    logger.warning(
                        "%s: bank balance differs from tracked transactions by %.2f",
                        scrub(self._log_id),
                        drift,
                    )
        except Exception as exc:
            logger.error(
                "%s: Error recalculating bank balance — %s",
                scrub(self._log_id),
                scrub(exc),
            )


class InsuranceIngestion(ScrapeIngestion):
    """Ingestion for insurance scrapes: memos, policy claims and metadata."""

    def to_frame(self, result: "ScrapingResult") -> pd.DataFrame:
        """Extend the base conversion with the ``memo`` column."""
        df = super().to_frame(result)
        if df.empty:
            return df

        # Reuse the base row-key generator so the memo map is keyed by the
        # same (discriminated) ids the frame's `id` column holds — building
        # the key a second time here is how the two drifted apart.
        memo_map: dict[str, str] = {}
        for _account, txn, _txn_date, row_id, _unique_id in scraped_rows(
            result, self.provider_name
        ):
            if txn.memo:
                memo_map[row_id] = txn.memo

        if memo_map:
            df["memo"] = df["id"].map(memo_map)

        return df

    def before_rows(self, result: "ScrapingResult") -> None:
        """Re-key the scrape onto stored policy IDs and adopt predecessors' rows.

        See ``InsuranceAccountService.claim_policies``. Runs before the rows
        are built so every deposit carries the policy ID the other tables
        join on, and before the save so re-reported deposits dedup against
        the adopted ones.
        """
        from backend.services.insurance_account_service import (
            InsuranceAccountService,
        )

        if not result.accounts:
            return
        try:
            with get_db_context() as db:
                stored = InsuranceAccountService(db).claim_policies(
                    self.provider_name,
                    self.account_name,
                    [account.account_number for account in result.accounts],
                )
        except Exception as exc:
            logger.error(
                "%s: Error resolving stored insurance policies — %s",
                scrub(self._log_id),
                scrub(exc),
            )
            return
        for account in result.accounts:
            policy_id = stored.get(account.account_number)
            if policy_id is None:
                continue
            account.account_number = policy_id
            if account.metadata:
                account.metadata["policy_id"] = policy_id

    def after_save(self, result: "ScrapingResult") -> None:
        """Persist insurance account metadata from ``AccountResult.metadata``."""
        from backend.services.insurance_account_service import (
            InsuranceAccountService,
        )
        from backend.services.investments import InvestmentsService

        self._save_clearing_house_reports(result)
        accounts_to_upsert = [
            dict(account.metadata) for account in result.accounts if account.metadata
        ]
        if not accounts_to_upsert:
            return

        try:
            with get_db_context() as db:
                service = InsuranceAccountService(db)
                saved = []
                for meta in accounts_to_upsert:
                    history = meta.pop("balance_history", None)
                    saved.append((service.upsert(**meta), history))
                logger.info(
                    "%s: Saved metadata for %d insurance accounts",
                    scrub(self._log_id),
                    len(accounts_to_upsert),
                )

                self._sync_policy_loans(db, [account for account, _ in saved])
                inv_service = InvestmentsService(db)
                for account, history in saved:
                    if account.policy_type != "hishtalmut":
                        continue
                    try:
                        inv_service.sync_from_insurance_account(account, history)
                        logger.info(
                            "%s: Synced hishtalmut investment for policy %s",
                            scrub(self._log_id),
                            scrub(account.policy_id),
                        )
                    except Exception:
                        logger.exception(
                            "%s: Failed to sync hishtalmut investment for policy %s",
                            scrub(self._log_id),
                            scrub(account.policy_id),
                        )
        except Exception as exc:
            logger.error(
                "%s: Error saving insurance metadata — %s",
                scrub(self._log_id),
                scrub(exc),
            )

    def _save_clearing_house_reports(self, result: "ScrapingResult") -> None:
        """Store the household summaries a clearing-house scrape handed back."""
        from backend.services.insurance_account_service import (
            InsuranceAccountService,
        )

        reports = (getattr(result, "extras", None) or {}).get(
            CLEARING_HOUSE_REPORTS_EXTRA
        )
        if not reports:
            return
        try:
            with get_db_context() as db:
                InsuranceAccountService(db).save_clearing_house_reports(
                    self.provider_name, self.account_name, reports
                )
        except Exception as exc:
            logger.error(
                "%s: Error saving clearing-house reports — %s",
                scrub(self._log_id),
                scrub(exc),
            )

    def _sync_policy_loans(self, db: "Session", accounts: list) -> None:
        """Mirror loans taken against the scraped policies as liabilities.

        Parameters
        ----------
        db : Session
            Open database session.
        accounts : list[InsuranceAccount]
            The accounts just upserted; their ``details`` carry any loans.
        """
        from backend.services.liabilities_service import LiabilitiesService

        for account in accounts:
            try:
                details = json.loads(account.details or "{}")
            except (TypeError, ValueError):
                continue
            if not details.get("loans"):
                continue
            try:
                LiabilitiesService(db).sync_insurance_loans(
                    account.policy_id,
                    account.custom_name or account.account_name,
                    details.get("manufacturer"),
                    details["loans"],
                )
            except Exception:
                logger.exception(
                    "%s: Failed to sync loans for policy %s",
                    scrub(self._log_id),
                    scrub(account.policy_id),
                )
