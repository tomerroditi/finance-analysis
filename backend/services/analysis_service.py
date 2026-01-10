from typing import Optional
from sqlalchemy.orm import Session
from backend.repositories.transactions_repository import TransactionsRepository
from fad.app.naming_conventions import (
    NonExpensesCategories, 
    IncomeCategories, 
    LiabilitiesCategories
)
import pandas as pd


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TransactionsRepository(db)

    def get_overview(self):
        """
        Get a financial overview including totals and latest data date.
        """
        # Get latest dates
        dates = []
        for table in self.repo.tables:
            date = self.repo.get_latest_date_from_table(table)
            if date:
                dates.append(date)
        
        # Get transaction counts
        all_transactions = self.repo.get_table()
        
        return {
            "latest_data_date": max(dates).isoformat() if dates else None,
            "total_transactions": len(all_transactions),
        }

    def get_total_income(self, start_date: Optional[str] = None, end_date: Optional[str] = None):
        df = self.repo.get_table()
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]
        return df[df['category'].isin([c.value for c in IncomeCategories])]['amount'].sum()

    def get_total_expenses(self, start_date: Optional[str] = None, end_date: Optional[str] = None):
        df = self.repo.get_table()
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]
        return abs(df[~df['category'].isin([c.value for c in NonExpensesCategories])]['amount'].sum())

    def get_expenses_by_category(self):
        """
        Get expenses grouped by category.
        """
        df = self.repo.get_table()
        
        if df.empty:
            return []
        
        expense_mask = ~df['category'].isin([c.value for c in NonExpensesCategories])
        expenses = df[expense_mask].copy()
        expenses['category'] = expenses['category'].fillna('Uncategorized')
        grouped = expenses.groupby('category')['amount'].sum()
        neg_grouped = grouped[grouped < 0].abs()
        pos_grouped = grouped[grouped > 0]
        return {"expenses": [
            {"category": cat, "amount": float(amt)}
            for cat, amt in neg_grouped.items()
        ], "refunds": [
            {"category": cat, "amount": float(amt)}
            for cat, amt in pos_grouped.items()
        ]}

    def get_monthly_trend(self):
        """
        Get monthly income and outcome trends.
        """
        df = self.repo.get_table()
        
        if df.empty:
            return []
        
        df['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
        
        trend = []
        
        for month, group in df.groupby('month'):
            salary_mask = (group['amount'] > 0) & (group['category'] == IncomeCategories.SALARY.value)
            salary = group[salary_mask]['amount'].sum()
            
            other_income_mask = (group['amount'] > 0) & (group['category'] != IncomeCategories.SALARY.value)
            other_income = group[other_income_mask]['amount'].sum()
            
            outcome_mask = (group['amount'] < 0) & (~group['category'].isin([c.value for c in NonExpensesCategories]))
            outcome = abs(group[outcome_mask]['amount'].sum())
            
            trend.append({
                "month": month,
                "salary": float(salary),
                "other_income": float(other_income),
                "outcome": float(outcome)
            })
        
        return sorted(trend, key=lambda x: x['month'])

    def get_sankey_data(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
        """
        Get data for Sankey diagram.
        """
        df = self.repo.get_table(include_split_parents=False)
 
        # Date Filtering
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]
        
        if df.empty:
            return {"nodes": [], "links": []}

        # --- Processing ---
        IGNORE = NonExpensesCategories.IGNORE.value
        SALARY = IncomeCategories.SALARY.value
        OTHER_INCOME = IncomeCategories.OTHER_INCOME.value
        LIABILITIES = LiabilitiesCategories.LIABILITIES.value
        SAVINGS = NonExpensesCategories.SAVINGS.value
        INVESTMENTS = NonExpensesCategories.INVESTMENTS.value
            
        total_income_node = "Total Income"
        
        # Initialize Aggregates
        sources = {} # name -> amount
        destinations = {} # name -> amount
        helpers = {} # name -> amount

        df = df[df['category'] != IGNORE]

        sources[SALARY] = df[df['category'] == SALARY]['amount'].sum()
        sources[OTHER_INCOME] = df[df['category'] == OTHER_INCOME]['amount'].sum()
        sources["Loans"] = df[(df['category'] == LIABILITIES) & (df['amount'] > 0)]['amount'].sum()
        # sources["Savings Withdrawal"] = df[(df['category'].isin([SAVINGS, INVESTMENTS])) & (df['amount'] > 0)]['amount'].sum()

        destinations["Paid Debt"] = abs(df[(df['category'] == LIABILITIES) & (df['amount'] < 0)]['amount'].sum())
        # destinations["Savings Deposit"] = abs(df[(df['category'].isin([SAVINGS, INVESTMENTS])) & (df['amount'] < 0)]['amount'].sum())

        exclude_cats = [SALARY, OTHER_INCOME, LIABILITIES, SAVINGS, INVESTMENTS, IGNORE]
        expenses_df = df[~df['category'].isin(exclude_cats)]
        for cat, group in expenses_df.groupby('category'):
            net = group['amount'].sum()
            if net > 0:
                sources[f"Refunds: {cat}"] = net
            elif net < 0:
                destinations[cat] = abs(net)

        # TODO: we need to account for payments and allocations from filtered out data to correctly calculate it
        helpers["Debt To Be Paid"] = df[(df['category'] == LIABILITIES)]['amount'].sum()
        net = sum(sources.values()) - sum(destinations.values())
        if net < 0:
            sources["Wealth Deficit"] = abs(net)
        else:
            destinations["Wealth Growth"] = net

        # --- Calculate Flows ---
        nodes: list[str] = []
        links: list[dict] = []
        
        def get_node_idx(name) -> int:
            if name not in nodes:
                nodes.append(name)
            return nodes.index(name)
        
        # Layer 1: Sources (income) -> grouped sources (salary, debt, wealth deficit)
        for name, val in sources.items():
            links.append({
                "source": get_node_idx(name),
                "target": get_node_idx(total_income_node),
                "value": round(val, 2),
                "label": ""
            })
        
        # Layer 2: Total Budget -> Destinations
        for name, val in destinations.items():
            links.append({
                "source": get_node_idx(total_income_node),
                "target": get_node_idx(name),
                "value": round(val, 2),
                "label": ""
            })
            
        return {
            "nodes": sorted(nodes, key=lambda x: (x != total_income_node, x)),
            "node_labels": nodes,
            "links": links
        }