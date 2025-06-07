import pandas as pd
from streamlit.connections import SQLConnection
from sqlalchemy import text
from typing import Literal

from fad.app.naming_conventions import Tables, CreditCardTableFields, BankTableFields, TransactionsTableFields


class TransactionsRepository:
    tables = [Tables.CREDIT_CARD.value, Tables.BANK.value]
    account_number_col = TransactionsTableFields.ACCOUNT_NUMBER.value
    type_col = TransactionsTableFields.TYPE.value
    id_col = TransactionsTableFields.ID.value
    date_col = TransactionsTableFields.DATE.value
    desc_col = TransactionsTableFields.DESCRIPTION.value
    amount_col = TransactionsTableFields.AMOUNT.value
    status_col = TransactionsTableFields.STATUS.value
    account_name_col = TransactionsTableFields.ACCOUNT_NAME.value
    provider_col = TransactionsTableFields.PROVIDER.value
    category_col = TransactionsTableFields.CATEGORY.value
    tag_col = TransactionsTableFields.TAG.value

    def __init__(self, conn: SQLConnection):
        """
        Initializes the TransactionsRepository with a database connection.

        Parameters
        ----------
        conn : SQLConnection
            The database connection to use for executing queries.
        """
        self.conn = conn
        self.cc_repo = CreditCardRepository(conn)
        self.bank_repo = BankRepository(conn)

    def update_tagging(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                       account_number: str | None = None) -> None:
        """
        update the tags of the raw data in the credit card and bank tables. If overwrite is True, all occurrences of the
        transaction with the name supplied will be updated. If overwrite is False, only transactions without a tag will
        be updated.

        Parameters
        ----------
        name : str
            the name of the transaction
        category : str
            the category to tag the transaction with
        tag : str
            the tag to tag the transaction with
        service : str
            the service of the transaction, should be one of 'credit_card' or 'bank'
        account_number : str | None
            the account number of the transaction, only used for bank transactions. If None, all transactions with the
            name supplied will be updated

        Returns
        -------
        None
        """
        assert service in ['credit_card', 'bank'], "service must be either 'credit_card' or 'bank'"

        if service == 'credit_card':
            self.cc_repo.update_tagging_by_name(name, category, tag)
        else:
            if account_number is None:
                raise ValueError("account_number should be provided for bank transactions tagging")
            self.bank_repo.update_tagging_by_name_and_account_number(name, account_number, category, tag)

    def update_tagging_by_id(self, id_: int, category: str, tag: str, service: Literal['credit_card', 'bank']) -> None:
        """
        Update the tags of the raw data in the credit card and bank tables by transaction ID.

        Parameters
        ----------
        id_ : int
            The ID of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.
        service : Literal['credit_card', 'bank']
            The service of the transaction, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        None
        """
        assert service in ['credit_card', 'bank'], f"service must be either 'credit_card' or 'bank'. Got '{service}'"

        if service == 'credit_card':
            self.cc_repo.update_tagging_by_id(id_, category, tag)
        else:
            self.bank_repo.update_tagging_by_id(id_, category, tag)

    def get_table(self, service: Literal['credit_card', 'bank']) -> pd.DataFrame:
        """
        Get the transactions table for the specified service.

        Parameters
        ----------
        service : str
            The service of the transactions, should be one of 'credit_card' or 'bank'.

        Returns
        -------
        pd.DataFrame
            The transactions table as a DataFrame.
        """
        assert service in ['credit_card', 'bank'], f"service must be either 'credit_card' or 'bank'. Got '{service}'"

        if service == 'credit_card':
            return self.cc_repo.get_table()
        else:
            return self.bank_repo.get_table()



class ServiceRepository:
    """
    Abstract base class for repositories that handle transactions data.
    This class defines the common interface for repositories that manage transactions data.
    """
    table: str
    desc_col: str
    tag_col: str
    category_col: str
    name_col: str
    id_col: str
    date_col: str
    provider_col: str
    account_name_col: str
    account_number_col: str
    amount_col: str

    def __init__(self, conn: SQLConnection):
        """
        Initializes the repository with a database connection.

        Parameters
        ----------
        conn : SQLConnection
            The database connection to use for executing queries.
        """
        self.conn = conn
        self.assure_table_exists()

    def assure_table_exists(self) -> None:
        """
        Ensure that the transactions table exists in the database.
        If it does not exist, create it with the necessary columns.
        """
        with self.conn.session as s:
            my_query = f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    {self.id_col} INTEGER PRIMARY KEY AUTOINCREMENT,
                    {self.date_col} DATE,
                    {self.provider_col} TEXT,
                    {self.account_name_col} TEXT,
                    {self.account_number_col} TEXT,
                    {self.desc_col} TEXT,
                    {self.amount_col} REAL,
                    {self.category_col} TEXT,
                    {self.tag_col} TEXT
                )
            """
            s.execute(text(my_query))
            s.commit()

    def get_table(self) -> pd.DataFrame:
        """
        Get the transactions table as a DataFrame.
        """
        table = self.conn.query(f'SELECT * FROM {self.table};', ttl=0)
        return table

    def get_table_columns(self) -> list[str]:
        """
        Get the columns of the transactions table.

        Returns
        -------
        list[str]
            A list of column names in the transactions table.
        """
        return [
            self.id_col,
            self.date_col,
            self.provider_col,
            self.account_name_col,
            self.account_number_col,
            self.desc_col,
            self.amount_col,
            self.category_col,
            self.tag_col
        ]

    def update_tagging_by_id(self, id_: int, category: str, tag: str) -> None:
        """
        Update the tags of bank transactions in the database by transaction ID.

        Parameters
        ----------
        id_ : int
            The ID of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.

        Returns
        -------
        None
        """
        with self.conn.session as s:
            my_query = f"""
                UPDATE {self.table}
                SET {self.category_col} = :category_val, {self.tag_col} = :tag_val
                WHERE {self.id_col} = :id_val
            """
            params = {
                'category_val': category,
                'tag_val': tag,
                'id_val': id_
            }
            s.execute(text(my_query), params)
            s.commit()


class CreditCardRepository(ServiceRepository):
    table = Tables.CREDIT_CARD.value
    desc_col = CreditCardTableFields.DESCRIPTION.value
    tag_col = CreditCardTableFields.TAG.value
    category_col = CreditCardTableFields.CATEGORY.value
    name_col = CreditCardTableFields.DESCRIPTION.value
    id_col = CreditCardTableFields.ID.value
    date_col = CreditCardTableFields.DATE.value
    provider_col = CreditCardTableFields.PROVIDER.value
    account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
    account_number_col = CreditCardTableFields.ACCOUNT_NUMBER.value
    amount_col = CreditCardTableFields.AMOUNT.value

    def update_tagging_by_name(self, name: str, category: str, tag: str) -> None:
        """
        Update the tags of credit card transactions in the database.

        Parameters
        ----------
        name : str
            The name of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.


        Returns
        -------
        None
        """
        with self.conn.session as s:
            my_query = f"""
                UPDATE {self.table}
                SET {self.category_col} = :category_val, {self.tag_col} = :tag_val
                WHERE {self.desc_col} = :name_val
            """
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name
            }
            s.execute(text(my_query), params)
            s.commit()


class BankRepository(ServiceRepository):
    table = Tables.BANK.value
    desc_col = BankTableFields.DESCRIPTION.value
    tag_col = BankTableFields.TAG.value
    category_col = BankTableFields.CATEGORY.value
    name_col = BankTableFields.DESCRIPTION.value
    id_col = BankTableFields.ID.value
    account_number_col = BankTableFields.ACCOUNT_NUMBER.value
    date_col = BankTableFields.DATE.value
    provider_col = BankTableFields.PROVIDER.value
    account_name_col = BankTableFields.ACCOUNT_NAME.value
    amount_col = BankTableFields.AMOUNT.value

    def update_tagging_by_name_and_account_number(self, name: str, account_number: str, category: str, tag: str) -> None:
        """
        Update the tags of bank transactions in the database.

        Parameters
        ----------
        name : str
            The name of the transaction.
        account_number : str
            The account number of the transaction.
        category : str
            The category to tag the transaction with.
        tag : str
            The tag to tag the transaction with.
        """
        with self.conn.session as s:
            my_query = f"""
                UPDATE {self.table}
                SET {self.category_col} = :category_val, {self.tag_col} = :tag_val
                WHERE {self.desc_col} = :name_val AND {self.account_number_col} = :account_number_val
            """
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name,
                'account_number_val': account_number
            }
            s.execute(text(my_query), params)
            s.commit()
