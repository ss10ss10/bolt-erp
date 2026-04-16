"""Sales & CRM agent tools."""

import logging

import pandas as pd
from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, line_chart, pie_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@function_tool(strict_mode=False)
def get_orders(
    ctx: RunContextWrapper[ERPContext],
    status: str = "",
    customer_id: str = "",
    sales_rep: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
) -> str:
    """Retrieve sales orders with optional filters.

    Args:
        status: Filter by order status (pending, confirmed, shipped, delivered, cancelled).
        customer_id: Filter by a specific customer ID.
        sales_rep: Filter by sales representative name.
        start_date: Filter orders on or after this date (YYYY-MM-DD).
        end_date: Filter orders on or before this date (YYYY-MM-DD).
        limit: Maximum number of rows to return (default 50).
    """
    logger.info("TOOL get_orders  status=%r customer=%r rep=%r start=%r end=%r limit=%d",
                status, customer_id, sales_rep, start_date, end_date, limit)
    ctx.context.active_agent = "Sales CRM Agent"
    df = load("orders")
    if df.empty:
        return "No orders data available."

    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if customer_id:
        df = df[df["customer_id"].astype(str) == str(customer_id)]
    if sales_rep:
        df = df[df["sales_rep"].str.contains(sales_rep, case=False, na=False)]
    if start_date:
        df = df[df["order_date"] >= start_date]
    if end_date:
        df = df[df["order_date"] <= end_date]

    df = df.head(limit)
    ctx.context.add_table("Orders", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_revenue_summary(
    ctx: RunContextWrapper[ERPContext],
    group_by: str = "month",
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Return total revenue grouped by a time period.

    Args:
        group_by: Time granularity — 'month', 'quarter', or 'year'.
        start_date: Optional start date (YYYY-MM-DD).
        end_date: Optional end date (YYYY-MM-DD).
    """
    logger.info("TOOL get_revenue_summary  group_by=%r start=%r end=%r", group_by, start_date, end_date)
    ctx.context.active_agent = "Sales CRM Agent"
    df = load("orders")
    if df.empty:
        return "No orders data available."

    df = df[df["status"].str.lower().isin(["delivered", "shipped", "confirmed"])]
    if start_date:
        df = df[df["order_date"] >= start_date]
    if end_date:
        df = df[df["order_date"] <= end_date]

    df["order_date"] = df["order_date"].astype(str)

    if group_by == "month":
        df["period"] = df["order_date"].str[:7]
    elif group_by == "quarter":
        import pandas as pd

        df["order_date_dt"] = pd.to_datetime(df["order_date"], errors="coerce")
        df["period"] = df["order_date_dt"].dt.to_period("Q").astype(str)
    else:
        df["period"] = df["order_date"].str[:4]

    summary = (
        df.groupby("period")
        .agg(total_revenue=("total_amount", "sum"), order_count=("order_id", "count"))
        .reset_index()
        .sort_values("period")
    )

    # Add period-over-period growth %
    summary["growth_pct"] = summary["total_revenue"].pct_change().mul(100).round(1)

    best_period = summary.loc[summary["total_revenue"].idxmax()]
    worst_period = summary.loc[summary["total_revenue"].idxmin()]
    avg_revenue = summary["total_revenue"].mean()
    latest_growth = summary["growth_pct"].iloc[-1] if len(summary) > 1 else 0.0

    ctx.context.add_table(f"Revenue by {group_by.capitalize()}", summary)
    ctx.context.add_chart(
        line_chart(summary, x="period", y="total_revenue", title=f"Revenue by {group_by.capitalize()}")
    )

    trend_icon = "📈" if latest_growth > 0 else "📉"
    return (
        f"**Revenue Summary ({group_by})**\n"
        f"- Total periods: {len(summary)}  |  Avg revenue/period: ${avg_revenue:,.0f}\n"
        f"- Peak period: **{best_period['period']}** (${best_period['total_revenue']:,.2f})\n"
        f"- Lowest period: **{worst_period['period']}** (${worst_period['total_revenue']:,.2f})\n"
        f"- Latest growth: {trend_icon} **{latest_growth:+.1f}%** vs previous period\n\n"
        + df_to_markdown(summary)
    )


@function_tool(strict_mode=False)
def get_top_customers(
    ctx: RunContextWrapper[ERPContext],
    n: int = 10,
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Return the top N customers ranked by total order revenue.

    Args:
        n: Number of top customers to return (default 10).
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
    """
    logger.info("TOOL get_top_customers  n=%d start=%r end=%r", n, start_date, end_date)
    ctx.context.active_agent = "Sales CRM Agent"
    orders = load("orders")
    customers = load("customers")
    if orders.empty:
        return "No orders data available."

    orders = orders[orders["status"].str.lower().isin(["delivered", "shipped", "confirmed"])]
    if start_date:
        orders = orders[orders["order_date"] >= start_date]
    if end_date:
        orders = orders[orders["order_date"] <= end_date]

    rev = (
        orders.groupby("customer_id")
        .agg(total_revenue=("total_amount", "sum"), order_count=("order_id", "count"))
        .reset_index()
    )

    if not customers.empty:
        rev = rev.merge(customers[["customer_id", "name", "country", "industry"]], on="customer_id", how="left")

    top = rev.nlargest(n, "total_revenue").reset_index(drop=True)
    total_rev = rev["total_revenue"].sum()
    top["revenue_share_pct"] = (top["total_revenue"] / total_rev * 100).round(1)
    top_n_share = top["revenue_share_pct"].sum()

    ctx.context.add_table(f"Top {n} Customers by Revenue", top)
    name_col = "name" if "name" in top.columns else "customer_id"
    ctx.context.add_chart(
        bar_chart(top, x=name_col, y="total_revenue", title=f"Top {n} Customers by Revenue")
    )
    return (
        f"**Top {n} Customers** account for **{top_n_share:.1f}%** of total revenue.\n"
        f"- #1: {top.iloc[0].get('name', top.iloc[0]['customer_id'])} — ${top.iloc[0]['total_revenue']:,.2f} ({top.iloc[0]['revenue_share_pct']}%)\n\n"
        + df_to_markdown(top)
    )


@function_tool(strict_mode=False)
def get_customers(
    ctx: RunContextWrapper[ERPContext],
    country: str = "",
    industry: str = "",
    account_manager: str = "",
    limit: int = 50,
) -> str:
    """Retrieve customer records with optional filters.

    Args:
        country: Filter by customer country.
        industry: Filter by industry sector.
        account_manager: Filter by assigned account manager name.
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_customers  country=%r industry=%r manager=%r", country, industry, account_manager)
    ctx.context.active_agent = "Sales CRM Agent"
    df = load("customers")
    if df.empty:
        return "No customers data available."

    if country:
        df = df[df["country"].str.lower() == country.lower()]
    if industry:
        df = df[df["industry"].str.contains(industry, case=False, na=False)]
    if account_manager:
        df = df[df["account_manager"].str.contains(account_manager, case=False, na=False)]

    df = df.head(limit)
    ctx.context.add_table("Customers", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_sales_by_channel(
    ctx: RunContextWrapper[ERPContext],
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Return revenue and order count broken down by sales channel.

    Args:
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
    """
    logger.info("TOOL get_sales_by_channel  start=%r end=%r", start_date, end_date)
    ctx.context.active_agent = "Sales CRM Agent"
    df = load("orders")
    if df.empty:
        return "No orders data available."

    if start_date:
        df = df[df["order_date"] >= start_date]
    if end_date:
        df = df[df["order_date"] <= end_date]

    summary = (
        df.groupby("channel")
        .agg(total_revenue=("total_amount", "sum"), order_count=("order_id", "count"))
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )
    ctx.context.add_table("Sales by Channel", summary)
    ctx.context.add_chart(pie_chart(summary, names="channel", values="total_revenue", title="Revenue by Sales Channel"))
    return df_to_markdown(summary)
