from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.procurement_tools import (
    get_procurement_spend_trend,
    get_purchase_orders,
    get_supplier_performance,
    get_suppliers,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "procurement_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Procurement Agent",
        handoff_description="Handles purchase orders, supplier records, supplier performance metrics, and procurement spend analysis.",
        instructions=instructions,
        tools=[
            get_purchase_orders,
            get_suppliers,
            get_supplier_performance,
            get_procurement_spend_trend,
        ],
        model="gpt-4o",
    )
