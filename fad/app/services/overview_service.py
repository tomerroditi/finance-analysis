import datetime

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.transactions_repository import TransactionsRepository
from fad.app.naming_conventions import SavingsAndInvestmentsCategories


class OverviewService:
    """Service for overview-related business logic and data processing."""

    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.transactions_repository = TransactionsRepository(conn)

    def get_bank_transactions_for_net_worth(self) -> pd.DataFrame:
        """
        Fetch bank transactions for net worth calculations.

        Returns
        -------
        pd.DataFrame
            Bank transactions with datetime-converted date column.
        """
        transactions = self.transactions_repository.get_table("bank")
        if not transactions.empty:
            transactions['date'] = pd.to_datetime(transactions['date'])
        return transactions

    def calculate_cumulative_balance(self, transactions: pd.DataFrame, frequency: str = "M") -> pd.DataFrame:
        """
        Calculate cumulative balance over time resampled by frequency.

        Parameters
        ----------
        transactions : pd.DataFrame
            Transaction data with 'date' and 'amount' columns.
        frequency : str, optional
            Pandas frequency string for resampling (default: "M" for monthly).
            Examples: "D" for daily, "W" for weekly, "M" for monthly, "Y" for yearly.

        Returns
        -------
        pd.DataFrame
            DataFrame with 'date' and 'balance' columns showing cumulative balance over time.
        """
        if transactions.empty:
            return pd.DataFrame(columns=['date', 'balance'])

        sorted_transactions = transactions.sort_values(by='date')
        balance_df = pd.DataFrame({
            "balance": sorted_transactions["amount"].cumsum(),
            "date": sorted_transactions["date"]
        })
        return balance_df.resample(frequency, on="date").last().ffill().reset_index(names="date")

    def get_investment_transactions(self, transactions: pd.DataFrame) -> pd.DataFrame:
        """
        Filter and prepare investment transactions from bank transactions.

        Parameters
        ----------
        transactions : pd.DataFrame
            All bank transactions.

        Returns
        -------
        pd.DataFrame
            Investment transactions with amounts flipped to positive values.
        """
        investment_categories = [
            SavingsAndInvestmentsCategories.INVESTMENTS.value,
            SavingsAndInvestmentsCategories.SAVINGS.value
        ]
        investments = transactions[transactions["category"].isin(investment_categories)].copy()
        investments['amount'] = investments['amount'] * -1
        return investments

    def prepare_investments_over_time(
        self,
        investments: pd.DataFrame,
        all_transactions: pd.DataFrame,
        frequency: str = "M"
    ) -> pd.DataFrame:
        """
        Prepare investment data with cumulative balances by tag, resampled over time.

        This method:
        1. Calculates cumulative balance per investment tag
        2. Adds a 'Total' line aggregating all investments
        3. Adds zero baseline before first transaction
        4. Resamples data by frequency with forward fill

        Parameters
        ----------
        investments : pd.DataFrame
            Investment transactions (filtered and amount-flipped).
        all_transactions : pd.DataFrame
            All bank transactions for determining date range.
        frequency : str, optional
            Pandas frequency string for resampling (default: "M").

        Returns
        -------
        pd.DataFrame
            DataFrame with 'date', 'balance', 'category', and 'tag' columns.
        """
        if investments.empty:
            return pd.DataFrame(columns=['date', 'balance', 'category', 'tag'])

        investments = self._add_cumulative_balance_per_tag(investments)
        investments = self._add_total_investments_line(investments)
        investments = self._add_zero_baseline(investments, all_transactions)
        investments = self._resample_by_tag(investments, frequency, all_transactions)
        return investments

    def _add_cumulative_balance_per_tag(self, investments: pd.DataFrame) -> pd.DataFrame:
        """Add cumulative balance column grouped by tag."""
        investments = investments.sort_values(by='date')
        investments["balance"] = investments.groupby("tag")["amount"].cumsum()
        return investments

    def _add_total_investments_line(self, investments: pd.DataFrame) -> pd.DataFrame:
        """Add a 'Total' tag line aggregating all investments."""
        total_line = investments.copy().sort_values(by='date')
        total_line["balance"] = total_line["amount"].cumsum()
        total_line["tag"] = "Total"
        total_line["category"] = "Total"
        total_line = total_line.drop_duplicates(subset=["date"], keep="last")
        return pd.concat([investments, total_line], ignore_index=True).sort_values(by="date")

    def _add_zero_baseline(
        self,
        investments: pd.DataFrame,
        all_transactions: pd.DataFrame
    ) -> pd.DataFrame:
        """Add zero balance entries before first transaction for each tag."""
        earliest_date = all_transactions['date'].min() - pd.Timedelta(days=1)
        zero_entries = []

        for cat, tag in investments[['category', 'tag']].drop_duplicates().itertuples(index=False):
            zero_entries.append({
                'date': earliest_date,
                'amount': 0,
                'category': cat,
                'tag': tag,
                'balance': 0
            })

        zero_df = pd.DataFrame(zero_entries)
        return pd.concat([investments, zero_df], ignore_index=True).sort_values(by='date')

    def _resample_by_tag(
        self,
        investments: pd.DataFrame,
        frequency: str,
        all_transactions: pd.DataFrame
    ) -> pd.DataFrame:
        """Resample investment data by frequency for each tag with forward fill."""
        investments = investments.sort_values(by='date')
        investments = investments.groupby(['category', 'tag', 'date']).last().reset_index()

        earliest_date = all_transactions['date'].min() - pd.Timedelta(days=1)
        latest_date = datetime.datetime.now() + pd.Timedelta(
            days=1 if frequency == 'D' else 30 if frequency == 'M' else 365
        )
        date_range = pd.date_range(start=earliest_date, end=latest_date, freq=frequency)

        reindexed_groups = []
        for (cat, tag), group in investments.groupby(['category', 'tag']):
            group_reindexed = group.set_index('date').reindex(date_range, method='ffill')
            group_reindexed['category'] = cat
            group_reindexed['tag'] = tag
            group_reindexed = group_reindexed.reset_index().rename(columns={'index': 'date'})
            reindexed_groups.append(group_reindexed)

        return pd.concat(reindexed_groups, ignore_index=True).sort_values(by='date')

