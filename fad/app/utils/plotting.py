import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def bar_plot_by_categories(df: pd.DataFrame, values_col: str, category_col: str) -> go.Figure:
    """
    Plot the expenses by categories

    Parameters
    ----------
    df : pd.DataFrame
        The data to plot
    values_col : str
        The column name of the values to plot
    category_col : str
        The column name of the category to group by the data into bars

    Returns
    -------
    None
    """
    df = df.copy()
    df[values_col] = df[values_col] * -1
    if not df.empty:
        df = df.groupby(category_col).sum(numeric_only=True).reset_index()
    fig = go.Figure(
        go.Bar(
            x=df[values_col],
            y=df[category_col],
            orientation='h',
            text=df[values_col].round(2),
            textposition='auto'
        )
    )
    fig.update_layout(
        title='Expenses Recap',
        xaxis_title='Outcome [₪]',
        yaxis_title='Category',
        annotations=[
            dict(
                x=0,  # position along the x-axis, slightly outside the plot
                y=-0.2,  # position along the y-axis, slightly above the plot
                xref='paper',
                yref='paper',
                text='* Negative values represent income',
                showarrow=False
            )
        ]
    )
    return fig


def bar_plot_by_categories_over_time(df: pd.DataFrame, values_col: str, category_col: str, date_col: str,
                                     time_interval: str) -> go.Figure:
    """
    Plot the expenses by categories over time as a stacked bar plot

    Parameters
    ----------
    df : pd.DataFrame
        The data to plot
    values_col : str
        The column name of the values to plot
    category_col : str
        The column name of the category
    date_col : str
        The column name of the date
    time_interval : str
        The time interval to group the data by. Should be one of "1W", "1M", "1Y"

    Returns
    -------
    None
    """
    df = df.copy()
    df[values_col] = df[values_col] * -1
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.groupby(pd.Grouper(key=date_col, freq=time_interval))
    time_str_format = '%Y-%m-%d' if time_interval == '1D' else '%Y-%m' if time_interval == '1M' else '%Y'
    fig = go.Figure()
    for date, data in df:
        curr_date_df = data.groupby(category_col).sum(numeric_only=True).reset_index()
        fig.add_trace(
            go.Bar(
                x=curr_date_df[values_col],
                y=curr_date_df[category_col],
                name=date.strftime(time_str_format),  # noqa, date is a datetime object (pandas sets it as hashable)
                orientation='h'
            )
        )
    title_time_period = 'Days' if time_interval == '1D' else 'Months' if time_interval == '1M' else 'Years'
    fig.update_layout(
        barmode='stack',
        title=f'Expenses Recap Over {title_time_period}',
        xaxis_title='Outcome [₪]',
        yaxis_title='Category',
        xaxis_tickformat=',d',
        annotations=[
            dict(
                x=0,  # position along the x-axis, slightly outside the plot
                y=-0.2,  # position along the y-axis, slightly above the plot
                xref='paper',
                yref='paper',
                text='* Negative values represent income',
                showarrow=False
            )
        ]
    )
    return fig


def pie_plot_by_categories(df: pd.DataFrame, values_col: str, category_col: str) -> go.Figure:
    """
    Plot the expenses by categories

    Parameters
    ----------
    df : pd.DataFrame
        The data to plot
    values_col : str
        The column name of the values to plot
    category_col : str
        The column name of the category to group by the data into bars

    Returns
    -------
    None
    """
    df = df.copy()
    df[values_col] = df[values_col] * -1

    # Get negative and positive values categories
    df_neg = df[df[values_col] < 0].copy()
    df_pos = df[df[values_col] >= 0].copy()

    if not df_neg.empty:
        df_neg = df_neg.groupby(category_col).sum(numeric_only=True).reset_index()

    if not df_pos.empty:
        df_pos = df_pos.groupby(category_col).sum(numeric_only=True).reset_index()

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{'type': 'pie'}, {'type': 'pie'}]],
        subplot_titles=['Outcome [₪]', 'Refunds & Paybacks [₪]']
    )

    fig.add_trace(
        go.Pie(
            labels=df_pos[category_col] if not df_pos.empty else ['No expenses'],
            values=df_pos[values_col] if not df_pos.empty else [1],
            textinfo='label+percent',
            hole=0.3,
            name="Outcome"
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Pie(
            labels=df_neg[category_col] if not df_neg.empty else ['No refunds or paybacks'],
            values=df_neg[values_col] * -1 if not df_neg.empty else [1],
            textinfo='label+percent',
            hole=0.3,
            name="Refunds & Paybacks"
        ),
        row=1, col=2
    )

    fig.update_layout(
        title_text='Expenses Recap',
    )

    return fig
