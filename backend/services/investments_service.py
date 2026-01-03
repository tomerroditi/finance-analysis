"""
Investments service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for investment tracking and analysis.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
from sqlalchemy.orm import Session

from backend.repositories.investments_repository import InvestmentsRepository
from backend.services.transactions_service import TransactionsService
from fad.app.naming_conventions import InvestmentsType


class InvestmentsService:
    """
    Service for managing investments with business logic for balance calculations,
    profit/loss tracking, and investment lifecycle management.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.investments_repo = InvestmentsRepository(db)
        self.transactions_service = TransactionsService(db)
    
    def get_portfolio_overview(self) -> Dict[str, Any]:
        """
        Get portfolio-level metrics and allocation data.
        """
        investments = self.investments_repo.get_all_investments(include_closed=False)
        
        if investments.empty:
            return {
                "total_value": 0.0,
                "total_profit": 0.0,
                "portfolio_roi": 0.0,
                "allocation": []
            }
        
        total_value = 0.0
        total_deposits = 0.0
        total_withdrawals = 0.0
        allocation = []
        
        for _, inv in investments.iterrows():
            metrics = self.calculate_profit_loss(inv['id'])
            
            total_value += metrics['current_balance']
            total_deposits += metrics['total_deposits']
            total_withdrawals += metrics['total_withdrawals']
            
            allocation.append({
                "name": inv['name'],
                "balance": metrics['current_balance'],
                "type": inv['type']
            })
            
        total_profit = total_value - (total_deposits - total_withdrawals)
        portfolio_roi = ((total_value / total_deposits) - 1) * 100 if total_deposits > 0 else 0.0
        
        return {
            "total_value": total_value,
            "total_profit": total_profit,
            "portfolio_roi": portfolio_roi,
            "allocation": allocation
        }

    def calculate_current_balance(self, investment_id: int) -> float:
        """
        Calculate current balance from ALL transaction sources.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return 0.0
        
        inv = investment.iloc[0]
        
        if inv['is_closed']:
            return 0.0
        
        transactions_df = self._get_all_transactions_for_investment(inv['category'], inv['tag'])
        return self._calculate_balance_from_transactions(transactions_df)
    
    def calculate_balance_over_time(
        self,
        investment_id: int,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Calculate balance at daily intervals for charting.
        Returns a list of dicts suitable for JSON response.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return []
        
        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(inv['category'], inv['tag'])
        
        if transactions_df.empty:
            return []
        
        # For closed investments, stop at closed_date
        actual_end_date = end_date
        if inv['is_closed'] and inv['closed_date']:
            closed_date = datetime.strptime(inv['closed_date'], '%Y-%m-%d').date()
            requested_end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            actual_end_date = min(closed_date, requested_end_date).strftime('%Y-%m-%d')
        
        dates = pd.date_range(start=start_date, end=actual_end_date, freq='D')
        
        balances = []
        for date in dates:
            balance = self._calculate_balance_from_transactions(
                transactions_df,
                as_of_date=date.strftime('%Y-%m-%d')
            )
            balances.append({'date': date.strftime('%Y-%m-%d'), 'balance': balance})
        
        if inv['is_closed'] and inv['closed_date']:
            balances.append({'date': inv['closed_date'], 'balance': 0.0})
        
        return balances
    
    def calculate_profit_loss(self, investment_id: int) -> Dict[str, Any]:
        """
        Calculate comprehensive profit/loss metrics.
        """
        investment = self.investments_repo.get_by_id(investment_id)     
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
        
        # Ensure numeric type for amount
        if 'amount' in transactions_df.columns:
             transactions_df['amount'] = pd.to_numeric(transactions_df['amount'], errors='coerce').fillna(0.0)

        # Transaction sign: Negative = deposit (money OUT), Positive = withdrawal (money IN)
        total_deposits = abs(transactions_df[transactions_df['amount'] < 0]['amount'].sum())
        total_withdrawals = transactions_df[transactions_df['amount'] > 0]['amount'].sum()
        net_invested = total_deposits - total_withdrawals
        
        if inv['is_closed']:
            current_balance = 0.0
            absolute_profit_loss = total_withdrawals - total_deposits
        else:
            current_balance = self._calculate_balance_from_transactions(transactions_df)
            absolute_profit_loss = current_balance - net_invested
        
        final_value = total_withdrawals if inv['is_closed'] else current_balance + total_withdrawals
        roi_percentage = ((final_value / total_deposits) - 1) * 100 if total_deposits > 0 else 0.0
        
        transactions_df = transactions_df.copy()
        transactions_df['date'] = pd.to_datetime(transactions_df['date'])
        first_date = transactions_df['date'].min().date()
        last_date = datetime.today().date()
        if inv['is_closed'] and inv['closed_date']:
            last_date = datetime.strptime(inv['closed_date'], '%Y-%m-%d').date()
        total_years = max((last_date - first_date).days / 365.25, 0.01) # Avoid division by zero
        
        cagr_percentage = 0.0
        if total_deposits > 0 and total_years > 0 and final_value > 0:
            cagr_percentage = ((final_value / total_deposits) ** (1 / total_years) - 1) * 100
        
        return {
            'total_deposits': float(total_deposits),
            'total_withdrawals': float(total_withdrawals),
            'net_invested': float(net_invested),
            'current_balance': float(current_balance),
            'absolute_profit_loss': float(absolute_profit_loss),
            'roi_percentage': float(roi_percentage),
            'total_years': float(total_years),
            'cagr_percentage': float(cagr_percentage),
            'first_transaction_date': first_date.strftime('%Y-%m-%d'),
        }

    def _get_all_transactions_for_investment(self, category: str, tag: str) -> pd.DataFrame:
        """Fetch ALL transactions for given category/tag."""
        return self.transactions_service.get_transactions_by_tag(category, tag)
    
    def _calculate_balance_from_transactions(
        self,
        transactions_df: pd.DataFrame,
        as_of_date: Optional[str] = None
    ) -> float:
        """
        Calculate balance from transactions.
        Deposits are negative amounts (money leaving account to investment), 
        so we negate them to get positive balance.
        """
        if as_of_date is None:
            as_of_date = datetime.today().date()
        else:
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        if transactions_df.empty:
            return 0.0
        
        transactions_df = transactions_df.copy()
        transactions_df['date'] = pd.to_datetime(transactions_df['date'])
        
        filtered_df = transactions_df.loc[transactions_df['date'].dt.date <= as_of_date]
        
        if filtered_df.empty:
            return 0.0
            
        if 'amount' not in filtered_df.columns:
            return 0.0
            
        filtered_df.loc[:, 'amount'] = pd.to_numeric(filtered_df.loc[:, 'amount'], errors='coerce').fillna(0.0)
        
        # Balance = -(sum of all transactions)
        # If I deposited -1000, balance is +1000.
        # If I withdrew +200, balance is -(-1000 + 200) = -(-800) = 800.
        balance = -filtered_df.loc[:, 'amount'].sum()
        
        return float(balance)
