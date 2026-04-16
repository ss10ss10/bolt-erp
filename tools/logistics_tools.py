"""Logistics & Shipping agent tools."""

import logging

import pandas as pd
from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, pie_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)


@function_tool(strict_mode=False)
def get_shipments(
    ctx: RunContextWrapper[ERPContext],
    status: str = "",
    carrier: str = "",
    destination_country: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
) -> str:
    """Retrieve shipment records with optional filters.

    Args:
        status: Filter by shipment status (pending, in_transit, customs, delivered).
        carrier: Filter by carrier name.
        destination_country: Filter by destination country.
        start_date: Filter shipments on or after this ship_date (YYYY-MM-DD).
        end_date: Filter shipments on or before this ship_date (YYYY-MM-DD).
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_shipments  status=%r carrier=%r dest=%r start=%r end=%r", status, carrier, destination_country, start_date, end_date)
    ctx.context.active_agent = "Logistics Shipping Agent"
    df = load("shipments")
    if df.empty:
        return "No shipments data available."

    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if carrier:
        df = df[df["carrier"].str.contains(carrier, case=False, na=False)]
    if destination_country:
        df = df[df["destination_country"].str.lower() == destination_country.lower()]
    if start_date:
        df = df[df["ship_date"] >= start_date]
    if end_date:
        df = df[df["ship_date"] <= end_date]

    df = df.head(limit)
    ctx.context.add_table("Shipments", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_delivery_performance(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Compute on-time delivery rate and average delay per carrier."""
    logger.info("TOOL get_delivery_performance")
    ctx.context.active_agent = "Logistics Shipping Agent"
    df = load("shipments")
    if df.empty:
        return "No shipments data available."

    delivered = df[df["status"].str.lower() == "delivered"].copy()
    if delivered.empty:
        # Accept any "completed" status
        delivered = df[df["status"].str.lower().isin({"delivered", "completed", "done"})].copy()
    if delivered.empty:
        return f"No completed shipments found. Statuses in data: {df['status'].unique().tolist()}"

    delivered["expected_delivery"] = pd.to_datetime(delivered["expected_delivery"], errors="coerce")
    delivered["actual_delivery"] = pd.to_datetime(delivered["actual_delivery"], errors="coerce")
    delivered["delay_days"] = (delivered["actual_delivery"] - delivered["expected_delivery"]).dt.days
    delivered["on_time"] = delivered["delay_days"] <= 0

    perf = (
        delivered.groupby("carrier")
        .agg(
            shipments=("shipment_id", "count"),
            avg_delay_days=("delay_days", "mean"),
            on_time_rate=("on_time", "mean"),
            total_freight_cost=("freight_cost", "sum"),
        )
        .reset_index()
    )
    perf["on_time_rate_pct"] = (perf["on_time_rate"] * 100).round(1)
    perf["avg_delay_days"] = perf["avg_delay_days"].round(1)
    perf["cost_per_shipment"] = (perf["total_freight_cost"] / perf["shipments"]).round(2)
    perf["grade"] = perf["on_time_rate_pct"].apply(
        lambda x: "A" if x >= 95 else ("B" if x >= 85 else ("C" if x >= 70 else "D"))
    )
    perf = perf.sort_values("on_time_rate_pct", ascending=False)

    best = perf.iloc[0]
    worst = perf.iloc[-1]
    avg_otd = perf["on_time_rate_pct"].mean()

    ctx.context.add_table("Delivery Performance by Carrier", perf)
    ctx.context.add_chart(
        bar_chart(perf, x="carrier", y="on_time_rate_pct", title="On-Time Delivery Rate by Carrier (%)")
    )
    ctx.context.add_chart(
        bar_chart(perf, x="carrier", y="cost_per_shipment", title="Average Cost per Shipment by Carrier ($)")
    )
    return (
        f"**Delivery Performance** ({len(delivered)} shipments, {len(perf)} carriers)\n"
        f"- Network avg OTD: **{avg_otd:.1f}%**\n"
        f"- Best carrier: **{best['carrier']}** — {best['on_time_rate_pct']}% OTD, ${best['cost_per_shipment']}/shipment (Grade {best['grade']})\n"
        f"- Worst carrier: **{worst['carrier']}** — {worst['on_time_rate_pct']}% OTD, avg {worst['avg_delay_days']} day delay (Grade {worst['grade']})\n\n"
        + df_to_markdown(perf)
    )


@function_tool(strict_mode=False)
def get_vessels(
    ctx: RunContextWrapper[ERPContext],
    vessel_type: str = "",
    current_status: str = "",
    flag: str = "",
) -> str:
    """Return vessel fleet records with optional filters.

    Args:
        vessel_type: Filter by vessel type (e.g. bulk carrier, tanker, container).
        current_status: Filter by operational status (active, docked, maintenance).
        flag: Filter by flag state / country of registration.
    """
    logger.info("TOOL get_vessels  type=%r status=%r flag=%r", vessel_type, current_status, flag)
    ctx.context.active_agent = "Logistics Shipping Agent"
    df = load("vessels")
    if df.empty:
        return "No vessels data available."

    if vessel_type:
        df = df[df["vessel_type"].str.lower().str.contains(vessel_type.lower(), na=False)]
    if current_status:
        df = df[df["current_status"].str.lower() == current_status.lower()]
    if flag:
        df = df[df["flag"].str.lower() == flag.lower()]

    ctx.context.add_table("Vessels", df)
    if not df.empty and "vessel_type" in df.columns:
        type_counts = df["vessel_type"].value_counts().reset_index()
        type_counts.columns = ["vessel_type", "count"]
        ctx.context.add_chart(pie_chart(type_counts, names="vessel_type", values="count", title="Fleet by Vessel Type"))
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_voyages(
    ctx: RunContextWrapper[ERPContext],
    vessel_id: str = "",
    status: str = "",
    departure_port: str = "",
    arrival_port: str = "",
    limit: int = 50,
) -> str:
    """Return voyage records with optional filters.

    Args:
        vessel_id: Filter by vessel ID.
        status: Filter by voyage status (planned, in_progress, completed).
        departure_port: Filter by departure port name.
        arrival_port: Filter by arrival port name.
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_voyages  vessel=%r status=%r dep=%r arr=%r", vessel_id, status, departure_port, arrival_port)
    ctx.context.active_agent = "Logistics Shipping Agent"
    df = load("voyages")
    vessels = load("vessels")
    if df.empty:
        return "No voyages data available."

    if vessel_id:
        df = df[df["vessel_id"].astype(str) == str(vessel_id)]
    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if departure_port:
        df = df[df["departure_port"].str.lower().str.contains(departure_port.lower(), na=False)]
    if arrival_port:
        df = df[df["arrival_port"].str.lower().str.contains(arrival_port.lower(), na=False)]

    if not vessels.empty:
        df = df.merge(vessels[["vessel_id", "name"]], on="vessel_id", how="left")

    df = df.head(limit)
    ctx.context.add_table("Voyages", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_freight_cost_by_carrier(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return total freight cost and shipment count grouped by carrier."""
    logger.info("TOOL get_freight_cost_by_carrier")
    ctx.context.active_agent = "Logistics Shipping Agent"
    df = load("shipments")
    if df.empty:
        return "No shipments data available."

    summary = (
        df.groupby("carrier")
        .agg(total_freight_cost=("freight_cost", "sum"), shipment_count=("shipment_id", "count"))
        .reset_index()
        .sort_values("total_freight_cost", ascending=False)
    )
    ctx.context.add_table("Freight Cost by Carrier", summary)
    ctx.context.add_chart(
        bar_chart(summary, x="carrier", y="total_freight_cost", title="Total Freight Cost by Carrier")
    )
    return df_to_markdown(summary)
