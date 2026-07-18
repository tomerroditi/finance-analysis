"""
Scraped-transaction ingestion for the aggregating transactions repository.

Provides the ``IngestionMixin`` with ``add_scraped_transactions`` (dedup
insert of scraped rows) and its pending-row reconciliation helper. Mixed
into ``TransactionsRepository`` (see ``core.py``).
"""

import logging

import pandas as pd
from sqlalchemy import select

from backend.models.pending_refund import PendingRefund
from backend.models.transaction import TransactionBase

logger = logging.getLogger(__name__)


class IngestionMixin:
    """Scraped-data ingestion methods for ``TransactionsRepository``."""

    def add_scraped_transactions(
        self,
        df: pd.DataFrame,
        table_name: str,
        scrape_start_date: str | None = None,
    ) -> None:
        """Persist scraped transactions, skipping rows that already exist.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame of scraped transactions to insert.  Must contain columns:
            id, provider, date, amount plus any other transaction fields.
        table_name : str
            Target table name; must be one of the four supported tables.
        scrape_start_date : str, optional
            Start of the scraped window (``YYYY-MM-DD``). When provided,
            existing ``pending`` rows for the scraped provider/account from
            this date onward are reconciled (see Notes). Falls back to the
            earliest date in ``df``.

        Raises
        ------
        ValueError
            If ``table_name`` is not in the list of supported tables.

        Notes
        -----
        Deduplication is based on the composite key (id, provider, date, amount).
        Only rows not already present in the DB are inserted.

        Pending reconciliation: a transaction scraped while still pending can
        settle with a different date or amount (FX conversion, card holds), so
        the settled row fails the duplicate check and BOTH rows persist,
        double-counting the spend. The scrape is authoritative for its window:
        stale pending rows are deleted, still-pending transactions are
        re-reported by the scrape and re-inserted, and any user-assigned
        category/tag is carried over by composite key. Split parents and rows
        referenced by pending refunds are never purged.
        """
        if table_name not in self.tables:
            raise ValueError(f"table_name should be one of {self.tables}")

        repo = self.get_repo_by_source(table_name)

        carried_tags = self._reconcile_pending_rows(repo, df, scrape_start_date)

        # Using pandas for the merge logic as in original code is robust for the
        # duplicate check. Read through the session's own connection so the
        # uncommitted pending-row deletions above are visible — otherwise
        # re-reported pending rows would be deduped against the rows just
        # deleted and silently dropped.
        stmt = select(
            repo.model.id, repo.model.provider, repo.model.date, repo.model.amount
        )
        existing_data = pd.read_sql(stmt, self.db.connection())

        # Make sure columns align for merge
        df = df.astype({col: str for col in self.unique_columns})
        existing_data = existing_data.astype({col: str for col in self.unique_columns})

        if carried_tags is not None and not carried_tags.empty:
            df = df.merge(
                carried_tags, on=self.unique_columns, how="left", suffixes=("", "_carried")
            )
            for col in ("category", "tag"):
                carried_col = f"{col}_carried"
                df[col] = df[col].fillna(df[carried_col])
                df = df.drop(columns=carried_col)

        if not existing_data.empty:
            merged_df = df.merge(
                existing_data, on=self.unique_columns, how="left", indicator=True
            )
            new_rows = merged_df[merged_df["_merge"] == "left_only"].drop(
                columns="_merge"
            )
        else:
            new_rows = df

        if new_rows.empty:
            # Still commit any pending-row deletions from the reconcile step.
            self.db.commit()
            return

        # Prepare list of model instances
        model_columns = {c.name for c in repo.model.__table__.columns}
        extra_columns = model_columns - TransactionBase.BASE_COLUMN_NAMES

        instances = []
        for _, row in new_rows.iterrows():
            kwargs = dict(
                id=row["id"],
                date=row["date"],
                provider=row["provider"],
                account_name=row["account_name"],
                account_number=row.get("account_number"),
                description=row.get("description"),
                amount=float(row["amount"]),
                category=row.get("category"),
                tag=row.get("tag"),
                source=row.get("source", repo.table),
                type=row.get("type", "normal"),
                status=row.get("status", "completed"),
            )
            for col in extra_columns:
                if col in row:
                    kwargs[col] = row.get(col)
            instance = repo.model(**kwargs)
            instances.append(instance)

        self.db.add_all(instances)
        self.db.commit()

    def _reconcile_pending_rows(
        self,
        repo,
        df: pd.DataFrame,
        scrape_start_date: str | None,
    ) -> pd.DataFrame | None:
        """Delete stale pending rows superseded by a re-scrape of their window.

        Deletions are flushed but not committed — the caller commits them
        together with the inserted rows so the reconcile is atomic.

        Parameters
        ----------
        repo
            Sub-repository whose model/table is being written to.
        df : pd.DataFrame
            Incoming scraped transactions.
        scrape_start_date : str or None
            Start of the scraped window; falls back to the earliest date
            in ``df``.

        Returns
        -------
        pd.DataFrame or None
            Carried-over ``category``/``tag`` values keyed by the composite
            (id, provider, date, amount) — already string-typed — or ``None``
            when nothing was purged.
        """
        required = {"date", "provider", "account_name"}
        if df.empty or not required.issubset(df.columns):
            return None

        window_start = scrape_start_date or df["date"].min()
        providers = [str(p) for p in df["provider"].dropna().unique()]
        accounts = [str(a) for a in df["account_name"].dropna().unique()]
        if not window_start or not providers or not accounts:
            return None

        model = repo.model
        stale = (
            self.db.execute(
                select(model).where(
                    model.status == "pending",
                    model.provider.in_(providers),
                    model.account_name.in_(accounts),
                    model.date >= str(window_start),
                    model.type != "split_parent",
                )
            )
            .scalars()
            .all()
        )
        if not stale:
            return None

        # Never purge rows a pending refund points at — the refund record
        # references the row's unique_id and would be orphaned.
        refund_locked = {
            row[0]
            for row in self.db.execute(
                select(PendingRefund.source_id).where(
                    PendingRefund.source_type == "transaction",
                    PendingRefund.source_table == repo.table,
                )
            ).all()
        }

        carried = []
        for row in stale:
            if row.unique_id in refund_locked:
                continue
            if row.category:
                carried.append(
                    {
                        "id": str(row.id),
                        "provider": str(row.provider),
                        "date": str(row.date),
                        "amount": str(row.amount),
                        "category": row.category,
                        "tag": row.tag,
                    }
                )
            self.db.delete(row)
        self.db.flush()

        if not carried:
            return None
        # Two distinct transactions can legitimately share
        # (id, provider, date, amount) — e.g. two identical same-day ATM
        # withdrawals with empty reference ids (see migration
        # d4f6a8c0e2b5). Collapse duplicate keys so the left-join that
        # restores tags can't cartesian-multiply a scraped row into
        # several inserts.
        return pd.DataFrame(carried).drop_duplicates(
            subset=self.unique_columns, keep="first"
        )
