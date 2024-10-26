import pandas as pd
import streamlit as st
import sqlalchemy as sa

from datetime import datetime
from copy import deepcopy

from fad.app.naming_conventions import Tables, TransactionsTableFields, NonExpensesCategories, BudgetRulesTableFields
from fad.app.utils.data import get_db_connection, get_table, get_categories_and_tags


ID = BudgetRulesTableFields.ID.value
NAME = BudgetRulesTableFields.NAME.value
YEAR = BudgetRulesTableFields.YEAR.value
MONTH = BudgetRulesTableFields.MONTH.value
CATEGORY = BudgetRulesTableFields.CATEGORY.value
TAGS = BudgetRulesTableFields.TAGS.value
AMOUNT = BudgetRulesTableFields.AMOUNT.value

ALL_TAGS = "All tags"
TOTAL_BUDGET = "Total Budget"

conn = get_db_connection()


###################################################
# Monthly Budget Management
###################################################
@st.dialog("Custom Month Selection")
def select_custom_month():
    """
    This function creates a UI for selecting a custom month and year to view its budget. The selected month and year are
    stored in the session state variables `year` and `month`
    """
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


def select_current_month() -> None:
    """
    This function creates a UI for selecting the current month and year to view its budget. The selected month and year
    are stored in the session state variables `year` and `month`
    """
    if st.button("Current Month", key="current_month_button_budget", use_container_width=True):
        st.session_state.year = datetime.now().year
        st.session_state.month = datetime.now().month


def select_next_month() -> None:
    """
    This function creates a UI for selecting the next month and year to view its budget. The selected month and year are
    stored in the session state variables `year` and `month`
    """
    if st.button("Next Month", key="next_month_button_budget", use_container_width=True):
        year = st.session_state.year
        month = st.session_state.month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

        st.session_state.year = year
        st.session_state.month = month


def select_previous_month() -> None:
    """
    This function creates a UI for selecting the previous month and year to view its budget. The selected month and year
    are stored in the session state variables `year` and `month`
    """
    if st.button("Previous Month", key="previous_month_button_budget", use_container_width=True):
        year = st.session_state.year
        month = st.session_state.month
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1

        st.session_state.year = year
        st.session_state.month = month


@st.fragment
def add_new_rule(year: int, month: int, budget_rules: pd.DataFrame) -> None:
    """
    This function creates a UI for adding a new budget rule for the selected month and year. the new rule is stored in
    the database. the function prompts an error to the user in any of the following cases:
    - the category is not selected
    - the name is not entered
    - no tags are selected
    - the amount is not a positive number
    - the total budget is exceeded by the sum of all rules and the new rule amount
    - a rule with all tags is added to a category that already has rules with specific tags

    Parameters
    ----------
    year: int
        the selected year
    month: int
        the selected month
    budget_rules:
        the budget rules table which contains all (updated) rules
    """
    budget_rules = budget_rules.loc[
        (budget_rules[YEAR] == year) &
        (budget_rules[MONTH] == month)
        ]

    if budget_rules.empty:
        func = _add_total_budget_rule_ui
        args = (year, month)
    else:
        func = _add_new_rule_ui
        args = (year, month, budget_rules)

    st.button("Add New Rule", on_click=func, args=args, key="add_new_rule_button", use_container_width=True)


@st.dialog("Set Total Budget")
def _add_total_budget_rule_ui(year: int, month: int) -> None:
    # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
    st.markdown("Before adding new budget allocation, please set your total budget")
    col_input, col_set = st.columns([3, 1])
    total_budget = col_input.number_input(TOTAL_BUDGET, key="total_budget_input", label_visibility="hidden", value=1)
    if total_budget <= 0:
        st.error("Total budget must be a positive number")

    col_set.markdown("<br>", unsafe_allow_html=True)
    if col_set.button("Set Total Budget", key="set_total_budget_button", use_container_width=True):
        _add_rule_to_db(TOTAL_BUDGET, total_budget, TOTAL_BUDGET, [TOTAL_BUDGET], month, year)
        st.rerun()


@st.dialog("Add New Rule")
def _add_new_rule_ui(year: int, month: int, budget_rules: pd.DataFrame) -> None:
    st.markdown("***you cannot use the same category and tag in two different rules, only available tags are shown for "
                "selection.***")

    cat_n_tags = _get_available_tags_for_each_category(budget_rules)

    name = st.text_input("Name", key="new_rule_name")
    category = st.selectbox("Category", cat_n_tags.keys(), key="new_rule_category", index=None)
    tags = st.multiselect("Tags", [ALL_TAGS] + cat_n_tags.get(category, []), key="new_rule_tags")
    amount = st.number_input("Amount", key="new_rule_amount", value=1)

    if ALL_TAGS in tags:
        if tags != [ALL_TAGS]:
            st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected. deselecting specific tags")
        tags = [ALL_TAGS]

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Add Rule"):
        _verify_new_values(budget_rules, name, category, tags, amount, year, month, None)
        _add_rule_to_db(name, amount, category, tags, month, year)
        st.rerun()


def _get_available_tags_for_each_category(budget_rules: pd.DataFrame) -> dict[str, list[str]]:
    cats_n_tags = get_categories_and_tags(copy=True)
    for _, rule in budget_rules.iterrows():
        used_tags = rule[TAGS].split(";")
        if used_tags == [ALL_TAGS]:
            cats_n_tags.pop(rule[CATEGORY], None)
            continue

        available_tags = cats_n_tags.get(rule[CATEGORY], [])
        available_tags = [tag for tag in available_tags if tag not in used_tags]
        if not available_tags:
            cats_n_tags.pop(rule[CATEGORY], None)
        else:
            cats_n_tags[rule[CATEGORY]] = available_tags

    return cats_n_tags


def copy_last_month_rules(year: int, month: int, budget_rules: pd.DataFrame) -> None:
    """
    This function copies the budget rules of the last month to the selected month. If the last month has no rules, the
    function does nothing. if the selected month already has rules, the function deletes them before copying the rules
    of the last month (if any). the updated rules are stored in the database.

    Parameters
    ----------
    year: int
        the selected year
    month: int
        the selected month
    budget_rules:
        the budget rules table which contains all (updated) rules

    Returns
    -------

    """
    last_month = month - 1 if month != 1 else 12
    last_year = year if month != 1 else year - 1

    last_month_rules = budget_rules.loc[
        (budget_rules[YEAR] == last_year) &
        (budget_rules[MONTH] == last_month)
        ]
    if last_month_rules.empty:
        return

    delete_monthly_budget_rules(year, month)
    for _, rule in last_month_rules.iterrows():
        _add_rule_to_db(rule[NAME], rule[AMOUNT], rule[CATEGORY], rule[TAGS].split(";"), month, year)


def delete_monthly_budget_rules(year: int, month: int) -> None:
    """
    This function deletes all budget rules of the selected month from the database.

    Parameters
    ----------
    year: int
        the selected year
    month: int
        the selected month
    """
    with conn.session as s:
        cmd = sa.text(
            f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE year = :year AND month = :month"
        )
        params = {
            YEAR: year,
            MONTH: month
        }
        s.execute(cmd, params)
        s.commit()


def budget_overview(year: int, month: int, budget_rules: pd.DataFrame) -> None:
    """
    This function creates a UI for viewing the budget overview of the selected month. expenses are fetched from the
    database based on the selected month view (project expenses are excluded). the budget rules of the selected month
    view are fetched and displayed in the UI. a window of other expenses is added in case we have expenses not covered
    by any rule. the UI allows the user to edit and delete the rules as well.

    Parameters
    ----------
    year: int
        the selected year
    month:
        the selected month
    budget_rules:
        the budget rules table which contains all (updated) rules
    """
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
    _rule_ui_window(budget_rules, total_budget_rule.iloc[0], total_sum, data, allow_edit=True, allow_delete=False)

    for _, rule in budget_rules_data.iterrows():
        tags = rule[TAGS].split(";")
        curr_data = data.loc[data[TransactionsTableFields.CATEGORY.value] == rule[CATEGORY]]
        data = data.loc[~data.index.isin(curr_data.index)]
        if tags != [ALL_TAGS]:
            curr_data = curr_data.loc[curr_data[TransactionsTableFields.TAG.value].isin(tags)]
        curr_sum = curr_data[TransactionsTableFields.AMOUNT.value].sum()
        if curr_sum != 0:
            curr_sum *= -1  # expenses are negative values
        _rule_ui_window(budget_rules, rule, curr_sum, curr_data)

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
        amount = data[TransactionsTableFields.AMOUNT.value].sum() * -1
        _rule_ui_window(budget_rules, rule, amount, data, allow_edit=False, allow_delete=False)


def _rule_ui_window(
        budget_rules: pd.DataFrame,
        rule: pd.Series,
        curr_amount: float,
        raw_data: pd.DataFrame,
        allow_edit: bool = True,
        allow_delete: bool = True
) -> None:
    """
    This function creates a UI window for a budget rule. the window contains the rule name, the amount of money
    available for the rule, a progress bar that shows the percentage of the amount spent, an edit button, and a delete
    button. the edit button opens a dialog for editing the rule, and the delete button opens a dialog for asking the
    user if they are sure they want to delete the rule.

    Parameters
    ----------
    budget_rules: pd.DataFrame
        the budget rules table which contains all (updated) rules
    rule:
        the budget rule to display
    curr_amount: float
        the amount of money spent on the rule
    raw_data: pd.DataFrame
        the raw data of the expenses related to the rule
    allow_edit:
        a boolean flag that indicates whether the user is allowed to edit the rule
    allow_delete:
        a boolean flag that indicates whether the user is allowed to delete the rule
    """
    expand_col, name_col, bar_col, edit_col, delete_col = st.columns([1, 4, 12, 2, 2])

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

    if expand_col.toggle("Expand", key=f"expand_{rule[ID]}", label_visibility="collapsed"):
        st.dataframe(
            raw_data.sort_values(by=[TransactionsTableFields.DATE.value], ascending=False),
            column_order=[
                TransactionsTableFields.PROVIDER.value,
                TransactionsTableFields.ACCOUNT_NAME.value,
                TransactionsTableFields.ACCOUNT_NUMBER.value,
                TransactionsTableFields.DATE.value,
                TransactionsTableFields.DESCRIPTION.value,
                TransactionsTableFields.AMOUNT.value,
                TransactionsTableFields.CATEGORY.value,
                TransactionsTableFields.TAG.value,
                TransactionsTableFields.STATUS.value,
                TransactionsTableFields.ID.value

            ]
        )

    edit_col.button(
        "Edit",
        key=f"edit_{rule[ID]}_button",
        on_click=_edit_budget_rule_dialog,
        args=(rule, budget_rules),
        use_container_width=True,
        disabled=not allow_edit
    )

    delete_col.button(
        "Delete",
        key=f"delete_{rule[ID]}_submit",
        on_click=_delete_budget_rule_dialog,
        args=(rule[ID],),
        use_container_width=True,
        disabled=not allow_delete
    )


@st.dialog("Edit Rule")
def _edit_budget_rule_dialog(rule: pd.Series, budget_rules: pd.DataFrame) -> None:
    """
    This function creates a dialog for editing a budget rule. the dialog contains input fields for the rule name, the
    amount of money available for the rule, the category, and the tags. the new rule is stored in the database. the
    dialog prompts an error to the user in any
    of the following cases:
    - the amount is not a positive number
    - the total budget is exceeded by the sum of all rules and the new rule amount
    - a rule with all tags is added to a category that already has rules with specific tags

    Parameters
    ----------
    rule: pd.Series
        the budget rule to edit
    budget_rules:
        the budget rules table which contains all (updated) rules
    """
    if rule[CATEGORY] != TOTAL_BUDGET:
        name, category, tags = _edit_name_category_tags_ui(rule, budget_rules)
    else:  # cannot edit total budget rule except for the amount
        name = rule[NAME]
        category = rule[CATEGORY]
        tags = rule[TAGS].split(";")

    amount = st.number_input("Amount", value=rule[AMOUNT], key=f"edit_{rule[ID]}_amount")

    if st.button("Update Rule", key=f"edit_{rule[ID]}_submit"):
        _verify_new_values(budget_rules, name, category, tags, amount, rule[YEAR], rule[MONTH], rule[ID])
        _update_rule_in_db(rule[ID], name=name, amount=amount, category=category, tags=";".join(tags))
        st.rerun()


def _edit_name_category_tags_ui(rule: pd.Series, budget_rules: pd.DataFrame) -> tuple[str, str, list[str]]:
    cat_n_tags = get_categories_and_tags(copy=True)
    is_project_rule = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])  # can't edit project rules but amount
    if not is_project_rule:
        used_tags = budget_rules.loc[
            (budget_rules[YEAR] == rule[YEAR])
            & (budget_rules[MONTH] == rule[MONTH])
            & (budget_rules[CATEGORY] == rule[CATEGORY])
            & (budget_rules[ID] != rule[ID])
            ][TAGS].apply(lambda x: x.split(";"))
        used_tags = [tag for tags in used_tags for tag in tags]  # flatten the lists
        cat_n_tags[rule[CATEGORY]] = [tag for tag in cat_n_tags[rule[CATEGORY]] if tag not in used_tags]

    name = st.text_input(
        "Name",
        value=rule[NAME],
        key=f"edit_{rule[ID]}_name",
        disabled=is_project_rule
    )

    category = st.selectbox(
        "Category",
        options=cat_n_tags.keys(),
        index=list(cat_n_tags.keys()).index(rule[CATEGORY]),
        key=f"edit_{rule[ID]}_category",
        disabled=is_project_rule
    )

    if category == rule[CATEGORY]:
        tags_default = rule[TAGS].split(";")
    else:
        tags_default = []
    tags = st.multiselect(
        "Tags",
        options=[ALL_TAGS] + cat_n_tags.get(category, []),
        default=tags_default,
        key=f"edit_{rule[ID]}_tags",
        disabled=is_project_rule
    )

    if ALL_TAGS in tags:
        if tags != [ALL_TAGS]:
            st.warning(f"If {ALL_TAGS} is selected, no other tags should be selected. deselecting specific tags")
            tags = [ALL_TAGS]

    return name, category, tags


def _verify_new_values(
        budget_rules: pd.DataFrame,
        name: str,
        category: str,
        tags: list[str],
        amount: float,
        year: int | None,
        month: int | None,
        id_: int | None
) -> None:
    """
    This function verifies the new values of the rule before updating it. the function prompts an error to the user in
    any of the following cases:
    - the amount is not a positive number
    - the new category is not selected
    - no tags are selected
    - the new name is not entered (empty)
    - the total budget is exceeded by the sum of all rules and the new rule amount
    - a rule with all tags is added to a category that already has rules with specific tags

    Parameters
    ----------
    budget_rules: pd.DataFrame
        the budget rules table which contains all (updated) rules
    amount: float
        the new amount of money available for the rule
    category: str
        the new category of the rule
    tags: list[str]
        the new tags of the rule
    name: str
        the new name of the rule
    year: int | float
        the year of the rule to edit. if float (nan), the rule is a project rule.
    month: int | float
        the month of the rule to edit. if float (nan), the rule is a project rule.
    id_: int | None
        the id of the rule to edit. if None, the rule is a new rule.

    """
    if id_ is not None:
        rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
        # if no change just return
        if (rule[NAME] == name
                and rule[AMOUNT] == amount
                and rule[CATEGORY] == category
                and rule[TAGS] == ";".join(tags)):
            return

    if name == "":
        st.error("Please enter a name")
        st.stop()
    if category is None:
        st.error("Please select a category")
        st.stop()
    if not tags:
        st.error("Please select at least one tag")
        st.stop()
    if amount <= 0:
        st.error("Amount must be a positive number")
        st.stop()

    if pd.isnull(year) and pd.isnull(month):
        # updating a project rule (you cannot add a new project rule, and can update amount only)
        rule = budget_rules.loc[budget_rules[ID] == id_].T.squeeze()
        budget_rules = budget_rules.loc[
            (budget_rules[YEAR].isnull())
            & (budget_rules[MONTH].isnull())
            & (budget_rules[CATEGORY] == category)
        ]
        total_rules_amount = budget_rules[budget_rules[TAGS] != ALL_TAGS][AMOUNT].sum()
        if rule[TAGS] == ALL_TAGS:
            # updating the project total budget
            if amount < total_rules_amount:
                st.error("The total budget must be greater than the sum of all other rules of the project")
                st.stop()
        else:
            # updating a project rule with specific tag
            total_budget = budget_rules.loc[budget_rules[TAGS] == ALL_TAGS][AMOUNT].values[0]
            new_total_rules_amount = total_rules_amount - rule[AMOUNT] + amount
            if new_total_rules_amount > total_budget:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                st.stop()
        return

    budget_rules = budget_rules.loc[
        (budget_rules[YEAR] == year)
        & (budget_rules[MONTH] == month)
    ]
    total_rules_amount = budget_rules.loc[budget_rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum()

    if category == TOTAL_BUDGET:
        # updating the total budget for a month, only amount might be updated
        if amount < total_rules_amount:
            st.error("The total budget must be greater than the sum of all other rules of the month")
            st.stop()
        return

    # add/update a rule for a specific month
    if id_ is not None:
        # updating a certain rule, hence we need to exclude it from the total rules amount
        total_rules_amount -= budget_rules.loc[budget_rules[ID] == id_][AMOUNT].values[0]
    total_budget = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
    new_total_rules_amount = total_rules_amount + amount
    if new_total_rules_amount > total_budget:
        st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
        st.stop()

    if tags == [ALL_TAGS]:
        condition = budget_rules[CATEGORY] == category
        if id_ is not None:
            condition &= budget_rules[ID] != id_
        if not budget_rules.loc[condition].empty:
            st.error(
                f"You cannot have a rule with {ALL_TAGS} for a category that already has rules with specific tags"
            )
            st.stop()


@st.dialog("Are you sure you want to delete this rule?")
def _delete_budget_rule_dialog(id_: int) -> None:
    """
    This function creates a dialog for asking the user if they are sure they want to delete the rule. if the user clicks
    on "Yes", the rule is deleted from the database. if the user clicks on "No", the dialog is closed.

    Parameters
    ----------
    id_: int
        the id of the rule to delete
    """
    if st.button("Yes"):
        _delete_rule_from_db(id_)
        st.rerun()
    if st.button("No"):
        st.rerun()


def _add_rule_to_db(name: str, amount: float, category: str, tags: list[str], month: int, year: int) -> None:
    """
    This function adds a new rule to the database.

    Parameters
    ----------
    name: str
        the name of the rule
    amount: float
        the amount of money available for the rule
    category: str
        the category of the rule
    tags: list[str]
        the tags of the rule
    month: int
        the month of the rule
    year: int
        the year of the rule
    """
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


def _delete_rule_from_db(id_: int) -> None:
    """
    This function deletes a rule from the database.

    Parameters
    ----------
    id_: int
        the id of the rule to delete
    """
    with conn.session as s:
        cmd = sa.text(
            f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE id = :id"
        )
        s.execute(cmd, {ID: id_})
        s.commit()


def _update_rule_in_db(id_: int, **kwargs) -> None:
    """
    This function updates a rule in the database. the function updates the rule with the given id with the new values
    passed as keyword arguments.

    Parameters
    ----------
    id_: int
        the id of the rule to update
    kwargs:
        the new values of the rule
    """
    assert all(key in [NAME, AMOUNT, CATEGORY, TAGS] for key in kwargs.keys())

    fields_to_update = list(kwargs.keys())

    with conn.session as s:
        cmd = sa.text(
            f"UPDATE {Tables.BUDGET_RULES.value} SET "
            + ", ".join([f"{field} = :{field}" for field in fields_to_update])
            + f" WHERE id = :id"
        )
        kwargs[ID] = int(id_)
        s.execute(cmd, kwargs)
        s.commit()


###################################################
# Project Budget Management
###################################################
@st.dialog("Add New Project")
def add_new_project(budget_rules: pd.DataFrame) -> None:
    """
    This function creates a dialog for adding a new project. the dialog contains a selection box for selecting the
    category of the project and an input field for setting the total budget of the project. the new project is stored in
    the database. the dialog prompts an error to the user in any of the following cases:
    - the total budget is not a positive number

    Parameters
    ----------
    budget_rules: pd.DataFrame
        the budget rules table which contains all (updated) rules from which already selected categories are excluded
        from the options available for the new project
    """
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


def delete_project(name: str) -> None:
    # TODO: add a dialog for asking the user if they are sure they want to delete the project
    """
    This function deletes a project from the database. the project is deleted by deleting all rules related to the
    project.

    Parameters
    ----------
    name: str
        the name of the project to delete
    """
    with conn.session as s:
        cmd = sa.text(
            f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE category = :category AND year IS NULL AND month IS NULL"
        )
        s.execute(cmd, {CATEGORY: name})
        s.commit()


def select_project(budget_rules: pd.DataFrame) -> str | None:
    """
    This function creates a UI for selecting a project to view its budget. the function returns the selected project.

    Parameters
    ----------
    budget_rules: pd.DataFrame
        the budget rules table which contains all (updated) rules from which we can fetch the projects that the user
        can select

    Returns
    -------
    str | None
        the selected project or None if no project is selected
    """
    curr_projects = budget_rules.loc[
        (budget_rules[YEAR].isnull()) &
        (budget_rules[MONTH].isnull())
    ]
    project = st.selectbox("Select Project", curr_projects[CATEGORY].unique(), key="project_selection", index=None)
    if project is None:
        return None
    return project


def view_project_budget(project: str, budget_rules: pd.DataFrame):
    """
    This function creates a UI for viewing the budget of a project. the function fetches the expenses of the project
    from the database and displays them in the UI. the function fetches the budget rules of the project and displays
    them in the UI. the UI allows the user to edit the amount of money available for the project and the rules of the
    project.

    Parameters
    ----------
    project: str
        the selected project name (category)
    budget_rules: pd.DataFrame
        the budget rules table which contains all (updated) rules from which we fetch the rules of the selected project
    """
    budget_rules = budget_rules.loc[
        (budget_rules[CATEGORY] == project)
        & budget_rules[YEAR].isnull()
        & budget_rules[MONTH].isnull()
    ]

    _assure_project_rules_integrity(project, budget_rules)

    budget_rules = get_table(conn, Tables.BUDGET_RULES.value)
    budget_rules = budget_rules.loc[
        (budget_rules[CATEGORY] == project)
        & budget_rules[YEAR].isnull()
        & budget_rules[MONTH].isnull()
    ]

    bank_data = get_table(conn, Tables.BANK.value)
    credit_card_data = get_table(conn, Tables.CREDIT_CARD.value)
    all_data = pd.concat([credit_card_data, bank_data])
    project_data = all_data.loc[
        all_data[TransactionsTableFields.CATEGORY.value] == project
    ]

    total_budget_rule = budget_rules.loc[budget_rules[TAGS] == ALL_TAGS]
    total_sum = project_data[TransactionsTableFields.AMOUNT.value].sum()
    if total_sum != 0:
        total_sum *= -1
    _rule_ui_window(budget_rules, total_budget_rule.iloc[0], total_sum, project_data, allow_edit=True, allow_delete=False)

    for _, rule in budget_rules.loc[budget_rules[TAGS] != ALL_TAGS].iterrows():
        tag = rule[TAGS]
        curr_data = project_data.loc[project_data[TransactionsTableFields.TAG.value] == tag]
        curr_sum = curr_data[TransactionsTableFields.AMOUNT.value].sum()
        if curr_sum != 0:
            curr_sum *= -1
        _rule_ui_window(budget_rules, rule, curr_sum, curr_data, allow_edit=True, allow_delete=False)


def _assure_project_rules_integrity(project: str, project_budget_rules: pd.DataFrame) -> None:
    """
    This function assures the integrity of the project rules. the function adds missing tags of the project to the rules
    and removes tags that are not in the project anymore.

    Parameters
    ----------
    project: str
        the selected project name (category)
    project_budget_rules: pd.DataFrame
        the budget rules of the selected project
    """
    cat_n_tags = get_categories_and_tags(copy=True)
    tags = cat_n_tags.get(project, [])

    for tag in tags:  # add missing tags of the project to the rules
        if tag in project_budget_rules[TAGS].values:
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

    for tag in project_budget_rules[TAGS].values:  # remove tags that are not in the project anymore
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
