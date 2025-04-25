import streamlit as st

from datetime import datetime


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