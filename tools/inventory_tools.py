"""Inventory & Warehouse agent tools."""

import logging

from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, pie_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)


@function_tool(strict_mode=False)
def get_inventory(
    ctx: RunContextWrapper[ERPContext],
    warehouse_id: str = "",
    product_id: str = "",
    low_stock_only: bool = False,
    limit: int = 50,
) -> str:
    """Return current inventory levels across warehouses.

    Args:
        warehouse_id: Filter by a specific warehouse ID.
        product_id: Filter by a specific product ID.
        low_stock_only: If true, return only items where qty_available <= min_stock_level.
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_inventory  warehouse=%r product=%r low_stock=%s", warehouse_id, product_id, low_stock_only)
    ctx.context.active_agent = "Inventory Warehouse Agent"
    inv = load("inventory")
    products = load("products")
    if inv.empty:
        return "No inventory data available."

    if warehouse_id:
        inv = inv[inv["warehouse_id"].astype(str) == str(warehouse_id)]
    if product_id:
        inv = inv[inv["product_id"].astype(str) == str(product_id)]

    if not products.empty:
        inv = inv.merge(
            products[["product_id", "name", "category", "min_stock_level"]],
            on="product_id",
            how="left",
        )

    if low_stock_only and "min_stock_level" in inv.columns:
        inv = inv[inv["qty_available"] <= inv["min_stock_level"]]

    inv = inv.head(limit)
    ctx.context.add_table("Inventory Levels", inv)
    return df_to_markdown(inv)


@function_tool(strict_mode=False)
def get_low_stock_alerts(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return all products where available quantity is at or below the minimum stock level."""
    logger.info("TOOL get_low_stock_alerts")
    ctx.context.active_agent = "Inventory Warehouse Agent"
    inv = load("inventory")
    products = load("products")
    if inv.empty:
        return "No inventory data available."

    if not products.empty:
        inv = inv.merge(
            products[["product_id", "name", "category", "min_stock_level", "reorder_qty"]],
            on="product_id",
            how="left",
        )

    if "min_stock_level" not in inv.columns:
        return "min_stock_level column not found. Cannot compute alerts."

    alerts = inv[inv["qty_available"] <= inv["min_stock_level"]].copy()
    alerts = alerts.sort_values("qty_available")

    ctx.context.add_table("Low Stock Alerts", alerts)
    if not alerts.empty and "name" in alerts.columns:
        ctx.context.add_chart(
            bar_chart(
                alerts.head(20),
                x="name",
                y="qty_available",
                title="Low Stock Items — Available Quantity",
            )
        )
    return df_to_markdown(alerts)


@function_tool(strict_mode=False)
def get_warehouses(
    ctx: RunContextWrapper[ERPContext],
    warehouse_type: str = "",
    country: str = "",
) -> str:
    """Return warehouse details including capacity and utilisation.

    Args:
        warehouse_type: Filter by type (raw, finished, transit).
        country: Filter by country.
    """
    logger.info("TOOL get_warehouses  type=%r country=%r", warehouse_type, country)
    ctx.context.active_agent = "Inventory Warehouse Agent"
    df = load("warehouses")
    if df.empty:
        return "No warehouse data available."

    if warehouse_type:
        df = df[df["warehouse_type"].str.lower() == warehouse_type.lower()]
    if country:
        df = df[df["location_country"].str.lower() == country.lower()]

    ctx.context.add_table("Warehouses", df)
    if not df.empty and "utilization_pct" in df.columns:
        ctx.context.add_chart(
            bar_chart(df, x="name", y="utilization_pct", title="Warehouse Utilisation (%)")
        )
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_inventory_by_category(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return total available inventory quantity grouped by product category."""
    logger.info("TOOL get_inventory_by_category")
    ctx.context.active_agent = "Inventory Warehouse Agent"
    inv = load("inventory")
    products = load("products")
    if inv.empty:
        return "No inventory data available."

    if products.empty:
        return "No products data available."

    merged = inv.merge(products[["product_id", "category"]], on="product_id", how="left")
    summary = (
        merged.groupby("category")
        .agg(
            total_available=("qty_available", "sum"),
            total_reserved=("qty_reserved", "sum"),
            product_count=("product_id", "nunique"),
        )
        .reset_index()
        .sort_values("total_available", ascending=False)
    )

    ctx.context.add_table("Inventory by Category", summary)
    ctx.context.add_chart(
        pie_chart(summary, names="category", values="total_available", title="Inventory Distribution by Category")
    )
    return df_to_markdown(summary)
