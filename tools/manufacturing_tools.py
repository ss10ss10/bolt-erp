"""Manufacturing agent tools."""

import logging

import pandas as pd
from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, pie_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)

# Normalise quality pass/fail — accept "pass", "passed", "ok", "good"
_PASS_VALS = {"pass", "passed", "ok", "good", "approved", "accepted"}
_COMPLETED_STATUSES = {"completed", "done", "finished", "closed"}


@function_tool(strict_mode=False)
def get_manufacturing_orders(
    ctx: RunContextWrapper[ERPContext],
    status: str = "",
    work_center: str = "",
    product_id: str = "",
    limit: int = 50,
) -> str:
    """Retrieve manufacturing / production orders with optional filters.

    Args:
        status: Filter by status (planned, in_progress, completed, cancelled).
        work_center: Filter by work centre name.
        product_id: Filter by product ID.
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_manufacturing_orders  status=%r work_center=%r product=%r", status, work_center, product_id)
    ctx.context.active_agent = "Manufacturing Agent"
    df = load("manufacturing_orders")
    products = load("products")
    if df.empty:
        return "No manufacturing orders data available."

    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if work_center:
        df = df[df["work_center"].str.lower().str.contains(work_center.lower(), na=False)]
    if product_id:
        df = df[df["product_id"].astype(str) == str(product_id)]

    if not products.empty:
        df = df.merge(products[["product_id", "name", "category"]], on="product_id", how="left")

    df = df.head(limit)
    ctx.context.add_table("Manufacturing Orders", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_production_summary(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return production summary: count and cost by status, top work centres, and efficiency insights."""
    logger.info("TOOL get_production_summary")
    ctx.context.active_agent = "Manufacturing Agent"
    df = load("manufacturing_orders")
    if df.empty:
        return "No manufacturing orders data available."

    by_status = (
        df.groupby("status")
        .agg(
            order_count=("mo_id", "count"),
            total_cost=("production_cost", "sum"),
            avg_yield_pct=("yield_pct", "mean"),
        )
        .reset_index()
    )
    by_status["avg_yield_pct"] = by_status["avg_yield_pct"].round(1)
    by_status["total_cost"] = by_status["total_cost"].round(2)

    # Work centre performance
    by_wc = (
        df.groupby("work_center")
        .agg(orders=("mo_id", "count"), avg_yield=("yield_pct", "mean"), total_cost=("production_cost", "sum"))
        .reset_index()
        .sort_values("avg_yield", ascending=False)
    )
    by_wc["avg_yield"] = by_wc["avg_yield"].round(1)

    overall_yield = df["yield_pct"].mean()
    total_cost = df["production_cost"].sum()

    ctx.context.add_table("Production Summary by Status", by_status)
    ctx.context.add_table("Work Centre Performance", by_wc)
    ctx.context.add_chart(
        bar_chart(by_status, x="status", y="order_count", title="Manufacturing Orders by Status")
    )
    ctx.context.add_chart(
        bar_chart(by_wc.head(10), x="work_center", y="avg_yield", title="Avg Yield by Work Centre (%)")
    )

    return (
        f"**Production Overview**\n"
        f"- Total orders: {len(df):,}  |  Total cost: ${total_cost:,.2f}  |  Overall avg yield: {overall_yield:.1f}%\n"
        f"- Top work centre: {by_wc.iloc[0]['work_center']} ({by_wc.iloc[0]['avg_yield']}% yield)\n"
        f"- Lowest yield: {by_wc.iloc[-1]['work_center']} ({by_wc.iloc[-1]['avg_yield']}%)\n\n"
        + df_to_markdown(by_status)
    )


@function_tool(strict_mode=False)
def get_bom(
    ctx: RunContextWrapper[ERPContext],
    product_id: str = "",
) -> str:
    """Return the Bill of Materials (BOM) for a given product, or the full BOM table.

    Args:
        product_id: The parent product ID to look up. Leave empty for the full BOM table.
    """
    logger.info("TOOL get_bom  product_id=%r", product_id)
    ctx.context.active_agent = "Manufacturing Agent"
    df = load("bom")
    products = load("products")
    if df.empty:
        return "No BOM data available."

    if product_id:
        df = df[df["parent_product_id"].astype(str) == str(product_id)]

    if not products.empty:
        df = df.merge(
            products[["product_id", "name"]].rename(columns={"product_id": "parent_product_id", "name": "parent_name"}),
            on="parent_product_id",
            how="left",
        )
        df = df.merge(
            products[["product_id", "name"]].rename(
                columns={"product_id": "component_product_id", "name": "component_name"}
            ),
            on="component_product_id",
            how="left",
        )

    ctx.context.add_table("Bill of Materials", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_quality_report(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return quality analysis: pass/fail rates per work centre, yield distribution, and underperformers."""
    logger.info("TOOL get_quality_report")
    ctx.context.active_agent = "Manufacturing Agent"
    df = load("manufacturing_orders")
    if df.empty:
        return "No manufacturing orders data available."

    # Accept all completed statuses
    completed = df[df["status"].str.lower().isin(_COMPLETED_STATUSES)].copy()
    if completed.empty:
        statuses = df["status"].unique().tolist()
        logger.warning("No completed MOs. Statuses in data: %s", statuses)
        # Fall back to all orders
        completed = df.copy()

    # Normalise quality_status to pass/fail
    completed["is_pass"] = completed["quality_status"].str.lower().isin(_PASS_VALS)
    overall_yield = completed["yield_pct"].mean()
    pass_rate = completed["is_pass"].mean() * 100

    by_wc = (
        completed.groupby("work_center")
        .agg(
            orders=("mo_id", "count"),
            avg_yield=("yield_pct", "mean"),
            pass_count=("is_pass", "sum"),
        )
        .reset_index()
    )
    by_wc["pass_rate_pct"] = (by_wc["pass_count"] / by_wc["orders"] * 100).round(1)
    by_wc["avg_yield"] = by_wc["avg_yield"].round(1)
    by_wc = by_wc.sort_values("pass_rate_pct")

    # Flag underperformers (below average yield)
    by_wc["status"] = by_wc["avg_yield"].apply(lambda y: "⚠ Below Avg" if y < overall_yield else "✓ OK")

    ctx.context.add_table("Quality Report by Work Centre", by_wc)
    ctx.context.add_chart(
        bar_chart(by_wc, x="work_center", y="pass_rate_pct", title="Quality Pass Rate by Work Centre (%)")
    )
    ctx.context.add_chart(
        bar_chart(by_wc, x="work_center", y="avg_yield", title="Average Yield by Work Centre (%)")
    )

    underperformers = by_wc[by_wc["avg_yield"] < overall_yield]
    return (
        f"**Quality Summary** ({len(completed)} completed orders)\n"
        f"- Overall pass rate: **{pass_rate:.1f}%**  |  Overall avg yield: **{overall_yield:.1f}%**\n"
        f"- Best work centre: {by_wc.iloc[-1]['work_center']} ({by_wc.iloc[-1]['avg_yield']}% yield)\n"
        f"- Underperforming work centres ({len(underperformers)}): "
        + ", ".join(underperformers["work_center"].tolist()) + "\n\n"
        + df_to_markdown(by_wc)
    )
