from datetime import datetime
from typing import Optional

import pandas as pd
from streamlit.connections import SQLConnection

from fad.app.data_access import get_db_connection
from fad.app.data_access.investments_repository import InvestmentsRepository
from fad.app.services.transactions_service import TransactionsService
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.naming_conventions import SavingsAndInvestmentsCategories, InvestmentsType


class InvestmentsService:
    """
    Service for managing investments with business logic for balance calculations,
    profit/loss tracking, and investment lifecycle management.
    """
    
    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.conn = conn
        self.investments_repo = InvestmentsRepository(conn)
        self.transactions_service = TransactionsService(conn)
        self.categories_service = CategoriesTagsService()
    
    def add_investment(
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
    ) -> tuple[bool, str]:
        """
        Add a new investment with validation.
        
        Returns
        -------
        tuple[bool, str]
            (success, error_message)
        """
        # Validation
        if not name or not name.strip():
            return False, "Investment name is required"
        
        if not category or not tag:
            return False, "Category and tag are required"
        
        if type_ not in [e.value for e in InvestmentsType]:
            return False, f"Invalid investment type: {type_}"
        
        # Check if investment with same category/tag already exists
        existing = self.investments_repo.get_by_category_tag(category, tag)
        if not existing.empty:
            return False, f"Investment already exists for {category} - {tag}"
        
        try:
            self.investments_repo.create_investment(
                category=category,
                tag=tag,
                type_=type_,
                name=name,
                interest_rate=interest_rate,
                interest_rate_type=interest_rate_type,
                commission_deposit=commission_deposit,
                commission_management=commission_management,
                commission_withdrawal=commission_withdrawal,
                liquidity_date=liquidity_date,
                maturity_date=maturity_date,
                notes=notes
            )
            return True, ""
        except Exception as e:
            return False, f"Failed to create investment: {str(e)}"
    
    def get_all_investments(self, include_closed: bool = False) -> pd.DataFrame:
        """Get all investments."""
        return self.investments_repo.get_all_investments(include_closed)
    
    def get_investment_by_id(self, investment_id: int) -> pd.DataFrame:
        """Get investment by ID."""
        return self.investments_repo.get_by_id(investment_id)
    
    def update_investment(self, investment_id: int, **fields) -> tuple[bool, str]:
        """
        Update investment fields with validation.
        
        Returns
        -------
        tuple[bool, str]
            (success, error_message)
        """
        try:
            self.investments_repo.update_investment(investment_id, **fields)
            return True, ""
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Failed to update investment: {str(e)}"
    
    def close_investment(self, investment_id: int) -> tuple[bool, str]:
        """
        Close an investment using the date of the last transaction as the close date.
        If no transactions exist, uses today's date.
        
        Parameters
        ----------
        investment_id : int
            Investment ID to close
        
        Returns
        -------
        tuple[bool, str]
            (success, error_message)
        """
        try:
            transactions_df = self.get_transactions_for_investment(investment_id)
            
            if transactions_df.empty:
                closed_date = datetime.today().strftime('%Y-%m-%d')
            else:
                date_col = 'date'
                transactions_df[date_col] = pd.to_datetime(transactions_df[date_col])
                last_transaction_date = transactions_df[date_col].max()
                closed_date = last_transaction_date.strftime('%Y-%m-%d')
            
            self.investments_repo.close_investment(investment_id, closed_date)
            return True, ""
        except Exception as e:
            return False, f"Failed to close investment: {str(e)}"
    
    def reopen_investment(self, investment_id: int) -> tuple[bool, str]:
        """
        Reopen a closed investment.
        
        Parameters
        ----------
        investment_id : int
            Investment ID to reopen
        
        Returns
        -------
        tuple[bool, str]
            (success, error_message)
        """
        try:
            # Check if investment exists and is closed
            investment = self.investments_repo.get_by_id(investment_id)
            if investment.empty:
                return False, "Investment not found"
            
            if not investment.iloc[0]['is_closed']:
                return False, "Investment is already open"
            
            self.investments_repo.reopen_investment(investment_id)
            return True, ""
        except Exception as e:
            return False, f"Failed to reopen investment: {str(e)}"
    
    def delete_investment(self, investment_id: int) -> tuple[bool, str]:
        """Delete an investment."""
        try:
            self.investments_repo.delete_investment(investment_id)
            return True, ""
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Failed to delete investment: {str(e)}"
    
    def calculate_current_balance(self, investment_id: int) -> float:
        """
        Calculate current balance from ALL transaction sources.
        For closed investments, returns 0 (no money remains in the investment).
        For active investments, calculates balance based on transactions only (no interest).
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return 0.0
        
        inv = investment.iloc[0]
        
        # Closed investments have 0 balance (money withdrawn/transferred out)
        if inv['is_closed']:
            return 0.0
        
        transactions_df = self._get_all_transactions_for_investment(inv['category'], inv['tag'])
        
        return self._calculate_balance_from_transactions(transactions_df)
    
    def calculate_balance_over_time(
        self,
        investment_id: int,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Calculate balance at daily intervals for charting (transactions only, no interest).
        For closed investments, stops at closed_date.
        
        Returns
        -------
        pd.DataFrame
            Columns: [date, balance]
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return pd.DataFrame()
        
        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(inv['category'], inv['tag'])
        
        if transactions_df.empty:
            return pd.DataFrame({'date': [], 'balance': []})
        
        # For closed investments, stop at closed_date
        actual_end_date = end_date
        if inv['is_closed'] and inv['closed_date']:
            closed_date = datetime.strptime(inv['closed_date'], '%Y-%m-%d').date()
            requested_end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            actual_end_date = min(closed_date, requested_end_date).strftime('%Y-%m-%d')
        
        # Generate daily date range
        dates = pd.date_range(start=start_date, end=actual_end_date, freq='D')
        
        balances = []
        for date in dates:
            balance = self._calculate_balance_from_transactions(
                transactions_df,
                as_of_date=date.strftime('%Y-%m-%d')
            )
            balances.append({'date': date.strftime('%Y-%m-%d'), 'balance': balance})
        
        # For closed investments, add final point at 0
        if inv['is_closed'] and inv['closed_date']:
            balances.append({'date': inv['closed_date'], 'balance': 0.0})
        
        return pd.DataFrame(balances)
    
    def calculate_profit_loss(self, investment_id: int) -> dict:
        """
        Calculate comprehensive profit/loss metrics.
        For closed investments: current_balance = 0, P/L based on total withdrawals vs deposits.
        For active investments: current_balance from transactions, P/L = balance - net_invested.
        
        Returns
        -------
        dict
            Profit/loss metrics including ROI
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return {}
        
        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(inv['category'], inv['tag'])
        
        if transactions_df.empty:
            return {
                'total_deposits': 0.0,
                'total_withdrawals': 0.0,
                'net_invested': 0.0,
                'current_balance': 0.0,
                'absolute_profit_loss': 0.0,
                'roi_percentage': 0.0,
                'total_years': 0.0,
                'cagr_percentage': 0.0,
                'first_transaction_date': None,
            }
        
        # Transaction sign: Negative = deposit (money OUT), Positive = withdrawal (money IN)
        total_deposits = abs(transactions_df[transactions_df['amount'] < 0]['amount'].sum())
        total_withdrawals = transactions_df[transactions_df['amount'] > 0]['amount'].sum()
        net_invested = total_deposits - total_withdrawals
        
        # For closed investments: balance is 0, P/L is total withdrawals - total deposits
        if inv['is_closed']:
            current_balance = 0.0
            absolute_profit_loss = total_withdrawals - total_deposits
        else:
            # For active investments: calculate current balance from transactions
            current_balance = self._calculate_balance_from_transactions(transactions_df)
            absolute_profit_loss = current_balance - net_invested
        
        # ROI = (final_value / total_deposits - 1) * 100
        # For closed: final_value = total_withdrawals
        # For active: final_value = current_balance + total_withdrawals
        final_value = total_withdrawals if inv['is_closed'] else current_balance + total_withdrawals
        roi_percentage = ((final_value / total_deposits) - 1) * 100 if total_deposits > 0 else 0.0
        
        # Holding period
        transactions_df = transactions_df.copy()
        transactions_df['date'] = pd.to_datetime(transactions_df['date'])
        first_date = transactions_df['date'].min().date()
        last_date = datetime.today().date()
        if inv['is_closed']:
            last_date = datetime.strptime(inv['closed_date'], '%Y-%m-%d').date()
        total_years = (last_date - first_date).days / 365.25
        
        # CAGR (Compound Annual Growth Rate) - annualized return
        # Formula: CAGR = ((final_value / total_deposits)^(1/years) - 1) * 100
        cagr_percentage = 0.0
        if total_deposits > 0 and total_years > 0:
            cagr_percentage = ((final_value / total_deposits) ** (1 / total_years) - 1) * 100
        
        return {
            'total_deposits': total_deposits,
            'total_withdrawals': total_withdrawals,
            'net_invested': net_invested,
            'current_balance': current_balance,
            'absolute_profit_loss': absolute_profit_loss,
            'roi_percentage': roi_percentage,
            'total_years': total_years,
            'cagr_percentage': cagr_percentage,
            'first_transaction_date': first_date.strftime('%Y-%m-%d'),
        }
    
    def get_available_tags(self, exclude_used: bool = True) -> dict:
        """
        Get available tags from Savings and Investments categories.
        
        Parameters
        ----------
        exclude_used : bool
            If True, exclude category/tag combinations already tracked
        
        Returns
        -------
        dict
            {category: [tags]} with unused tags only if exclude_used=True
        """
        categories_and_tags = self.categories_service.get_categories_and_tags()
        
        result = {}
        for cat_enum in SavingsAndInvestmentsCategories:
            category = cat_enum.value
            if category in categories_and_tags:
                result[category] = categories_and_tags[category].copy()
        
        if exclude_used:
            # Get all existing investments (including closed to prevent reuse)
            existing = self.investments_repo.get_all_investments(include_closed=True)
            
            # Filter out used combinations
            for _, inv in existing.iterrows():
                if inv['category'] in result and inv['tag'] in result[inv['category']]:
                    result[inv['category']].remove(inv['tag'])
            
            # Remove empty categories
            result = {k: v for k, v in result.items() if v}
        
        return result
    
    def is_investment_closed(self, investment_id: int) -> bool:
        """
        Check if an investment is closed.
        
        Parameters
        ----------
        investment_id : int
            Investment ID to check
        
        Returns
        -------
        bool
            True if investment is closed, False otherwise
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return False
        return bool(investment.iloc[0]['is_closed'])
    
    def get_transactions_for_investment(self, investment_id: int) -> pd.DataFrame:
        """Get all transactions for an investment."""
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return pd.DataFrame()
        
        inv = investment.iloc[0]
        return self._get_all_transactions_for_investment(inv['category'], inv['tag'])
    
    def _get_all_transactions_for_investment(self, category: str, tag: str) -> pd.DataFrame:
        """
        Fetch ALL transactions (CC, bank, cash, manual) for given category/tag.
        Uses existing TransactionsService method.
        """
        return self.transactions_service.get_transactions_by_tag(category, tag)
    
    def _calculate_balance_from_transactions(
        self,
        transactions_df: pd.DataFrame,
        as_of_date: Optional[str] = None
    ) -> float:
        """
        Calculate investment balance from transactions only (no interest calculations).
        This is the actual balance based on deposits and withdrawals.
        
        Parameters
        ----------
        transactions_df : pd.DataFrame
            All transactions for the investment
        as_of_date : str, optional
            Calculate balance as of this date (YYYY-MM-DD). If None, uses today.
        
        Returns
        -------
        float
            Current balance based on transactions only
        """
        if as_of_date is None:
            as_of_date = datetime.today().date()
        else:
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        if transactions_df.empty:
            return 0.0
        
        transactions_df = transactions_df.copy()
        transactions_df['date'] = pd.to_datetime(transactions_df['date'])
        
        # Filter transactions up to as_of_date
        filtered_df = transactions_df[transactions_df['date'].dt.date <= as_of_date]
        
        if filtered_df.empty:
            return 0.0
        
        # Sum all transactions: Negative = deposit (add to balance), Positive = withdrawal (subtract from balance)
        # Flip the sign: deposits are negative amounts, so negate to make them positive contributions
        balance = -filtered_df['amount'].sum()
        
        return balance
    
    def _calculate_balance_with_interest(
        self,
        investment: pd.Series,
        transactions_df: pd.DataFrame,
        as_of_date: Optional[str] = None
    ) -> float:
        """
        Calculate investment balance with estimated compound interest.
        
        NOTE: This method is for FUTURE USE to display estimated balance with interest rates.
        Currently NOT used in calculations - we use actual transaction balances only.
        Will be used later to show estimated current balance with margins.
        
        Parameters
        ----------
        investment : pd.Series
            Investment record with interest_rate and other metadata
        transactions_df : pd.DataFrame
            All transactions for the investment
        as_of_date : str, optional
            Calculate balance as of this date (YYYY-MM-DD)
        
        Returns
        -------
        float
            Estimated balance with compound interest applied
        """
        if as_of_date is None:
            as_of_date = datetime.today().date()
        else:
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        if transactions_df.empty:
            return 0.0
        
        transactions_df = transactions_df.sort_values('date').copy()
        
        balance = 0.0
        previous_date = None
        
        for _, txn in transactions_df.iterrows():
            txn_date = datetime.strptime(txn['date'], '%Y-%m-%d').date()
            
            if txn_date > as_of_date:
                break
            
            # Apply interest from previous transaction to this one
            if previous_date and self._should_apply_interest(investment['type']):
                days_elapsed = (txn_date - previous_date).days
                daily_rate = (investment.get('interest_rate') or 0) / 365 / 100
                balance *= (1 + daily_rate) ** days_elapsed
            
            # Apply transaction amount (negative = deposit, positive = withdrawal)
            if txn['amount'] < 0:  # Deposit
                deposit_amount = abs(txn['amount'])
                if investment.get('commission_deposit'):
                    deposit_amount -= (deposit_amount * investment['commission_deposit'] / 100)
                balance += deposit_amount
            else:  # Withdrawal
                withdrawal_amount = txn['amount']
                if investment.get('commission_withdrawal'):
                    withdrawal_amount += (withdrawal_amount * investment['commission_withdrawal'] / 100)
                balance -= withdrawal_amount
            
            previous_date = txn_date
        
        # Apply interest from last transaction to as_of_date
        if previous_date and self._should_apply_interest(investment['type']):
            days_elapsed = (as_of_date - previous_date).days
            daily_rate = (investment.get('interest_rate') or 0) / 365 / 100
            balance *= (1 + daily_rate) ** days_elapsed
        
        # Apply annual management fee (pro-rated)
        if investment.get('commission_management') and previous_date:
            years_held = (as_of_date - previous_date).days / 365
            balance -= (balance * investment['commission_management'] / 100 * years_held)
        
        return balance
    
    def _should_apply_interest(self, investment_type: str) -> bool:
        """Check if investment type should have compound interest applied."""
        interest_types = [
            InvestmentsType.PAKAM.value,
            InvestmentsType.BONDS.value,
            InvestmentsType.PENSION.value,
            InvestmentsType.STUDY_FUNDS.value,
            InvestmentsType.P2P_LENDING.value
        ]
        return investment_type in interest_types
