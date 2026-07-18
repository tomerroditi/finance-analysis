"""
Split-transaction handling for the aggregating transactions repository.

Provides the ``SplitsMixin`` with the batched split-children builder used
by the merged ``get_table`` view, plus the split / revert-split write
operations. Mixed into ``TransactionsRepository`` (see ``core.py``).
"""

import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.constants.tables import SplitTransactionsTableFields

from backend.repositories.transactions.service_repositories import T_service

logger = logging.getLogger(__name__)


class SplitsMixin:
    """Split-transaction methods for ``TransactionsRepository``."""

    def _filter_split_parents(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows where type is ``"split_parent"`` from the DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Input transactions DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with split_parent rows removed.
        """
        if df.empty or "type" not in df.columns:
            return df
        return df[df["type"] != "split_parent"]

    def _get_split_children(
        self,
        service: T_service | None,
        exclude_services: list[T_service] | None = None,
    ) -> pd.DataFrame:
        """Build split-child rows for all splits, filtered by service if given.

        Parameters
        ----------
        service : T_service | None
            If provided, include only splits whose source maps to this service.
        exclude_services : list[T_service] | None
            If provided, exclude splits whose source maps to any of these services.

        Returns
        -------
        pd.DataFrame
            DataFrame of split-child rows; empty if no splits exist or all filtered.
        """
        splits_df = self.split_repo.get_data()

        if splits_df.empty:
            return pd.DataFrame()

        src_col = SplitTransactionsTableFields.SOURCE.value
        tid_col = SplitTransactionsTableFields.TRANSACTION_ID.value

        # Batch: one SELECT ... WHERE unique_id IN (...) per source table
        # instead of one query per split row — this runs inside get_table(),
        # i.e. on essentially every analytics/budget/transactions request.
        parents_by_key: dict[tuple[str, int], dict] = {}
        for source, group in splits_df.groupby(src_col):
            repo = self.get_repo_by_source(source)
            if repo is None:
                logger.warning(
                    "Splits reference unknown source %s — skipping", source
                )
                continue
            ids = [int(v) for v in group[tid_col].unique()]
            rows = (
                self.db.execute(
                    select(repo.model).where(repo.model.unique_id.in_(ids))
                )
                .scalars()
                .all()
            )
            for parent in rows:
                parents_by_key[(source, parent.unique_id)] = {
                    c.name: getattr(parent, c.name)
                    for c in parent.__table__.columns
                }

        children = []
        for _, split in splits_df.iterrows():
            parent_dict = parents_by_key.get(
                (split[src_col], int(split[tid_col]))
            )
            if parent_dict is None:
                continue
            children.append(
                {
                    **parent_dict,
                    "unique_id": f"split_{split[SplitTransactionsTableFields.ID.value]}",
                    "amount": split[SplitTransactionsTableFields.AMOUNT.value],
                    "category": split[SplitTransactionsTableFields.CATEGORY.value],
                    "tag": split[SplitTransactionsTableFields.TAG.value],
                    "type": "split_child",
                    "source": split[src_col],
                }
            )

        if not children:
            return pd.DataFrame()

        children_df = pd.DataFrame(children)

        if service:
            target_repo = self.get_repo_by_source(service)
            valid_sources = [
                src
                for src in children_df["source"].unique()
                if self.get_repo_by_source(src) == target_repo
            ]
            children_df = children_df[children_df["source"].isin(valid_sources)]
        elif exclude_services:
            excluded_repos = {
                repo
                for s in exclude_services
                if (repo := self.get_repo_by_source(s)) is not None
            }
            excluded_sources = [
                src
                for src in children_df["source"].unique()
                if self.get_repo_by_source(src) in excluded_repos
            ]
            children_df = children_df[~children_df["source"].isin(excluded_sources)]

        return children_df

    def _add_split_children(
        self,
        df: pd.DataFrame,
        service: T_service | None,
        exclude_services: list[T_service] | None = None,
    ) -> pd.DataFrame:
        """Concatenate split-child rows onto the transactions DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Base transactions DataFrame (with split parents already filtered).
        service : T_service | None
            Passed through to ``_get_split_children`` for filtering.
        exclude_services : list[T_service] | None
            Passed through to ``_get_split_children`` for filtering.

        Returns
        -------
        pd.DataFrame
            DataFrame with split children appended; original df if none exist.
        """
        children_df = self._get_split_children(service, exclude_services)

        if children_df.empty:
            return df

        return pd.concat([df, children_df], ignore_index=True)

    def split_transaction(
        self, unique_id: int, source: str, splits: list[dict]
    ) -> bool:
        """Split a transaction into multiple partial amounts across categories.

        Parameters
        ----------
        unique_id : int
            unique_id of the transaction to split.
        source : str
            Table name of the source repository.
        splits : list[dict]
            List of split dicts, each with keys: amount, category, tag.

        Returns
        -------
        bool
            True if the split was committed successfully, False on error
            (rolls back the transaction in that case).

        Notes
        -----
        Marks the original transaction as type ``"split_parent"`` and creates
        one split_transaction record per element in ``splits``.  Any existing
        splits for this transaction are replaced.
        """
        try:
            repo = self.get_repo_by_source(source)
            parent_updated = repo.update_transaction_by_unique_id(
                str(unique_id), {"type": "split_parent"}
            )
            if not parent_updated:
                self.db.rollback()
                raise ValueError(
                    f"Cannot split: no {source} row with unique_id={unique_id}"
                )

            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            for split in splits:
                self.split_repo.add_split(
                    transaction_id=unique_id,
                    source=source,
                    amount=split["amount"],
                    category=split["category"],
                    tag=split["tag"],
                )
            return True
        except ValueError:
            raise
        except SQLAlchemyError:
            logger.exception(
                "Split failed for unique_id=%s in %s", unique_id, source
            )
            self.db.rollback()
            raise

    def revert_split(self, unique_id: int, source: str) -> bool:
        """Revert a split transaction back to a normal transaction.

        Parameters
        ----------
        unique_id : int
            unique_id of the split-parent transaction to revert.
        source : str
            Table name of the source repository.

        Returns
        -------
        bool
            True if reverted successfully, False on error.

        Notes
        -----
        Sets the transaction type back to ``"normal"`` and deletes all associated
        split_transaction records.
        """
        try:
            repo = self.get_repo_by_source(source)
            repo.update_transaction_by_unique_id(str(unique_id), {"type": "normal"})

            self.split_repo.delete_all_splits_for_transaction(unique_id, source)
            return True
        except SQLAlchemyError:
            logger.exception(
                "Revert split failed for unique_id=%s in %s", unique_id, source
            )
            self.db.rollback()
            raise
