import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from fad.app.services.investments_service import InvestmentsService
from fad.app.services.transactions_service import TransactionsService
from fad.app.naming_conventions import InvestmentsType, InterestRateType


class InvestmentsComponent:
    """
    Component for managing investments portfolio with tracking, analysis, and manual transactions.
    """
    
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
        self.service = InvestmentsService()
        self.transactions_service = TransactionsService()
    
    def render(self) -> None:
        """Main entry point - orchestrates all tabs."""
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Portfolio Overview",
            "⚙️ Manage Investments",
            "💰 Manual Transactions",
            "📈 Analysis"
        ])
        
        with tab1:
            self._display_portfolio_overview()
        
        with tab2:
            self._display_manage_investments()
        
        with tab3:
            self._display_manual_transactions()
        
        with tab4:
            self._display_analysis()
    
    def _display_portfolio_overview(self) -> None:
        """Tab 1: Portfolio overview with metrics and charts."""
        st.markdown("### 📊 Portfolio Overview")
        
        investments = self.service.get_all_investments(include_closed=False)
        
        if investments.empty:
            st.info("No active investments. Add your first investment in the 'Manage Investments' tab.")
            return
        
        # Calculate portfolio-level metrics
        total_value = 0.0
        total_deposits = 0.0
        total_withdrawals = 0.0
        
        investment_data = []
        
        for _, inv in investments.iterrows():
            metrics = self.service.calculate_profit_loss(inv['id'])
            
            total_value += metrics['current_balance']
            total_deposits += metrics['total_deposits']
            total_withdrawals += metrics['total_withdrawals']
            
            investment_data.append({
                'ID': inv['id'],
                'Name': inv['name'],
                'Type': inv['type'],
                'Tag': inv['tag'],
                'Opened Date': metrics['first_transaction_date'],
                'Years': metrics['total_years'],
                'Balance': metrics['current_balance'],
                'P/L': metrics['absolute_profit_loss'],
                'ROI': metrics['roi_percentage'],
                'CAGR': metrics['cagr_percentage'],
            })
        
        # Portfolio-level metrics
        total_profit = total_value - (total_deposits - total_withdrawals)
        portfolio_roi = ((total_value / total_deposits) - 1) * 100 if total_deposits > 0 else 0.0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Value", f"₪{total_value:,.2f}")
        col2.metric("Total P/L", f"₪{total_profit:+,.2f}")
        col3.metric("Portfolio ROI", f"{portfolio_roi:+.2f}%")
        
        # Investments table
        st.markdown("### 📈 Active Investments")
        if investment_data:
            df = pd.DataFrame(investment_data)
            df_display = df.copy()
            df_display['Years'] = df_display['Years'].apply(lambda x: f"{x:.2f}")
            df_display['Balance'] = df_display['Balance'].apply(lambda x: f"₪{x:,.2f}")
            df_display['P/L'] = df_display['P/L'].apply(lambda x: f"₪{x:+,.2f}")
            df_display['ROI'] = df_display['ROI'].apply(lambda x: f"{x:+.2f}%")
            df_display['CAGR'] = df_display['CAGR'].apply(lambda x: f"{x:+.2f}%")
            
            st.dataframe(
                df_display.drop(columns=['ID']),
                use_container_width=True,
                hide_index=True,
                key=f"portfolio_table_{self.key_suffix}"
            )
            
            # Portfolio allocation pie chart
            st.markdown("### 📊 Portfolio Allocation")
            fig = px.pie(
                df,
                values='Balance',
                names='Name',
                title='Portfolio by Investment'
            )
            st.plotly_chart(fig, use_container_width=True, key=f"allocation_chart_{self.key_suffix}")
        
        # Show closed investments toggle
        if st.toggle("Show Closed Investments", key=f"show_closed_{self.key_suffix}"):
            self._display_closed_investments()
    
    def _display_closed_investments(self) -> None:
        """Display closed investments."""
        closed = self.service.get_all_investments(include_closed=True)
        closed = closed[closed['is_closed'] == 1]
        
        if closed.empty:
            st.info("No closed investments.")
            return
        
        st.markdown("### 🔒 Closed Investments")
        
        closed_data = []
        for _, inv in closed.iterrows():
            metrics = self.service.calculate_profit_loss(inv['id'])
            closed_data.append({
                'Name': inv['name'],
                'Type': inv['type'],
                'Opened Date': metrics['first_transaction_date'],
                'Closed Date': inv['closed_date'],
                'Years': f"{metrics['total_years']:.2f}",
                'Final Balance': f"₪{metrics['current_balance']:,.2f}",
                'P/L': f"₪{metrics['absolute_profit_loss']:+,.2f}",
                'ROI': f"{metrics['roi_percentage']:+.2f}%",
                'CAGR': f"{metrics['cagr_percentage']:+.2f}%"
            })
        
        if closed_data:
            df = pd.DataFrame(closed_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    def _display_manage_investments(self) -> None:
        """Tab 2: Add/edit/close investments."""
        st.markdown("### ⚙️ Manage Investments")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("➕ Add New Investment", key=f"add_inv_btn_{self.key_suffix}", use_container_width=True):
                self._add_investment_dialog()
        
        # Active investments section
        st.markdown("### 📋 Active Investments")
        active_investments = self.service.get_all_investments(include_closed=False)
        
        if active_investments.empty:
            st.info("No active investments. Click 'Add New Investment' to get started.")
        else:
            for _, inv in active_investments.iterrows():
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                    
                    with col1:
                        st.markdown(f"**{inv['name']}** ({inv['type']})")
                        st.caption(f"Category: {inv['category']} | Tag: {inv['tag']}")
                    
                    with col2:
                        if st.button("✏️ Edit", key=f"edit_inv_{inv['id']}_{self.key_suffix}"):
                            self._edit_investment_dialog(inv['id'])
                    
                    with col3:
                        if st.button("🔒 Close", key=f"close_inv_{inv['id']}_{self.key_suffix}"):
                            success, msg = self.service.close_investment(inv['id'])
                            if success:
                                st.success(f"Closed investment: {inv['name']}")
                                st.rerun()
                            else:
                                st.error(msg)
                    
                    with col4:
                        if st.button("🗑️ Delete", key=f"delete_active_inv_{inv['id']}_{self.key_suffix}", type="secondary"):
                            self._confirm_delete_investment_dialog(inv['id'], inv['name'])
        
        # Closed investments section
        st.markdown("---")
        st.markdown("### 🔒 Closed Investments")
        self._display_closed_investments_manage()
    
    def _display_closed_investments_manage(self) -> None:
        """Display closed investments in manage tab."""
        closed = self.service.get_all_investments(include_closed=True)
        closed = closed[closed['is_closed'] == 1]
        
        if closed.empty:
            st.info("No closed investments.")
            return
        
        for _, inv in closed.iterrows():
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.markdown(f"**{inv['name']}** ({inv['type']}) - Closed on {inv['closed_date']}")
                    st.caption(f"Category: {inv['category']} | Tag: {inv['tag']}")
                
                with col2:
                    if st.button("🔓 Reopen", key=f"reopen_inv_{inv['id']}_{self.key_suffix}"):
                        success, msg = self.service.reopen_investment(inv['id'])
                        if success:
                            st.success(f"Reopened investment: {inv['name']}")
                            st.rerun()
                        else:
                            st.error(msg)
                
                with col3:
                    if st.button("📊 View", key=f"view_closed_{inv['id']}_{self.key_suffix}"):
                        st.info("Switch to the Analysis tab to view detailed metrics for this investment.")
                
                with col4:
                    if st.button("🗑️ Delete", key=f"delete_inv_{inv['id']}_{self.key_suffix}", type="secondary"):
                        self._confirm_delete_investment_dialog(inv['id'], inv['name'])
    
    @st.dialog("Add New Investment")
    def _add_investment_dialog(self) -> None:
        """Dialog for adding new investment."""
        # Get available tags (excluding already used ones)
        available_tags = self.service.get_available_tags(exclude_used=True)
        
        if not available_tags:
            st.warning("All available Savings and Investments tags are already being tracked.")
            st.info("Please either:\n- Create new tags in the Categories & Tags page, or\n- Close an existing investment to free up its tag")
            return
        
        # Category selection
        category = st.selectbox(
            "Category",
            options=list(available_tags.keys()),
            key=f"add_category_{self.key_suffix}"
        )
        
        # Tag selection
        tags_for_category = available_tags.get(category, [])
        if not tags_for_category:
            st.warning(f"No available tags for category '{category}'. All tags are already being tracked.")
            return
        
        tag = st.selectbox(
            "Tag",
            options=tags_for_category,
            key=f"add_tag_{self.key_suffix}"
        )
        
        # Investment details
        name = st.text_input(
            "Investment Name",
            placeholder="e.g., My Pakam Account",
            key=f"add_name_{self.key_suffix}"
        )
        
        type_ = st.selectbox(
            "Investment Type",
            options=[e.value for e in InvestmentsType],
            key=f"add_type_{self.key_suffix}"
        )
        
        # Metadata fields (conditional based on type)
        st.markdown("#### Investment Details")
        
        col1, col2 = st.columns(2)
        
        with col1:
            interest_rate = None
            interest_rate_type = 'fixed'
            if type_ in ['pakam', 'bonds', 'pension', 'study_funds', 'p2p_lending']:
                interest_rate = st.number_input(
                    "Annual Interest Rate (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    key=f"add_interest_{self.key_suffix}"
                )
                
                # Interest rate type selection for P2P lending
                if type_ == 'p2p_lending':
                    interest_rate_type = st.radio(
                        "Interest Rate Type",
                        options=[InterestRateType.FIXED.value, InterestRateType.EXPECTED.value],
                        format_func=lambda x: "Fixed (Guaranteed)" if x == 'fixed' else "Expected (Projected)",
                        key=f"add_interest_type_{self.key_suffix}",
                        horizontal=True
                    )
            
            commission_deposit = None
            if type_ in ['pension', 'study_funds', 'pakam', 'brokerage_account', 'stocks', 'crypto']:
                commission_deposit = st.number_input(
                    "Deposit Commission (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    key=f"add_comm_dep_{self.key_suffix}"
                )
        
        with col2:
            commission_management = None
            if type_ in ['pension', 'study_funds', 'pakam', 'brokerage_account', 'p2p_lending']:
                commission_management = st.number_input(
                    "Annual Management Fee (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    key=f"add_comm_mgmt_{self.key_suffix}"
                )
            
            commission_withdrawal = None
            if type_ in ['pension', 'study_funds', 'pakam', 'brokerage_account', 'stocks', 'crypto']:
                commission_withdrawal = st.number_input(
                    "Withdrawal Commission (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    key=f"add_comm_wdraw_{self.key_suffix}"
                )
        
        liquidity_date = None
        if type_ in ['pension', 'study_funds', 'pakam', 'p2p_lending']:
            liquidity_date = st.date_input(
                "Liquidity Date (when accessible)",
                key=f"add_liquidity_{self.key_suffix}"
            )
            if liquidity_date:
                liquidity_date = liquidity_date.strftime('%Y-%m-%d')
        
        maturity_date = None
        if type_ == 'bonds':
            maturity_date = st.date_input(
                "Maturity Date",
                key=f"add_maturity_{self.key_suffix}"
            )
            if maturity_date:
                maturity_date = maturity_date.strftime('%Y-%m-%d')
        
        notes = st.text_area(
            "Notes (optional)",
            key=f"add_notes_{self.key_suffix}"
        )
        
        # Submit
        if st.button("Create Investment", key=f"add_submit_{self.key_suffix}", type="primary"):
            if not name or not name.strip():
                st.error("Investment name is required")
                return
            
            success, msg = self.service.add_investment(
                category=category,
                tag=tag,
                type_=type_,
                name=name.strip(),
                interest_rate=interest_rate,
                interest_rate_type=interest_rate_type,
                commission_deposit=commission_deposit,
                commission_management=commission_management,
                commission_withdrawal=commission_withdrawal,
                liquidity_date=liquidity_date,
                maturity_date=maturity_date,
                notes=notes
            )
            
            if success:
                st.success(f"Created investment: {name}")
                st.rerun()
            else:
                st.error(msg)
    
    @st.dialog("Edit Investment")
    def _edit_investment_dialog(self, investment_id: int) -> None:
        """Dialog for editing investment metadata."""
        investment = self.service.get_investment_by_id(investment_id)
        if investment.empty:
            st.error("Investment not found")
            return
        
        inv = investment.iloc[0]
        
        st.markdown(f"### Editing: {inv['name']}")
        st.caption(f"Category: {inv['category']} | Tag: {inv['tag']}")
        
        # Editable fields
        name = st.text_input(
            "Investment Name",
            value=inv['name'],
            key=f"edit_name_{investment_id}_{self.key_suffix}"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            interest_rate = st.number_input(
                "Annual Interest Rate (%)",
                value=float(inv.get('interest_rate') or 0.0),
                min_value=0.0,
                max_value=100.0,
                step=0.1,
                key=f"edit_interest_{investment_id}_{self.key_suffix}"
            )
            
            # Interest rate type for P2P lending
            interest_rate_type = inv.get('interest_rate_type', 'fixed')
            if inv['type'] == 'p2p_lending':
                interest_rate_type = st.radio(
                    "Interest Rate Type",
                    options=[InterestRateType.FIXED.value, InterestRateType.EXPECTED.value],
                    index=0 if interest_rate_type == 'fixed' else 1,
                    format_func=lambda x: "Fixed (Guaranteed)" if x == 'fixed' else "Expected (Projected)",
                    key=f"edit_interest_type_{investment_id}_{self.key_suffix}",
                    horizontal=True
                )
            
            commission_deposit = st.number_input(
                "Deposit Commission (%)",
                value=float(inv.get('commission_deposit') or 0.0),
                min_value=0.0,
                max_value=100.0,
                step=0.1,
                key=f"edit_comm_dep_{investment_id}_{self.key_suffix}"
            )
        
        with col2:
            commission_management = st.number_input(
                "Management Fee (%)",
                value=float(inv.get('commission_management') or 0.0),
                min_value=0.0,
                max_value=100.0,
                step=0.1,
                key=f"edit_comm_mgmt_{investment_id}_{self.key_suffix}"
            )
            
            commission_withdrawal = st.number_input(
                "Withdrawal Commission (%)",
                value=float(inv.get('commission_withdrawal') or 0.0),
                min_value=0.0,
                max_value=100.0,
                step=0.1,
                key=f"edit_comm_wdraw_{investment_id}_{self.key_suffix}"
            )
        
        notes = st.text_area(
            "Notes",
            value=inv.get('notes') or "",
            key=f"edit_notes_{investment_id}_{self.key_suffix}"
        )
        
        if st.button("Save Changes", key=f"edit_submit_{investment_id}_{self.key_suffix}", type="primary"):
            success, msg = self.service.update_investment(
                investment_id,
                name=name,
                interest_rate=interest_rate if interest_rate > 0 else None,
                interest_rate_type=interest_rate_type,
                commission_deposit=commission_deposit if commission_deposit > 0 else None,
                commission_management=commission_management if commission_management > 0 else None,
                commission_withdrawal=commission_withdrawal if commission_withdrawal > 0 else None,
                notes=notes
            )
            
            if success:
                st.success("Investment updated successfully")
                st.rerun()
            else:
                st.error(msg)
    
    def _display_manual_transactions(self) -> None:
        """Tab 3: Add and view manual transactions for investments."""
        st.markdown("### 💰 Manual Transactions")
        
        investments = self.service.get_all_investments(include_closed=True)  # Include closed
        
        if investments.empty:
            st.info("No investments available. Add an investment first.")
            return
        
        # Investment selector with visual indicators for closed
        investment_options = {}
        for _, inv in investments.iterrows():
            status = " 🔒 (Closed)" if inv['is_closed'] else ""
            label = f"{inv['name']} ({inv['category']} - {inv['tag']}){status}"
            investment_options[label] = inv['id']
        
        selected_name = st.selectbox(
            "Select Investment",
            options=list(investment_options.keys()),
            key=f"txn_inv_selector_{self.key_suffix}"
        )
        
        selected_id = investment_options[selected_name]
        
        # Get investment details to check if closed
        investment = self.service.get_investment_by_id(selected_id)
        inv = investment.iloc[0]
        
        # Add transaction button (disabled for closed investments)
        if inv['is_closed']:
            st.warning("⚠️ This investment is closed. You can view transaction history but cannot add new transactions.")
        else:
            if st.button("➕ Add Transaction", key=f"add_txn_btn_{self.key_suffix}"):
                self._add_transaction_dialog(selected_id)
        
        # Display transactions for selected investment
        transactions = self.service.get_transactions_for_investment(selected_id)
        
        if transactions.empty:
            if inv['is_closed']:
                st.info(f"No transactions for {inv['name']}.")
            else:
                st.info(f"No transactions for {inv['name']}. Add your first transaction above.")
            return
        
        st.markdown(f"### Transaction History: {inv['name']}")
        
        # Display with running balance
        transactions_sorted = transactions.sort_values('date')
        display_data = []
        
        for idx, txn in transactions_sorted.iterrows():
            display_data.append({
                'Date': txn['date'],
                'Description': txn['desc'],
                'Amount': f"₪{txn['amount']:+,.2f}",
                'Type': 'Withdrawal' if txn['amount'] > 0 else 'Deposit',
                'Provider': txn.get('provider', 'Manual')
            })
        
        if display_data:
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True, hide_index=True, key=f"txn_history_{self.key_suffix}")
            
            # Show current balance
            metrics = self.service.calculate_profit_loss(selected_id)
            col1, col2, col3 = st.columns(3)
            col1.metric("Current Balance", f"₪{metrics['current_balance']:,.2f}")
            col2.metric("Total Deposits", f"₪{metrics['total_deposits']:,.2f}")
            col3.metric("Total Withdrawals", f"₪{metrics['total_withdrawals']:,.2f}")
    
    @st.dialog("Add Transaction")
    def _add_transaction_dialog(self, investment_id: int) -> None:
        """Dialog for adding manual transaction."""
        investment = self.service.get_investment_by_id(investment_id)
        if investment.empty:
            st.error("Investment not found")
            return
        
        inv = investment.iloc[0]
        st.markdown(f"### Add Transaction: {inv['name']}")
        
        transaction_type = st.radio(
            "Transaction Type",
            options=['Deposit', 'Withdrawal'],
            key=f"txn_type_{investment_id}_{self.key_suffix}",
            horizontal=True
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            date = st.date_input(
                "Date",
                value=datetime.today(),
                key=f"txn_date_{investment_id}_{self.key_suffix}"
            )
        
        with col2:
            amount = st.number_input(
                "Amount (₪)",
                min_value=0.01,
                step=10.0,
                key=f"txn_amount_{investment_id}_{self.key_suffix}"
            )
        
        description = st.text_input(
            "Description",
            placeholder="e.g., Monthly deposit",
            key=f"txn_desc_{investment_id}_{self.key_suffix}"
        )
        
        if st.button("Add Transaction", key=f"txn_submit_{investment_id}_{self.key_suffix}", type="primary"):
            if amount <= 0:
                st.error("Amount must be positive")
                return
            
            # Prepare transaction data
            transaction_data = {
                'date': date,
                'account_name': inv['name'],
                'desc': description or f"{transaction_type} - {inv['name']}",
                'amount': amount,
                'transaction_type': transaction_type.lower(),
                'provider': 'Manual',
                'account_number': '',
                'category': inv['category'],
                'tag': inv['tag']
            }

            success = self.transactions_service.add_transaction(transaction_data, service='manual_investments')
            
            if success:
                st.success(f"Transaction added: {transaction_type} of ₪{amount:,.2f}")
                st.rerun()
            else:
                st.error("Failed to add transaction")
    
    @st.dialog("Confirm Delete Investment")
    def _confirm_delete_investment_dialog(self, investment_id: int, investment_name: str) -> None:
        """Confirmation dialog for deleting an investment."""
        st.warning(f"⚠️ Are you sure you want to delete **{investment_name}**?")
        
        st.markdown("""
        **This action will:**
        - Remove the investment from tracking
        - Free up the category/tag combination for reuse
        - **NOT** delete any transaction data (transactions remain in the database)
        
        **Note:** All historical transactions will remain in your transaction history. Only the investment tracking record will be removed.
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Yes, Delete", key=f"confirm_delete_{investment_id}", type="primary", use_container_width=True):
                success, msg = self.service.delete_investment(investment_id)
                if success:
                    st.success(f"Deleted investment: {investment_name}")
                    st.rerun()
                else:
                    st.error(msg)
        
        with col2:
            if st.button("❌ Cancel", key=f"cancel_delete_{investment_id}", use_container_width=True):
                st.rerun()
    
    def _display_analysis(self) -> None:
        """Tab 4: Detailed analysis for selected investment."""
        st.markdown("### 📈 Investment Analysis")
        
        investments = self.service.get_all_investments(include_closed=True)  # Include closed
        
        if investments.empty:
            st.info("No investments available for analysis.")
            return
        
        # Investment selector with visual indicators for closed
        investment_options = {}
        for _, inv in investments.iterrows():
            status = " 🔒 (Closed)" if inv['is_closed'] else ""
            label = f"{inv['name']} ({inv['category']} - {inv['tag']}){status}"
            investment_options[label] = inv['id']
        
        selected_name = st.selectbox(
            "Select Investment",
            options=list(investment_options.keys()),
            key=f"analysis_inv_selector_{self.key_suffix}"
        )
        
        selected_id = investment_options[selected_name]
        
        investment = self.service.get_investment_by_id(selected_id)
        inv = investment.iloc[0]
        
        # Performance metrics
        metrics = self.service.calculate_profit_loss(selected_id)
        
        if metrics.get('total_deposits', 0) == 0:
            st.info("No transactions yet for this investment.")
            return
        
        st.markdown(f"### Performance Metrics: {inv['name']}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Current Balance", f"₪{metrics['current_balance']:,.2f}")
        col2.metric("Profit/Loss", f"₪{metrics['absolute_profit_loss']:+,.2f}")
        col3.metric("ROI", f"{metrics['roi_percentage']:+.2f}%")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Deposits", f"₪{metrics['total_deposits']:,.2f}")
        col2.metric("Total Withdrawals", f"₪{metrics['total_withdrawals']:,.2f}")
        col3.metric("Holding Period", f"{metrics['total_years']:.2f} years")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Opened Date", metrics['first_transaction_date'] if metrics['first_transaction_date'] else "---")
        col2.metric("Closed Date", inv['closed_date'] if inv['is_closed'] else "---")
        col3.metric("CAGR", f"{metrics['cagr_percentage']:+.2f}%")
        
        # Balance over time chart
        st.markdown("### 📊 Balance Over Time")
        
        transactions = self.service.get_transactions_for_investment(selected_id)
        if not transactions.empty:
            first_date = transactions['date'].min()
            last_date = datetime.today().strftime('%Y-%m-%d')
            
            balance_df = self.service.calculate_balance_over_time(
                selected_id,
                start_date=first_date,
                end_date=last_date
            )
            
            if not balance_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=balance_df['date'],
                    y=balance_df['balance'],
                    mode='lines',
                    name='Balance',
                    line=dict(color='#1f77b4', width=2)
                ))
                
                fig.update_layout(
                    title=f"Balance Over Time: {inv['name']}",
                    xaxis_title="Date",
                    yaxis_title="Balance (₪)",
                    hovermode='x unified',
                    showlegend=True
                )
                
                st.plotly_chart(fig, use_container_width=True, key=f"balance_chart_{self.key_suffix}")
        
        # Investment details
        with st.expander("Investment Details"):
            st.markdown(f"**Type:** {inv['type']}")
            st.markdown(f"**Category:** {inv['category']}")
            st.markdown(f"**Tag:** {inv['tag']}")
            st.markdown(f"**Created:** {inv['created_date']}")
            
            if inv.get('interest_rate'):
                rate_type = inv.get('interest_rate_type', 'fixed')
                rate_label = "Fixed" if rate_type == 'fixed' else "Expected"
                st.markdown(f"**Interest Rate:** {inv['interest_rate']:.2f}% annually ({rate_label})")
            if inv.get('commission_deposit'):
                st.markdown(f"**Deposit Commission:** {inv['commission_deposit']:.2f}%")
            if inv.get('commission_management'):
                st.markdown(f"**Management Fee:** {inv['commission_management']:.2f}% annually")
            if inv.get('commission_withdrawal'):
                st.markdown(f"**Withdrawal Commission:** {inv['commission_withdrawal']:.2f}%")
            if inv.get('liquidity_date'):
                st.markdown(f"**Liquidity Date:** {inv['liquidity_date']}")
            if inv.get('maturity_date'):
                st.markdown(f"**Maturity Date:** {inv['maturity_date']}")
            if inv.get('notes'):
                st.markdown(f"**Notes:** {inv['notes']}")
