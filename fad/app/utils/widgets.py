from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac


class PandasFilterWidgets:

    BASE_STREAMLIT_KEY = 'pandas_filter_widgets'
    widget_keys = ["slider", "select", "multiselect", "text", "date_input", "buttons", "text_contains"]

    def __init__(self, df: pd.DataFrame, widgets_map: dict[str, str] = None, key_suffix: str = None):
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
        key_suffix: str
            A prefix to add to the keys of the widgets. This is useful when using multiple instances of this class in
            the same script.
        """
        self.df = df.copy()
        self.widgets_map = widgets_map if widgets_map is not None else {}
        self.keys_suffix = f'{self.BASE_STREAMLIT_KEY}_{key_suffix if key_suffix is not None else ""}'
        self.widgets_returns = {}
        self._dates = {}

    def __new__(cls, *args, **kwargs):
        key = f"{cls.BASE_STREAMLIT_KEY}_{kwargs.get('key_suffix', '')}"  # equivalent to self.keys_suffix
        if key in st.session_state:
            instance = st.session_state[key]
            new_df = args[0] if args else kwargs.get('df', None)
            if new_df is None:
                raise ValueError("DataFrame must be provided as a positional or keyword argument.")
            instance.df = new_df.copy()
            return instance
        instance = super(PandasFilterWidgets, cls).__new__(cls)
        st.session_state[key] = instance
        return instance

    def delete_session_state(self):
        """
        This function will remove all the keys from the session state that were created by this instance of the class.
        It also removes the instance itself from the session state.
        It is useful when the DataFrame or the widgets_map change, and we want to reset the widgets.
        """
        for widget_key in self.widget_keys:
            key = f"{widget_key}_{self.keys_suffix}_"
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith(key)]
            for k in keys_to_remove:
                del st.session_state[k]
        del st.session_state[self.keys_suffix]

    def display_widgets(self):
        """
        This function will create the widgets based on the widgets_map and store the values of the widgets in the
        widgets_returns dictionary.
        """
        for column, widget_type in self.widgets_map.items():
            match widget_type:
                case 'text':
                    self.widgets_returns[column] = self.create_text_widget(column)
                case 'text_contains':
                    self.widgets_returns[column] = self.create_text_contains_widget(column)
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
        if df.empty:
            max_val = 0.0
            min_val = 1.0
        else:
            max_val = float(df[column].max())
            min_val = float(df[column].min())

        # Handle case where all values are the same
        if min_val == max_val:
            # Create a small range around the single value
            if min_val == 0:
                min_val = -1.0
                max_val = 1.0
            else:
                # Add/subtract 10% of the absolute value, minimum of 1
                offset = max(abs(min_val) * 0.1, 1.0)
                min_val = min_val - offset
                max_val = max_val + offset

        name = column.replace('_', ' ').title()
        lower_bound, upper_bound = st.slider(
            name, min_val, max_val, (min_val, max_val), 50.0, key=f'slider_{self.keys_suffix}_{column}'
        )
        return lower_bound, upper_bound

    def create_select_widget(self, column: str, multi: bool) -> str | list[str]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        options = df[column].unique()
        options.sort()
        name = column.replace('_', ' ').title()
        if multi:
            selected_list = st.multiselect(name, options, key=f'multiselect_{self.keys_suffix}_{column}')
            return selected_list
        else:
            selected_item = st.selectbox(name, options, key=f'select_{self.keys_suffix}_{column}')
            return selected_item

    def create_text_widget(self, column: str) -> str | None:
        name = column.replace('_', ' ').title()
        text_ = st.text_input(name, key=f"text_{self.keys_suffix}_{column}")
        return text_

    def create_text_contains_widget(self, column: str) -> str | None:
        name = column.replace('_', ' ').title()
        text_ = st.text_input(f"Contains {name}", key=f"text_contains_{self.keys_suffix}_{column}")
        return text_

    def create_date_range_widget(self, column: str) -> tuple[datetime.date, datetime.date]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        if df.empty:
            max_val = datetime.today().date()
            min_val = datetime.today().date()
        else:
            max_val = datetime.today().date()
            min_val = df[column].apply(lambda x: datetime.strptime(x, '%Y-%m-%d') if isinstance(x, str) else x).min().date()

        st.markdown("<br>", unsafe_allow_html=True)
        selection = sac.buttons(
            items=["Custom Date", "Current Month", "Current Year"],
            use_container_width=True,
            variant='outline',
            color=None,
            index=0,
            direction='horizontal',
            key=f'buttons_{self.keys_suffix}_{column}'
        )
        if selection == "Custom Date":
            name = column.replace('_', ' ').title()
            _dates = st.date_input(
                name, (min_val, datetime.today()), min_val, max_val, key=f'date_input_{self.keys_suffix}_{column}',
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

    def filter_df(self) -> pd.DataFrame:
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
                case 'text_contains':
                    res = self.filter_text_contains(res, column, widget_return)
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
        if text is None or text == "":
            return df
        df = df.loc[df[column].str.equals(text, case=False, na=False), :]
        return df

    @staticmethod
    def filter_text_contains(df: pd.DataFrame, column: str, text: str | None) -> pd.DataFrame:
        if text is None or text == "":
            return df
        df = df.loc[df[column].str.contains(text, case=False, na=False), :]
        return df

    @staticmethod
    def filter_date(df: pd.DataFrame, column: str, start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
        df[column] = df[column].apply(lambda x: datetime.strptime(x, '%Y-%m-%d').date() if isinstance(x, str) else x.date())
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
