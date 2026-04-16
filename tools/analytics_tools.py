"""Analytics & BI agent tools — cross-domain KPI and trend analysis."""

import logging

import pandas as pd
from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, line_chart, pie_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)

_COMPLETED_ORDER_STATUSES = {"delivered", "shipped", "confirmed"}
_COMPLETED_MFG_STATUSES = {"completed", "done", "finished"}


@function_tool(strict_mode=False)
def get_executive_kpi_dashboard(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return a high-level KPI dashboard spanning sales, inventory, procurement, finance, and manufacturing.

    Always call this first for any 'overview', 'dashboard', or 'how is the business doing' requests.
    """
    logger.info("TOOL get_executive_kpi_dashboard")
    ctx.context.active_agent = "Analytics BI Agent"

    kpis = {}
    alerts = []

    # ── Sales ──────────────────────────────────────────────────────────────────
    orders = load("orders")
    if not orders.empty:
        active = orders[orders["status"].str.lower().isin(_COMPLETED_ORDER_STATUSES)]
        kpis["Total Revenue"] = f"${active['total_amount'].sum():,.0f}"
        kpis["Total Orders"] = f"{len(orders):,}"
        kpis["Avg Order Value"] = f"${active['total_amount'].mean():,.0f}"

        # MoM revenue trend for last 2 periods
        try:
            orders["_period"] = orders["order_date"].astype(str).str[:7]
            rev_by_month = (
                active.assign(_period=active["order_date"].astype(str).str[:7])
                .groupby("_period")["total_amount"]
                .sum()
                .sort_index()
            )
            if len(rev_by_month) >= 2:
                growth = (rev_by_month.iloc[-1] - rev_by_month.iloc[-2]) / rev_by_month.iloc[-2] * 100
                kpis["Latest Revenue Growth (MoM)"] = f"{growth:+.1f}%"
                if growth < -10:
                    alerts.append(f"⚠️ Revenue down {abs(growth):.1f}% MoM")
        except Exception:
            pass

    # ── Inventory ──────────────────────────────────────────────────────────────
    inv = load("inventory")
    products = load("products")
    if not inv.empty and not products.empty:
        merged = inv.merge(products[["product_id", "min_stock_level"]], on="product_id", how="left")
        if "min_stock_level" in merged.columns:
            low_stock = int((merged["qty_available"] <= merged["min_stock_level"]).sum())
            kpis["Low Stock SKUs"] = str(low_stock)
            if low_stock > 0:
                alerts.append(f"⚠️ {low_stock} SKUs below minimum stock level")
        kpis["Total Inventory Units"] = f"{int(inv['qty_available'].sum()):,}"

    # ── Procurement ─────────────────────────────────────────────────────────────
    pos = load("purchase_orders")
    if not pos.empty:
        kpis["Total Procurement Spend"] = f"${pos['total_amount'].sum():,.0f}"
        open_pos = int((pos["status"].str.lower().isin(["pending", "confirmed"])).sum())
        kpis["Open Purchase Orders"] = str(open_pos)

    # ── Finance ─────────────────────────────────────────────────────────────────
    invoices = load("invoices")
    if not invoices.empty:
        overdue = invoices[
            (invoices["type"].str.lower() == "sales")
            & (invoices["status"].str.lower() == "overdue")
        ]
        total_overdue = overdue["amount"].sum()
        kpis["Overdue Receivables"] = f"${total_overdue:,.0f}"
        if total_overdue > 50000:
            alerts.append(f"⚠️ ${total_overdue:,.0f} in overdue receivables")

    # ── Manufacturing ───────────────────────────────────────────────────────────
    mfg = load("manufacturing_orders")
    if not mfg.empty:
        in_prog = mfg[mfg["status"].str.lower() == "in_progress"]
        kpis["Active Production Orders"] = str(len(in_prog))
        comp = mfg[mfg["status"].str.lower().isin(_COMPLETED_MFG_STATUSES)]
        if not comp.empty:
            avg_yield = comp["yield_pct"].mean()
            kpis["Avg Production Yield"] = f"{avg_yield:.1f}%"
            if avg_yield < 85:
                alerts.append(f"⚠️ Avg production yield {avg_yield:.1f}% — below 85% target")

    # ── Gross Margin ────────────────────────────────────────────────────────────
    if "Total Revenue" in kpis and "Total Procurement Spend" in kpis:
        try:
            rev_val = float(kpis["Total Revenue"].replace("$", "").replace(",", ""))
            spend_val = float(kpis["Total Procurement Spend"].replace("$", "").replace(",", ""))
            margin = (rev_val - spend_val) / rev_val * 100 if rev_val > 0 else 0
            kpis["Estimated Gross Margin"] = f"{margin:.1f}%"
            if margin < 20:
                alerts.append(f"⚠️ Gross margin {margin:.1f}% — below 20% threshold")
        except Exception:
            pass

    if not kpis:
        return "No data available yet. Please add CSV files to the data/ folder."

    kpi_df = pd.DataFrame([{"KPI": k, "Value": v} for k, v in kpis.items()])
    ctx.context.add_table("Executive KPI Dashboard", kpi_df)

    alert_text = "\n".join(alerts) if alerts else "✅ No critical alerts"
    return (
        f"## Executive Dashboard\n\n"
        f"**Alerts & Watchlist:**\n{alert_text}\n\n"
        + df_to_markdown(kpi_df)
    )


@function_tool(strict_mode=False)
def get_revenue_vs_cost_trend(
    ctx: RunContextWrapper[ERPContext],
    group_by: str = "month",
) -> str:
    """Compare revenue (from orders) vs procurement spend over time, including gross margin.

    Args:
        group_by: Time granularity — 'month', 'quarter', or 'year'.
    """
    logger.info("TOOL get_revenue_vs_cost_trend  group_by=%r", group_by)
    ctx.context.active_agent = "Analytics BI Agent"

    orders = load("orders")
    pos = load("purchase_orders")
    if orders.empty and pos.empty:
        return "No data available for revenue vs cost analysis."

    def assign_period(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
        df = df.copy()
        df[date_col] = df[date_col].astype(str)
        if group_by == "month":
            df["period"] = df[date_col].str[:7]
        elif group_by == "quarter":
            df["date_dt"] = pd.to_datetime(df[date_col], errors="coerce")
            df["period"] = df["date_dt"].dt.to_period("Q").astype(str)
        else:
            df["period"] = df[date_col].str[:4]
        return df

    rows = []
    if not orders.empty:
        o = assign_period(orders, "order_date")
        o = o[o["status"].str.lower().isin(_COMPLETED_ORDER_STATUSES)]
        rev = o.groupby("period")["total_amount"].sum().rename("revenue")
        rows.append(rev)

    if not pos.empty:
        p = assign_period(pos, "po_date")
        spend = p.groupby("period")["total_amount"].sum().rename("procurement_spend")
        rows.append(spend)

    summary = pd.concat(rows, axis=1).fillna(0).reset_index().sort_values("period")

    if "revenue" in summary.columns and "procurement_spend" in summary.columns:
        summary["gross_margin"] = summary["revenue"] - summary["procurement_spend"]
        summary["margin_pct"] = (summary["gross_margin"] / summary["revenue"] * 100).round(1)
        summary["rev_growth_pct"] = summary["revenue"].pct_change().mul(100).round(1)

    ctx.context.add_table(f"Revenue vs Cost ({group_by.capitalize()})", summary)
    y_cols = [c for c in ["revenue", "procurement_spend", "gross_margin"] if c in summary.columns]
    ctx.context.add_chart(
        line_chart(summary, x="period", y=y_cols, title=f"Revenue vs Procurement Spend ({group_by.capitalize()})")
    )

    if "margin_pct" in summary.columns:
        avg_margin = summary["margin_pct"].mean()
        best_margin_period = summary.loc[summary["margin_pct"].idxmax(), "period"]
        worst_margin_period = summary.loc[summary["margin_pct"].idxmin(), "period"]
        return (
            f"**Revenue vs Cost Analysis ({group_by})**\n"
            f"- Avg gross margin: **{avg_margin:.1f}%**\n"
            f"- Best margin period: {best_margin_period} ({summary.loc[summary['margin_pct'].idxmax(), 'margin_pct']}%)\n"
            f"- Worst margin period: {worst_margin_period} ({summary.loc[summary['margin_pct'].idxmin(), 'margin_pct']}%)\n\n"
            + df_to_markdown(summary)
        )
    return df_to_markdown(summary)


@function_tool(strict_mode=False)
def get_top_products_by_revenue(
    ctx: RunContextWrapper[ERPContext],
    n: int = 10,
) -> str:
    """Return the top N products ranked by total revenue from order line items, with category breakdown.

    Args:
        n: Number of top products to return (default 10).
    """
    logger.info("TOOL get_top_products_by_revenue  n=%d", n)
    ctx.context.active_agent = "Analytics BI Agent"
    items = load("order_items")
    products = load("products")
    orders = load("orders")
    if items.empty:
        return "No order items data available."

    if not orders.empty:
        valid_orders = orders[orders["status"].str.lower().isin(_COMPLETED_ORDER_STATUSES)]["order_id"]
        items = items[items["order_id"].isin(valid_orders)]

    rev = (
        items.groupby("product_id")
        .agg(total_revenue=("line_total", "sum"), units_sold=("quantity", "sum"))
        .reset_index()
    )
    total_rev = rev["total_revenue"].sum()

    if not products.empty:
        rev = rev.merge(products[["product_id", "name", "category"]], on="product_id", how="left")

    top = rev.nlargest(n, "total_revenue").reset_index(drop=True)
    top["revenue_share_pct"] = (top["total_revenue"] / total_rev * 100).round(1)

    ctx.context.add_table(f"Top {n} Products by Revenue", top)
    name_col = "name" if "name" in top.columns else "product_id"
    ctx.context.add_chart(
        bar_chart(top, x=name_col, y="total_revenue", title=f"Top {n} Products by Revenue ($)")
    )

    # Category concentration
    if "category" in top.columns:
        cat_share = top.groupby("category")["total_revenue"].sum().sort_values(ascending=False)
        cat_share_pct = (cat_share / total_rev * 100).round(1)
        cat_text = ", ".join([f"{cat} {pct}%" for cat, pct in cat_share_pct.items()])
    else:
        cat_text = "n/a"

    top_n_share = top["revenue_share_pct"].sum()
    return (
        f"**Top {n} Products** account for **{top_n_share:.1f}%** of total revenue.\n"
        f"- #1: {top.iloc[0].get('name', top.iloc[0]['product_id'])} — ${top.iloc[0]['total_revenue']:,.0f} ({top.iloc[0]['revenue_share_pct']}%)\n"
        f"- Category breakdown: {cat_text}\n\n"
        + df_to_markdown(top)
    )


@function_tool(strict_mode=False)
def get_operational_health_summary(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return a cross-domain operational health scorecard with RAG status (Green/Amber/Red) for each domain."""
    logger.info("TOOL get_operational_health_summary")
    ctx.context.active_agent = "Analytics BI Agent"

    metrics = []

    # ── Logistics ──────────────────────────────────────────────────────────────
    shipments = load("shipments")
    if not shipments.empty:
        delivered = shipments[shipments["status"].str.lower().isin({"delivered", "completed"})]
        if not delivered.empty:
            try:
                ed = pd.to_datetime(delivered["expected_delivery"], errors="coerce")
                ad = pd.to_datetime(delivered["actual_delivery"], errors="coerce")
                otd = round(((ad - ed).dt.days <= 0).mean() * 100, 1)
                rag = "🟢 Green" if otd >= 90 else ("🟡 Amber" if otd >= 75 else "🔴 Red")
                metrics.append({"Domain": "Logistics", "Metric": "On-Time Delivery Rate", "Value": f"{otd}%", "Status": rag})
            except Exception:
                pass

    # ── Inventory ──────────────────────────────────────────────────────────────
    inv = load("inventory")
    products = load("products")
    if not inv.empty and not products.empty:
        m = inv.merge(products[["product_id", "min_stock_level"]], on="product_id", how="left")
        if "min_stock_level" in m.columns:
            low = int((m["qty_available"] <= m["min_stock_level"]).sum())
            total_skus = len(m)
            low_pct = low / total_skus * 100 if total_skus else 0
            rag = "🟢 Green" if low_pct < 5 else ("🟡 Amber" if low_pct < 15 else "🔴 Red")
            metrics.append({"Domain": "Inventory", "Metric": "Low Stock SKUs", "Value": f"{low} ({low_pct:.1f}%)", "Status": rag})

    # ── Manufacturing ───────────────────────────────────────────────────────────
    mfg = load("manufacturing_orders")
    if not mfg.empty:
        comp = mfg[mfg["status"].str.lower().isin(_COMPLETED_MFG_STATUSES)]
        if not comp.empty:
            avg_yield = round(comp["yield_pct"].mean(), 1)
            rag = "🟢 Green" if avg_yield >= 90 else ("🟡 Amber" if avg_yield >= 80 else "🔴 Red")
            metrics.append({"Domain": "Manufacturing", "Metric": "Avg Production Yield", "Value": f"{avg_yield}%", "Status": rag})

    # ── Procurement ─────────────────────────────────────────────────────────────
    pos = load("purchase_orders")
    suppliers = load("suppliers")
    if not pos.empty and not suppliers.empty:
        _COMPLETED = {"delivered", "closed", "completed", "received"}
        completed_pos = pos[pos["status"].str.lower().isin(_COMPLETED)]
        if not completed_pos.empty:
            try:
                cp = completed_pos.copy()
                cp["expected_delivery"] = pd.to_datetime(cp["expected_delivery"], errors="coerce")
                cp["actual_delivery"] = pd.to_datetime(cp["actual_delivery"], errors="coerce")
                otd_po = round(((cp["actual_delivery"] - cp["expected_delivery"]).dt.days <= 0).mean() * 100, 1)
                rag = "🟢 Green" if otd_po >= 85 else ("🟡 Amber" if otd_po >= 70 else "🔴 Red")
                metrics.append({"Domain": "Procurement", "Metric": "Supplier On-Time Rate", "Value": f"{otd_po}%", "Status": rag})
            except Exception:
                pass

    # ── Finance ─────────────────────────────────────────────────────────────────
    invoices = load("invoices")
    if not invoices.empty:
        overdue = invoices[
            (invoices["type"].str.lower() == "sales")
            & (invoices["status"].str.lower() == "overdue")
        ]
        total_rev = invoices[invoices["type"].str.lower() == "sales"]["amount"].sum()
        overdue_val = overdue["amount"].sum()
        overdue_pct = overdue_val / total_rev * 100 if total_rev > 0 else 0
        rag = "🟢 Green" if overdue_pct < 5 else ("🟡 Amber" if overdue_pct < 15 else "🔴 Red")
        metrics.append({"Domain": "Finance", "Metric": "Overdue Receivables", "Value": f"${overdue_val:,.0f} ({overdue_pct:.1f}%)", "Status": rag})

    if not metrics:
        return "No data available yet."

    df = pd.DataFrame(metrics)
    ctx.context.add_table("Operational Health Scorecard", df)

    green = sum(1 for m in metrics if "Green" in m["Status"])
    amber = sum(1 for m in metrics if "Amber" in m["Status"])
    red = sum(1 for m in metrics if "Red" in m["Status"])

    return (
        f"**Operational Health Scorecard** — {green} Green / {amber} Amber / {red} Red\n\n"
        + df_to_markdown(df)
    )
