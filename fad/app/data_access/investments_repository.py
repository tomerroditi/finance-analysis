from datetime import datetime

import pandas as pd
from sqlalchemy import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import Tables, InvestmentsTableFields


class InvestmentsRepository:
    """
    Repository for managing investment tracking records.
    Handles CRUD operations for investments that users want to track over time.
    """
    table = Tables.INVESTMENTS.value
    
    # Field names
    id_col = InvestmentsTableFields.ID.value
    category_col = InvestmentsTableFields.CATEGORY.value
    tag_col = InvestmentsTableFields.TAG.value
    type_col = InvestmentsTableFields.TYPE.value
    name_col = InvestmentsTableFields.NAME.value
    is_closed_col = InvestmentsTableFields.IS_CLOSED.value
    created_date_col = InvestmentsTableFields.CREATED_DATE.value
    closed_date_col = InvestmentsTableFields.CLOSED_DATE.value
    notes_col = InvestmentsTableFields.NOTES.value
    
    # Metadata fields (not in enum - flexible schema)
    interest_rate_col = 'interest_rate'
    interest_rate_type_col = 'interest_rate_type'
    commission_deposit_col = 'commission_deposit'
    commission_management_col = 'commission_management'
    commission_withdrawal_col = 'commission_withdrawal'
    liquidity_date_col = 'liquidity_date'
    maturity_date_col = 'maturity_date'
    
    def __init__(self, conn: SQLConnection):
        self.conn = conn
        self.assure_table_exists()
    
    def assure_table_exists(self) -> None:
        with self.conn.session as s:
            s.execute(text(
                f"""CREATE TABLE IF NOT EXISTS {self.table} (
                    {self.id_col} INTEGER PRIMARY KEY AUTOINCREMENT,
                    {self.category_col} TEXT NOT NULL,
                    {self.tag_col} TEXT NOT NULL,
                    {self.type_col} TEXT NOT NULL,
                    {self.name_col} TEXT NOT NULL,
                    {self.interest_rate_col} REAL,
                    {self.interest_rate_type_col} TEXT DEFAULT 'fixed',
                    {self.commission_deposit_col} REAL,
                    {self.commission_management_col} REAL,
                    {self.commission_withdrawal_col} REAL,
                    {self.liquidity_date_col} TEXT,
                    {self.maturity_date_col} TEXT,
                    {self.is_closed_col} INTEGER DEFAULT 0,
                    {self.created_date_col} TEXT NOT NULL,
                    {self.closed_date_col} TEXT,
                    {self.notes_col} TEXT,
                    UNIQUE({self.category_col}, {self.tag_col})
                );"""
            ))
            s.commit()
            
            # Migration: Add interest_rate_type column to existing databases
            result = s.execute(text(f"PRAGMA table_info({self.table})"))
            columns = [row[1] for row in result.fetchall()]
            
            if self.interest_rate_type_col not in columns:
                s.execute(text(f"ALTER TABLE {self.table} ADD COLUMN {self.interest_rate_type_col} TEXT DEFAULT 'fixed'"))
                s.commit()
    
    def create_investment(
        self,
        category: str,
        tag: str,
        type_: str,
        name: str,
        interest_rate: float = None,
        interest_rate_type: str = 'fixed',
        commission_deposit: float = None,
        commission_management: float = None,
        commission_withdrawal: float = None,
        liquidity_date: str = None,
        maturity_date: str = None,
        notes: str = None
    ) -> None:
        with self.conn.session as s:
            cmd = text(f"""
                INSERT INTO {self.table} (
                    {self.category_col}, {self.tag_col}, {self.type_col}, {self.name_col},
                    {self.interest_rate_col}, {self.interest_rate_type_col},
                    {self.commission_deposit_col}, {self.commission_management_col},
                    {self.commission_withdrawal_col}, {self.liquidity_date_col},
                    {self.maturity_date_col}, {self.created_date_col}, {self.notes_col}
                ) VALUES (
                    :category, :tag, :type, :name,
                    :interest_rate, :interest_rate_type,
                    :commission_deposit, :commission_management,
                    :commission_withdrawal, :liquidity_date,
                    :maturity_date, :created_date, :notes
                )
            """)
            s.execute(cmd, {
                'category': category,
                'tag': tag,
                'type': type_,
                'name': name,
                'interest_rate': interest_rate,
                'interest_rate_type': interest_rate_type,
                'commission_deposit': commission_deposit,
                'commission_management': commission_management,
                'commission_withdrawal': commission_withdrawal,
                'liquidity_date': liquidity_date,
                'maturity_date': maturity_date,
                'created_date': datetime.today().strftime('%Y-%m-%d'),
                'notes': notes
            })
            s.commit()
    
    def get_all_investments(self, include_closed: bool = False) -> pd.DataFrame:
        with self.conn.session as s:
            if include_closed:
                query = f"SELECT * FROM {self.table}"
            else:
                query = f"SELECT * FROM {self.table} WHERE {self.is_closed_col} = 0"
            
            result = s.execute(text(query))
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df
    
    def get_by_id(self, investment_id: int) -> pd.DataFrame:
        with self.conn.session as s:
            query = f"SELECT * FROM {self.table} WHERE {self.id_col} = :id"
            result = s.execute(text(query), {'id': investment_id})
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df
    
    def get_by_category_tag(self, category: str, tag: str) -> pd.DataFrame:
        with self.conn.session as s:
            query = f"""
                SELECT * FROM {self.table} 
                WHERE {self.category_col} = :category AND {self.tag_col} = :tag
            """
            result = s.execute(text(query), {'category': category, 'tag': tag})
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df
    
    def update_investment(self, investment_id: int, **fields) -> None:
        if not fields:
            return
        
        set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
        fields['id'] = investment_id
        
        with self.conn.session as s:
            cmd = text(f"UPDATE {self.table} SET {set_clause} WHERE {self.id_col} = :id")
            result = s.execute(cmd, fields)
            s.commit()
            
            if result.rowcount == 0:
                raise ValueError(f"No investment found with ID {investment_id}")
    
    def close_investment(self, investment_id: int, closed_date: str) -> None:
        """
        Close an investment by setting is_closed flag and closed_date.
        
        Parameters
        ----------
        investment_id : int
            Investment ID to close
        closed_date : str
            Date when the investment was closed (YYYY-MM-DD format)
        """
        with self.conn.session as s:
            cmd = text(f"""
                UPDATE {self.table}
                SET {self.is_closed_col} = 1, {self.closed_date_col} = :closed_date
                WHERE {self.id_col} = :id
            """)
            s.execute(cmd, {
                'id': investment_id,
                'closed_date': closed_date
            })
            s.commit()
    
    def reopen_investment(self, investment_id: int) -> None:
        """
        Reopen a closed investment by clearing is_closed flag and closed_date.
        
        Parameters
        ----------
        investment_id : int
            Investment ID to reopen
        """
        with self.conn.session as s:
            cmd = text(f"""
                UPDATE {self.table}
                SET {self.is_closed_col} = 0, {self.closed_date_col} = NULL
                WHERE {self.id_col} = :id
            """)
            s.execute(cmd, {'id': investment_id})
            s.commit()
    
    def delete_investment(self, investment_id: int) -> None:
        with self.conn.session as s:
            cmd = text(f"DELETE FROM {self.table} WHERE {self.id_col} = :id")
            result = s.execute(cmd, {'id': investment_id})
            s.commit()
            
            if result.rowcount == 0:
                raise ValueError(f"No investment found with ID {investment_id}")
