"""Procurement agent tools."""

import logging

import pandas as pd
from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, line_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)

# Status values that indicate a PO has been fully processed/received
_COMPLETED_STATUSES = {"delivered", "closed", "completed", "received", "done"}


@function_tool(strict_mode=False)
def get_purchase_orders(
    ctx: RunContextWrapper[ERPContext],
    status: str = "",
    supplier_id: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
) -> str:
    """Retrieve purchase orders with optional filters.

    Args:
        status: Filter by PO status (e.g. pending, confirmed, delivered, closed).
        supplier_id: Filter by supplier ID.
        start_date: Filter POs on or after this date (YYYY-MM-DD).
        end_date: Filter POs on or before this date (YYYY-MM-DD).
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_purchase_orders  status=%r supplier=%r start=%r end=%r", status, supplier_id, start_date, end_date)
    ctx.context.active_agent = "Procurement Agent"
    df = load("purchase_orders")
    suppliers = load("suppliers")
    if df.empty:
        return "No purchase orders data available."

    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if supplier_id:
        df = df[df["supplier_id"].astype(str) == str(supplier_id)]
    if start_date:
        df = df[df["po_date"] >= start_date]
    if end_date:
        df = df[df["po_date"] <= end_date]

    if not suppliers.empty:
        df = df.merge(suppliers[["supplier_id", "name"]], on="supplier_id", how="left")

    df = df.head(limit)
    ctx.context.add_table("Purchase Orders", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_suppliers(
    ctx: RunContextWrapper[ERPContext],
    country: str = "",
    category: str = "",
    min_reliability_score: float = 0.0,
) -> str:
    """Return supplier records with optional filters.

    Args:
        country: Filter by supplier country.
        category: Filter by supplier category (raw_material, packaging, equipment).
        min_reliability_score: Only show suppliers with a reliability score >= this value.
    """
    logger.info("TOOL get_suppliers  country=%r category=%r min_score=%.1f", country, category, min_reliability_score)
    ctx.context.active_agent = "Procurement Agent"
    df = load("suppliers")
    if df.empty:
        return "No suppliers data available."

    if country:
        df = df[df["country"].str.lower() == country.lower()]
    if category:
        df = df[df["category"].str.lower() == category.lower()]
    if min_reliability_score > 0 and "reliability_score" in df.columns:
        df = df[df["reliability_score"] >= min_reliability_score]

    ctx.context.add_table("Suppliers", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_supplier_performance(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Analyse supplier performance: on-time delivery rate, average delay, spend, and risk rating.

    Accepts any 'completed' PO status (delivered, closed, completed, received).
    """
    logger.info("TOOL get_supplier_performance")
    ctx.context.active_agent = "Procurement Agent"
    pos = load("purchase_orders")
    suppliers = load("suppliers")
    if pos.empty:
        return "No purchase orders data available."

    # Accept all statuses that indicate the PO is finished
    completed = pos[pos["status"].str.lower().isin(_COMPLETED_STATUSES)].copy()
    if completed.empty:
        statuses = pos["status"].unique().tolist()
        logger.warning("No completed POs found. Statuses in data: %s", statuses)
        return f"No completed purchase orders found. Current PO statuses in data: {statuses}"

    completed["expected_delivery"] = pd.to_datetime(completed["expected_delivery"], errors="coerce")
    completed["actual_delivery"] = pd.to_datetime(completed["actual_delivery"], errors="coerce")
    completed["delay_days"] = (completed["actual_delivery"] - completed["expected_delivery"]).dt.days
    completed["on_time"] = completed["delay_days"] <= 0

    perf = (
        completed.groupby("supplier_id")
        .agg(
            total_orders=("po_id", "count"),
            avg_delay_days=("delay_days", "mean"),
            on_time_rate=("on_time", "mean"),
            total_spend=("total_amount", "sum"),
        )
        .reset_index()
    )
    perf["on_time_rate_pct"] = (perf["on_time_rate"] * 100).round(1)
    perf["avg_delay_days"] = perf["avg_delay_days"].round(1)

    if not suppliers.empty:
        perf = perf.merge(suppliers[["supplier_id", "name", "country", "reliability_score"]], on="supplier_id", how="left")

    # Add risk rating
    def _risk(row):
        if row["on_time_rate_pct"] >= 90:
            return "Low"
        elif row["on_time_rate_pct"] >= 70:
            return "Medium"
        else:
            return "High"
    perf["risk"] = perf.apply(_risk, axis=1)

    perf = perf.sort_values("on_time_rate_pct")  # worst first
    name_col = "name" if "name" in perf.columns else "supplier_id"

    # Summary stats
    worst = perf.iloc[0]
    best = perf.iloc[-1]
    high_risk = (perf["risk"] == "High").sum()
    avg_otd = perf["on_time_rate_pct"].mean()

    ctx.context.add_table("Supplier Performance", perf)
    ctx.context.add_chart(
        bar_chart(perf, x=name_col, y="on_time_rate_pct", title="Supplier On-Time Delivery Rate (%)")
    )

    summary = (
        f"Analysed {len(perf)} suppliers across {len(completed)} completed POs.\n"
        f"- Average on-time delivery rate: {avg_otd:.1f}%\n"
        f"- Best performer: {best.get('name', best['supplier_id'])} ({best['on_time_rate_pct']}%)\n"
        f"- Worst performer: {worst.get('name', worst['supplier_id'])} ({worst['on_time_rate_pct']}%)\n"
        f"- High-risk suppliers (OTD < 70%): {high_risk}\n\n"
    )
    return summary + df_to_markdown(perf)


@function_tool(strict_mode=False)
def get_procurement_spend_trend(
    ctx: RunContextWrapper[ERPContext],
    group_by: str = "month",
) -> str:
    """Return total procurement spend grouped by time period with month-over-month growth.

    Args:
        group_by: Time granularity — 'month', 'quarter', or 'year'.
    """
    logger.info("TOOL get_procurement_spend_trend  group_by=%r", group_by)
    ctx.context.active_agent = "Procurement Agent"
    df = load("purchase_orders")
    if df.empty:
        return "No purchase orders data available."

    df["po_date"] = df["po_date"].astype(str)

    if group_by == "month":
        df["period"] = df["po_date"].str[:7]
    elif group_by == "quarter":
        df["po_date_dt"] = pd.to_datetime(df["po_date"], errors="coerce")
        df["period"] = df["po_date_dt"].dt.to_period("Q").astype(str)
    else:
        df["period"] = df["po_date"].str[:4]

    summary = (
        df.groupby("period")
        .agg(total_spend=("total_amount", "sum"), po_count=("po_id", "count"))
        .reset_index()
        .sort_values("period")
    )
    summary["growth_pct"] = summary["total_spend"].pct_change().mul(100).round(1)

    ctx.context.add_table(f"Procurement Spend by {group_by.capitalize()}", summary)
    ctx.context.add_chart(
        line_chart(summary, x="period", y="total_spend", title=f"Procurement Spend by {group_by.capitalize()}")
    )
    return df_to_markdown(summary)
