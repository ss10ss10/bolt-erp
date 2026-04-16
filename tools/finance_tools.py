"""Finance & Accounting agent tools."""

import logging

import pandas as pd
from agents import RunContextWrapper, function_tool

from context import ERPContext
from tools.chart_tools import bar_chart, df_to_markdown, line_chart, pie_chart
from tools.data_loader import load

logger = logging.getLogger(__name__)


@function_tool(strict_mode=False)
def get_invoices(
    ctx: RunContextWrapper[ERPContext],
    invoice_type: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
) -> str:
    """Retrieve invoice records with optional filters.

    Args:
        invoice_type: Filter by type — 'sales' or 'purchase'.
        status: Filter by status (draft, sent, paid, overdue).
        start_date: Filter invoices issued on or after this date (YYYY-MM-DD).
        end_date: Filter invoices issued on or before this date (YYYY-MM-DD).
        limit: Maximum rows to return (default 50).
    """
    logger.info("TOOL get_invoices  type=%r status=%r start=%r end=%r", invoice_type, status, start_date, end_date)
    ctx.context.active_agent = "Finance Accounting Agent"
    df = load("invoices")
    if df.empty:
        return "No invoices data available."

    if invoice_type:
        df = df[df["type"].str.lower() == invoice_type.lower()]
    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if start_date:
        df = df[df["issue_date"] >= start_date]
    if end_date:
        df = df[df["issue_date"] <= end_date]

    df = df.head(limit)
    ctx.context.add_table("Invoices", df)
    return df_to_markdown(df)


@function_tool(strict_mode=False)
def get_overdue_receivables(
    ctx: RunContextWrapper[ERPContext],
) -> str:
    """Return all overdue sales invoices with days overdue."""
    logger.info("TOOL get_overdue_receivables")
    ctx.context.active_agent = "Finance Accounting Agent"
    import pandas as pd

    df = load("invoices")
    if df.empty:
        return "No invoices data available."

    # Try strict overdue filter first, fall back to unpaid invoices
    overdue_mask = (df["type"].str.lower() == "sales") & (df["status"].str.lower() == "overdue")
    overdue = df[overdue_mask].copy()

    if overdue.empty:
        # Fall back: show all unpaid sales invoices as potential overdue
        unpaid_mask = (df["type"].str.lower() == "sales") & (~df["status"].str.lower().isin(["paid", "cancelled"]))
        overdue = df[unpaid_mask].copy()
        if overdue.empty:
            all_statuses = df["status"].value_counts().to_dict()
            return f"No overdue or unpaid sales invoices found. Invoice statuses in data: {all_statuses}"

    today = pd.Timestamp.today()
    overdue["due_date_dt"] = pd.to_datetime(overdue["due_date"], errors="coerce")
    overdue["days_overdue"] = (today - overdue["due_date_dt"]).dt.days
    overdue = overdue.sort_values("days_overdue", ascending=False)

    total_overdue = overdue["amount"].sum()
    critical = overdue[overdue["days_overdue"] > 60]

    ctx.context.add_table(
        f"Overdue Receivables — ${total_overdue:,.2f}",
        overdue.drop(columns=["due_date_dt"], errors="ignore"),
    )
    return (
        f"**Overdue Receivables Summary**\n"
        f"- Total at risk: **${total_overdue:,.2f}** across {len(overdue)} invoices\n"
        f"- Critical (>60 days overdue): {len(critical)} invoices worth ${critical['amount'].sum():,.2f}\n"
        f"- Oldest overdue: {int(overdue['days_overdue'].max())} days\n\n"
        + df_to_markdown(overdue.drop(columns=["due_date_dt"], errors="ignore"))
    )


@function_tool(strict_mode=False)
def get_cash_flow_summary(
    ctx: RunContextWrapper[ERPContext],
    group_by: str = "month",
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Return income vs expense cash flow grouped by time period.

    Args:
        group_by: Time granularity — 'month', 'quarter', or 'year'.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
    """
    logger.info("TOOL get_cash_flow_summary  group_by=%r start=%r end=%r", group_by, start_date, end_date)
    ctx.context.active_agent = "Finance Accounting Agent"
    df = load("transactions")
    if df.empty:
        return "No transactions data available."

    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]

    df["date"] = df["date"].astype(str)

    if group_by == "month":
        df["period"] = df["date"].str[:7]
    elif group_by == "quarter":
        import pandas as pd

        df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
        df["period"] = df["date_dt"].dt.to_period("Q").astype(str)
    else:
        df["period"] = df["date"].str[:4]

    income = df[df["type"].str.lower() == "income"].groupby("period")["amount"].sum().rename("income")
    expense = df[df["type"].str.lower() == "expense"].groupby("period")["amount"].sum().rename("expense")

    import pandas as pd

    summary = pd.concat([income, expense], axis=1).fillna(0).reset_index().sort_values("period")
    summary["net_cash_flow"] = summary["income"] - summary["expense"]

    summary["income_growth_pct"] = summary["income"].pct_change().mul(100).round(1)
    negative_periods = summary[summary["net_cash_flow"] < 0]

    ctx.context.add_table(f"Cash Flow by {group_by.capitalize()}", summary)
    ctx.context.add_chart(
        line_chart(summary, x="period", y=["income", "expense", "net_cash_flow"], title=f"Cash Flow by {group_by.capitalize()}")
    )

    total_net = summary["net_cash_flow"].sum()
    return (
        f"**Cash Flow Summary ({group_by})**\n"
        f"- Cumulative net cash flow: **${total_net:,.2f}**\n"
        f"- Periods with negative cash flow: **{len(negative_periods)}** "
        + (f"({', '.join(negative_periods['period'].tolist())})" if len(negative_periods) > 0 else "") + "\n"
        f"- Best period: {summary.loc[summary['net_cash_flow'].idxmax(), 'period']} "
        f"(${summary['net_cash_flow'].max():,.2f})\n\n"
        + df_to_markdown(summary)
    )


@function_tool(strict_mode=False)
def get_expense_breakdown(
    ctx: RunContextWrapper[ERPContext],
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Return expense transactions grouped by category.

    Args:
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
    """
    logger.info("TOOL get_expense_breakdown  start=%r end=%r", start_date, end_date)
    ctx.context.active_agent = "Finance Accounting Agent"
    df = load("transactions")
    if df.empty:
        return "No transactions data available."

    df = df[df["type"].str.lower() == "expense"]
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]

    summary = (
        df.groupby("category")
        .agg(total_expense=("amount", "sum"), transaction_count=("transaction_id", "count"))
        .reset_index()
        .sort_values("total_expense", ascending=False)
    )
    ctx.context.add_table("Expense Breakdown by Category", summary)
    ctx.context.add_chart(pie_chart(summary, names="category", values="total_expense", title="Expenses by Category"))
    return df_to_markdown(summary)


@function_tool(strict_mode=False)
def get_payroll_summary(
    ctx: RunContextWrapper[ERPContext],
    period_month: int = 0,
    period_year: int = 0,
    department: str = "",
) -> str:
    """Return payroll summary, optionally filtered by period or department.

    Args:
        period_month: Month number (1-12). Use 0 to include all months.
        period_year: Year (e.g. 2024). Use 0 to include all years.
        department: Filter by employee department name.
    """
    logger.info("TOOL get_payroll_summary  month=%d year=%d dept=%r", period_month, period_year, department)
    ctx.context.active_agent = "Finance Accounting Agent"
    payroll = load("payroll")
    employees = load("employees")
    if payroll.empty:
        return "No payroll data available."

    if period_month > 0:
        payroll = payroll[payroll["period_month"] == period_month]
    if period_year > 0:
        payroll = payroll[payroll["period_year"] == period_year]

    if not employees.empty:
        payroll = payroll.merge(employees[["employee_id", "name", "department"]], on="employee_id", how="left")

    if department and "department" in payroll.columns:
        payroll = payroll[payroll["department"].str.lower().str.contains(department.lower(), na=False)]

    if "department" in payroll.columns:
        summary = (
            payroll.groupby("department")
            .agg(
                headcount=("employee_id", "nunique"),
                total_net_pay=("net_pay", "sum"),
                total_bonus=("bonus", "sum"),
            )
            .reset_index()
            .sort_values("total_net_pay", ascending=False)
        )
        ctx.context.add_table("Payroll Summary by Department", summary)
        ctx.context.add_chart(
            bar_chart(summary, x="department", y="total_net_pay", title="Total Net Pay by Department")
        )
        return df_to_markdown(summary)

    ctx.context.add_table("Payroll", payroll)
    return df_to_markdown(payroll)
