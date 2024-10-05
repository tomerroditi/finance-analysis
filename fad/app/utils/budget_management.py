import pandas as pd
import streamlit as st
import sqlalchemy as sa

from datetime import datetime
from copy import deepcopy

from fad.app.naming_conventions import Tables, TransactionsTableFields, NonExpensesCategories
from fad.app.utils.data import get_db_connection, get_table, get_categories_and_tags

# TODO: refactor this module to use the naming conventions and to be more modular and clean


@st.fragment
def select_custom_month():
    with st.expander("View Historical Data"):
        curr_year = datetime.now().year
        year_col, month_col, view_col = st.columns([1, 1, 1])
        years = [i for i in range(curr_year - 50, curr_year + 1)]
        years.reverse()
        year_ = year_col.selectbox(
            "Year",
            years,
            index=None,
            key="budget_custom_year_selection"
        )

        if year_ == curr_year:
            months = [i for i in range(1, datetime.now().month + 1)]
        else:
            months = [i for i in range(1, 13)]
        month_ = month_col.selectbox(
            "Month", months, index=None, key="budget_custom_month_selection"
        )

        view_col.markdown("<br>", unsafe_allow_html=True)
        if view_col.button("View", use_container_width=True):
            if year_ is None or month_ is None:
                st.error("Please select a year and a month")
            st.session_state.year = year_
            st.session_state.month = month_
            st.rerun()


def select_current_month():
    if st.button("Current Month"):
        st.session_state.year = datetime.now().year
        st.session_state.month = datetime.now().month


@st.fragment
def add_new_rule(year: int, month: int):
    curr_rules = get_table(get_db_connection(), Tables.BUDGET_RULES.value)
    curr_rules = curr_rules.loc[
        (curr_rules["year"] == year) &
        (curr_rules["month"] == month)
    ]

    cat_n_tags = deepcopy(get_categories_and_tags())
    for _, rule in curr_rules.iterrows():
        used_tags = rule["tags"].split(";")
        if used_tags == ["All tags"]:
            cat_n_tags.pop(rule["category"], None)
        else:
            available_tags = cat_n_tags.get(rule["category"], [])
            available_tags = [tag for tag in available_tags if tag not in used_tags]
            cat_n_tags[rule["category"]] = available_tags

    with st.expander("Add New Rule"):
        if curr_rules.empty:
            # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
            st.markdown("Before adding new budget allocation, please set your total budget")
            col_input, col_set = st.columns([3, 1])
            total_budget = col_input.number_input("Total Budget", key="total_budget_input", label_visibility="hidden", value=1)
            if total_budget <= 0:
                st.error("Total budget must be a positive number")

            col_set.markdown("<br>", unsafe_allow_html=True)
            if col_set.button("Set Total Budget", key="set_total_budget_button", use_container_width=True):
                conn = get_db_connection()
                with conn.session as s:
                    cmd = sa.text(
                        f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                        f"(:name, :amount, :category, :tags, :month, :year)"
                    )
                    params = {
                        "name": "Total Budget",
                        "amount": total_budget,
                        "category": "Total Budget",
                        "tags": "Total Budget",
                        "month": month,
                        "year": year
                    }
                    s.execute(cmd, params)
                    s.commit()
                st.rerun()
            return  # do not show the add new rule expander if the total budget is not set

        name_col, category_col, tags_col, amount_col, submit_col = st.columns([1, 1, 1, 1, 1])
        name = name_col.text_input("Name", key="new_rule_name")
        category = category_col.selectbox("Category", cat_n_tags.keys(), key="new_rule_category", index=None)
        tags = tags_col.multiselect("Tags", ['All tags'] + cat_n_tags.get(category, []), key="new_rule_tags")
        amount = amount_col.number_input("Amount", key="new_rule_amount", value=1)

        if amount <= 0:
            st.error("Amount must be a positive number")

        if "All tags" in tags:
            if tags != ["All tags"]:
                st.warning("If 'All tags' is selected, no other tags should be selected. deselecting specific tags")
            tags = ["All tags"]

        submit_col.markdown("<br>", unsafe_allow_html=True)
        if submit_col.button("Add Rule"):
            total_budget = curr_rules.loc[curr_rules["category"] == "Total Budget"]["amount"].values[0]
            curr_rules = curr_rules.loc[~curr_rules.index.isin(curr_rules.loc[curr_rules["category"] == "Total Budget"].index)]
            if total_budget < curr_rules["amount"].sum() + amount:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                return

            conn = get_db_connection()
            with conn.session as s:
                cmd = sa.text(
                    f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                    f"(:name, :amount, :category, :tags, :month, :year)"
                )
                params = {
                    "name": name,
                    "amount": amount,
                    "category": category,
                    "tags": ';'.join(tags),
                    "month": month,
                    "year": year
                }
                s.execute(cmd, params)
                s.commit()
            st.rerun()

        st.markdown("***you cannot use the same category and tag in two different rules, "
                    "only available tags are shown for selection.***")


def copy_last_month_rules(year: int, month: int, overwrite: bool = False):
    last_month = month - 1 if month != 1 else 12
    last_year = year if month != 1 else year - 1
    conn = get_db_connection()
    budget_rules = get_table(conn, Tables.BUDGET_RULES.value)

    curr_month_rules = budget_rules.loc[
        (budget_rules["year"] == year) &
        (budget_rules["month"] == month)
    ]
    if not curr_month_rules.empty and not overwrite:
        return

    with conn.session as s:
        last_month_rules = budget_rules.loc[
            (budget_rules["year"] == last_year) &
            (budget_rules["month"] == last_month)
        ]
        if not last_month_rules.empty:
            for _, rule in last_month_rules.iterrows():
                cmd = sa.text(
                    f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                    f"(:name, :amount, :category, :tags, :month, :year)"
                )
                params = {
                    "name": rule["name"],
                    "amount": rule["amount"],
                    "category": rule["category"],
                    "tags": rule["tags"],
                    "month": month,
                    "year": year
                }
                s.execute(cmd, params)
                s.commit()


def budget_overview(year: int, month: int):
    conn = get_db_connection()

    budget_rules = get_table(conn, Tables.BUDGET_RULES.value)
    bank_data = get_table(conn, Tables.BANK.value)
    credit_card_data = get_table(conn, Tables.CREDIT_CARD.value)
    all_data = pd.concat([credit_card_data, bank_data])

    expenses_data = all_data.loc[
        ~all_data[TransactionsTableFields.CATEGORY.value].isin([category.value for category in NonExpensesCategories])
    ]
    liabilities_data = all_data.loc[
        all_data[TransactionsTableFields.CATEGORY.value] == NonExpensesCategories.LIABILITIES.value
        ]

    expenses_data[TransactionsTableFields.DATE.value] = pd.to_datetime(
        expenses_data[TransactionsTableFields.DATE.value])

    # fetch data from database based on the selected month view
    data = expenses_data.loc[
        (expenses_data[TransactionsTableFields.DATE.value].dt.year == year) &
        (expenses_data[TransactionsTableFields.DATE.value].dt.month == month)
    ]

    # fetch budget rules of the selected month view
    budget_rules_data = budget_rules.loc[
        (budget_rules["year"] == year) &
        (budget_rules["month"] == month)
    ]

    if budget_rules_data.empty:
        st.warning("No budget rules for the selected month")
        return

    total_budget_rule = budget_rules_data.loc[budget_rules_data["category"] == "Total Budget"]
    budget_rules_data = budget_rules_data.loc[~budget_rules_data.index.isin(total_budget_rule.index)]
    total_sum = data[TransactionsTableFields.AMOUNT.value].sum()
    if total_sum != 0:
        total_sum *= -1  # expenses are negative values
    rule_window(total_budget_rule.iloc[0], total_sum, allow_edit=True, allow_delete=False)

    for _, rule in budget_rules_data.iterrows():
        tags = rule["tags"].split(";")
        tags = [tag.strip() for tag in tags]
        curr_data = data.loc[data[TransactionsTableFields.CATEGORY.value] == rule["category"]]
        data = data.loc[~data.index.isin(curr_data.index)]
        if tags != ["All tags"]:
            curr_data = curr_data.loc[curr_data[TransactionsTableFields.TAG.value].isin(tags)]
        curr_sum = curr_data[TransactionsTableFields.AMOUNT.value].sum()
        if curr_sum != 0:
            curr_sum *= -1  # expenses are negative values
        rule_window(rule, curr_sum)

    # add other expenses window in case we have expenses not covered by any rule
    if not data.empty and not budget_rules_data.empty:
        total_budget = total_budget_rule.iloc[0]["amount"]
        rule = pd.Series({
            "name": "Other Expenses",
            "amount": total_budget - budget_rules_data["amount"].sum(),
            "category": "Other Expenses",
            "tags": "Other Expenses",
            "id": f"{year}{month}_Other_Expenses"
        })
        rule_window(rule, data[TransactionsTableFields.AMOUNT.value].sum() * -1, allow_edit=False, allow_delete=False)


def rule_window(rule: pd.Series, curr_amount: float, allow_edit: bool = True, allow_delete: bool = True):
    name_col, bar_col, edit_col, delete_col = st.columns([2, 6, 1, 1])

    if rule['category'] == "Total Budget":
        help_txt = "Total amount of money available for the month"
    elif rule['category'] == "Other Expenses":
        help_txt = "Expenses not covered by any other rule"
    else:
        help_txt = f"{rule['category']}: {rule['tags'].replace(';', ', ')}"
    name_col.markdown(f"### {rule['name']}", unsafe_allow_html=True, help=help_txt)

    total_amount = rule['amount']
    perc = max((curr_amount / total_amount) * 100, 0)  # cases where we have a surplus (negative percentage)
    bar_col.html(
        f"""
        <div style="width: 100%; background-color: #f3f3f3; border-radius: 10px; box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1); padding: 5px; position: relative;">
            <div style="position: absolute; left: 15px; top: 50%; transform: translateY(-50%); font-weight: bold; color: black;">
                {curr_amount:.2f} / {total_amount}
            </div>
            <div style="width: {min(perc, 100)}%; background-color: {'#4caf50' if perc < 90 else '#ffeb3b' if perc <= 100 else '#f44336'}; height: 30px; border-radius: 8px; text-align: center; color: white; line-height: 30px; transition: width 0.4s ease;">
            </div>
        </div>
        """
    )

    edit_col.button(
        "Edit",
        key=f"edit_{rule['id']}_button",
        on_click=edit_budget_rule_dialog,
        args=(rule,),
        use_container_width=True,
        disabled=not allow_edit
    )

    delete_col.button(
        "Delete",
        key=f"delete_{rule['id']}_submit",
        on_click=delete_budget_rule_dialog,
        args=(rule["id"],),
        use_container_width=True,
        disabled=not allow_delete
    )


@st.dialog("Edit Rule")
def edit_budget_rule_dialog(rule: pd.Series):
    if rule["category"] != "Total Budget":
        cat_n_tags = get_categories_and_tags()
        name = st.text_input("Name", value=rule['name'], key=f"edit_{rule['id']}_name")
        category = st.selectbox("Category", options=cat_n_tags.keys(), index=list(cat_n_tags.keys()).index(rule['category']), key=f"edit_{rule['id']}_category")
        tags = st.multiselect("Tags", options=['All tags'] + cat_n_tags.get(category, []), default=rule['tags'].split(";"), key=f"edit_{rule['id']}_tags")
    else:
        name = rule['name']
        category = rule['category']
        tags = rule['tags']

    amount = st.number_input("Amount", value=rule['amount'], key=f"edit_{rule['id']}_amount")
    if st.button("Update Rule", key=f"edit_{rule['id']}_submit"):
        if amount <= 0:
            st.error("Amount must be a positive number")
            return
        conn = get_db_connection()
        with conn.session as s:
            cmd = sa.text(
                f"UPDATE {Tables.BUDGET_RULES.value} SET name = :name, amount = :amount, category = :category, tags = :tags "
                f"WHERE id = :id"
            )
            params = {
                "name": name,
                "amount": amount,
                "category": category,
                "tags": ';'.join(tags),
                "id": rule["id"]
            }
            s.execute(cmd, params)
            s.commit()
        st.rerun()


@st.dialog("Are you sure you want to delete this rule?")
def delete_budget_rule_dialog(id_: int):
    if st.button("Yes"):
        conn = get_db_connection()
        with conn.session as s:
            cmd = sa.text(
                f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id"
            )
            s.execute(cmd, {"id": id_})
            s.commit()
        st.rerun()
    if st.button("No"):
        st.rerun()
