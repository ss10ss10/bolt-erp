from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.finance_tools import (
    get_cash_flow_summary,
    get_expense_breakdown,
    get_invoices,
    get_overdue_receivables,
    get_payroll_summary,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "finance_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Finance Accounting Agent",
        handoff_description="Handles invoices, overdue receivables, cash flow analysis, expense breakdown, and payroll summaries.",
        instructions=instructions,
        tools=[
            get_invoices,
            get_overdue_receivables,
            get_cash_flow_summary,
            get_expense_breakdown,
            get_payroll_summary,
        ],
        model="gpt-4o",
    )
