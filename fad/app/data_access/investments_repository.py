from datetime import datetime
from typing import Optional

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.sql import text
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.naming_conventions import Tables, InvestmentsTableFields


class InvestmentsRepository:
    """
    Repository for managing investment tracking records.

    Handles CRUD operations for investment records including creation,
    retrieval, balance updates, and lifecycle management (closing/reopening).
    """

    def __init__(self, conn: SQLConnection = get_db_connection()):
        """
        Initialize the investments repository.

        Parameters
        ----------
        conn : SQLConnection, optional
            Database connection to use. Defaults to application's DB connection.
        """
        self.conn = conn
        self.table_name = Tables.INVESTMENTS.value
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """
        Create the investments table if it doesn't exist.

        Creates table with fields for tracking investment lifecycle,
        balances, categorization, and metadata.
        """
        with self.conn.session as s:
            s.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {self.table_name} ("
                    f"{InvestmentsTableFields.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT, "
                    f"{InvestmentsTableFields.CATEGORY.value} TEXT NOT NULL, "
                    f"{InvestmentsTableFields.TAG.value} TEXT, "
                    f"{InvestmentsTableFields.NAME.value} TEXT, "
                    f"{InvestmentsTableFields.CURRENT_BALANCE.value} REAL DEFAULT 0, "
                    f"{InvestmentsTableFields.LAST_BALANCE_UPDATE.value} TEXT, "
                    f"{InvestmentsTableFields.IS_CLOSED.value} INTEGER DEFAULT 0, "
                    f"{InvestmentsTableFields.CREATED_DATE.value} TEXT, "
                    f"{InvestmentsTableFields.CLOSED_DATE.value} TEXT, "
                    f"{InvestmentsTableFields.NOTES.value} TEXT"
                    f");"
                )
            )
            s.commit()

    def get_all(self) -> pd.DataFrame:
        """
        Get all investment tracking records.

        Returns
        -------
        pd.DataFrame
            DataFrame containing all investment records with all fields.
        """
        with self.conn.session as s:
            query = f"SELECT * FROM {self.table_name}"
            result = s.execute(text(query))
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def get_active_investments(self) -> pd.DataFrame:
        """
        Get all active (non-closed) investments.

        Returns
        -------
        pd.DataFrame
            DataFrame containing only investments where is_closed = 0.
        """
        with self.conn.session as s:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE {InvestmentsTableFields.IS_CLOSED.value} = 0
            """
            result = s.execute(text(query))
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def get_closed_investments(self) -> pd.DataFrame:
        """
        Get all closed investments.

        Returns
        -------
        pd.DataFrame
            DataFrame containing only investments where is_closed = 1.
        """
        with self.conn.session as s:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE {InvestmentsTableFields.IS_CLOSED.value} = 1
            """
            result = s.execute(text(query))
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def get_by_category_tag(self, category: str, tag: Optional[str] = None) -> pd.DataFrame:
        """
        Get investment record by category and optionally tag.

        Parameters
        ----------
        category : str
            The investment category to filter by.
        tag : str, optional
            The tag to filter by. If None, searches for records with NULL tag.

        Returns
        -------
        pd.DataFrame
            DataFrame containing matching investment records.
        """
        with self.conn.session as s:
            if tag:
                query = f"""
                    SELECT * FROM {self.table_name}
                    WHERE {InvestmentsTableFields.CATEGORY.value} = :category
                    AND {InvestmentsTableFields.TAG.value} = :tag
                """
                result = s.execute(text(query), {'category': category, 'tag': tag})
            else:
                query = f"""
                    SELECT * FROM {self.table_name}
                    WHERE {InvestmentsTableFields.CATEGORY.value} = :category
                    AND {InvestmentsTableFields.TAG.value} IS NULL
                """
                result = s.execute(text(query), {'category': category})

            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def create_or_update(self, category: str, tag: Optional[str] = None, name: Optional[str] = None,
                         notes: Optional[str] = None) -> int:
        """
        Create a new investment record or update existing one.

        If an investment with the same category and tag exists, updates it.
        Otherwise, creates a new record with the current timestamp.

        Parameters
        ----------
        category : str
            The investment category.
        tag : str, optional
            The tag for additional categorization.
        name : str, optional
            Display name for the investment.
        notes : str, optional
            Additional notes or description.

        Returns
        -------
        int
            ID of the created or updated investment record.
        """
        existing = self.get_by_category_tag(category, tag)

        with self.conn.session as s:
            if not existing.empty:
                investment_id = existing.iloc[0][InvestmentsTableFields.ID.value]
                cmd = sa.text(f"""
                    UPDATE {self.table_name}
                    SET {InvestmentsTableFields.NAME.value} = :name,
                        {InvestmentsTableFields.NOTES.value} = :notes
                    WHERE {InvestmentsTableFields.ID.value} = :id
                """)
                s.execute(cmd, {
                    'name': name,
                    'notes': notes,
                    'id': investment_id
                })
                s.commit()
                return investment_id
            else:
                cmd = sa.text(f"""
                    INSERT INTO {self.table_name} (
                        {InvestmentsTableFields.CATEGORY.value},
                        {InvestmentsTableFields.TAG.value},
                        {InvestmentsTableFields.NAME.value},
                        {InvestmentsTableFields.NOTES.value},
                        {InvestmentsTableFields.CREATED_DATE.value}
                    ) VALUES (:category, :tag, :name, :notes, :created_date)
                """)
                result = s.execute(cmd, {
                    'category': category,
                    'tag': tag,
                    'name': name,
                    'notes': notes,
                    'created_date': datetime.now().isoformat()
                })
                s.commit()
                return result.lastrowid

    def update_current_balance(self, investment_id: int, current_balance: float) -> None:
        """
        Update the current balance of an investment.

        Parameters
        ----------
        investment_id : int
            The ID of the investment to update.
        current_balance : float
            The new current balance value.
        """
        with self.conn.session as s:
            cmd = sa.text(f"""
                UPDATE {self.table_name}
                SET {InvestmentsTableFields.CURRENT_BALANCE.value} = :current_balance,
                    {InvestmentsTableFields.LAST_BALANCE_UPDATE.value} = :last_update
                WHERE {InvestmentsTableFields.ID.value} = :id
            """)
            s.execute(cmd, {
                'current_balance': current_balance,
                'last_update': datetime.now().isoformat(),
                'id': investment_id
            })
            s.commit()

    def close_investment(self, investment_id: int) -> None:
        """
        Mark an investment as closed.

        Sets the is_closed flag to 1 and records the closing date.

        Parameters
        ----------
        investment_id : int
            The ID of the investment to close.
        """
        with self.conn.session as s:
            cmd = sa.text(f"""
                UPDATE {self.table_name}
                SET {InvestmentsTableFields.IS_CLOSED.value} = 1,
                    {InvestmentsTableFields.CLOSED_DATE.value} = :closed_date
                WHERE {InvestmentsTableFields.ID.value} = :id
            """)
            s.execute(cmd, {'closed_date': datetime.now().isoformat(), 'id': investment_id})
            s.commit()

    def reopen_investment(self, investment_id: int) -> None:
        """
        Reopen a closed investment.

        Sets the is_closed flag to 0 and clears the closed_date.

        Parameters
        ----------
        investment_id : int
            The ID of the investment to reopen.
        """
        with self.conn.session as s:
            cmd = sa.text(f"""
                UPDATE {self.table_name}
                SET {InvestmentsTableFields.IS_CLOSED.value} = 0,
                    {InvestmentsTableFields.CLOSED_DATE.value} = NULL
                WHERE {InvestmentsTableFields.ID.value} = :id
            """)
            s.execute(cmd, {'id': investment_id})
            s.commit()

    def get_by_id(self, investment_id: int) -> pd.DataFrame:
        """
        Get a specific investment by its ID.

        Parameters
        ----------
        investment_id : int
            The ID of the investment to retrieve.

        Returns
        -------
        pd.DataFrame
            DataFrame containing the investment record, or empty DataFrame if not found.
        """
        with self.conn.session as s:
            query = f"""
                SELECT * FROM {self.table_name}
                WHERE {InvestmentsTableFields.ID.value} = :id
            """
            result = s.execute(text(query), {'id': investment_id})
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df
