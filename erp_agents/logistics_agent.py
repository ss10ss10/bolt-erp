from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.logistics_tools import (
    get_delivery_performance,
    get_freight_cost_by_carrier,
    get_shipments,
    get_vessels,
    get_voyages,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "logistics_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Logistics Shipping Agent",
        handoff_description="Handles shipments, delivery tracking, carrier performance, vessels, voyages, and freight cost analysis.",
        instructions=instructions,
        tools=[
            get_shipments,
            get_delivery_performance,
            get_vessels,
            get_voyages,
            get_freight_cost_by_carrier,
        ],
        model="gpt-4o",
    )
