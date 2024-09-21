import streamlit as st
import pandas as pd
import streamlit_antd_components as sac
from sqlalchemy.sql import text

from datetime import datetime


class PandasFilterWidgets:
    def __init__(self, df: pd.DataFrame, widgets_map: dict[str, str] = None, keys_prefix: str = None):
        """
        This class will create widgets for filtering a Pandas DataFrame and return the filtered DataFrame.

        Parameters
        ----------
        df: pd.DataFrame
            The DataFrame to filter using the widgets.
        widgets_map: dict
            A dictionary whose keys are the column names of the DataFrame and whose values are the type of widget
            to create for that column. Only the columns in this dictionary will be used to create the widgets.
            Optional widgets are: 'text', 'select', 'multiselect', 'number_range', 'date_range'.
        keys_prefix: str
            A prefix to add to the keys of the widgets. This is useful when using multiple instances of this class in
            the same script.
        """
        self.df = df.copy()
        self.widgets_map = widgets_map if widgets_map is not None else {}
        self.keys_prefix = f'pandas_filter_widgets_{keys_prefix if keys_prefix is not None else ""}'
        self.widgets_returns = {}
        self._dates = {}

    def display_widgets(self):
        """
        This function will create the widgets based on the widgets_map and store the values of the widgets in the
        widgets_returns dictionary.
        """
        for column, widget_type in self.widgets_map.items():
            match widget_type:
                case 'text':
                    self.widgets_returns[column] = self.create_text_widget(column)
                case 'select':
                    self.widgets_returns[column] = self.create_select_widget(column, multi=False)
                case 'multiselect':
                    self.widgets_returns[column] = self.create_select_widget(column, multi=True)
                case 'number_range':
                    self.widgets_returns[column] = self.create_slider_widget(column)
                case 'date_range':
                    self.widgets_returns[column] = self.create_date_range_widget(column)
                case _:
                    raise ValueError(f'Invalid widget type: {widget_type}')

    def create_slider_widget(self, column: str) -> tuple[float, float]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        max_val = float(df[column].max())
        min_val = float(df[column].min())
        name = column.replace('_', ' ').title()
        lower_bound, upper_bound = st.slider(
            name, min_val, max_val, (min_val, max_val), 50.0, key=f'{self.keys_prefix}_{column}_slider'
        )
        return lower_bound, upper_bound

    def create_select_widget(self, column: str, multi: bool) -> str | list[str]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        options = df[column].unique()
        options.sort()
        name = column.replace('_', ' ').title()
        if multi:
            selected_list = st.multiselect(name, options, key=f'{self.keys_prefix}_{column}_multiselect')
            return selected_list
        else:
            selected_item = st.selectbox(name, options, key=f'{self.keys_prefix}_{column}_select')
            return selected_item

    def create_text_widget(self, column: str) -> str | None:
        name = column.replace('_', ' ').title()
        text_ = st.text_input(name, key=f"{self.keys_prefix}_{column}_text")
        return text_

    def create_date_range_widget(self, column: str) -> tuple[datetime.date, datetime.date]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        max_val = datetime.today().date()
        min_val = df[column].apply(lambda x: datetime.strptime(x, '%Y-%m-%d')).min().date()

        st.markdown("<br>", unsafe_allow_html=True)
        selection = sac.buttons(
            items=["Custom Date", "Current Month", "Current Year"],
            use_container_width=True,
            variant='outline',
            color=None,
            index=0,
            direction='horizontal',
            key=f'{self.keys_prefix}_{column}_buttons'
        )
        if selection == "Custom Date":
            name = column.replace('_', ' ').title()
            _dates = st.date_input(
                name, (min_val, datetime.today()), min_val, max_val, key=f'{self.keys_prefix}_{column}_date_input',
            )
            self._dates[column] = _dates
        elif selection == "Current Month":
            today = datetime.today()
            month_start = today.replace(day=1)
            self._dates[column] = (month_start.date(), today.date())
        elif selection == "Current Year":
            today = datetime.today()
            year_start = today.replace(month=1, day=1)
            self._dates[column] = (year_start.date(), today.date())

        dates = self._dates.get(column, (min_val, max_val))
        try:
            start_date, end_date = dates
        except ValueError:
            start_date, end_date = dates[0], dates[0]

        return start_date, end_date

    def filter_df(self):
        """
        This function will take the input dataframe and all the widgets generated from
        Streamlit Pandas. It will then return a filtered DataFrame based on the changes
        to the input widgets.

        df => the original Pandas DataFrame
        all_widgets => the widgets created by the function create_widgets().
        """
        res = self.df.copy()
        for column, widget_return in self.widgets_returns.items():
            match self.widgets_map[column]:
                case 'text':
                    res = self.filter_string(res, column, widget_return)
                case 'select':
                    res = self.filter_select(res, column, widget_return)
                case 'multiselect':
                    res = self.filter_select(res, column, widget_return)
                case 'number_range':
                    res = self.filter_range(res, column, widget_return[0], widget_return[1])
                case 'date_range':
                    res = self.filter_date(res, column, widget_return[0], widget_return[1])
        return res

    @staticmethod
    def filter_string(df: pd.DataFrame, column: str, text: str | None) -> pd.DataFrame:
        if text is not None:
            return df
        df = df.loc[df[column].str.contains(text, case=False, na=False), :]
        return df

    @staticmethod
    def filter_date(df: pd.DataFrame, column: str, start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
        df[column] = df[column].apply(lambda x: datetime.strptime(x, '%Y-%m-%d').date())
        df = df.loc[(df[column] >= start_date) & (df[column] <= end_date), :]
        return df

    @staticmethod
    def filter_range(df: pd.DataFrame, column: str, min_val: float, max_val: float) -> pd.DataFrame:
        df = df.loc[(df[column] >= min_val) & (df[column] <= max_val), :]
        return df

    @staticmethod
    def filter_select(df: pd.DataFrame, column: str, selected_values: str | list[str] | None) -> pd.DataFrame:
        if selected_values is None or selected_values == []:
            return df

        if isinstance(selected_values, str):
            selected_values = [selected_values]
        df = df.loc[df[column].isin(selected_values), :]
        return df
