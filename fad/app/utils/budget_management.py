import pandas as pd
import streamlit as st
import sqlalchemy as sa

from datetime import datetime
from copy import deepcopy

from fad.app.naming_conventions import Tables, TransactionsTableFields, NonExpensesCategories, BudgetRulesTableFields
from fad.app.utils.data import get_db_connection, get_table, get_categories_and_tags

# TODO: refactor this module to be more modular and clean
# TODO: make the budget rules table fetching less repetitive to avoid unnecessary reads from the database

ID = BudgetRulesTableFields.ID.value
NAME = BudgetRulesTableFields.NAME.value
YEAR = BudgetRulesTableFields.YEAR.value
MONTH = BudgetRulesTableFields.MONTH.value
CATEGORY = BudgetRulesTableFields.CATEGORY.value
TAGS = BudgetRulesTableFields.TAGS.value
AMOUNT = BudgetRulesTableFields.AMOUNT.value

ALL_TAGS = "All tags"
TOTAL_BUDGET = "Total Budget"

###################################################
# Monthly Budget Management
###################################################
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
        (curr_rules[YEAR] == year) &
        (curr_rules[MONTH] == month)
    ]

    cat_n_tags = get_categories_and_tags(copy=True)
    for _, rule in curr_rules.iterrows():
        used_tags = rule[TAGS].split(";")
        if used_tags == [ALL_TAGS]:
            cat_n_tags.pop(rule[CATEGORY], None)
        else:
            available_tags = cat_n_tags.get(rule[CATEGORY], [])
            available_tags = [tag for tag in available_tags if tag not in used_tags]
            cat_n_tags[rule[CATEGORY]] = available_tags

    with st.expander("Add New Rule"):
        if curr_rules.empty:
            # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
            st.markdown("Before adding new budget allocation, please set your total budget")
            col_input, col_set = st.columns([3, 1])
            total_budget = col_input.number_input(TOTAL_BUDGET, key="total_budget_input", label_visibility="hidden", value=1)
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
                        NAME: TOTAL_BUDGET,
                        AMOUNT: total_budget,
                        CATEGORY: TOTAL_BUDGET,
                        TAGS: TOTAL_BUDGET,
                        MONTH: month,
                        YEAR: year
                    }
                    s.execute(cmd, params)
                    s.commit()
                st.rerun()
            return  # do not show the add new rule expander if the total budget is not set

        name_col, category_col, tags_col, amount_col, submit_col = st.columns([1, 1, 1, 1, 1])
        name = name_col.text_input("Name", key="new_rule_name")
        category = category_col.selectbox("Category", cat_n_tags.keys(), key="new_rule_category", index=None)
        tags = tags_col.multiselect("Tags", [ALL_TAGS] + cat_n_tags.get(category, []), key="new_rule_tags")
        amount = amount_col.number_input("Amount", key="new_rule_amount", value=1)

        if ALL_TAGS in tags:
            if tags != [ALL_TAGS]:
                st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected. deselecting specific tags")
            tags = [ALL_TAGS]

        submit_col.markdown("<br>", unsafe_allow_html=True)
        if submit_col.button("Add Rule"):
            if category is None:
                st.error("Please select a category")
                return
            if name == "":
                st.error("Please enter a name")
                return
            if not tags:
                st.error("Please select at least one tag")
                return
            if amount <= 0:
                st.error("Amount must be a positive number")
                return

            total_budget = curr_rules.loc[curr_rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
            curr_rules = curr_rules.loc[~curr_rules.index.isin(curr_rules.loc[curr_rules[CATEGORY] == TOTAL_BUDGET].index)]
            if total_budget < curr_rules[AMOUNT].sum() + amount:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                return
            if not curr_rules.loc[curr_rules[CATEGORY] == category].empty and tags == [ALL_TAGS]:
                st.error(f"You cannot have a rule with {ALL_TAGS} for a category that already has rules with specific tags")
                return

            conn = get_db_connection()
            with conn.session as s:
                cmd = sa.text(
                    f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                    f"(:name, :amount, :category, :tags, :month, :year)"
                )
                params = {
                    NAME: name,
                    AMOUNT: amount,
                    CATEGORY: category,
                    TAGS: ';'.join(tags),
                    MONTH: month,
                    YEAR: year
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
        (budget_rules[YEAR] == year) &
        (budget_rules[MONTH] == month)
    ]
    if not curr_month_rules.empty and not overwrite:
        return

    with conn.session as s:
        last_month_rules = budget_rules.loc[
            (budget_rules[YEAR] == last_year) &
            (budget_rules[MONTH] == last_month)
        ]
        if not last_month_rules.empty:
            for _, rule in last_month_rules.iterrows():
                cmd = sa.text(
                    f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                    f"(:name, :amount, :category, :tags, :month, :year)"
                )
                params = {
                    NAME: rule[NAME],
                    AMOUNT: rule[AMOUNT],
                    CATEGORY: rule[CATEGORY],
                    TAGS: rule[TAGS],
                    MONTH: month,
                    YEAR: year
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

    # fetch data from database based on the selected month view, and exclude projects expenses
    projects_categories = budget_rules.loc[
        (budget_rules[YEAR].isnull()) &
        (budget_rules[MONTH].isnull())
    ][CATEGORY].unique()
    data = expenses_data.loc[
        (expenses_data[TransactionsTableFields.DATE.value].dt.year == year)
        & (expenses_data[TransactionsTableFields.DATE.value].dt.month == month)
        & ~expenses_data[TransactionsTableFields.CATEGORY.value].isin(projects_categories)
    ]

    # fetch budget rules of the selected month view
    budget_rules_data = budget_rules.loc[
        (budget_rules[YEAR] == year) &
        (budget_rules[MONTH] == month)
    ]

    if budget_rules_data.empty:
        st.warning("No budget rules for the selected month")
        return

    total_budget_rule = budget_rules_data.loc[budget_rules_data[CATEGORY] == TOTAL_BUDGET]
    budget_rules_data = budget_rules_data.loc[~budget_rules_data.index.isin(total_budget_rule.index)]
    total_sum = data[TransactionsTableFields.AMOUNT.value].sum()
    if total_sum != 0:
        total_sum *= -1  # expenses are negative values
    rule_window(total_budget_rule.iloc[0], total_sum, allow_edit=True, allow_delete=False)

    for _, rule in budget_rules_data.iterrows():
        tags = rule[TAGS].split(";")
        tags = [tag.strip() for tag in tags]
        curr_data = data.loc[data[TransactionsTableFields.CATEGORY.value] == rule[CATEGORY]]
        data = data.loc[~data.index.isin(curr_data.index)]
        if tags != [ALL_TAGS]:
            curr_data = curr_data.loc[curr_data[TransactionsTableFields.TAG.value].isin(tags)]
        curr_sum = curr_data[TransactionsTableFields.AMOUNT.value].sum()
        if curr_sum != 0:
            curr_sum *= -1  # expenses are negative values
        rule_window(rule, curr_sum)

    # add other expenses window in case we have expenses not covered by any rule
    if not data.empty and not budget_rules_data.empty:
        total_budget = total_budget_rule.iloc[0][AMOUNT]
        rule = pd.Series({
            NAME: "Other Expenses",
            AMOUNT: total_budget - budget_rules_data[AMOUNT].sum(),
            CATEGORY: "Other Expenses",
            TAGS: "Other Expenses",
            ID: f"{year}{month}_Other_Expenses"
        })
        rule_window(rule, data[TransactionsTableFields.AMOUNT.value].sum() * -1, allow_edit=False, allow_delete=False)


def rule_window(rule: pd.Series, curr_amount: float, allow_edit: bool = True, allow_delete: bool = True):
    name_col, bar_col, edit_col, delete_col = st.columns([2, 6, 1, 1])

    if rule[CATEGORY] == TOTAL_BUDGET:
        help_txt = "Total amount of money available for the month"
    elif rule[CATEGORY] == "Other Expenses":
        help_txt = "Expenses not covered by any other rule"
    else:
        help_txt = f"{rule[CATEGORY]}: {rule[TAGS].replace(';', ', ')}"
    name_col.markdown(f"### {rule[NAME]}", unsafe_allow_html=True, help=help_txt)

    total_amount = rule[AMOUNT]
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
        key=f"edit_{rule[ID]}_button",
        on_click=edit_budget_rule_dialog,
        args=(rule,),
        use_container_width=True,
        disabled=not allow_edit
    )

    # is_project_rule = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])
    # if is_project_rule:
    #     return  # we never let the user delete a project rule, so we hide the button (?)

    delete_col.button(
        "Delete",
        key=f"delete_{rule[ID]}_submit",
        on_click=delete_budget_rule_dialog,
        args=(rule[ID],),
        use_container_width=True,
        disabled=not allow_delete
    )


@st.dialog("Edit Rule")
def edit_budget_rule_dialog(rule: pd.Series):
    is_project_rule = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])
    if rule[CATEGORY] != TOTAL_BUDGET:
        cat_n_tags = get_categories_and_tags(copy=True)
        if not is_project_rule:
            rules = get_table(get_db_connection(), Tables.BUDGET_RULES.value)
            rules = rules.loc[
                (rules[YEAR] == rule[YEAR])
                & (rules[MONTH] == rule[MONTH])
            ]
            rules = rules[rules[CATEGORY] == rule[CATEGORY]]
            current_tags = rule[TAGS].split(";")
            used_tags = rules[TAGS].apply(lambda x: x.split(";"))
            used_tags = [tag for tags in used_tags for tag in tags if tag not in current_tags]
            cat_n_tags[rule[CATEGORY]] = [tag for tag in cat_n_tags[rule[CATEGORY]] if tag not in used_tags]

        name = st.text_input("Name", value=rule[NAME], key=f"edit_{rule[ID]}_name", disabled=is_project_rule)
        category = st.selectbox("Category", options=cat_n_tags.keys(), index=list(cat_n_tags.keys()).index(rule[CATEGORY]), key=f"edit_{rule[ID]}_category", disabled=is_project_rule)
        tags = st.multiselect("Tags", options=[ALL_TAGS] + cat_n_tags.get(category, []), default=rule[TAGS].split(";"), key=f"edit_{rule[ID]}_tags", disabled=is_project_rule)
    else:
        name = rule[NAME]
        category = rule[CATEGORY]
        tags = rule[TAGS]

    if ALL_TAGS in tags:
        if tags != [ALL_TAGS]:
            st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected. deselecting specific tags")
            tags = [ALL_TAGS]

    amount = st.number_input("Amount", value=rule[AMOUNT], key=f"edit_{rule[ID]}_amount")
    verify_new_values(rule, amount, category, tags)

    if st.button("Update Rule", key=f"edit_{rule[ID]}_submit"):
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
                NAME: name,
                AMOUNT: amount,
                CATEGORY: category,
                TAGS: ';'.join(tags),
                ID: rule[ID]
            }
            s.execute(cmd, params)
            s.commit()
        st.rerun()


def verify_new_values(rule: pd.Series, new_amount: float, new_category: str, new_tags: list[str]):
    if new_amount <= 0:
        st.error("Amount must be a positive number")

    is_project_rule = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])
    rules = get_table(get_db_connection(), Tables.BUDGET_RULES.value)
    if is_project_rule:
        rules = rules.loc[
            (rules[YEAR].isnull())
            & (rules[MONTH].isnull())
            & (rules[CATEGORY] == rule[CATEGORY])
        ]
        if rule[TAGS] == ALL_TAGS:
            total_rules_amount = rules[rules[TAGS] != ALL_TAGS][AMOUNT].sum()
            if new_amount < total_rules_amount:
                st.error("The total budget must be greater than the sum of all other rules of the project")
                st.stop()
        else:
            total_budget = rules.loc[rules[TAGS] == ALL_TAGS][AMOUNT].values[0]
            total_rules_amount = rules[rules[TAGS] != ALL_TAGS][AMOUNT].sum() - rule[AMOUNT]
            new_total_rules_amount = total_rules_amount + new_amount
            if new_total_rules_amount > total_budget:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                st.stop()
    else:
        rules = rules.loc[
            (rules[YEAR] == rule[YEAR])
            & (rules[MONTH] == rule[MONTH])
        ]
        if rule[CATEGORY] == TOTAL_BUDGET:
            total_rules_amount = rules.loc[rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum()
            if new_amount < total_rules_amount:
                st.error("The total budget must be greater than the sum of all other rules of the month")
                st.stop()
        else:
            total_budget = rules.loc[rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
            total_rules_amount = rules.loc[rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum() - rule[AMOUNT]
            new_total_rules_amount = total_rules_amount + new_amount
            if new_total_rules_amount > total_budget:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                st.stop()

    if new_tags == [ALL_TAGS]:
        if is_project_rule:
            pass
        else:
            if not rules.loc[rules[CATEGORY] == new_category].empty:
                st.error(f"You cannot have a rule with {ALL_TAGS} for a category that already has rules with specific tags")
                st.stop()




@st.dialog("Are you sure you want to delete this rule?")
def delete_budget_rule_dialog(id_: int):
    if st.button("Yes"):
        conn = get_db_connection()
        with conn.session as s:
            cmd = sa.text(
                f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id"
            )
            s.execute(cmd, {ID: id_})
            s.commit()
        st.rerun()
    if st.button("No"):
        st.rerun()


###################################################
# Project Budget Management
###################################################
@st.dialog("Select Project")
def add_new_project():
    budget_rules = get_table(get_db_connection(), Tables.BUDGET_RULES.value)
    curr_projects = budget_rules.loc[
        (budget_rules[YEAR].isnull()) &
        (budget_rules[MONTH].isnull())
    ]

    cat_n_tags = deepcopy(get_categories_and_tags())
    for _, rule in curr_projects.iterrows():
        cat_n_tags.pop(rule[CATEGORY], None)

    # select the category for which the project is related to
    category = st.selectbox("Select project category", cat_n_tags.keys(), key="new_project_category", index=None)
    # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
    col_input, col_set = st.columns([3, 1])
    total_budget = col_input.number_input("Set your total budget for the project", key="total_budget_project_input", value=1)
    if total_budget <= 0:
        st.error("Total budget must be a positive number")

    col_set.markdown("<br>", unsafe_allow_html=True)
    if col_set.button("Set", key="set_total_budget_project_button", use_container_width=True):
        conn = get_db_connection()
        with conn.session as s:
            cmd = sa.text(
                f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                f"(:name, :amount, :category, :tags, :month, :year)"
            )
            params = {
                NAME: TOTAL_BUDGET,
                AMOUNT: total_budget,
                CATEGORY: category,
                TAGS: ALL_TAGS,
                MONTH: None,
                YEAR: None
            }
            s.execute(cmd, params)
            s.commit()
        st.rerun()


def delete_project(name: str):
    conn = get_db_connection()
    with conn.session as s:
        cmd = sa.text(
            f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE category = :category AND year IS NULL AND month IS NULL"
        )
        s.execute(cmd, {CATEGORY: name})
        s.commit()


def select_project() -> str | None:
    budget_rules = get_table(get_db_connection(), Tables.BUDGET_RULES.value)
    curr_projects = budget_rules.loc[
        (budget_rules[YEAR].isnull()) &
        (budget_rules[MONTH].isnull())
    ]
    project = st.selectbox("Select Project", curr_projects[CATEGORY].unique(), key="project_selection", index=None)
    if project is None:
        return None
    return project


def view_project_rules(project: str):
    conn = get_db_connection()

    rules = get_table(conn, Tables.BUDGET_RULES.value)
    rules = rules.loc[
        (rules[CATEGORY] == project)
        & rules[YEAR].isnull()
        & rules[MONTH].isnull()
    ]

    cat_n_tags = deepcopy(get_categories_and_tags())
    tags = cat_n_tags.get(project, [])
    for tag in tags:  # add missing tags of the project to the rules
        if tag in rules[TAGS].values:
            continue
        with conn.session as s:
            cmd = sa.text(
                f"INSERT INTO {Tables.BUDGET_RULES.value} (name, amount, category, tags, month, year) VALUES "
                f"(:name, :amount, :category, :tags, :month, :year)"
            )
            params = {
                NAME: tag,
                AMOUNT: 1,
                CATEGORY: project,
                TAGS: tag,
                MONTH: None,
                YEAR: None
            }
            s.execute(cmd, params)
            s.commit()

    for tag in rules[TAGS].values:  # remove tags that are not in the project anymore
        if tag not in tags + [ALL_TAGS]:
            with conn.session as s:
                cmd = sa.text(
                    f"DELETE FROM {Tables.BUDGET_RULES.value} "
                    f"WHERE category = :category AND tags = :tags AND year IS NULL AND month IS NULL"
                )
                params = {
                    CATEGORY: project,
                    TAGS: tag
                }
                s.execute(cmd, params)
                s.commit()

    rules = get_table(conn, Tables.BUDGET_RULES.value)
    rules = rules.loc[
        (rules[CATEGORY] == project)
        & rules[YEAR].isnull()
        & rules[MONTH].isnull()
    ]

    bank_data = get_table(conn, Tables.BANK.value)
    credit_card_data = get_table(conn, Tables.CREDIT_CARD.value)
    all_data = pd.concat([credit_card_data, bank_data])
    project_data = all_data.loc[
        all_data[TransactionsTableFields.CATEGORY.value] == project
    ]

    total_budget_rule = rules.loc[rules[TAGS] == ALL_TAGS]
    total_sum = project_data[TransactionsTableFields.AMOUNT.value].sum()
    if total_sum != 0:
        total_sum *= -1
    rule_window(total_budget_rule.iloc[0], total_sum, allow_edit=True, allow_delete=False)

    rules = rules.loc[~rules.index.isin(total_budget_rule.index)]
    for _, rule in rules.iterrows():
        tag = rule[TAGS]
        curr_data = project_data.loc[project_data[TransactionsTableFields.TAG.value] == tag]
        curr_sum = curr_data[TransactionsTableFields.AMOUNT.value].sum()
        if curr_sum != 0:
            curr_sum *= -1
        rule_window(rule, curr_sum, allow_edit=True, allow_delete=False)
