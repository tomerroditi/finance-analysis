import pandas as pd
import streamlit as st
import sqlalchemy as sa

from datetime import datetime
from copy import deepcopy

from fad.app.naming_conventions import Tables, TransactionsTableFields, NonExpensesCategories, BudgetRulesTableFields
from fad.app.utils.data import get_db_connection, get_table, get_categories_and_tags

# TODO: refactor this module to be more modular and clean

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
@st.fragment
def select_custom_month():
    """
    This function creates a UI for selecting a custom month and year to view its budget. The selected month and year are
    stored in the session state variables `year` and `month`
    """
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


def select_current_month() -> None:
    """
    This function creates a UI for selecting the current month and year to view its budget. The selected month and year
    are stored in the session state variables `year` and `month`
    """
    if st.button("Current Month"):
        st.session_state.year = datetime.now().year
        st.session_state.month = datetime.now().month


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

    cat_n_tags = get_categories_and_tags(copy=True)
    for _, rule in budget_rules.iterrows():
        used_tags = rule[TAGS].split(";")
        if used_tags == [ALL_TAGS]:
            cat_n_tags.pop(rule[CATEGORY], None)
        else:
            available_tags = cat_n_tags.get(rule[CATEGORY], [])
            available_tags = [tag for tag in available_tags if tag not in used_tags]
            cat_n_tags[rule[CATEGORY]] = available_tags

    with st.expander("Add New Rule"):
        if budget_rules.empty:
            # add a total budget rule, this could not be deleted hence if curr rules are not empty it must already exist
            st.markdown("Before adding new budget allocation, please set your total budget")
            col_input, col_set = st.columns([3, 1])
            total_budget = col_input.number_input(TOTAL_BUDGET, key="total_budget_input", label_visibility="hidden", value=1)
            if total_budget <= 0:
                st.error("Total budget must be a positive number")

            col_set.markdown("<br>", unsafe_allow_html=True)
            if col_set.button("Set Total Budget", key="set_total_budget_button", use_container_width=True):
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

            total_budget = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
            budget_rules = budget_rules.loc[~budget_rules.index.isin(budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET].index)]
            if total_budget < budget_rules[AMOUNT].sum() + amount:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                return
            if not budget_rules.loc[budget_rules[CATEGORY] == category].empty and tags == [ALL_TAGS]:
                st.error(f"You cannot have a rule with {ALL_TAGS} for a category that already has rules with specific tags")
                return

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

    with conn.session as s:
        last_month_rules = budget_rules.loc[
            (budget_rules[YEAR] == last_year) &
            (budget_rules[MONTH] == last_month)
        ]
        if last_month_rules.empty:
            return

        cmd = sa.text(
            f"DELETE FROM {Tables.BUDGET_RULES.value} WHERE year = :year AND month = :month"
        )
        params = {
            YEAR: year,
            MONTH: month
        }
        s.execute(cmd, params)
        s.commit()

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
    rule_ui_window(budget_rules, total_budget_rule.iloc[0], total_sum, allow_edit=True, allow_delete=False)

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
        rule_ui_window(budget_rules, rule, curr_sum)

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
        rule_ui_window(budget_rules, rule, data[TransactionsTableFields.AMOUNT.value].sum() * -1, allow_edit=False, allow_delete=False)


def rule_ui_window(budget_rules: pd.DataFrame, rule: pd.Series, curr_amount: float, allow_edit: bool = True, allow_delete: bool = True) -> None:
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
    allow_edit:
        a boolean flag that indicates whether the user is allowed to edit the rule
    allow_delete:
        a boolean flag that indicates whether the user is allowed to delete the rule
    """
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
        args=(rule, budget_rules),
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
def edit_budget_rule_dialog(rule: pd.Series, budget_rules: pd.DataFrame) -> None:
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
    is_project_rule = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])
    if rule[CATEGORY] != TOTAL_BUDGET:
        cat_n_tags = get_categories_and_tags(copy=True)
        if not is_project_rule:
            budget_rules = budget_rules.loc[
                (budget_rules[YEAR] == rule[YEAR])
                & (budget_rules[MONTH] == rule[MONTH])
            ]
            budget_rules = budget_rules[budget_rules[CATEGORY] == rule[CATEGORY]]
            current_tags = rule[TAGS].split(";")
            used_tags = budget_rules[TAGS].apply(lambda x: x.split(";"))
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
    verify_new_values(budget_rules, rule, amount, category, tags)

    if st.button("Update Rule", key=f"edit_{rule[ID]}_submit"):
        if amount <= 0:
            st.error("Amount must be a positive number")
            return
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


def verify_new_values(
        budget_rules: pd.DataFrame,
        rule: pd.Series,
        new_amount: float,
        new_category: str,
        new_tags: list[str],
        new_name: str
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
    rule: pd.Series
        the budget rule to edit
    new_amount: float
        the new amount of money available for the rule
    new_category: str
        the new category of the rule
    new_tags: list[str]
        the new tags of the rule
    new_name: str
        the new name of the rule
    """
    if new_amount <= 0:
        st.error("Amount must be a positive number")
    if new_category is None:
        st.error("Please select a category")
        st.stop()
    if not new_tags:
        st.error("Please select at least one tag")
        st.stop()
    if new_name == "":
        st.error("Please enter a name")
        st.stop()

    is_project_rule = pd.isnull(rule[YEAR]) and pd.isnull(rule[MONTH])
    if is_project_rule:
        budget_rules = budget_rules.loc[
            (budget_rules[YEAR].isnull())
            & (budget_rules[MONTH].isnull())
            & (budget_rules[CATEGORY] == rule[CATEGORY])
        ]
        if rule[TAGS] == ALL_TAGS:
            total_rules_amount = budget_rules[budget_rules[TAGS] != ALL_TAGS][AMOUNT].sum()
            if new_amount < total_rules_amount:
                st.error("The total budget must be greater than the sum of all other rules of the project")
                st.stop()
        else:
            total_budget = budget_rules.loc[budget_rules[TAGS] == ALL_TAGS][AMOUNT].values[0]
            total_rules_amount = budget_rules[budget_rules[TAGS] != ALL_TAGS][AMOUNT].sum() - rule[AMOUNT]
            new_total_rules_amount = total_rules_amount + new_amount
            if new_total_rules_amount > total_budget:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                st.stop()
    else:
        budget_rules = budget_rules.loc[
            (budget_rules[YEAR] == rule[YEAR])
            & (budget_rules[MONTH] == rule[MONTH])
        ]
        if rule[CATEGORY] == TOTAL_BUDGET:
            total_rules_amount = budget_rules.loc[budget_rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum()
            if new_amount < total_rules_amount:
                st.error("The total budget must be greater than the sum of all other rules of the month")
                st.stop()
        else:
            total_budget = budget_rules.loc[budget_rules[CATEGORY] == TOTAL_BUDGET][AMOUNT].values[0]
            total_rules_amount = budget_rules.loc[budget_rules[CATEGORY] != TOTAL_BUDGET][AMOUNT].sum() - rule[AMOUNT]
            new_total_rules_amount = total_rules_amount + new_amount
            if new_total_rules_amount > total_budget:
                st.error("The total budget is exceeded. please set a lower amount or increase the total budget")
                st.stop()

        if new_tags == [ALL_TAGS]:
            if not budget_rules.loc[budget_rules[CATEGORY] == new_category].empty:
                st.error(
                    f"You cannot have a rule with {ALL_TAGS} for a category that already has rules with specific tags"
                )
                st.stop()


@st.dialog("Are you sure you want to delete this rule?")
def delete_budget_rule_dialog(id_: int) -> None:
    """
    This function creates a dialog for asking the user if they are sure they want to delete the rule. if the user clicks
    on "Yes", the rule is deleted from the database. if the user clicks on "No", the dialog is closed.

    Parameters
    ----------
    id_: int
        the id of the rule to delete
    """
    if st.button("Yes"):
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

    cat_n_tags = deepcopy(get_categories_and_tags())
    tags = cat_n_tags.get(project, [])
    for tag in tags:  # add missing tags of the project to the rules
        if tag in budget_rules[TAGS].values:
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

    for tag in budget_rules[TAGS].values:  # remove tags that are not in the project anymore
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
    rule_ui_window(budget_rules, total_budget_rule.iloc[0], total_sum, allow_edit=True, allow_delete=False)

    budget_rules = budget_rules.loc[~budget_rules.index.isin(total_budget_rule.index)]
    for _, rule in budget_rules.iterrows():
        tag = rule[TAGS]
        curr_data = project_data.loc[project_data[TransactionsTableFields.TAG.value] == tag]
        curr_sum = curr_data[TransactionsTableFields.AMOUNT.value].sum()
        if curr_sum != 0:
            curr_sum *= -1
        rule_ui_window(budget_rules, rule, curr_sum, allow_edit=True, allow_delete=False)
