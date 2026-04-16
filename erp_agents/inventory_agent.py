from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.inventory_tools import (
    get_inventory,
    get_inventory_by_category,
    get_low_stock_alerts,
    get_warehouses,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "inventory_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Inventory Warehouse Agent",
        handoff_description="Handles inventory levels, low-stock alerts, warehouse capacity, and stock distribution by category.",
        instructions=instructions,
        tools=[
            get_inventory,
            get_low_stock_alerts,
            get_warehouses,
            get_inventory_by_category,
        ],
        model="gpt-4o",
    )
