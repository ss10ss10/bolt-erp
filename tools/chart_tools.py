"""Plotly figure factory helpers used by agent query tools."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str | list[str],
    title: str = "",
    color: str | None = None,
    orientation: str = "v",
) -> go.Figure:
    fig = px.bar(
        df,
        x=x,
        y=y,
        title=title,
        color=color,
        orientation=orientation,
        template="plotly_white",
    )
    fig.update_layout(title_font_size=16, margin=dict(t=50, b=40))
    return fig


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str | list[str],
    title: str = "",
    color: str | None = None,
) -> go.Figure:
    fig = px.line(
        df,
        x=x,
        y=y,
        title=title,
        color=color,
        markers=True,
        template="plotly_white",
    )
    fig.update_layout(title_font_size=16, margin=dict(t=50, b=40))
    return fig


def pie_chart(
    df: pd.DataFrame,
    names: str,
    values: str,
    title: str = "",
) -> go.Figure:
    fig = px.pie(df, names=names, values=values, title=title, template="plotly_white")
    fig.update_layout(title_font_size=16, margin=dict(t=50, b=40))
    return fig


def scatter_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str | None = None,
    size: str | None = None,
    hover_name: str | None = None,
) -> go.Figure:
    fig = px.scatter(
        df,
        x=x,
        y=y,
        title=title,
        color=color,
        size=size,
        hover_name=hover_name,
        template="plotly_white",
    )
    fig.update_layout(title_font_size=16, margin=dict(t=50, b=40))
    return fig


def heatmap(
    df: pd.DataFrame,
    title: str = "",
) -> go.Figure:
    """Render a DataFrame as a heatmap (numeric values only)."""
    numeric = df.select_dtypes("number")
    fig = px.imshow(
        numeric,
        title=title,
        aspect="auto",
        template="plotly_white",
        color_continuous_scale="Blues",
    )
    fig.update_layout(title_font_size=16, margin=dict(t=50, b=40))
    return fig


def df_to_markdown(df: pd.DataFrame, max_rows: int = 20) -> str:
    """Return a Markdown table string for LLM consumption."""
    if df.empty:
        return "(no data)"
    sample = df.head(max_rows)
    md = sample.to_markdown(index=False)
    if len(df) > max_rows:
        md += f"\n\n*… {len(df) - max_rows} more rows not shown*"
    return md
