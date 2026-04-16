from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.sales_tools import (
    get_customers,
    get_orders,
    get_revenue_summary,
    get_sales_by_channel,
    get_top_customers,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "sales_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Sales CRM Agent",
        handoff_description="Handles sales orders, customers, revenue analysis, top customers, and sales channel performance.",
        instructions=instructions,
        tools=[
            get_orders,
            get_revenue_summary,
            get_top_customers,
            get_customers,
            get_sales_by_channel,
        ],
        model="gpt-4o",
    )
